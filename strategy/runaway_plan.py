"""
strategy/runaway_plan.py  v1.1
v1.1  2026-09-09  OTV4TEST r12 — participation read from the prints at the boundary
      (record only; the composite is unchanged) and anchors stamped: charm/vanna at
      the target strike, 15m fork, VWAP distance.
v1.0  2026-09-08  OTV4TEST r3 — THE RUNAWAY PLAN (PLAN_SPEC §30), agreed with
      the operator 2026-09-08. The intent, his words: *"catch an early high
      velocity move from the market open where there's a lot of participation
      and a lot of volume and we just wanna participate in it and when it
      fizzles out … we want out of it."* Starting at the 50.

      ARM — the 50% level ACCEPTED: a 1m close beyond it that held. That is
      the engine's own latch (`orb.fifty_accepted`, r221), now also what
      invalidates the ORB (orb_engine v4.13) — one event, two consumers.
      Direction is the break's. A wick to the 50 arms nothing.

      MEASURE ONCE, AT ARM, AND FREEZE — the move from the boundary to the 50
      is a complete sample: `analysis.trend_strength.measure()` over the bars
      since the impulsive candle gives PACE (displacement per bar against true
      range — the bars-to-the-50 question, normalised) and ACCEPTANCE (where
      the closes sat in their bars). PARTICIPATION (aggressor share from the
      prints) is not wired here yet — recorded None, filed RUN.6 — so the
      composite is the mean of the two available components. Nothing gates on
      it: it is a DIAL.

      BAND FROM STRENGTH, GAMMA INSIDE IT — `gamma_leverage_pick` is unchanged
      and still runs on `run` (distance from the boundary); the plan hands it
      `run × band` where band is a declared prior: grind (< 0.40) 0.5 — nearer
      the money, pay for delta; normal 1.0 — today's rule; rip (≥ 0.70) 1.5 —
      cheaper, further out, gamma does the work. The teenie gate (a floor that
      does not clear its own spread is not a stop) still bounds the cheap end.
      ⚠️ The cutoffs and multipliers are CATEGORY 1 — a baseline so there is a
      starting point, not a fit. They are recorded on every row and fire.

      ONE PER BREAK, ANY EXIT — `FINISHED_BREAKS` keyed on (direction,
      boundary) as at r174, but a WIN finishes the break too (trade_logger
      v4.9). RE-VALIDATION ON ACTUAL (operator): after any exit the standing
      state never re-fires; the plan watches the closed bars and re-opens the
      break only when the 50 was LOST on a close and then ACCEPTED again
      (close beyond, held). The r179 one-per-session cap is retired for this
      strategy: a new break is a new trade, as it is for the ORB.

      OUTSIDE 09:35–11:30 THE PLAN OBSERVES AND DOES NOT WRITE (dormant, one
      row on the transition). The feasibility floor (ATR) is KEPT by ruling.

      WHAT IT HANDS THE STRATEGY, ready before the fire: direction, the 50,
      the frozen strength vector and band, the contract, premium, floor, R
      (muteable through 09-11), run. The strategy's bars: 50 accepted, break
      not finished, ATR reachable, a contract, R (strict only). Zero of the
      selection lives in the strategy.
"""
from __future__ import annotations

import logging
from typing import Optional

import config
from strategy.plan import Plan, _n
from strategy.runaway_continuation import (
    ATR_FLOOR_PCT, CUTOFF_ET, FINISHED_BREAKS, _break_key, gamma_leverage_pick,
    target_delta,
)
from utils.math_utils import safe_float

logger = logging.getLogger(__name__)

# ── GATE CATEGORIES AS DATA (WA §36) — the plan's own values ────────────────
GATES = {
    "ATR_FLOOR_PCT": "FEASIBILITY",       # kept by ruling 2026-09-08 (the strategy's)
    "CUTOFF_ET":     "FOUNDATIONAL",      # never relaxed (r176)
    "BAND_GRIND":    "SELECTION",         # prior — a dial, gates nothing
    "BAND_RIP":      "SELECTION",
}

WINDOW_OPEN_ET   = getattr(config, "ENTRY_OPEN_ET", (9, 35))
MAX_LOSS_PCT     = float(getattr(config, "RUNAWAY_MAX_LOSS_PCT", 0.20))
# the strength → band prior (category 1: a baseline, recorded, unfitted)
STRENGTH_GRIND   = float(getattr(config, "RUNAWAY_STRENGTH_GRIND", 0.40))
STRENGTH_RIP     = float(getattr(config, "RUNAWAY_STRENGTH_RIP", 0.70))
BAND_GRIND       = float(getattr(config, "RUNAWAY_BAND_GRIND", 0.5))
BAND_NORMAL      = 1.0
BAND_RIP         = float(getattr(config, "RUNAWAY_BAND_RIP", 1.5))
MEASURE_MIN_BARS = 2                      # a two-bar rip is a reading, not noise


