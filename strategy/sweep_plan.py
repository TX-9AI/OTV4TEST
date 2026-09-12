"""
strategy/sweep_plan.py  v1.4
v1.4  2026-09-12  OTV4TEST r15 — the rails come from `tines_now` (never a stored row); the
      PDH/PDL ladder is visible now that pools are classified by side (levels v4.3).
v1.3  2026-09-09  OTV4TEST r12 — anchors on the chosen structure (record only): GEX at the
      level, OI at the short, aggressor share at the level, charm at the short, nearest tine.
v1.2  2026-09-09  OTV4TEST r11 — `complement_richness`: as a condor's second leg the
      structure must be at least as rich as leg one, or it is REJECTED by name.
v1.1  2026-09-09  OTV4TEST r10 — `LAST_PREP`: the most recent preparation, so the
      condor's management plan can name the complement it is waiting on.
v1.0  2026-09-08  OTV4TEST r5 — THE SWEEP CREDIT SPREAD PLAN (PLAN_SPEC §31),
      agreed with the operator 2026-09-08/09. The thesis: a previously held
      extreme is swept and rejected; THE LEVEL HOLDS TO THE CLOSE. Sell a
      credit vertical against it, near the money, while it is rich.

      LEVELS IN PLAY — read from the derived level store (`live_levels`),
      never from a private map: the 3 nearest live named levels ABOVE spot
      (resistances) and the 3 nearest BELOW (supports), plus the 1h fork's
      tines (in the store since derived/levels v4.2, keyed on the tine, the
      tine rule applied there). Nothing inside the opening range exists (the
      store retired it TRAVERSED). The geometry gate (session_map.classify)
      still runs per level.

      BOTH SIDES PREPARED EVERY TICK FROM 09:35 — for every level in play the
      structure it WOULD sell if rejected: short strike = the first listed
      strike at/beyond THE LEVEL (the held extreme — operator's ruling, not the
      wick's extreme; a deep pierce is a weak level, so the cushion was
      protecting the trades least worth taking), wing searched with
      `credit_vertical.search_wing` against R_FLOOR on bid/ask, credit, width,
      R, and RICHNESS = credit / width recorded as a dial. The row carries the
      nearest candidate each side: "nearest above: PDH 712.40 — would sell
      713/718C for 0.85 (R 1.10, 17% of width) — waiting on: REJECTED".

      THE TRIGGER IS THE FACT. `DerivedStore.latest_rejection()` — a REJECTED
      event on a level in play, on the trade's side of spot, FRESH (within
      REJECTION_FRESH_BARS of its bar — the operator: "it has to decide
      quickly … wait too long and it was for nothing"; a declared prior,
      recorded), pierce depth inside the band (MIN/MAX_REJECTION_PCT, the
      relaxed x3 ceiling as before), each event fired at most once. On a
      shallow pierce that is the wicking bar's own close; on a deep one, the
      next. Nothing is computed at the fire that was not on the row the tick
      before.

      THE BARS the strategy reads (PLAN_SPEC §31.2): window 09:35–14:00 ·
      REJECTED on a level in play · level not spent · price on the profitable
      side · ATR <= ATR_MAX_PCT (FEASIBLE) · the wing clears R_FLOOR
      (ECONOMICAL) · geometry. Sizing is the env default for verticals.
      The condor complement (`required_side`, `_can_open_credit_spread`) is
      untouched — the sweep may still form the other side of a condor; its
      spec comes last.

      OUTSIDE THE WINDOW THE PLAN OBSERVES AND DOES NOT WRITE (dormant).
"""
from __future__ import annotations

import logging
import time
import config
from strategy import credit_vertical as cv
from strategy import relaxed
from strategy.criteria import R_FLOOR, R_FLOOR_STOP
from strategy.plan import Plan, _n
from strategy.sweep_credit_spread import (
    ATR_MAX_PCT, MAX_REJECTION_PCT, MIN_REJECTION_PCT,
    is_spent, strike_beyond_sweep, tine_spent_key, _symbol_of,
)
from utils.math_utils import safe_float

logger = logging.getLogger(__name__)

