"""
strategy/tcs_plan.py  v1.0
v1.0  2026-09-09  OTV4TEST r9 — THE TREND CREDIT SPREAD PLAN (PLAN_SPEC §34),
      agreed with the operator 2026-09-09. The purpose, his words: *"catch
      large moves in the afternoon on some macro catalyst good or bad, and let
      theta do the work on our behalf since debits on 0DTE late in the day are
      deteriorating rapidly."*

      TRIGGER — a live SESSION EXTREME (the store's `ny` levels: today's high
      as resistance, today's low as support) ACCEPTED after 11:30 — two closed
      1m bars beyond it, the level store's own ACCEPTED event — AND the move
      OUTSIDE THE EXPECTED MOVE. "Outside" is read against the EM assessment
      that stood BEFORE the move: every tick the plan computes spot ± EM
      (ATM IV, remaining session) and prints it; on the first 1m close beyond
      a live extreme it FREEZES the previous tick's band as that move's
      reference; acceptance (the second close) with price outside the frozen
      band fires. A close back inside before acceptance clears the reference.
      Re-centering each tick would chase the move and never be exceeded.
      Operator: if it never fires, or fires too loosely, the EM gate is the
      first suspect — so the row carries the band and the distance every tick.

      DIRECTION AND ANCHOR — the move's. A high accepted -> sell the PUT spread
      behind it, short at the first strike at/below THE ACCEPTED LEVEL (the
      former resistance is now the floor the trade sells against — near the
      money, rich, and the exit has a name). A low accepted -> the CALL spread
      above it.

      STRUCTURE — r238's rule KEPT on purpose: the WIDEST wing that clears 1:1
      on the expiry basis = the most credit the R floor allows (best-R would
      pick the narrowest, thinnest-credit wing — "it was for nothing"). Bars:
      POP >= TCS_MIN_POP (1 - |short delta|; the theta-not-direction bar),
      credit >= TCS_MIN_CREDIT_PCT_WIDTH of width, the nickel-multiple floor,
      the 15%-of-credit stop survivable against the short's spread. RECORDED:
      ADX (retired as a bar — measured flat; the EM breach is the size read),
      richness = credit / width, and the protective leg's own bid/ask as a
      fraction of the wing (long_leg_spread_pct) — barred once seen.

      ONE PER SESSION is NOT a rule here; leg-one-of-a-condor is: the TCS may
      be the FIRST vertical on the board, never the second (authorize() and
      `_can_open_credit_spread` are untouched — the complement must be a
      sweep). The 15% stop applies to a LONE vertical only (the sibling
      suppresses it when hedged — exit_engine, unchanged mechanism).

      WINDOW 11:31–14:00; outside it the plan observes and does not write.
      The plan prepares BOTH sides every tick: the nearest live extreme each
      way, the EM band, and the spread it would sell if that extreme were
      accepted — "waiting on: ACCEPTED outside the EM".
"""
from __future__ import annotations

import logging
import time

import config
from strategy import credit_vertical as cv
from strategy.criteria import stop_survivable
from strategy.plan import Plan, _n
from strategy.sweep_credit_spread import strike_beyond_sweep, _symbol_of
from utils.math_utils import safe_float

logger = logging.getLogger(__name__)

GATES = {
    "TCS_START_ET":         "FOUNDATIONAL",
    "TCS_ENTRY_END_ET":     "SELECTION",
    "ACCEPT_FRESH_BARS":    "SELECTION",     # prior — recorded on every fire
}

TCS_START_ET        = getattr(config, "TCS_START_ET", (11, 31))
TCS_ENTRY_END_ET    = getattr(config, "TCS_ENTRY_END_ET", (14, 0))
TCS_MIN_POP         = float(getattr(config, "TCS_MIN_POP", 0.70))
TCS_MIN_CREDIT_PCT  = float(getattr(config, "TCS_MIN_CREDIT_PCT_WIDTH", 0.10))
TCS_R_FLOOR_EXPIRY  = float(getattr(config, "TCS_R_FLOOR_EXPIRY", 1.00))
TCS_STOP_PCT        = float(getattr(config, "TCS_STOP_PCT_OF_CREDIT", 0.15))
TCS_NICKEL_REF      = float(getattr(config, "TCS_NICKEL_REF", 0.05))
TCS_NICKEL_MULT     = float(getattr(config, "TCS_MIN_CREDIT_NICKEL_MULT", 4.0))
ACCEPT_FRESH_BARS   = int(getattr(config, "TCS_ACCEPT_FRESH_BARS", 3))          # prior