def band_for(strength: Optional[float]) -> float:
    if strength is None:
        return BAND_NORMAL
    if strength < STRENGTH_GRIND:
        return BAND_GRIND
    if strength >= STRENGTH_RIP:
        return BAND_RIP
    return BAND_NORMAL


def _hm(now_et: str):
    try:
        h, m = str(now_et).split(":")[:2]
        return int(h), int(m)
    except (ValueError, AttributeError):
        return None


def _cutoff_hm():
    try:
        h, m = str(CUTOFF_ET).split(":")[:2]
        return int(h), int(m)
    except (ValueError, AttributeError):
        return (11, 30)


class RunawayPreparation:
    __slots__ = ("tick", "direction", "side", "boundary", "tp50", "run", "strength",
                 "pace", "acceptance", "participation", "band", "contract", "premium",
                 "floor_premium", "leverage", "considered", "r", "structural",
                 "starved", "unmet", "ready", "revalidation")

    def __init__(self, tick):
        self.tick = tick
        self.direction = self.side = ""
        self.boundary = self.tp50 = self.run = None
        self.strength = self.pace = self.acceptance = self.participation = None
        self.band = BAND_NORMAL
        self.contract = None
        self.premium = self.floor_premium = self.leverage = self.r = None
        self.considered = 0
        self.structural, self.starved, self.unmet = [], [], []
        self.ready = False
        self.revalidation = ""

    def trade_line(self) -> str:
        c = self.contract
        if c is None:
            return "no contract selected"
        return (f"buy {float(c.strike):g}{self.side[0].upper()} @ {_n(self.premium)}  "
                f"floor {_n(self.floor_premium)} (-{MAX_LOSS_PCT:.0%})  R {_n(self.r)}  "
                f"band {self.band:g}x run {_n(self.run)} "
                f"(strength {_n(self.strength)}: pace {_n(self.pace)}, "
                f"acceptance {_n(self.acceptance)})  50% {_n(self.tp50)}")