GATES = {
    "MAX_REJECTION_PCT":    "SELECTION",     # the relaxed x3 ceiling (r321 shape)
    "EARLIEST_ET":          "SELECTION",
    "LATEST_ET":            "SELECTION",
    "REJECTION_FRESH_BARS": "SELECTION",     # prior — recorded on every fire
    "LEVELS_EACH_SIDE":     "SELECTION",
}

EARLIEST_ET          = getattr(config, "SWEEP_CS_EARLIEST_ET_FORK", (9, 35))     # operator 2026-09-09
LATEST_ET            = getattr(config, "SWEEP_CS_LATEST_ET_FORK", (14, 0))
REJECTION_FRESH_BARS = int(getattr(config, "SWEEP_CS_REJECTION_FRESH_BARS", 3))  # prior
LEVELS_EACH_SIDE     = int(getattr(config, "SWEEP_CS_LEVELS_EACH_SIDE", 3))


def _session_open_epoch() -> float:
    """Today's 09:30 ET as an epoch — the rejection must be today's."""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        et = ZoneInfo("US/Eastern")
        n = datetime.now(et)
        return n.replace(hour=9, minute=30, second=0, microsecond=0).timestamp()
    except Exception:                                           # noqa: BLE001
        return 0.0


def _hm(now_et: str):
    try:
        h, m = str(now_et).split(":")[:2]
        return int(h), int(m)
    except (ValueError, AttributeError):
        return None


class Candidate:
    __slots__ = ("level_id", "price", "kind", "provenance", "side", "boundary",
                 "short", "long", "credit", "width", "r", "r_stop", "richness",
                 "stop_prem", "why", "why_key", "geometry")

    def __init__(self, lvl):
        self.level_id, self.price = lvl["level_id"], float(lvl["price"])
        self.kind, self.provenance = lvl["kind"], lvl["provenance"]
        self.side = "call" if self.kind == "resistance" else "put"
        self.boundary = "ceiling" if self.kind == "resistance" else "floor"
        self.short = self.long = None
        self.credit = self.width = self.r = self.r_stop = self.richness = self.stop_prem = None
        self.why = self.why_key = ""
        self.geometry = None

    @property
    def sellable(self) -> bool:
        return self.short is not None and self.long is not None and (self.credit or 0) > 0

    def line(self) -> str:
        if not self.sellable:
            return f"{self.provenance} {self.price:.2f}: {self.why or 'no structure'}"
        return (f"{self.provenance} {self.price:.2f} — would sell "
                f"{float(self.short.strike):g}/{float(self.long.strike):g}"
                f"{'C' if self.side == 'call' else 'P'} for {_n(self.credit)} "
                f"(R {_n(self.r)}, {self.richness:.0%} of width)")


class SweepPreparation:
    __slots__ = ("tick", "above", "below", "nearest_above", "nearest_below", "rejected",
                 "chosen", "side", "boundary", "pool", "name", "rej_pct", "depth",
                 "short", "long", "credit", "width", "r", "stop_prem", "stop_dist",
                 "richness", "structural", "starved", "unmet", "ready")

    def __init__(self, tick):
        self.tick = tick
        self.above, self.below = [], []
        self.nearest_above = self.nearest_below = None
        self.rejected = None
        self.chosen = None
        self.side = self.boundary = self.name = ""
        self.pool = self.rej_pct = None
        self.depth = ""
        self.short = self.long = None
        self.credit = self.width = self.r = self.stop_prem = self.stop_dist = self.richness = None
        self.structural, self.starved, self.unmet = [], [], []
        self.ready = False

    def trade_line(self) -> str:
        return self.chosen.line() if self.chosen else "no trade prepared"


LAST_PREP = None          # r10: the condor's management plan reads the complement from here


