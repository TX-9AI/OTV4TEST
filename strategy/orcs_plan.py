"""
strategy/orcs_plan.py  v1.1
v1.1  2026-10-03  OTV4TEST r204 (PREM.2) — THE OPENING RANGE CREDIT SPREAD (ORCS): THE PLAN NOW FEEDS A TRADE.
      The operator, 2026-10-03: "No, keep going. I want to paper trade it Monday. Retire the sweep & TCS.
      Call this new one the opening range credit spread ORCS." Renamed from open_premium_plan.py (r203);
      the plan name is OpeningRangeCreditSpread and the dials are ORCS_*. WHAT CHANGED IN THE PLAN:
      (1) `prep.fills` names the sides whose frozen offer FILLED ON THIS TICK (the mark reached the
      limit) - the strategy trades exactly those, at the limit; (2) a new offer is frozen only while a
      full rest still fits inside the window (the last offer is at END minus ORCS_REST_MIN), so every
      offer resolves inside the admission window; (3) the window comes from config.ENTRY_WINDOWS;
      (4) the plan's row is TAKE on a fill tick. Location, pricing, gates and the restart read are r203's.
v1.0  2026-10-03  OTV4TEST r203 (PREM.1) — THE OPENING PREMIUM SPREAD PLAN, RECORD-ONLY (PLAN_SPEC §41).
      The operator, 2026-10-03: "Build this spec, use it to draft the strategy's trigger components
      Incorporating derivative informers if it enhances the edge further. After the trigger components
      are selected, set preliminary dials, then build the plan that searches the chain for our trigger
      components' location on the chain." And on fills: "we get better than mark or we don't trade it."

      THE TRADE: on a 0DTE session, from 09:45 ET, sell one put spread and one call spread far out of
      the money and hold them to the close. The studies behind it (X5-X8, /var/tmp/levels_1003/
      RESULT.md): QQQ 0DTE, 28 priced sessions, short strike at |delta| <= 0.15 entered 09:45, mid
      fills - 96% winners, R +0.036 / +0.029 by half. NOT PROVEN: those 28 sessions were calm.

      WHAT IT SEARCHES THE CHAIN FOR, each side, every tick of the window:
        the SHORT strike - the nearest-to-spot OTM strike whose |delta| <= ORCS_SHORT_DELTA_MAX and
          whose distance from spot is >= ORCS_MIN_IM_MULT x the implied move (the ATM straddle's mark);
        the LONG strike  - the listed strike nearest ORCS_WING_PCT of spot further out;
        the CREDIT at the mark, and the same credit at bid/ask (recorded beside it);
        the OFFER - a limit ORCS_LIMIT_IMPROVE better than the mark, frozen at the first ready tick and
          watched for ORCS_REST_MIN minutes: filled_mark when the frozen spread's mark reaches the limit,
          filled_natural when its bid/ask does. Unfilled at the end = NO TRADE (the ruling above).
      DAY GATES: the chain expires today (0DTE); |overnight gap| <= ORCS_MAX_GAP_PCT (the one informer
      that agreed on both samples - large-gap days paid out more on the 56-day sample).
      RECORDED, GATING NOTHING: implied move, opening-range width, VIX, each short's distance.

      The frozen offer is re-read from this plan's own rows at the first look, so a restart inside the
      window continues the offer instead of re-freezing it (nothing lives only in memory).
"""
from __future__ import annotations

import logging
import time

import config
from strategy.plan import Plan
from utils.math_utils import safe_float

logger = logging.getLogger(__name__)

# ── GATE CATEGORIES AS DATA (WA §36) ────────────────────────────────────────
GATES = {
    "ORCS_START_ET":         "FOUNDATIONAL",   # the edge is gone from 11:00 (X6)
    "ORCS_END_ET":           "FOUNDATIONAL",
    "ORCS_SHORT_DELTA_MAX":  "SELECTION",
    "ORCS_MIN_IM_MULT":      "SELECTION",
    "ORCS_MIN_CREDIT":       "FEASIBILITY",
    "ORCS_MAX_GAP_PCT":      "SELECTION",
}

NAME = "OpeningRangeCreditSpread"
ORCS_START_ET        = tuple(config.ENTRY_WINDOWS[NAME][0])     # one window table (r148)
ORCS_END_ET          = tuple(config.ENTRY_WINDOWS[NAME][1])
ORCS_SHORT_DELTA_MAX = float(config.ORCS_SHORT_DELTA_MAX)
ORCS_MIN_IM_MULT     = float(config.ORCS_MIN_IM_MULT)
ORCS_WING_PCT        = float(config.ORCS_WING_PCT)
ORCS_MIN_CREDIT      = float(config.ORCS_MIN_CREDIT)
ORCS_MAX_GAP_PCT     = float(config.ORCS_MAX_GAP_PCT)
ORCS_LIMIT_IMPROVE   = float(config.ORCS_LIMIT_IMPROVE)
ORCS_REST_MIN        = float(config.ORCS_REST_MIN)

