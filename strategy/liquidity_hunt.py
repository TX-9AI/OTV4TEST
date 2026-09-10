"""
strategy/liquidity_hunt.py  v1.0
v1.0  2026-09-10  OTV4TEST r12 — THE LIQUIDITY HUNT (PLAN_SPEC §37). Operator,
      2026-09-10, from the predecessor's own numbers: the ORB break-and-retest
      risks $71 to make $37; the momentum trade pays ~2:1 with the least
      give-back across ~300 trades. *"Under most circumstances price is going
      to go towards where the liquidity is."* So: from the five-minute opening
      range, price sweeps the nearest liquidity level; trade the BREAK TOWARD
      that level rather than wait for a retest, and on the rejection hand off
      to the sweep. Morning only. Runs in PARALLEL with the ORB — neither
      blocks the other — so the two are compared on the same range, the same
      levels, the same fills.

      BIAS — read at 09:35 from the level store: the nearest live named level
      (PDH/PDL, session extremes, pools, the 1h tines; nothing inside the range
      exists) measured from the RANGE EDGE, above vs below. The nearer side is
      the market's intent. *"Some of the earliest moves of the session are
      fake-outs and do not represent the intent."*

      ENTRIES — the liquidity picks the side; the break only times it.
        A1  a 1m close outside the range ON THE BIAS SIDE.
        A2  a far-side break that CLOSES BACK INSIDE the range — entered on
            that close, from the far boundary, direction = bias. *"Taking out
            a previous session high from the lower bound of the opening range
            boundary."* The whole range is runway.
        A far-side break that does NOT fail: not traded, recorded ("broke away
        from the liquidity"). One hunt per break key (direction, boundary).

      TARGET — the level itself. The runway is KNOWN at entry, so the strike is
      the gamma pick over that runway (runaway_continuation.gamma_leverage_pick
      with run = distance to the level), teenie gate bounding the cheap end.

      EXITS (exit_engine, the runaway's family routed by strategy name):
        · thesis dead — a 1m close back through the entry boundary
          (A1: the range edge it broke; A2: the far boundary it re-entered)
        · REJECTED at the level — the hunt exits and GRANTS THE HANDOFF to the
          sweep (execution/handoff.py) — the reversal is the sweep's trade
        · ACCEPTED at the level — over-delivered; hold on the runaway's exits
        · the fizzle read · 15:45. No premium stop.

      SLOT — exempt on entry and not counted as blocking (position_manager
      v4.9), exactly the butterfly's rule, so an open ORB and an open hunt can
      both be long the same break. That is the paired comparison.

      Every tick from 09:35 the row carries: the bias, both nearest levels and
      their distance in EM, the entry armed for, the runway, the strike. Every
      "not traded" names why.
"""
from __future__ import annotations

import logging

import config
from strategy import relaxed
from strategy.base_strategy import OptionsSignal as Signal
from strategy.plan import Plan, _n
from strategy.runaway_continuation import gamma_leverage_pick, target_delta, ATR_FLOOR_PCT
from strategy.sweep_credit_spread import _symbol_of
from utils.math_utils import safe_float

logger = logging.getLogger(__name__)

GATES = {
    "ATR_FLOOR_PCT":   "FEASIBILITY",     # the runaway's; can the tape reach a strike
    "WINDOW_OPEN_ET":  "FOUNDATIONAL",
    "CUTOFF_ET":       "FOUNDATIONAL",
}

WINDOW_OPEN_ET = getattr(config, "ENTRY_OPEN_ET", (9, 35))
CUTOFF_ET      = getattr(config, "HUNT_CUTOFF_ET", (11, 30))
MAX_LOSS_PCT   = float(getattr(config, "HUNT_MAX_LOSS_PCT", getattr(config, "RUNAWAY_MAX_LOSS_PCT", 0.20)))

FINISHED: set = set()          # (direction, boundary) — one hunt per break


def _hm(now_et: str):
    try:
        h, m = str(now_et).split(":")[:2]
        return int(h), int(m)
    except (ValueError, AttributeError):
        return None