class SweepPlan:
    name = "SweepCreditSpread"
    PLAN_CHECKS = ("entry_window", "price", "atr_pct", "levels_above", "levels_below",
                   "nearest_above", "nearest_above_credit", "nearest_above_r",
                   "nearest_below", "nearest_below_credit", "nearest_below_r",
                   "rejected", "rejection_age_bars", "rejection", "pierce_depth",
                   "side_of_pool", "spent_level", "geometry", "short_anchor", "contract",
                   "credit", "width", "richness", "r", "r_stop", "stop_premium",
                   "complement_richness")

    def __init__(self, store=None):
        self.planner = Plan(self.name, self.PLAN_CHECKS,
                            record_only=True, self_ledgers=True)
        self._store = store
        self._fired_events: set = set()      # (level_id, bar_ts) — each REJECTED fires once

    def _store_(self):
        if self._store is not None:
            return self._store
        try:
            from data.derived_store import get_derived_store
            return get_derived_store()
        except Exception:                                       # noqa: BLE001
            return None

    # ── selection for one level: the structure it would sell ─────────────
    def _structure(self, cand: Candidate, chain) -> Candidate:
        contracts = chain.calls if cand.side == "call" else chain.puts
        if not contracts:
            cand.why, cand.why_key = "no contracts on this side", "chain"
            return cand
        inc = float(getattr(config, "STRIKE_INCREMENT", 1) or 1)
        # ANCHORED ON THE LEVEL, not the wick: sweep_price == pool_price
        k = strike_beyond_sweep(cand.price, cand.price, cand.boundary == "ceiling",
                                contracts=contracts, increment=inc)
        if k is None:
            cand.why, cand.why_key = "no listed strike at/beyond the level", "short_anchor"
            return cand
        short = next((c for c in contracts if abs(float(c.strike) - k) < 1e-6), None)
        if short is None or not (float(getattr(short, "mark", 0) or 0) > 0):
            cand.why, cand.why_key = f"no live quote at {k:g}", "contract"
            return cand
        w = cv.search_wing(contracts, short, cand.side, R_FLOOR, r_floor_stop=R_FLOOR_STOP)
        cand.short = short
        if w.long is None or not (w.credit or 0) > 0:
            cand.why, cand.why_key = (w.why or "no wing clears the R floor"), (w.why_key or "r")
            return cand
        cand.long, cand.credit, cand.width = w.long, float(w.credit), float(w.width)
        cand.r, cand.r_stop = float(w.r), (float(w.r_stop) if w.r_stop is not None else None)
        cand.richness = (cand.credit / cand.width) if cand.width > 0 else None
        cand.stop_prem = (float(w.fill) + float(w.stop_dist)) if (w.fill is not None and w.stop_dist is not None) else None
        return cand

    # ══════════════════════════════════════════════════════════════════════
    def prepare(self, *, price_now, now_et, atr_pct=None, chain=None,
                orb_high=None, orb_low=None, df_1m=None, required_side: str = "",
                session_open_epoch: float = 0.0,
                complement_min_richness: float = 0.0) -> SweepPreparation:
        global LAST_PREP
        t = self.planner.tick(price_now)
        prep = SweepPreparation(t)
        LAST_PREP = prep
        hm = _hm(now_et)
        if hm is not None and hm >= tuple(LATEST_ET):
            t.dormant("entry_window", f"past {LATEST_ET[0]:02d}:{LATEST_ET[1]:02d} ET — observing only")
            return prep
        if hm is not None and hm < tuple(EARLIEST_ET):
            t.dormant("entry_window", f"before {EARLIEST_ET[0]:02d}:{EARLIEST_ET[1]:02d} ET — the opening "
                                      f"range is forming; observing only")
            return prep
        t.check("entry_window", None, True)
        price_now = safe_float(price_now)
        if not price_now or price_now <= 0 or price_now > 1e7:
            prep.starved.append("price_now"); t.starved("price_now"); return prep
        t.check("price", price_now, True)
        _atr = safe_float(atr_pct)
        atr_ok = _atr is None or _atr <= ATR_MAX_PCT
        t.check("atr_pct", _atr, atr_ok)
        if not atr_ok:
            prep.unmet.append(("atr_pct", f"ATR {_atr:.3f}% above the {ATR_MAX_PCT}% ceiling — "
                                          f"a boundary does not hold in that tape"))

        store = self._store_()
        if store is None:
            prep.starved.append("level_store"); t.starved("level_store"); return prep
        sym = _symbol_of()
        levels = store.live_levels(sym)
        # r15 — the rails are read, not stored (levels v4.3): add them from the engine
        try:
            from derived.registry import level_engine
            _eng = level_engine()
            if _eng is not None:
                for t_ in _eng.tines_now(price_now):
                    levels.append({"level_id": _eng._lid(sym, t_["provenance"], 0.0), "price": t_["price"],
                                   "kind": t_["kind"], "provenance": t_["provenance"], "timeframe": "1h", "touches": 0})
        except Exception:                                       # noqa: BLE001
            pass
        above = sorted([l for l in levels if l["kind"] == "resistance" and float(l["price"]) > price_now],
                       key=lambda l: float(l["price"]))[:LEVELS_EACH_SIDE]
        below = sorted([l for l in levels if l["kind"] == "support" and float(l["price"]) < price_now],
                       key=lambda l: -float(l["price"]))[:LEVELS_EACH_SIDE]
        t.check("levels_above", len(above), None)
        t.check("levels_below", len(below), None)
        if required_side:
            above = above if required_side == "call" else []
            below = below if required_side == "put" else []

        if chain is None:
            prep.starved.append("chain"); t.starved("chain"); return prep
        prep.above = [self._structure(Candidate(l), chain) for l in above]
        prep.below = [self._structure(Candidate(l), chain) for l in below]
        for c in prep.above + prep.below:
            c.geometry = t.level(c.price, c.boundary, c.provenance, orb_high, orb_low, price_now)
        na = next((c for c in prep.above if c.sellable), None) or (prep.above[0] if prep.above else None)
        nb = next((c for c in prep.below if c.sellable), None) or (prep.below[0] if prep.below else None)
        prep.nearest_above, prep.nearest_below = na, nb
        if na:
            t.check("nearest_above", na.price, None)
            t.check("nearest_above_credit", na.credit, None if na.credit is None else na.credit > 0)
            t.check("nearest_above_r", na.r, None)
        if nb:
            t.check("nearest_below", nb.price, None)
            t.check("nearest_below_credit", nb.credit, None if nb.credit is None else nb.credit > 0)
            t.check("nearest_below_r", nb.r, None)
        head = (f"in play: {len(prep.above)} above / {len(prep.below)} below — "
                f"nearest above: {na.line() if na else 'none'}; "
                f"nearest below: {nb.line() if nb else 'none'}")

        # ── the trigger: a fresh REJECTED on a level in play ──────────────
        _open = _session_open_epoch()
        _since = float(session_open_epoch or (_open if _open <= time.time() else time.time() - 86400.0))
        rej = store.latest_rejection(sym, since_ts=_since)
        in_play = {c.level_id: c for c in prep.above + prep.below}
        chosen = None
        if rej and rej["level_id"] in in_play:
            key = (rej["level_id"], rej["bar_ts"])
            age_s = max(0.0, time.time() - float(rej["ts_epoch"] or 0.0))
            age_bars = age_s / 60.0
            t.check("rejected", rej["price"], True)
            t.check("rejection_age_bars", round(age_bars, 2), age_bars <= REJECTION_FRESH_BARS)
            if key in self._fired_events:
                t.check("rejected", rej["price"], False)
            elif age_bars > REJECTION_FRESH_BARS:
                # a stale rejection is not a trigger — noted, not declined every tick
                head += (f" (last REJECTED: {rej['provenance']} {rej['price']:.2f}, "
                         f"{age_bars:.0f} bars ago — beyond the {REJECTION_FRESH_BARS}-bar "
                         f"freshness prior)")
            else:
                chosen = in_play[rej["level_id"]]
                prep.rejected = rej
        else:
            t.check("rejected", None, False)

        if not chosen:
            if prep.unmet:
                gate, why = prep.unmet[0]
                t.refuse(gate, f"{head}. {why}")
                return prep
            t.hold(f"{head}. Waiting on: REJECTED")
            return prep

        # ── the bars, on the rejected level ───────────────────────────────
        prep.chosen, prep.side, prep.boundary = chosen, chosen.side, chosen.boundary
        prep.pool, prep.name = chosen.price, chosen.provenance
        prep.rej_pct, prep.depth = float(rej.get("pierce_pct") or 0.0), str(rej.get("depth") or "")
        t.anchor(invalidation=chosen.price)
        t.check("rejection", prep.rej_pct, prep.rej_pct >= MIN_REJECTION_PCT)
        if prep.rej_pct < MIN_REJECTION_PCT:
            prep.unmet.append(("rejection", f"pierce {prep.rej_pct*100:.3f}% below the "
                                            f"{MIN_REJECTION_PCT*100:.2f}% minimum — a touch, not a sweep"))
        _max = relaxed.widen(MAX_REJECTION_PCT, 3.0, name="pierce_ceiling")
        t.check("pierce_depth", prep.rej_pct, prep.rej_pct <= _max)
        if prep.rej_pct > _max:
            prep.unmet.append(("pierce_depth", f"pierce {prep.rej_pct*100:.3f}% beyond the "
                                               f"{_max*100:.2f}% ceiling — a deep pierce is a WEAK level"))
        on_side = (price_now < chosen.price) if chosen.boundary == "ceiling" else (price_now > chosen.price)
        t.check("side_of_pool", price_now - chosen.price, on_side)
        if not on_side:
            prep.unmet.append(("side_of_pool", f"price {price_now:.2f} is not on the profitable side of "
                                               f"{chosen.price:.2f}"))
        _sk = tine_spent_key(chosen.provenance) or chosen.price
        # r11 — as a condor's complement, the second leg is rich or it is not taken:
        # at least as rich (credit / width) as the leg already on. A comparison,
        # not an invented number (operator 2026-09-09).
        if required_side and complement_min_richness > 0 and chosen.sellable:
            t.check("complement_richness", chosen.richness, (chosen.richness or 0) >= complement_min_richness)
            if (chosen.richness or 0) < complement_min_richness:
                prep.unmet.append(("complement_richness",
                                   f"as leg two: {chosen.richness:.0%} of width is thinner than leg one's "
                                   f"{complement_min_richness:.0%} — not rich enough to complete a condor"))
        spent, spent_why = is_spent(sym, chosen.side, _sk)
        t.check("spent_level", 1.0 if spent else 0.0, not spent)
        if spent:
            prep.structural.append(("spent_level", f"{chosen.provenance} {chosen.price:.2f} is SPENT — {spent_why}"))
        if chosen.geometry is False:
            prep.structural.append(("geometry", t.last_why))
        if not chosen.sellable:
            prep.structural.append((chosen.why_key or "contract", chosen.why))
        else:
            prep.short, prep.long = chosen.short, chosen.long
            prep.credit, prep.width, prep.r = chosen.credit, chosen.width, chosen.r
            prep.richness, prep.stop_prem = chosen.richness, chosen.stop_prem
            t.check("short_anchor", float(chosen.short.strike), True)
            t.check("contract", float(chosen.short.strike), True)
            t.check("credit", chosen.credit, chosen.credit > 0)
            t.check("width", chosen.width, None)
            t.check("richness", round(chosen.richness, 4) if chosen.richness else None, None)
            t.check("r", chosen.r, chosen.r >= R_FLOOR)
            t.check("r_stop", chosen.r_stop, None)
            t.check("stop_premium", chosen.stop_prem, None)
            t.credit_spread(chosen.short.strike, chosen.long.strike, chosen.credit,
                            invalidation=chosen.price)
            # r12 — ANCHORS, record only: is the pool a gamma wall; who traded the rejection;
            # charm's sign into the close (the thesis is HOLDS TO THE CLOSE)
            from derived import anchors as _A
            _A.stamp(t, gex_at_level=_A.gex_at(chosen.price), oi_at_short=_A.oi_at(chosen.short.strike, chain),
                     aggressor_at_level=_A.aggressor_share(chosen.price), charm_at_short=_A.charm_at(chosen.short.strike),
                     tine_to_level=_A.nearest_tine(chosen.price))
        if prep.starved:
            t.starved(*prep.starved); return prep
        if prep.structural:
            gate, why = prep.structural[0]
            t.refuse(gate, f"{chosen.provenance} {chosen.price:.2f} REJECTED ({prep.depth}): {why}")
            return prep
        if prep.unmet:
            gate, why = prep.unmet[0]
            t.refuse(gate, f"{chosen.provenance} {chosen.price:.2f} REJECTED ({prep.depth}): {why}")
            return prep
        self._fired_events.add((rej["level_id"], rej["bar_ts"]))
        prep.ready = True
        t.note(f"{chosen.provenance} {chosen.price:.2f} REJECTED ({prep.depth}, "
               f"{prep.rej_pct*100:.3f}%): {chosen.line()}")
        return prep