SIDES = ("put", "call")


def _hm(now_et):
    try:
        if hasattr(now_et, "hour"):
            return int(now_et.hour), int(now_et.minute)
        h, m = str(now_et).split(":")[:2]
        return int(h), int(m)
    except (ValueError, AttributeError, TypeError):
        return None


def _session_open_epoch(now_et=None) -> float:
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        n = now_et if hasattr(now_et, "replace") else datetime.now(ZoneInfo("US/Eastern"))
        return n.replace(hour=9, minute=30, second=0, microsecond=0).timestamp()
    except Exception:                                           # noqa: BLE001
        return 0.0


def mark_of(c):
    """A contract's mark: the midpoint of a two-sided quote, else its own mark field, else None.
    A zero bid with a live ask is a real quote (half the ask); no ask is no quote."""
    b, a = safe_float(getattr(c, "bid", None)), safe_float(getattr(c, "ask", None))
    if a is not None and a > 0 and b is not None and b >= 0:
        return (a + b) / 2.0
    m = safe_float(getattr(c, "mark", None))
    return m if m is not None and m > 0 else None


def implied_move(chain, spot: float):
    """The ATM straddle's mark, in dollars: the strike nearest spot listed on BOTH sides."""
    try:
        calls = {float(c.strike): c for c in (chain.calls or [])}
        puts = {float(p.strike): p for p in (chain.puts or [])}
        both = sorted(set(calls) & set(puts), key=lambda k: abs(k - spot))
        for k in both[:3]:
            mc, mp = mark_of(calls[k]), mark_of(puts[k])
            if mc is not None and mp is not None:
                return round(mc + mp, 4), k
    except Exception as exc:                                    # noqa: BLE001
        logger.debug("[orcs] implied move unavailable: %s", exc)
    return None, None


class Located:
    """One side's location on the chain."""
    __slots__ = ("side", "short", "long", "delta", "dist", "dist_pct", "im_mult", "width",
                 "credit", "natural", "why", "why_key")

    def __init__(self, side):
        self.side = side
        self.short = self.long = None
        self.delta = self.dist = self.dist_pct = self.im_mult = None
        self.width = self.credit = self.natural = None
        self.why = self.why_key = ""

    @property
    def priced(self):
        return self.short is not None and self.long is not None and self.credit is not None

    def line(self):
        if not self.priced:
            return f"{self.side}: {self.why or 'not located'}"
        return (f"{self.side} {float(self.short.strike):g}/{float(self.long.strike):g} "
                f"delta {self.delta:.2f}, {self.dist_pct:.2f}% out, credit {self.credit:.2f} at mark")


def locate(side: str, chain, spot: float, im: float) -> Located:
    """Search one side of the chain for the short and long strikes. Pure: reads the chain, decides nothing."""
    loc = Located(side)
    contracts = list(getattr(chain, "puts" if side == "put" else "calls", None) or [])
    otm = []
    for c in contracts:
        k = safe_float(getattr(c, "strike", None))
        if not k or k <= 0 or (k >= spot if side == "put" else k <= spot):
            continue
        otm.append((abs(k - spot), k, c))
    if not otm:
        loc.why, loc.why_key = "no out-of-the-money strike on this side", f"{side}_short"
        return loc
    otm.sort(key=lambda x: x[0])
    with_delta = [(d, k, c) for d, k, c in otm if abs(safe_float(getattr(c, "delta", 0)) or 0.0) > 0]
    if not with_delta:
        loc.why, loc.why_key = "no delta on any out-of-the-money strike", f"{side}_delta"
        return loc
    floor = ORCS_MIN_IM_MULT * im
    pick = next(((d, k, c) for d, k, c in with_delta
                 if abs(float(c.delta)) <= ORCS_SHORT_DELTA_MAX and d >= floor), None)
    if pick is None:
        loc.why = (f"no strike with delta <= {ORCS_SHORT_DELTA_MAX:g} at least "
                   f"{ORCS_MIN_IM_MULT:g} implied moves ({floor:.2f}) out")
        loc.why_key = f"{side}_short"
        return loc
    d, k, short = pick
    loc.short, loc.delta, loc.dist = short, abs(float(short.delta)), round(d, 4)
    loc.dist_pct = round(100.0 * d / spot, 4)
    loc.im_mult = round(d / im, 4) if im else None
    want = ORCS_WING_PCT * spot
    wings = [(abs(abs(kk - k) - want), kk, c) for _d, kk, c in otm
             if (kk < k if side == "put" else kk > k) and mark_of(c) is not None]
    if not wings:
        loc.why, loc.why_key = f"no quoted strike beyond {k:g} for the long leg", f"{side}_long"
        return loc
    _x, kk, long_c = min(wings, key=lambda x: (x[0], x[1]))
    ms, ml = mark_of(short), mark_of(long_c)
    if ms is None:
        loc.why, loc.why_key = f"short {k:g} has no quote", f"{side}_credit"
        return loc
    loc.long, loc.width = long_c, round(abs(kk - k), 4)
    loc.credit = round(ms - ml, 4)
    sb, la = safe_float(getattr(short, "bid", None)), safe_float(getattr(long_c, "ask", None))
    loc.natural = round(sb - la, 4) if sb is not None and la is not None and la > 0 else None
    return loc