def window_end() -> tuple:
    """The TCS entry window's end, for main.py's remainder (HYG.5): read here,
    never from config, so the plan is the one owner of its window."""
    return tuple(TCS_ENTRY_END_ET)


def _hm(now_et):
    try:
        if hasattr(now_et, "hour"):
            return int(now_et.hour), int(now_et.minute)
        h, m = str(now_et).split(":")[:2]
        return int(h), int(m)
    except (ValueError, AttributeError, TypeError):
        return None


def _session_open_epoch() -> float:
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        n = datetime.now(ZoneInfo("US/Eastern"))
        return n.replace(hour=9, minute=30, second=0, microsecond=0).timestamp()
    except Exception:                                           # noqa: BLE001
        return 0.0


class Candidate:
    __slots__ = ("level_id", "price", "kind", "provenance", "side", "short", "long", "credit",
                 "width", "r", "stop_dist", "pop", "richness", "long_leg_spread_pct", "why", "why_key")

    def __init__(self, lvl):
        self.level_id, self.price = lvl["level_id"], float(lvl["price"])
        self.kind, self.provenance = lvl["kind"], lvl["provenance"]
        # a HIGH accepted -> sell the PUT spread behind it; a LOW -> the CALL spread
        self.side = "put" if self.kind == "resistance" else "call"
        self.short = self.long = None
        self.credit = self.width = self.r = self.stop_dist = self.pop = None
        self.richness = self.long_leg_spread_pct = None
        self.why = self.why_key = ""

    @property
    def sellable(self):
        return self.short is not None and self.long is not None and (self.credit or 0) > 0

    def line(self):
        if not self.sellable:
            return f"{self.provenance} {self.price:.2f}: {self.why or 'no structure'}"
        return (f"{self.provenance} {self.price:.2f} — would sell "
                f"{float(self.short.strike):g}/{float(self.long.strike):g}"
                f"{'P' if self.side == 'put' else 'C'} for {_n(self.credit)} "
                f"(R {_n(self.r)}, POP {_n(self.pop)}, {self.richness:.0%} of width)")


class TCSPreparation:
    __slots__ = ("tick", "em", "band_lo", "band_hi", "above", "below", "nearest_above",
                 "nearest_below", "accepted", "chosen", "side", "direction", "bound",
                 "short", "long", "credit", "width", "r", "stop_dist", "pop", "richness",
                 "ref_band", "outside_by", "structural", "starved", "unmet", "ready")

    def __init__(self, tick):
        self.tick = tick
        self.em = self.band_lo = self.band_hi = None
        self.above, self.below = [], []
        self.nearest_above = self.nearest_below = None
        self.accepted = self.chosen = None
        self.side = self.direction = ""
        self.bound = None
        self.short = self.long = None
        self.credit = self.width = self.r = self.stop_dist = self.pop = self.richness = None
        self.ref_band = None
        self.outside_by = None
        self.structural, self.starved, self.unmet = [], [], []
        self.ready = False

    def trade_line(self):
        return self.chosen.line() if self.chosen else "no trade prepared"


