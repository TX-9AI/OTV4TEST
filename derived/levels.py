"""
derived/levels.py  v4.3
Owns `level_ledger` and `level_event`. Tier 3 — stateful; the object has a biography.
v4.3  2026-09-12  OTV4TEST r15 — TWO LEVEL DEFECTS, mainline r364's fix ported in its
      own shape (one implementation for otv5). (1) A POOL IS CLASSIFIED BY SIDE:
      the detector wrote "high"/"low" and `live_levels()` filters
      support/resistance, so PDH/PDL and the whole R1/R2/R3 ladder were
      invisible to the hunt, the sweep and the TCS — above the live price is
      resistance, below is support, formation as the fallback. (2) A TINE IS
      NEVER STORED: `_tines()` is gone from `_sources()`; `tines_now(price)`
      computes the rails from the fork the ForkEngine holds right now (with a
      rate: `bars_to_contact`), and a dead fork yields nothing on the next read
      — there is no row to go stale. The emitter reads the tines beside the
      ledger's levels and drops their pierce state when the fork goes. (3)
      `board(price, orb_high, orb_low, limit)` — the level board the plans read
      (PLAN_SPEC §38): held levels beyond the opening range ordered outward,
      the rails, four distinct empty answers, `count` never padded.
v4.2  2026-09-08  OTV4TEST r5 — THREE RULINGS FROM THE SWEEP UNTANGLE.
      · THE 1H PITCHFORK'S TINES ARE LEVELS. Moving ones (time + slope), so
        they are keyed on the TINE, not the price: `fork1h/upper`,
        `fork1h/median`, `fork1h/lower` (the `_level_id` price part is fixed at
        0.00 for them), and the price is read at the bar from the fork the
        ForkEngine built (`forks.last_forks["1h"]`). WICKED / REJECTED /
        ACCEPTED accrue on the tine.
      · THE TINE RULE: a top tine can never be a floor, a bottom tine never a
        ceiling. Upper -> resistance only; lower -> support only; median ->
        whichever side price is on at the bar. A wick UP through the lower
        tine is not an event.
      · NO LEVEL INSIDE THE OPENING RANGE. Once the 09:30 five-minute bar has
        printed (ctx["orb"] carries orb_high/orb_low), every level with
        orb_low <= price <= orb_high is retired TRAVERSED — price has been
        through it — and leaves every consumer at once. Tines are exempt
        (they move; the rule is evaluated per bar for them instead: a tine
        inside the range at the bar emits nothing).
v4.1  2026-09-08  OTV4TEST r3 — THE REJECTION FACT, EMITTED ONCE, HERE. Before
      this the only thing in the tree that could see a wick through a pool was
      the sweep strategy's private rule; this engine read the 5m CLOSE and never
      a high or a low, so a rejection was invisible to the derived layer. Now,
      on every CLOSED 1m bar (iloc[-2], processed once per bar timestamp), for
      every live support/resistance level:
        · close beyond the level (outside tolerance)  -> `beyond` += 1; at
          ACCEPT_CLOSES (2, measured) the level retires ACCEPTED_THROUGH and
          an ACCEPTED event is written. Any pierce state is cleared.
        · wick beyond, close inside                    -> WICKED, with depth:
            shallow  pierce <= SHALLOW_PIERCE_PCT (the sweep's strict ceiling,
                     SWEEP_CS_MAX_REJECTION_PCT = 0.25%)
            deep     pierce <= DEEP_PIERCE_PCT (3x, the relaxed ceiling)
            beyond   deeper than that — the level is being TAKEN, not swept;
                     recorded, never rejected
          Operator, 2026-09-08: *"one on a shallow and 2 on a deep pierce just
          to be sure"* — closes back inside COUNT THE WICKING BAR'S OWN CLOSE.
          A shallow pierce is REJECTED on that bar; a deep pierce needs the
          next bar to close inside too. A close beyond in between clears it.
      Consumers read `DerivedStore.latest_rejection()`; nobody re-detects.
      Wicks are tests, closes are acceptance — the whole emitter is that line.

v4.0  2026-08-22  See docs/DERIVED_STORES.md.

🔴 THE OPERATOR'S RULING, 2026-08-22:
    "In a live session a touch count is a HELD level, and when it doesn't
     hold, that level is FINISHED."

A touch is a HOLD. `touch_count` is the length of a run that TERMINATES at the
break — not a score that accumulates forever.

⚠️ THE EXISTING CODE DOES NOT MODEL THIS. `LiquidityPool` carries `touch_count`
and `swept` as separate fields, so a pool can read five-touch AND swept at the
same time — the count survives its own invalidation. Here the break is a
RECORDED EVENT: `retired_ts` + `retired_reason`, after which the level is
history and stops competing for attention.

🔴 BODIES DECIDE, WICKS TEST — universal convention, operator 2026-08-22, taken
from the sweep rules whose own doctrine says it plainly:
    `closes_beyond >= ACCEPT_CLOSES` is no longer a sweep — it is a BREAKOUT.
A wick through a level is a TEST. A close through is ACCEPTANCE.
⚠️ MEASURED, NOT INVENTED: closes_beyond >= 2 blocked 64.5% of named-pool
sweeps (2026-08-15). And it already fixed this exact defect once — the old
`rejection_pct` measured wick-to-last-close and STAMPED A BREAKOUT AS A
CONFIRMED SWEEP, which is precisely the error a wick-based rule produces.

🔴 NY IS THE DANGEROUS SESSION and the operator has been bitten by it. It is
the only session that is LIVE while being traded; Asia and London are closed
and final by the time an RTH box reads them. So "store once at session close"
is WRONG for NY. The resolution is the operator's own framing: **do not read
session fields at all.** Walk outward from price and report the first level
each way WITH ITS PROVENANCE — the session becomes a LABEL ON THE ANSWER, not
the query. A still-forming NY high that is nearest above genuinely IS the level
that matters, because that is where the stops are. `is_live_session` marks it
as still forming so nothing mistakes it for settled.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from derived.base import DerivedEngine

logger = logging.getLogger(__name__)

# A close beyond by less than this is inside the noise of the level itself.
TOUCH_TOL_PCT = 0.0015
# Closes through required before the level is retired. Inherited from the
# sweep rules, where it was MEASURED rather than chosen.
ACCEPT_CLOSES = 2
# v4.1 — pierce depth bands, from the sweep's own ceiling (strict / relaxed x3).
try:
    import config as _cfg
    SHALLOW_PIERCE_PCT = float(getattr(_cfg, "SWEEP_CS_MAX_REJECTION_PCT", 0.0025))
except Exception:                                               # noqa: BLE001
    SHALLOW_PIERCE_PCT = 0.0025
DEEP_PIERCE_PCT = SHALLOW_PIERCE_PCT * 3.0
CLOSES_BACK = {"shallow": 1, "deep": 2}          # operator, 2026-09-08


def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _level_id(symbol: str, provenance: str, price: float) -> str:
    """Stable identity so touches land on the SAME row across ticks.

    ⚠️ ROUNDED INTO THE ID ON PURPOSE. A level is a zone, not a float; without
    rounding, a price that wobbles in the fifth decimal creates a NEW level
    every tick and every one of them has touch_count=1 — which would silently
    destroy the entire premise of scoring by touches.
    """
    return f"{symbol}:{provenance}:{price:.2f}"


class LevelEngine(DerivedEngine):
    name = "levels"
    table = "level_ledger"
    min_interval_s = 0.0

    def __init__(self, store=None, symbol: str = "", forks=None):
        super().__init__(store)
        self.symbol = symbol
        self._forks = forks              # v4.2: the ForkEngine, for tine prices
        self._live: dict = {}
        self._pierce: dict = {}          # level_id -> {"depth", "pierce_pct", "closes_back", "bar_ts"}
        self._last_bar_ts: str = ""
        self.last_events: list = []      # events emitted on the most recent derive()          # level_id -> mutable state

    def _sources(self, ctx: dict):
        """(provenance, price, kind, timeframe, is_live) for every known level.

        ⚠️ PROVENANCE TRAVELS WITH THE LEVEL. "Resistance at 218.40, from Asia"
        is a different trade from "resistance at 218.40, from yesterday's
        close", and today the map exposes a bare price with the origin lost.
        """
        liq = ctx.get("liq_map")
        vol = ctx.get("vol")
        out = []
        if liq is not None:
            for attr, prov, kind, live in (
                ("prev_day_high", "prev_day", "resistance", 0),
                ("prev_day_low", "prev_day", "support", 0),
                ("asia_session_high", "asia", "resistance", 0),
                ("asia_session_low", "asia", "support", 0),
                ("london_session_high", "london", "resistance", 0),
                ("london_session_low", "london", "support", 0),
                # NY is LIVE — flagged, never treated as settled.
                ("ny_session_high", "ny", "resistance", 1),
                ("ny_session_low", "ny", "support", 1),
            ):
                p = _f(getattr(liq, attr, None))
                if p and p > 0:
                    out.append((prov, p, kind, "1d" if "prev" in prov else "session", live))
            # r15 (mainline r364, LVL.2): a pool is classified by SIDE at write —
            # above the live price is resistance, below is support; with no price,
            # the formation ("high"→resistance). The detector wrote "high"/"low"
            # and live_levels() filters support/resistance, so PDH/PDL and the
            # whole R1/R2/R3 ladder were INVISIBLE to the hunt, the sweep and the
            # TCS (measured on mainline's warehouse, 786 rows, 2026-09-11).
            _px_now = _f(ctx.get("price"))
            for pool in (getattr(liq, "pools", None) or []):
                p = _f(getattr(pool, "price", None))
                if p and p > 0:
                    _formed = str(getattr(pool, "kind", "") or "")
                    if _px_now and _px_now > 0:
                        _side = "resistance" if p > _px_now else "support"
                    else:
                        _side = "resistance" if _formed == "high" else "support"
                    out.append((str(getattr(pool, "name", None) or "pool"), p,
                                _side,
                                str(getattr(pool, "timeframe", "") or ""), 0))
        # VWAP is a level too and belongs in the same walk — operator.
        if vol is not None:
            p = _f(getattr(vol, "vwap", None))
            if p and p > 0:
                out.append(("vwap", p, "dynamic", "session", 1))
        # r15 — tines are NOT sources any more: never stored, computed at read
        # (`tines_now`); the emitter reads them beside the ledger's levels.
        return out

    def tines_now(self, price: float):
        """The 1h fork's rails at THIS read, from the fork the ForkEngine holds
        right now — never a stored row (mainline r364, the operator's rule: "as
        long as there's a fork present, there should be a map of its points. And
        if the fork stops emitting, then the map has to go with it"). A dead
        fork yields [] on the next read; there is no row to go stale.
        A tine has a RATE: `bars_to_contact` is the convergence at a standing
        price — None when diverging, never a negative time. Kind by the tine
        rule: upper resistance, lower support, median by the side price is on."""
        fe = self._forks
        fork = (getattr(fe, "last_forks", {}) or {}).get("1h") if fe is not None else None
        if fork is None:
            return []
        idx = _f((getattr(fe, "last_idx", {}) or {}).get("1h")) or 0.0
        slope = _f(getattr(fork, "slope", None)) or 0.0
        out = []
        for name, fn in (("fork1h/upper", "upper_at"), ("fork1h/median", "median_at"),
                         ("fork1h/lower", "lower_at")):
            try:
                p = _f(getattr(fork, fn)(idx))
            except Exception:                                   # noqa: BLE001
                continue
            if not p or p <= 0:
                continue
            gap = p - (price or 0.0)
            bars = None
            if slope and price:
                b = -gap / slope
                bars = round(b, 2) if b > 0 else None
            out.append({"provenance": name, "price": p,
                        "kind": "resistance" if name.endswith("upper") else
                                ("support" if name.endswith("lower") else
                                 ("resistance" if price and price < p else "support")),
                        "slope_per_bar": slope, "bars_to_contact": bars,
                        "dist_pct": (abs(gap) / price * 100.0) if price else None})
        return out

    def board(self, price: float, orb_high=None, orb_low=None, limit: int = 3):
        """THE LEVEL BOARD (mainline r364, PLAN_SPEC §38): the held levels beyond
        the OPENING RANGE — up to `limit` above orb_high and below orb_low,
        ordered outward from the edge (monotone by construction) — plus the
        fork's rails when it exists. Four answers stay distinct: no_store,
        no_range, no fork, no level that side; fewer than three is an answer
        (`count`), never padded. VWAP is not a level a trade contends with."""
        out = {"state": "ok", "above": [], "below": [], "tines": [], "fork": "absent",
               "as_of": time.time()}
        if self._store is None or not price:
            out["state"] = "no_store"
            return out
        if not (orb_high and orb_low and orb_high > orb_low):
            out["state"] = "no_range"
            return out
        try:
            rows = self._store.conn.execute(
                "SELECT price, kind, provenance, touch_count, is_live_session, level_id"
                " FROM level_ledger WHERE symbol=? AND retired_ts IS NULL"
                " AND kind IN ('support','resistance')", (self.symbol,)).fetchall()
        except Exception:                                       # noqa: BLE001
            out["state"] = "no_store"
            return out
        above = sorted([r for r in rows if r[0] > orb_high], key=lambda r: r[0] - orb_high)
        below = sorted([r for r in rows if r[0] < orb_low], key=lambda r: orb_low - r[0])

        def fmt(r, edge):
            return {"price": r[0], "kind": r[1], "provenance": r[2], "touches": r[3],
                    "live": bool(r[4]), "level_id": r[5],
                    "dist_pct": abs(r[0] - edge) / edge * 100.0}
        out["above"] = [fmt(r, orb_high) for r in above[:limit]]
        out["below"] = [fmt(r, orb_low) for r in below[:limit]]
        out["tines"] = self.tines_now(price)
        for t_ in out["tines"]:
            t_["level_id"] = self._lid(self.symbol, t_["provenance"], 0.0)
        out["fork"] = "built" if out["tines"] else "absent"
        out["count"] = {"above": len(out["above"]), "below": len(out["below"]),
                        "tines": len(out["tines"])}
        return out

    @staticmethod
    def _is_tine(prov: str) -> bool:
        return str(prov).startswith("fork1h/")

    def _lid(self, sym: str, prov: str, price: float) -> str:
        # a tine's identity is the tine; its price moves every bar
        return _level_id(sym, prov, 0.0 if self._is_tine(prov) else price)

    def derive(self, ctx: dict) -> int:
        store = self._store
        if store is None:
            return 0
        sym = self.symbol or ctx.get("symbol") or ""
        price = _f(ctx.get("price"))
        if not sym or not price:
            return 0

        # ⚠️ THE LAST CLOSED BAR DECIDES, NOT THE LIVE PRICE. Bodies decide,
        # wicks test — so acceptance is judged on a CLOSE. Using `price`
        # mid-bar would retire levels on wicks, which is the failure the
        # convention exists to prevent.
        close = price
        df = ctx.get("df_5m")
        try:
            if df is not None and not getattr(df, "empty", True):
                close = _f(df["close"].iloc[-1]) or price
        except Exception:                                       # noqa: BLE001
            pass

        now = time.time()
        written = 0
        self.last_events = []
        orb = ctx.get("orb")
        rng_lo = _f(getattr(orb, "orb_low", None)) if orb is not None else None
        rng_hi = _f(getattr(orb, "orb_high", None)) if orb is not None else None
        in_range = (lambda p: bool(rng_lo and rng_hi and rng_lo <= p <= rng_hi))
        for prov, lvl_price, kind, tf, live in self._sources(ctx):
            lid = self._lid(sym, prov, lvl_price)
            st = self._live.get(lid)
            if st is None:
                st = {"created": now, "touches": 0, "beyond": 0,
                      "last_touch": None, "retired": None, "reason": None}
                self._live[lid] = st
            if st["retired"]:
                continue                       # finished — operator's ruling
            # v4.2 — NO LEVEL INSIDE THE OPENING RANGE (tines exempt: they move)
            if kind in ("support", "resistance") and not self._is_tine(prov) and in_range(lvl_price):
                st["retired"] = now
                st["reason"] = "TRAVERSED"
                self._pierce.pop(lid, None)
                logger.info("[level] %s %s %.2f (%s) retired TRAVERSED — inside the "
                            "opening range %.2f-%.2f", sym, kind, lvl_price, prov, rng_lo, rng_hi)
                store.upsert_level((lid, sym, lvl_price, kind, prov, tf,
                                    st["created"], st["touches"], st["last_touch"],
                                    st["beyond"], st["retired"], st["reason"], int(live)))
                written += 1
                continue

            tol = lvl_price * TOUCH_TOL_PCT
            if kind == "resistance":
                accepted = close > lvl_price + tol
            elif kind == "support":
                accepted = close < lvl_price - tol
            else:
                accepted = False               # VWAP is crossed, not broken

            if accepted:
                st["beyond"] += 1
                if st["beyond"] >= ACCEPT_CLOSES:
                    st["retired"] = now
                    st["reason"] = "ACCEPTED_THROUGH"
                    self._pierce.pop(lid, None)
                    self._emit(store, sym, lid, lvl_price, kind, prov, "5m", now,
                               "ACCEPTED", {"pierce_pct": 0.0, "depth": "accepted",
                                            "closes_back": 0}, close)
            elif abs(close - lvl_price) <= tol:
                # Held at the level — that is a TOUCH.
                st["touches"] += 1
                st["last_touch"] = now
                st["beyond"] = 0               # the run of acceptance is broken

            store.upsert_level((lid, sym, lvl_price, kind, prov, tf,
                                st["created"], st["touches"], st["last_touch"],
                                st["beyond"], st["retired"], st["reason"],
                                int(live)))
            written += 1
        written += self._derive_events(ctx, sym, now)
        return written

    # ── v4.1: the rejection fact, from the CLOSED 1m bar ────────────────
    def _emit(self, store, sym, lid, lvl, kind, prov, bar_ts, now, name, p, close):
        row = (sym, lid, bar_ts, now, name, lvl, kind, prov,
               float(p["pierce_pct"]), p["depth"], int(p["closes_back"]), close)
        self.last_events.append({"event": name, "level_id": lid, "price": lvl,
                                 "kind": kind, "provenance": prov, "bar_ts": bar_ts,
                                 "pierce_pct": p["pierce_pct"], "depth": p["depth"],
                                 "closes_back": p["closes_back"], "bar_close": close})
        logger.info("[level] %s %s %s %.2f (%s) pierce %.3f%% %s closes_back=%d bar=%s",
                    sym, name, kind, lvl, prov, p["pierce_pct"] * 100, p["depth"],
                    p["closes_back"], bar_ts)
        return store.insert_level_event(row) if store is not None else 0

    def _derive_events(self, ctx: dict, sym: str, now: float) -> int:
        store = self._store
        df = ctx.get("df_1m")
        try:
            if df is None or len(df) < 2:
                return 0
            bar = df.iloc[-2]
            bar_ts = str(df.index[-2])
            hi, lo, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        except Exception:                                       # noqa: BLE001
            return 0
        if bar_ts == self._last_bar_ts:
            return 0                                 # one closed bar, once
        self._last_bar_ts = bar_ts
        written = 0
        _px = _f(ctx.get("price")) or close
        # r15 — the tines are read, not stored: they join the ledger's levels here
        # for the emitter only, and vanish with the fork (their pierce state too)
        _tines = self.tines_now(_px)
        _tine_names = {t_["provenance"] for t_ in _tines}
        for k in [k for k in self._pierce if any(k.endswith(f":{n}:0.00") for n in ("fork1h/upper", "fork1h/median", "fork1h/lower"))]:
            if not any(k.endswith(f":{n}:0.00") for n in _tine_names):
                self._pierce.pop(k, None)
        srcs = [(p_, l_, k_, t_, v_) for p_, l_, k_, t_, v_ in self._sources(ctx)]
        srcs += [(t_["provenance"], t_["price"], t_["kind"], "1h", 1) for t_ in _tines]
        for prov, lvl, kind, tf, live in srcs:
            if kind not in ("support", "resistance"):
                continue                             # VWAP is crossed, not swept
            lid = self._lid(sym, prov, lvl)
            if self._is_tine(prov):
                orb = ctx.get("orb")
                lo_, hi_ = (_f(getattr(orb, "orb_low", None)), _f(getattr(orb, "orb_high", None))) if orb is not None else (None, None)
                if lo_ and hi_ and lo_ <= lvl <= hi_:
                    continue                   # a tine inside the range, this bar
            else:
                st = self._live.get(lid)
                if st is None or st["retired"]:
                    continue
            tol = lvl * TOUCH_TOL_PCT
            # the CLOSE keeps the touch tolerance (inside it is noise, as
            # derive() counts touches); the WICK does not — a wick through
            # the level is a wick through the level, and the depth bands
            # (0.25% / 0.75%) are what grade it, not the 0.15% close noise.
            # "inside" means the close is on the HELD side of the level — not
            # merely within the touch tolerance on the far side, which is a
            # bar trading beyond it (v4.2, found by T2: a bar wholly below a
            # support is not a rejection of it).
            if kind == "resistance":
                close_beyond = close > lvl + tol
                close_held = close <= lvl
                wick_beyond = hi > lvl
                pierce = (hi - lvl) / lvl if wick_beyond else 0.0
            else:
                close_beyond = close < lvl - tol
                close_held = close >= lvl
                wick_beyond = lo < lvl
                pierce = (lvl - lo) / lvl if wick_beyond else 0.0
            if close_beyond or not close_held:
                # a rejection cannot survive a close through the level;
                # acceptance itself is counted by derive() on the 5m close.
                if close_beyond:
                    self._pierce.pop(lid, None)
                continue
            ps = self._pierce.get(lid)
            if wick_beyond:
                depth = ("shallow" if pierce <= SHALLOW_PIERCE_PCT
                         else "deep" if pierce <= DEEP_PIERCE_PCT else "beyond")
                ps = {"depth": depth, "pierce_pct": pierce, "closes_back": 1, "bar_ts": bar_ts}
                self._pierce[lid] = ps
                written += self._emit(store, sym, lid, lvl, kind, prov, bar_ts, now,
                                      "WICKED", ps, close)
            elif ps:
                ps["closes_back"] += 1
            if ps and ps["depth"] in CLOSES_BACK and ps["closes_back"] >= CLOSES_BACK[ps["depth"]]:
                written += self._emit(store, sym, lid, lvl, kind, prov, bar_ts, now,
                                      "REJECTED", ps, close)
                self._pierce.pop(lid, None)
        return written

    def walk(self, price: float, limit: int = 3):
        """Levels ordered by DISTANCE from price, nearest first, with grade.

        🔴 THE OPERATOR'S OWN FRAMING: walk up from where price is until you
        hit the last session high — which could be overnight, previous day or
        previous session — and the same going down. **The session is a label on
        the answer, not the query.** That is what makes the live NY high safe
        to use: if it is nearest above, it IS the level that matters.

        ⚠️ DISTANCE ORDERS, TOUCH COUNT SCORES. The nearest level may be a
        one-touch artifact while the one 0.4% beyond has held five times — that
        is the whole distinction between trading into something and trading
        into noise.
        """
        if self._store is None or not price:
            return {"above": [], "below": []}
        try:
            cur = self._store.conn.execute(
                "SELECT price, kind, provenance, touch_count, is_live_session"
                " FROM level_ledger WHERE symbol=? AND retired_ts IS NULL",
                (self.symbol,))
            rows = cur.fetchall()
        except Exception:                                       # noqa: BLE001
            return {"above": [], "below": []}
        above = sorted([r for r in rows if r[0] > price], key=lambda r: r[0] - price)
        below = sorted([r for r in rows if r[0] < price], key=lambda r: price - r[0])
        def fmt(r):
            return {"price": r[0], "kind": r[1], "provenance": r[2],
                    "touches": r[3], "live": bool(r[4]),
                    "dist_pct": abs(r[0] - price) / price * 100.0}
        return {"above": [fmt(r) for r in above[:limit]],
                "below": [fmt(r) for r in below[:limit]]}