def spread_value(chain, side: str, short_k: float, long_k: float):
    """(mark credit, bid/ask credit) of a FROZEN pair of strikes now, or (None, None)."""
    contracts = list(getattr(chain, "puts" if side == "put" else "calls", None) or [])
    by = {}
    for c in contracts:
        k = safe_float(getattr(c, "strike", None))
        if k:
            by[round(k, 4)] = c
    s, l = by.get(round(float(short_k), 4)), by.get(round(float(long_k), 4))
    if s is None or l is None:
        return None, None
    ms, ml = mark_of(s), mark_of(l)
    sb, la = safe_float(getattr(s, "bid", None)), safe_float(getattr(l, "ask", None))
    nat = round(sb - la, 4) if sb is not None and la is not None and la > 0 else None
    return (round(ms - ml, 4) if ms is not None and ml is not None else None), nat


class ORCSPreparation:
    __slots__ = ("tick", "im", "atm", "sides", "ready", "offers", "why", "fills")

    def __init__(self, tick):
        self.tick = tick
        self.im = self.atm = None
        self.sides = {}
        self.ready = []           # sides whose every gate passed this tick
        self.offers = {}
        self.why = ""
        self.fills = []           # sides whose offer FILLED ON THIS TICK: (side, short, long, limit)


def _checks():
    per = ("short", "long", "delta", "dist_pct", "im_mult", "width", "credit", "credit_natural",
           "credit_pct_width", "ready", "offer_short", "offer_long", "offer_limit", "offer_ts",
           "offer_mark", "offer_natural", "offer_age_min", "offer_filled_mark", "offer_filled_natural",
           "offer_expired")
    return tuple(f"{s}_{p}" for s in SIDES for p in per)