class TCSPlan:
    name = "TrendCreditSpread"
    PLAN_CHECKS = ("entry_window", "price", "atm_iv", "em", "band_lo", "band_hi",
                   "extremes_above", "extremes_below", "nearest_above", "nearest_above_credit",
                   "nearest_below", "nearest_below_credit", "adx", "accepted",
                   "accepted_age_bars", "ref_band_lo", "ref_band_hi", "outside_by",
                   "outside_em", "contract", "wing", "width", "credit", "credit_pct_width",
                   "r", "r_expiry", "wing_r_best", "stop_vs_spread", "stop_dist", "risk",
                   "pop", "nickel_floor", "richness", "long_leg_spread_pct", "fifty",
                   "fifty_accepted", "holds_fifty", "dist_from_fifty_pts")

    def __init__(self, store=None):
        self.planner = Plan(self.name, self.PLAN_CHECKS, record_only=True, self_ledgers=True)
        self._store = store
        self._prev_band = None            # (lo, hi) from the previous tick
        self._ref: dict = {}              # level_id -> frozen (lo, hi) at the first close beyond
        self._fired: set = set()          # (level_id, bar_ts) — each ACCEPTED fires once
        self._last_bar_ts = ""

    def _store_(self):
        if self._store is not None:
            return self._store
        try:
            from data.derived_store import get_derived_store
            return get_derived_store()
        except Exception:                                       # noqa: BLE001
            return None

    # ── the structure it would sell against a given extreme ─────────────
    def _structure(self, cand: Candidate, chain) -> Candidate:
        contracts = list(getattr(chain, "puts" if cand.side == "put" else "calls", None) or [])
        if not contracts:
            cand.why, cand.why_key = "no contracts on this side", "chain"
            return cand
        inc = float(getattr(config, "STRIKE_INCREMENT", 1) or 1)
        # anchor ON THE LEVEL: the first strike at/beyond it on the sell side
        k = strike_beyond_sweep(cand.price, cand.price, cand.side == "call", contracts=contracts, increment=inc)
        if k is None:
            cand.why, cand.why_key = "no listed strike at/beyond the level", "contract"
            return cand
        short = cv.find_contract_at_strike(contracts, k)
        if short is None:
            cand.why, cand.why_key = f"no contract at {k:g}", "contract"
            return cand
        cand.short = short
        cand.pop = round(1.0 - abs(float(getattr(short, "delta", 0) or 0)), 4)
        sb = safe_float(getattr(short, "bid", 0.0)) or 0.0
        sa = safe_float(getattr(short, "ask", 0.0)) or 0.0
        best, why = None, ""
        for c in contracts:
            kk = safe_float(getattr(c, "strike", 0)) or 0.0
            if kk <= 0 or (kk >= k if cand.side == "put" else kk <= k):
                continue
            ask = safe_float(getattr(c, "ask", None))
            if ask is None or ask < 0:
                continue
            width = abs(k - kk)
            credit = sb - ask                        # judged bid/ask (r219)
            if width <= 0 or credit <= 0 or credit >= width:
                continue
            r_expiry = credit / (width - credit)
            if r_expiry < TCS_R_FLOOR_EXPIRY:
                why = why or f"widest wing clearing 1:1 not found — best R {r_expiry:.2f} at {width:g} wide"
                continue
            sd = credit * TCS_STOP_PCT
            ok, svwhy = stop_survivable(sd, sb, sa)
            if not ok:
                why = f"15%-of-credit stop is unsurvivable: {svwhy}"
                continue
            if best is None or width > best[0]:      # WIDEST clearing 1R = the most credit
                best = (width, c, credit, r_expiry, sd)
        if best is None:
            cand.why = why or f"no wing beyond {k:g} prices a credit"
            cand.why_key = "wing_r_best" if "1:1" in cand.why else "stop_vs_spread"
            return cand
        width, long_c, credit, r_expiry, sd = best
        cand.long, cand.credit, cand.width, cand.r, cand.stop_dist = long_c, round(credit, 4), width, round(r_expiry, 4), round(sd, 4)
        cand.richness = round(credit / width, 4) if width else None
        lb, la = safe_float(getattr(long_c, "bid", 0.0)) or 0.0, safe_float(getattr(long_c, "ask", 0.0)) or 0.0
        cand.long_leg_spread_pct = round((la - lb) / width, 4) if width else None
        return cand

    # ══════════════════════════════════════════════════════════════════════
    def prepare(self, *, price_now, now_et, atm_iv=None, chain=None, df_1m=None,
                adx=None, session_open_epoch: float = 0.0) -> TCSPreparation:
        t = self.planner.tick(price_now)
        prep = TCSPreparation(t)
        hm = _hm(now_et)
        if hm is not None and hm >= tuple(TCS_ENTRY_END_ET):
            t.dormant("entry_window", f"past TCS_ENTRY_END_ET {TCS_ENTRY_END_ET[0]:02d}:{TCS_ENTRY_END_ET[1]:02d} — observing only")
            return prep
        if hm is not None and hm < tuple(TCS_START_ET):
            t.dormant("entry_window", f"before TCS_START_ET {TCS_START_ET[0]:02d}:{TCS_START_ET[1]:02d} — dormant, not looking at the chart")
            return prep
        t.check("entry_window", None, True)
        price_now = safe_float(price_now)
        if not price_now or price_now <= 0:
            prep.starved.append("price_now"); t.starved("price_now"); return prep
        t.check("price", price_now, True)
        t.check("adx", safe_float(adx), None)                    # recorded, never a bar (r9)

        # ── the EM band, every tick ────────────────────────────────────
        from strategy.gex_pin_butterfly import expected_move
        em = expected_move(price_now, atm_iv)
        t.check("atm_iv", safe_float(atm_iv), em is not None)
        if em is None:
            prep.starved.append("atm_iv"); t.starved("atm_iv"); return prep
        prep.em, prep.band_lo, prep.band_hi = em, round(price_now - em, 4), round(price_now + em, 4)
        t.check("em", round(em, 4), None)
        t.check("band_lo", prep.band_lo, None)
        t.check("band_hi", prep.band_hi, None)

        store = self._store_()
        if store is None:
            prep.starved.append("level_store"); t.starved("level_store"); return prep
        sym = _symbol_of()
        levels = [l for l in store.live_levels(sym) if str(l["provenance"]) == "ny"]
        # NOT filtered by side of spot: after the move the accepted high is BELOW
        # price and is exactly the level the spread sells against.
        above = sorted([l for l in levels if l["kind"] == "resistance"], key=lambda l: abs(float(l["price"]) - price_now))
        below = sorted([l for l in levels if l["kind"] == "support"], key=lambda l: abs(float(l["price"]) - price_now))
        t.check("extremes_above", len(above), None)
        t.check("extremes_below", len(below), None)
        if chain is None:
            prep.starved.append("chain"); t.starved("chain"); return prep
        prep.above = [self._structure(Candidate(l), chain) for l in above]
        prep.below = [self._structure(Candidate(l), chain) for l in below]
        na = next((c for c in prep.above if c.sellable), None) or (prep.above[0] if prep.above else None)
        nb = next((c for c in prep.below if c.sellable), None) or (prep.below[0] if prep.below else None)
        prep.nearest_above, prep.nearest_below = na, nb
        if na:
            t.check("nearest_above", na.price, None); t.check("nearest_above_credit", na.credit, None)
        if nb:
            t.check("nearest_below", nb.price, None); t.check("nearest_below_credit", nb.credit, None)

        # ── the reference band: frozen on the FIRST close beyond an extreme ──
        try:
            if df_1m is not None and len(df_1m) >= 2:
                bar_ts = str(df_1m.index[-2]); close = float(df_1m.iloc[-2]["close"])
                if bar_ts != self._last_bar_ts:
                    self._last_bar_ts = bar_ts
                    for l in levels:
                        lid, lp, kind = l["level_id"], float(l["price"]), l["kind"]
                        beyond = close > lp if kind == "resistance" else close < lp
                        if beyond and lid not in self._ref and self._prev_band is not None:
                            self._ref[lid] = self._prev_band       # the assessment BEFORE the move
                        elif not beyond and lid in self._ref:
                            self._ref.pop(lid, None)               # the move failed; next attempt refreezes
        except Exception as exc:                                # noqa: BLE001
            logger.debug("tcs ref band read failed: %s", exc)
        self._prev_band = (prep.band_lo, prep.band_hi)

        head = (f"EM ±{em:.2f} ({prep.band_lo:.2f}–{prep.band_hi:.2f}); "
                f"nearest above: {na.line() if na else 'none'}; nearest below: {nb.line() if nb else 'none'}")

        # ── the trigger: a fresh ACCEPTED on a live extreme, outside the frozen band ──
        _open = session_open_epoch or _session_open_epoch()
        since = _open if _open <= time.time() else time.time() - 86400.0
        acc = store.latest_event(sym, "ACCEPTED", since_ts=since)
        cand = None
        if acc and acc["level_id"] in {c.level_id for c in prep.above + prep.below}:
            key = (acc["level_id"], acc["bar_ts"])
            age_bars = max(0.0, time.time() - float(acc["ts_epoch"] or 0)) / 60.0
            t.check("accepted", acc["price"], key not in self._fired)
            t.check("accepted_age_bars", round(age_bars, 2), age_bars <= ACCEPT_FRESH_BARS)
            if key not in self._fired and age_bars <= ACCEPT_FRESH_BARS:
                cand = next(c for c in prep.above + prep.below if c.level_id == acc["level_id"])
                prep.accepted = acc
        else:
            t.check("accepted", None, False)
        if cand is None:
            t.hold(f"{head}. Waiting on: a session extreme ACCEPTED outside the EM")
            return prep

        ref = self._ref.get(cand.level_id) or self._prev_band
        prep.ref_band = ref
        t.check("ref_band_lo", ref[0] if ref else None, None)
        t.check("ref_band_hi", ref[1] if ref else None, None)
        outside_by = (price_now - ref[1]) if cand.kind == "resistance" else (ref[0] - price_now)
        prep.outside_by = round(outside_by, 4)
        t.check("outside_by", prep.outside_by, outside_by > 0)
        t.check("outside_em", prep.outside_by, outside_by > 0)
        if outside_by <= 0:
            prep.unmet.append(("outside_em", f"{cand.provenance} {cand.price:.2f} accepted but price {price_now:.2f} "
                                             f"is INSIDE the reference band {ref[0]:.2f}–{ref[1]:.2f} by {-outside_by:.2f} "
                                             f"— not a move beyond the expected move"))
        prep.chosen, prep.side = cand, cand.side
        prep.direction = "long" if cand.side == "put" else "short"
        prep.bound = cand.price
        t.direction = prep.direction
        t.anchor(trigger=cand.price, invalidation=cand.price)
        if not cand.sellable:
            prep.structural.append((cand.why_key or "contract", cand.why))
        else:
            t.check("contract", float(cand.short.strike), True)
            t.check("wing", float(cand.long.strike), True)
            t.check("width", cand.width, True)
            t.check("credit", cand.credit, True)
            cpw = cand.richness or 0.0
            t.check("credit_pct_width", cpw, cpw >= TCS_MIN_CREDIT_PCT)
            if cpw < TCS_MIN_CREDIT_PCT:
                prep.unmet.append(("credit_pct_width", f"credit {cpw:.0%} of width below the {TCS_MIN_CREDIT_PCT:.0%} floor — not rich"))
            t.check("r_expiry", cand.r, cand.r >= TCS_R_FLOOR_EXPIRY)
            t.check("wing_r_best", cand.r, True)
            t.check("r", cand.r, True)
            t.check("stop_dist", cand.stop_dist, None)
            t.check("stop_vs_spread", cand.stop_dist, True)
            t.check("risk", round(cand.width - cand.credit, 4), None)
            t.check("pop", cand.pop, cand.pop >= TCS_MIN_POP)
            if cand.pop < TCS_MIN_POP:
                prep.unmet.append(("pop", f"POP {cand.pop:.2f} below {TCS_MIN_POP:.2f} — too near the money to be a theta trade"))
            nick = TCS_NICKEL_REF * TCS_NICKEL_MULT
            t.check("nickel_floor", cand.credit, cand.credit >= nick)
            if cand.credit < nick:
                prep.structural.append(("nickel_floor", f"credit ${cand.credit:.2f} below the nickel floor ${nick:.2f}"))
            t.check("richness", cand.richness, None)
            t.check("long_leg_spread_pct", cand.long_leg_spread_pct, None)
            prep.short, prep.long, prep.credit, prep.width = cand.short, cand.long, cand.credit, cand.width
            prep.r, prep.stop_dist, prep.pop, prep.richness = cand.r, cand.stop_dist, cand.pop, cand.richness
            t.credit_spread(cand.short.strike, cand.long.strike, cand.credit, invalidation=cand.price)
        if prep.starved:
            t.starved(*prep.starved); return prep
        if prep.structural:
            g, w = prep.structural[0]; t.refuse(g, f"{cand.provenance} {cand.price:.2f} ACCEPTED: {w}"); return prep
        if prep.unmet:
            g, w = prep.unmet[0]; t.refuse(g, f"{cand.provenance} {cand.price:.2f} ACCEPTED: {w}"); return prep
        self._fired.add((acc["level_id"], acc["bar_ts"]))
        prep.ready = True
        t.note(f"{cand.provenance} {cand.price:.2f} ACCEPTED, price {price_now:.2f} outside the EM by "
               f"{outside_by:.2f}: {cand.line()}")
        return prep