class RunawayPlan:
    name = "RunawayContinuation"
    PLAN_CHECKS = ("entry_window", "price", "atr_pct", "orb_direction", "fifty_accepted",
                   "break_finished", "revalidation", "run", "strength", "pace",
                   "acceptance", "participation", "band", "considered", "spread_rejected",
                   "contract", "leverage", "debit", "stop_premium", "target_distance", "r")

    def __init__(self):
        self.planner = Plan(self.name, self.PLAN_CHECKS,
                            record_only=True, self_ledgers=True)
        self._frozen: dict = {}        # break key -> {"strength","pace","acceptance","band"}
        self._reval: dict = {}         # break key -> {"lost": bool, "beyond": int}
        self._last_bar_ts: str = ""

    # ── strength, measured once per break ───────────────────────────────
    def _measure(self, key, orb, df_1m, direction):
        if key in self._frozen:
            return self._frozen[key]
        out = {"strength": None, "pace": None, "acceptance": None, "band": BAND_NORMAL,
               "reason": ""}
        try:
            from analysis.trend_strength import measure
            k = int(getattr(orb, "bars_since_break", 0) or 0)
            if df_1m is None or len(df_1m) < MEASURE_MIN_BARS + 1:
                out["reason"] = "not enough bars"
            else:
                # the closed bars since the impulsive candle (k retest bars + the
                # candle); the frame may hold fewer — take what it has
                bars = df_1m.iloc[-(k + 2):-1] if len(df_1m) >= k + 2 else df_1m.iloc[:-1]
                ts = measure(bars, direction, min_bars=MEASURE_MIN_BARS)
                out["pace"] = getattr(ts, "pace", None)
                out["acceptance"] = getattr(ts, "acceptance", None)
                comps = [v for v in (out["pace"], out["acceptance"]) if v is not None]
                out["strength"] = round(sum(comps) / len(comps), 4) if comps else None
                out["reason"] = str(getattr(ts, "reason", "") or "")
        except Exception as exc:                                # noqa: BLE001
            out["reason"] = f"measure failed: {exc}"
        out["band"] = band_for(out["strength"])
        self._frozen[key] = out
        logger.info("[runaway-plan] strength FROZEN for %s: %s -> band %.1fx (%s)",
                    key, out["strength"], out["band"], out["reason"] or "ok")
        return out

    # ── re-validation on actual, after any exit ─────────────────────────
    def _revalidate(self, key, tp50, direction, df_1m) -> str:
        """Returns "" when the break may trade, else the reason it may not."""
        if key not in FINISHED_BREAKS:
            return ""
        st = self._reval.setdefault(key, {"lost": False, "beyond": 0})
        try:
            if df_1m is None or len(df_1m) < 2:
                return "break finished — waiting for the 50 to be lost and re-accepted (no bars)"
            bar_ts = str(df_1m.index[-2])
            if bar_ts == self._last_bar_ts:
                return ("break finished — waiting for the 50 to be lost on a close and "
                        "re-accepted (close + hold)")
            self._last_bar_ts = bar_ts
            close = float(df_1m.iloc[-2]["close"])
            beyond = close > tp50 if direction == "long" else close < tp50
            if not st["lost"]:
                if not beyond:
                    st["lost"] = True
                return ("break finished — the 50 must be LOST on a close, then accepted "
                        "again" if not st["lost"] else
                        "the 50 was lost on a close — waiting for a fresh acceptance")
            if beyond:
                st["beyond"] += 1
                if st["beyond"] >= 2:
                    FINISHED_BREAKS.discard(key)
                    self._reval.pop(key, None)
                    self._frozen.pop(key, None)         # a new move: measure it anew
                    logger.info("[runaway-plan] %s RE-VALIDATED — the 50 was lost and "
                                "accepted again; the break may trade", key)
                    return ""
                return "the 50 re-crossed on a close — pending the hold"
            st["beyond"] = 0
            return "the 50 was lost on a close — waiting for a fresh acceptance"
        except Exception as exc:                                # noqa: BLE001
            return f"re-validation unreadable: {exc}"

    # ══════════════════════════════════════════════════════════════════════
    def prepare(self, *, orb, atr_pct, price_now, now_et, chain=None,
                df_1m=None, participation=None) -> RunawayPreparation:
        t = self.planner.tick(price_now)
        prep = RunawayPreparation(t)

        # window — outside it, observe only (one dormant row on the transition)
        hm = _hm(now_et)
        if hm is not None and hm >= _cutoff_hm():
            t.dormant("entry_window", f"past the {CUTOFF_ET} ET debit cutoff — observing only")
            return prep
        if hm is not None and hm < tuple(WINDOW_OPEN_ET):
            t.dormant("entry_window", f"before {WINDOW_OPEN_ET[0]:02d}:{WINDOW_OPEN_ET[1]:02d} "
                                      f"ET — the opening range is forming; observing only")
            return prep
        t.check("entry_window", None, True)

        price_now = safe_float(price_now)
        if not price_now or price_now <= 0 or price_now > 1e7:
            prep.starved.append("price_now")
            t.starved("price_now")
            return prep
        t.check("price", price_now, True)

        # feasibility — kept by ruling
        _atr = safe_float(atr_pct)
        reachable = target_delta(atr_pct) is not None
        t.check("atr_pct", _atr, reachable)
        if not reachable:
            prep.unmet.append(("atr_pct", f"ATR {_n(_atr, '.3f')}% below the "
                                          f"{ATR_FLOOR_PCT}% reachability floor"))

        # direction: the break's
        state = str(getattr(orb, "state", "") or "").upper()
        bd = str(getattr(orb, "break_direction", "") or "").lower()
        inval = str(getattr(orb, "invalidation_reason", "") or "")
        direction = ("long" if "LONG" in state else "short" if "SHORT" in state
                     else bd if (inval == "runaway" and bd in ("long", "short")) else "")
        t.check("orb_direction", (1.0 if direction == "long" else -1.0) if direction else None,
                bool(direction))
        if not direction:
            t.hold(f"ORB {state.lower() or 'none'}"
                   + (f" (invalidated: {inval})" if inval else "")
                   + " carries no direction — nothing to prepare until it breaks")
            return prep
        prep.direction, prep.side = direction, "call" if direction == "long" else "put"
        t.direction = direction
        tp50 = safe_float(getattr(orb, "target_50pct", None))
        boundary = safe_float(getattr(orb, "orb_high", None) if direction == "long"
                              else getattr(orb, "orb_low", None))
        if not tp50 or not boundary:
            miss = [n for n, v in (("target_50pct", tp50), ("orb_boundary", boundary)) if not v]
            prep.starved.extend(miss)
            t.starved(*miss)
            return prep
        prep.tp50, prep.boundary = float(tp50), float(boundary)
        t.anchor(trigger=prep.tp50)
        key = _break_key(direction, prep.boundary)

        # one per break, any exit — and re-validation on actual
        why_not = self._revalidate(key, prep.tp50, direction, df_1m)
        t.check("break_finished", prep.boundary, not why_not)
        if why_not:
            prep.revalidation = why_not
            t.check("revalidation", None, False)
            t.hold(f"ORB broke {direction} at {prep.boundary:.2f}: {why_not}")
            return prep
        t.check("revalidation", None, True)

        # the trigger: the 50 ACCEPTED (close + hold) — the engine's latch
        accepted = bool(getattr(orb, "fifty_accepted", False))
        t.check("fifty_accepted", prep.tp50, accepted)
        run = abs(price_now - prep.boundary)
        prep.run = run
        t.check("run", run, run > 0)
        head = (f"ORB broke {direction} at {prep.boundary:.2f}, run {_n(run)} to "
                f"{price_now:.2f}, 50% {prep.tp50:.2f}")
        if not accepted:
            beyond_now = price_now > prep.tp50 if direction == "long" else price_now < prep.tp50
            t.hold(f"{head}: waiting on: the 50 ACCEPTED (a 1m close beyond, held)"
                   f"{' — price is beyond it now, pending the close' if beyond_now else ''}")
            return prep

        # strength, measured once and frozen; the band follows it
        m = self._measure(key, orb, df_1m, direction)
        prep.strength, prep.pace, prep.acceptance = m["strength"], m["pace"], m["acceptance"]
        # r12 — participation READ from the prints at the boundary (RUN.6, record only
        # this revision: the composite still uses pace + acceptance)
        from derived import anchors as _A
        if participation is None:
            participation = _A.aggressor_share(prep.boundary)
        prep.participation = participation
        prep.band = m["band"]
        t.check("strength", prep.strength, None)
        t.check("pace", prep.pace, None)
        t.check("acceptance", prep.acceptance, None)
        t.check("participation", participation, None)
        t.check("band", prep.band, None)

        if run <= 0:
            prep.structural.append(("run", f"price {price_now:.2f} is at/inside the ORB "
                                           f"boundary {prep.boundary:.2f} — no run to lever"))
        elif chain is None:
            prep.starved.append("chain")
        else:
            contracts = chain.calls if prep.side == "call" else chain.puts
            c, lev, n, spread_rej = gamma_leverage_pick(
                contracts, direction, price_now, run * prep.band, floor_pct=MAX_LOSS_PCT)
            t.check("considered", n, n > 0)
            t.check("spread_rejected", spread_rej, None)
            if c is None:
                prep.structural.append(("contract",
                    f"no {prep.side} whose {MAX_LOSS_PCT:.0%} floor clears its own bid/ask "
                    f"spread ({spread_rej} rejected) inside a {prep.band:g}x band on a "
                    f"{run:.2f} run"))
            else:
                prem = float(getattr(c, "ask", 0) or getattr(c, "mark", 0) or 0)
                d_ = abs(float(getattr(c, "delta", 0) or 0))
                g_ = float(getattr(c, "gamma", 0) or 0)
                gain = d_ * run + 0.5 * g_ * run * run
                risk = prem * MAX_LOSS_PCT
                t.debit = prem
                t.reward, t.risk = round(gain, 4), round(risk, 4)
                t.r = round(gain / risk, 4) if risk > 0 else None
                t.check("contract", c.strike, True)
                t.check("leverage", lev, lev > 0)
                t.check("debit", prem, True)
                t.check("stop_premium", round(prem * (1 - MAX_LOSS_PCT), 4), None)
                t.check("target_distance", run, run > 0)
                t.check("r", t.r, None)
                ok, why = t.executable()          # strict vetoes R; relaxed records
                if not ok:
                    prep.structural.append(("r", why))
                else:
                    prep.contract, prep.premium, prep.leverage = c, prem, lev
                    prep.floor_premium = round(prem * (1 - MAX_LOSS_PCT), 4)
                    prep.considered, prep.r = n, t.r
                    t.note(why)

        # r12 — ANCHORS, record only: dealer flow at the target strike, the 15m fork
        _k = float(getattr(prep.contract, "strike", 0) or 0) if prep.contract is not None else None
        _A.stamp(t, charm_at_strike=_A.charm_at(_k), vanna_at_strike=_A.vanna_at(_k),
                 fork15=_A.fork_dir("15m"), vwap_minus_price=(lambda v: None if v is None else v - price_now)(_A.vwap()))
        if prep.starved:
            t.starved(*prep.starved)
            return prep
        if prep.structural:
            gate, why = prep.structural[0]
            t.refuse(gate, f"{head}: {why}")
            return prep
        if prep.unmet:
            gate, why = prep.unmet[0]
            t.refuse(gate, f"{head}: {why}")
            return prep
        prep.ready = True
        t.note(f"{head}: 50 ACCEPTED — {prep.trade_line()}")
        return prep