class ORCSPlan:
    name = NAME
    PLAN_CHECKS = ("entry_window", "price", "zero_dte", "gap_abs_pct", "implied_move", "im_pct", "atm_strike",
                   "or_width_pct", "vix") + _checks()

    def __init__(self, store=None):
        self.planner = Plan(self.name, self.PLAN_CHECKS, self_ledgers=True)
        self._store = store
        self._offers: dict = {}           # side -> {"short","long","limit","ts","filled_mark","filled_natural"}
        self._first_look_done = False

    def _store_(self):
        if self._store is not None:
            return self._store
        try:
            return self.planner._store_ref()
        except Exception:                                       # noqa: BLE001
            return None

    def _restore(self, since: float) -> None:
        """The first look of this process: re-read today's frozen offers from this plan's own rows."""
        st = self._store_()
        if st is None or not since:
            return
        try:
            from strategy.plan import ensure_tables
            ensure_tables(st)                                   # a fresh store has no rows, not no table
            rows = st.conn.execute(
                "SELECT check_name, value, verdict, ts_epoch FROM plan_check WHERE strategy=? AND symbol=? "
                "AND ts_epoch>=? AND check_name LIKE '%_offer_%' ORDER BY ts_epoch",
                (self.name, self.planner.symbol, since)).fetchall()
        except Exception as exc:                                # noqa: BLE001
            logger.warning("[orcs] first-look read failed - no offer restored: %s", exc)
            return
        got = {}
        for name, value, verdict, _ts in rows:
            side, _, field = str(name).partition("_offer_")
            if side not in SIDES:
                continue
            o = got.setdefault(side, {})
            if field in ("short", "long", "limit", "ts") and value is not None:
                o.setdefault(field, float(value))           # frozen: the FIRST value stands
            elif field in ("filled_mark", "filled_natural") and verdict == "PASS":
                o[field] = True
        for side, o in got.items():
            if all(k in o for k in ("short", "long", "limit", "ts")):
                o.setdefault("filled_mark", False)
                o.setdefault("filled_natural", False)
                self._offers[side] = o
                logger.info("[orcs] first look: %s offer %g/%g at %.2f restored from the plan's rows",
                            side, o["short"], o["long"], o["limit"])

    def prepare(self, *, price_now, now_et, chain=None, gap=None, informers=None,
                today: str = "", now_epoch: float = 0.0) -> ORCSPreparation:
        t = self.planner.tick(price_now)
        prep = ORCSPreparation(t)
        hm = _hm(now_et)
        now_epoch = float(now_epoch or time.time())
        if not self._first_look_done:
            self._first_look_done = True
            self._restore(_session_open_epoch(now_et))
        if hm is not None and hm < ORCS_START_ET:
            t.dormant("entry_window", f"before ORCS_START_ET {ORCS_START_ET[0]:02d}:{ORCS_START_ET[1]:02d} - dormant")
            return prep
        live = [s for s, o in self._offers.items()
                if not o.get("filled_mark") and (now_epoch - o["ts"]) / 60.0 <= ORCS_REST_MIN]
        if hm is not None and hm >= ORCS_END_ET and not live:
            t.dormant("entry_window", f"past ORCS_END_ET {ORCS_END_ET[0]:02d}:{ORCS_END_ET[1]:02d} - observing only")
            return prep
        in_window = hm is None or hm < ORCS_END_ET
        # r204: a NEW offer only while a full rest still fits inside the window
        _left = ((ORCS_END_ET[0] * 60 + ORCS_END_ET[1]) - (hm[0] * 60 + hm[1])) if hm is not None else ORCS_REST_MIN
        may_offer = in_window and _left >= ORCS_REST_MIN
        t.check("entry_window", None, in_window)
        spot = safe_float(price_now)
        if not spot or spot <= 0:
            t.starved("price"); return prep
        t.check("price", spot, True)
        if chain is None:
            t.starved("chain"); return prep

        # ── day gates ────────────────────────────────────────────────────────
        unmet = []
        if not today:
            try:
                today = now_et.strftime("%Y-%m-%d")
            except Exception:                                   # noqa: BLE001
                today = ""
        expiry = str(getattr(chain, "expiry", "") or "")
        zero = bool(today) and expiry == today
        t.check("zero_dte", None, zero, note=f"chain expiry {expiry or 'unknown'}, today {today or 'unknown'}")
        if not zero:
            unmet.append(("zero_dte", f"the chain expires {expiry or 'unknown'}, not today - not a 0DTE session"))
        g = None
        try:
            g = gap.get("gap_abs_pct") if isinstance(gap, dict) else getattr(gap, "gap_abs_pct", None)
            g = safe_float(g)
        except Exception:                                       # noqa: BLE001
            g = None
        t.check("gap_abs_pct", g, None if g is None else g <= ORCS_MAX_GAP_PCT)
        if g is None:
            unmet.append(("gap_abs_pct", "the overnight gap is unmeasured - a gate with no input does not pass"))
        elif g > ORCS_MAX_GAP_PCT:
            unmet.append(("gap_abs_pct", f"overnight gap {g:.2f}% above the {ORCS_MAX_GAP_PCT:.2f}% limit"))
        for k in ("or_width_pct", "vix"):                      # recorded, gating nothing
            t.check(k, safe_float((informers or {}).get(k)), None)

        im, atm = implied_move(chain, spot)
        t.check("implied_move", im, im is not None)
        if im is None:
            t.starved("implied_move"); return prep
        prep.im, prep.atm = im, atm
        t.check("im_pct", round(100.0 * im / spot, 4), None)
        t.check("atm_strike", atm, None)

        # ── the search, each side ────────────────────────────────────────────
        lines = []
        for side in SIDES:
            loc = locate(side, chain, spot, im)
            prep.sides[side] = loc
            lines.append(loc.line())
            if loc.short is not None:
                t.check(f"{side}_short", float(loc.short.strike), True)
                t.check(f"{side}_delta", round(loc.delta, 4), True)
                t.check(f"{side}_dist_pct", loc.dist_pct, None)
                t.check(f"{side}_im_mult", loc.im_mult, True)
            ok = False
            if loc.priced:
                t.check(f"{side}_long", float(loc.long.strike), True)
                t.check(f"{side}_width", loc.width, True)
                rich = loc.credit >= ORCS_MIN_CREDIT and loc.credit < loc.width
                t.check(f"{side}_credit", loc.credit, rich)
                t.check(f"{side}_credit_natural", loc.natural, None)
                t.check(f"{side}_credit_pct_width", round(loc.credit / loc.width, 4) if loc.width else None, None)
                if not rich:
                    loc.why = f"credit {loc.credit:.2f} at mark below the {ORCS_MIN_CREDIT:.2f} floor"
                    loc.why_key = f"{side}_credit"
                ok = rich and not unmet and may_offer
            elif loc.why_key:
                t.check(loc.why_key, None, False, note=loc.why)
            t.check(f"{side}_ready", None, ok)
            if ok:
                prep.ready.append(side)
                if side not in self._offers:                    # the first ready tick freezes the offer
                    self._offers[side] = {"short": float(loc.short.strike), "long": float(loc.long.strike),
                                          "limit": round(loc.credit + ORCS_LIMIT_IMPROVE, 2), "ts": now_epoch,
                                          "filled_mark": False, "filled_natural": False}
                    logger.info("[orcs] %s OFFER: sell %g/%g at %.2f, mark %.2f, "
                                "resting %g min", side, loc.short.strike, loc.long.strike,
                                self._offers[side]["limit"], loc.credit, ORCS_REST_MIN)

        # ── the offers: frozen, then watched ─────────────────────────────────
        for side, o in self._offers.items():
            age = (now_epoch - o["ts"]) / 60.0
            t.check(f"{side}_offer_short", o["short"], None)
            t.check(f"{side}_offer_long", o["long"], None)
            t.check(f"{side}_offer_limit", o["limit"], None)
            t.check(f"{side}_offer_ts", o["ts"], None)
            t.check(f"{side}_offer_age_min", round(age, 2), None)
            if age <= ORCS_REST_MIN and age > 0:
                m, nat = spread_value(chain, side, o["short"], o["long"])
                t.check(f"{side}_offer_mark", m, None)
                t.check(f"{side}_offer_natural", nat, None)
                if m is not None and m >= o["limit"] - 1e-9 and not o["filled_mark"]:
                    o["filled_mark"] = True
                    if not unmet:                               # r204: the fill the strategy trades
                        prep.fills.append((side, o["short"], o["long"], o["limit"]))
                if nat is not None and nat >= o["limit"] - 1e-9:
                    o["filled_natural"] = True
            t.check(f"{side}_offer_filled_mark", None, bool(o["filled_mark"]))
            t.check(f"{side}_offer_filled_natural", None, bool(o["filled_natural"]))
            t.check(f"{side}_offer_expired", None, age > ORCS_REST_MIN and not o["filled_mark"])
        prep.offers = {s: dict(o) for s, o in self._offers.items()}

        head = "; ".join(lines) + f" (implied move {im:.2f})"
        if unmet:
            gate, why = unmet[0]
            prep.why = why
            t.refuse(gate, f"{why}. Located: {head}")
            return prep
        if not prep.ready:
            first = next((l for l in prep.sides.values() if l.why_key), None)
            prep.why = first.why if first else "no side ready"
            if prep.fills:
                t.hold("FILLED at the limit: " + "; ".join(f"{s} {a:g}/{b:g} at {l:.2f}" for s, a, b, l in prep.fills)
                       + f". {head}", verdict="TAKE")
            elif first:
                t.refuse(first.why_key, f"{first.why}. Located: {head}")
            else:
                t.hold(f"no new offer this late; watching the resting offer(s). {head}")
            return prep
        t.direction = "neutral"
        offers = "; ".join(f"{s} offer {o['short']:g}/{o['long']:g} at {o['limit']:.2f}"
                           f"{' FILLED at mark' if o['filled_mark'] else ''}" for s, o in self._offers.items())
        if prep.fills:
            t.hold("FILLED at the limit: " + "; ".join(f"{s} {a:g}/{b:g} at {l:.2f}" for s, a, b, l in prep.fills)
                   + f". {head}", verdict="TAKE")
            return prep
        t.hold(f"Ready: {', '.join(prep.ready)}. {head}. {offers}")
        return prep


def contracts_for(chain, side: str, short_k: float, long_k: float):
    """The two contract objects of a frozen offer, off the live chain, or (None, None)."""
    contracts = list(getattr(chain, "puts" if side == "put" else "calls", None) or [])
    by = {}
    for c in contracts:
        k = safe_float(getattr(c, "strike", None))
        if k:
            by[round(k, 4)] = c
    return by.get(round(float(short_k), 4)), by.get(round(float(long_k), 4))