class HuntPreparation:
    __slots__ = ("tick", "bias", "above", "below", "target", "target_name", "entry", "direction",
                 "side", "boundary", "runway", "em_frac", "contract", "premium", "floor_premium",
                 "leverage", "structural", "starved", "unmet", "ready", "note")

    def __init__(self, tick):
        self.tick = tick
        self.bias = ""
        self.above = self.below = None
        self.target = self.target_name = None
        self.entry = self.direction = self.side = ""
        self.boundary = self.runway = self.em_frac = None
        self.contract = self.premium = self.floor_premium = self.leverage = None
        self.structural, self.starved, self.unmet = [], [], []
        self.ready = False
        self.note = ""

    def trade_line(self):
        c = self.contract
        if c is None:
            return "no contract selected"
        return (f"buy {float(c.strike):g}{self.side[0].upper()} @ {_n(self.premium)}  "
                f"floor {_n(self.floor_premium)}  runway {_n(self.runway)} to "
                f"{self.target_name} {_n(self.target)} ({_n(self.em_frac)} EM)  "
                f"entry {self.entry} from {_n(self.boundary)}")


class LiquidityHunt:
    name = "LiquidityHunt"
    PLAN_CHECKS = ("entry_window", "price", "atr_pct", "orb_range", "nearest_above", "nearest_below",
                   "above_em", "below_em", "bias", "break_state", "fake_seen", "fake_failed",
                   "entry", "break_finished", "runway", "considered", "spread_rejected",
                   "contract", "leverage", "debit", "stop_premium")

    def __init__(self):
        self.planner = Plan(self.name, self.PLAN_CHECKS, record_only=True, self_ledgers=True)
        self._store = None
        self._fake: dict = {}         # break key -> {"seen": bar_ts, "failed": bool}
        self._last_bar_ts = ""
        self._bias_day = ""           # the bias is read once per session, at 09:35

    def _store_(self):
        if self._store is not None:
            return self._store
        try:
            from data.derived_store import get_derived_store
            return get_derived_store()
        except Exception:                                       # noqa: BLE001
            return None

    # ── the plan ──────────────────────────────────────────────────────────
    def prepare(self, *, orb, price_now, now_et, atr_pct=None, chain=None, df_1m=None,
                atm_iv=None) -> HuntPreparation:
        t = self.planner.tick(price_now)
        prep = HuntPreparation(t)
        hm = _hm(now_et)
        if hm is not None and hm >= tuple(CUTOFF_ET):
            t.dormant("entry_window", f"past {CUTOFF_ET[0]:02d}:{CUTOFF_ET[1]:02d} ET — observing only")
            return prep
        if hm is not None and hm < tuple(WINDOW_OPEN_ET):
            t.dormant("entry_window", f"before {WINDOW_OPEN_ET[0]:02d}:{WINDOW_OPEN_ET[1]:02d} ET — the range is forming")
            return prep
        t.check("entry_window", None, True)
        price_now = safe_float(price_now)
        if not price_now or price_now <= 0:
            prep.starved.append("price_now"); t.starved("price_now"); return prep
        t.check("price", price_now, True)
        _atr = safe_float(atr_pct)
        reachable = target_delta(atr_pct) is not None
        t.check("atr_pct", _atr, reachable)

        hi = safe_float(getattr(orb, "orb_high", None)) or 0.0
        lo = safe_float(getattr(orb, "orb_low", None)) or 0.0
        if hi <= 0 or lo <= 0 or hi <= lo:
            prep.starved.append("opening_range"); t.starved("opening_range"); return prep
        t.check("orb_range", round(hi - lo, 4), True)
        store = self._store_()
        if store is None:
            prep.starved.append("level_store"); t.starved("level_store"); return prep
        sym = _symbol_of()
        levels = store.live_levels(sym)
        above = sorted([l for l in levels if float(l["price"]) > hi], key=lambda l: float(l["price"]))
        below = sorted([l for l in levels if float(l["price"]) < lo], key=lambda l: -float(l["price"]))
        na = above[0] if above else None
        nb = below[0] if below else None
        prep.above, prep.below = na, nb
        em = None
        try:
            from strategy.gex_pin_butterfly import expected_move
            em = expected_move(price_now, atm_iv)
        except Exception:                                       # noqa: BLE001
            em = None
        da = (float(na["price"]) - hi) if na else None
        db = (lo - float(nb["price"])) if nb else None
        t.check("nearest_above", float(na["price"]) if na else None, None)
        t.check("nearest_below", float(nb["price"]) if nb else None, None)
        t.check("above_em", round(da / em, 3) if (da is not None and em) else None, None)
        t.check("below_em", round(db / em, 3) if (db is not None and em) else None, None)
        if na is None and nb is None:
            t.hold(f"range {lo:.2f}-{hi:.2f}: NO live level outside the range on either side — nothing to hunt")
            return prep
        # the bias: the nearer liquidity, measured from the range edge
        if da is not None and (db is None or da <= db):
            bias, target, tname, dist = "long", float(na["price"]), na["provenance"], da
        else:
            bias, target, tname, dist = "short", float(nb["price"]), nb["provenance"], db
        prep.bias, prep.target, prep.target_name = bias, target, tname
        prep.em_frac = round(dist / em, 3) if em else None
        t.check("bias", 1.0 if bias == "long" else -1.0, True)
        head = (f"range {lo:.2f}-{hi:.2f}; nearest above {_n(na['price'] if na else None)} "
                f"({na['provenance'] if na else '-'}, {_n(da)}), nearest below "
                f"{_n(nb['price'] if nb else None)} ({nb['provenance'] if nb else '-'}, {_n(db)}) "
                f"→ bias {bias.upper()}, target {tname} {target:.2f} ({_n(prep.em_frac)} EM)")

        # the closed bar: where is price relative to the range, and did a fake fail?
        if df_1m is None or len(df_1m) < 2:
            prep.starved.append("df_1m"); t.starved("df_1m"); return prep
        bar = df_1m.iloc[-2]; bar_ts = str(df_1m.index[-2])
        close = float(bar["close"])
        new_bar = bar_ts != self._last_bar_ts
        self._last_bar_ts = bar_ts
        state = "inside" if lo <= close <= hi else ("above" if close > hi else "below")
        t.check("break_state", {"inside": 0.0, "above": 1.0, "below": -1.0}[state], None)
        bias_side = "above" if bias == "long" else "below"
        far_side = "below" if bias == "long" else "above"
        far_key = ("short" if bias == "long" else "long", lo if bias == "long" else hi)
        fk = self._fake.setdefault(far_key, {"seen": "", "failed": False})
        if new_bar and state == far_side:
            fk["seen"] = fk["seen"] or bar_ts
            fk["failed"] = False
        if new_bar and fk["seen"] and state == "inside" and not fk["failed"]:
            fk["failed"] = True
            fk["failed_ts"] = bar_ts
        t.check("fake_seen", 1.0 if fk["seen"] else 0.0, None)
        t.check("fake_failed", 1.0 if fk["failed"] else 0.0, None)

        entry = ""
        if state == bias_side:
            entry, boundary = "A1", (hi if bias == "long" else lo)
        elif fk["failed"] and fk.get("failed_ts") == bar_ts and state == "inside":
            entry, boundary = "A2", (lo if bias == "long" else hi)
        elif state == far_side:
            t.hold(f"{head}. Broke AWAY from the liquidity ({far_side}) — a fake-out candidate; "
                   f"not traded; waiting on: the fake to fail (a close back inside)")
            return prep
        t.check("entry", {"": 0.0, "A1": 1.0, "A2": 2.0}[entry], bool(entry))
        if not entry:
            t.hold(f"{head}. Inside the range — waiting on: A1 (a close out {bias_side}) or A2 "
                   f"(a far-side break that closes back inside)")
            return prep
        prep.entry, prep.direction, prep.boundary = entry, bias, boundary
        prep.side = "call" if bias == "long" else "put"
        t.direction = bias
        key = (bias, round(boundary, 2))
        t.check("break_finished", 1.0 if key in FINISHED else 0.0, key not in FINISHED)
        if key in FINISHED:
            t.hold(f"{head}. {entry} armed but this break already had its hunt — one per break")
            return prep
        t.anchor(trigger=boundary, invalidation=boundary)
        runway = abs(target - price_now)
        prep.runway = runway
        t.check("runway", round(runway, 4), runway > 0)
        if runway <= 0:
            prep.structural.append(("runway", f"price {price_now:.2f} is already at/through the target {target:.2f}"))
        if not reachable:
            prep.unmet.append(("atr_pct", f"ATR {_n(_atr, '.3f')}% below the {ATR_FLOOR_PCT}% reachability floor"))
        if chain is None:
            prep.starved.append("chain")
        elif not prep.structural and not prep.unmet:
            contracts = chain.calls if prep.side == "call" else chain.puts
            c, lev, n, spread_rej = gamma_leverage_pick(contracts, bias, price_now, runway, floor_pct=MAX_LOSS_PCT)
            t.check("considered", n, n > 0)
            t.check("spread_rejected", spread_rej, None)
            if c is None:
                prep.structural.append(("contract", f"no {prep.side} whose {MAX_LOSS_PCT:.0%} floor clears its own "
                                                    f"spread over a {runway:.2f} runway ({spread_rej} rejected)"))
            else:
                prem = float(getattr(c, "ask", 0) or getattr(c, "mark", 0) or 0)
                prep.contract, prep.premium, prep.leverage = c, prem, lev
                prep.floor_premium = round(prem * (1 - MAX_LOSS_PCT), 4)
                t.check("contract", float(c.strike), True)
                t.check("leverage", lev, lev > 0)
                t.check("debit", prem, True)
                t.check("stop_premium", prep.floor_premium, None)
                t.debit = prem
        if prep.starved:
            t.starved(*prep.starved); return prep
        if prep.structural:
            g, w = prep.structural[0]; t.refuse(g, f"{head}. {entry}: {w}"); return prep
        if prep.unmet:
            g, w = prep.unmet[0]; t.refuse(g, f"{head}. {entry}: {w}"); return prep
        prep.ready = True
        t.note(f"{head}. {entry} FIRES — {prep.trade_line()}")
        return prep

    # ── the strategy: bars + fire ─────────────────────────────────────────
    def generate_signal(self, *, orb, price_now, now_et, atr_pct=None, chain=None, df_1m=None,
                        atm_iv=None, **_ignored):
        prep = self.prepare(orb=orb, price_now=price_now, now_et=now_et, atr_pct=atr_pct,
                            chain=chain, df_1m=df_1m, atm_iv=atm_iv)
        if not prep.ready or prep.unmet or prep.structural or prep.starved:
            return prep.tick.already()
        c = prep.contract
        sig = Signal(
            strategy_name=self.name,
            setup_type=f"liquidity_hunt_{prep.entry}",
            direction=prep.direction,
            option_side=prep.side,
            underlying_entry=float(price_now),
            underlying_stop=float(prep.boundary),       # thesis-dead: a close back through it
            underlying_target=float(prep.target),
            orb_range_high=float(getattr(orb, "orb_high", 0.0) or 0.0),
            orb_range_low=float(getattr(orb, "orb_low", 0.0) or 0.0),
            stop_loss_pct=MAX_LOSS_PCT,                  # recorded; the exit engine HOLDS
            strike=c.strike, expiry=getattr(c, "expiry", ""),
            entry_premium=c.mark, contract=c,
        )
        sig.hunt_entry = prep.entry
        sig.hunt_target_name = prep.target_name
        sig.hunt_em_frac = prep.em_frac
        sig.run_at_entry = prep.runway
        sig.gamma_leverage = prep.leverage
        sig.is_liquidity_hunt = True
        sig.disarms_retest = False                       # the ORB is untouched
        relaxed.tag(sig)
        FINISHED.add((prep.direction, round(prep.boundary, 2)))
        logger.info("[hunt] FIRE %s %s — %s", prep.entry, prep.direction, prep.trade_line())
        return prep.tick.take(sig)
