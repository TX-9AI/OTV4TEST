"""
strategy/breakout_plan.py  v1.4
v1.4  2026-09-22  OTV4TEST r91 — carries `entry_delta`, same as the ORB.
      ⚠️ PARITY IS THE POINT: Breakout exists to be the ORB without the
      retest, so a sizing input one supplies and the other does not would make
      the operator's A/B a comparison of two sizers instead of two entries.
THE SEARCH. Every tick, for the setup that satisfies `strategy/breakout.py`.

v1.3  2026-09-21  OTV4TEST r77 — emit() imported OptionsSignal from
      `strategy.structure`, which does not export it. ImportError on EVERY tick
      from 09:37:04; 127 crashes in one session and NOT ONE Breakout trade,
      ever. Lazy import, so check_imports passed; _safe_strategy caught the
      raise, so the board showed a stale skip label instead of a crash.
v1.2  2026-09-19  OTV4TEST r59 — the FADE route read `prep.unmet`, which is
      EMPTY while acceptance is "any", so DEFER->HUNT / DEFER->SWEEP could not
      fire for the whole research window. Reads the FITTED dials, like `pooled`.
v1.1  2026-09-19  OTV4TEST r55 — THE INFORMERS ARE DIALS, NOT A BYPASS.
      Operator: "I still want the informer set as triggers in the strategy
      package, but set the acceptance to 'any'." An earlier cut made them SKIP
      `cond()`; he ruled against it and he was right — a bypass has to be
      un-bypassed later, and that code is code nobody has run. Every bar is a
      real trigger again; `B.accepts(bar, value)` carries the acceptance.
      ⚠️ The FADE route reads the FITTED dial, not the live acceptance: while
      acceptance is "any" every pool distance clears room_to_run, so asking
      "did room_to_run fail?" would never route a harvest to the sweep.
      Declares `sizes_on_geometry` so it sizes as the ORB does.
v1.0  2026-09-18  OTV4TEST r51 (BRK.1).

🔑 WHAT THIS FILE IS FOR, IN THE OPERATOR'S WORDS (2026-09-18): *"The plan file
is what searches the feed every tick for the nearest qualifying setup that
satisfies the strategy. The plan knows exactly what bars must be cleared in
order to deliver a working plan to the strategy. If it can't satisfy every
single hurdle then it doesn't put forward a plan. The plan exists for the sole
purpose of forming the trigger the strategy executes on. Literally A, B, C was
satisfied at X strike, execute if/when it reaches."*

So the OUTPUT of this file is a TRIGGER and nothing else: every declared bar
already TRUE, a strike selected, a stop and an R that clear the floor — and one
thing left pending, which the strategy confirms on the next tick.

🔑 AND IT ROUTES RATHER THAN MERELY REFUSING. Operator: *"if we identify that
it's a fakeout before it happens, maybe we can tip off the appropriate trade to
take that."* When the bars fail in the shape that says HARVEST — a pool sitting
where the stops are, a pinning regime, depth refilling after the sweep — this
plan does not go quiet. It `permit()`s, which `strategy/plan.py` defines as
*"a PERMISSION, not a signal… the plan's terminal for an informer"*, and writes
a PERMIT row so the account separates "informed another strategy" from "took a
trade". **The breakout and the fade are ONE SETUP READ TWO WAYS**, which is why
one search can decide both.

⚠️ THE BREAK IS A CLOSE, NEVER A WICK (r5). That single bar is the anti-fakeout
gate that costs nothing in TIME — which is the whole reason this trade can skip
the retest the ORB waits for.
"""
from __future__ import annotations

import logging
from typing import Optional

import config
from strategy.plan import Plan

logger = logging.getLogger(__name__)

# ── WA §36 ──────────────────────────────────────────────────────────────────
# ⚠️ THE PLAN OWNS NO THRESHOLDS. Every bar it clears is declared in
# `strategy/breakout.py` and read from there, which is the whole point of the
# split: a gate that lived here could be tuned without the specification
# changing, and then the spec would describe a trade the box no longer takes.
# `QUOTE_FLOOR` is the one constant here and it is FEASIBILITY — a contract
# with no live quote cannot be bought at any price.
GATES = {
    "QUOTE_FLOOR": "FEASIBILITY",
}

QUOTE_FLOOR = float(getattr(config, "QUOTE_FLOOR", 0.01))


def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _hm(now_et: str):
    """'HH:MM' -> (h, m), or None when unreadable."""
    try:
        h, m = str(now_et).split(":")[:2]
        return int(h), int(m)
    except Exception:                                           # noqa: BLE001
        return None


def _et(s: str):
    p = _hm(s)
    return p if p else (0, 0)


class BreakoutPreparation:
    """What the search found. `ready` is True ONLY when every bar cleared."""

    __slots__ = ("tick", "spec", "conditions", "unmet", "ready", "direction", "side",
                 "edge", "break_close", "stop", "risk", "target", "target_src",
                 "contract", "premium", "r", "trigger", "invalidation",
                 "pool_price", "pool_name", "pool_dist_r", "verdict", "defer_to",
                 "defer_side", "defer_level", "defer_why", "price_now", "orb",
                 "persist")

    def __init__(self, tick, spec):
        self.tick, self.spec = tick, spec
        self.conditions, self.unmet = {}, []
        self.ready = False
        self.direction = self.side = ""
        self.edge = self.break_close = self.stop = self.risk = None
        self.target = self.target_src = None
        self.contract = self.premium = self.r = None
        self.trigger = self.invalidation = None
        self.pool_price = self.pool_name = self.pool_dist_r = None
        self.verdict, self.defer_to = "WAIT", ""
        self.defer_side = self.defer_level = self.defer_why = None
        self.price_now = self.orb = None
        self.persist = ()

    def cond(self, name, current, met):
        """Record one declared bar: its value now, and whether it cleared.

        🔑 EVERY BAR IS A REAL TRIGGER. r55 briefly made the informers BYPASS
        this method during the research window; the operator ruled otherwise —
        *"I still want the informer set as triggers in the strategy package, but
        set the acceptance to 'all'."* That is the better shape: the plan still
        refuses to form unless EVERY bar clears, and what changed is the
        ACCEPTANCE BAND, declared on the spec beside the bar it belongs to.
        Nothing here is special-cased, so nothing here has to be un-special-cased
        when the window closes.
        ⚠️ AND THE FIT DOES NOT NEED A BYPASS TO BE POSSIBLE: each informer's
        CONTINUOUS value is recorded every tick (`flow_imbalance`, `regime`,
        `depth_ratio`, `pool_dist_r`, `range_width_pct`), so any threshold can be
        fitted afterwards from the values themselves — which is strictly more
        than a stored would-have boolean could ever have told us.
        """
        required = self.spec.CONDITIONS.get(name, "")
        self.conditions[name] = (current, required, bool(met))
        if not met:
            self.unmet.append(name)
        self.tick.check(name, current if isinstance(current, (int, float)) else None,
                        bool(met))

    def trade_line(self) -> str:
        if not self.ready:
            return "no trade prepared"
        still = ", ".join(self.persist) or "nothing"
        return (f"buy {float(self.contract.strike):g}{self.side[0].upper()} @ "
                f"{self.premium:.2f}  stop {self.stop:.2f} ({self.risk:.2f} risk)  "
                f"target {self.target:.2f} via {self.target_src}  R {self.r:.2f}  "
                f"— execute IF {still} are STILL true AND price holds beyond "
                f"{self.trigger:.2f}")

    def emit(self, strategy_name: str):
        """Build the signal from what the PLAN selected. The strategy picks nothing."""
        # 🔴 r77 — `OptionsSignal` LIVES IN base_strategy, NOT structure.
        # This raised ImportError on EVERY tick from the moment Breakout first
        # had a signal to build: 127 crashes on 2026-09-21, first at 09:37:04,
        # and the strategy has NEVER ONCE produced a trade.
        # ⚠️ WHY NOTHING CAUGHT IT. The import is LAZY — inside emit() — so the
        # module imports cleanly and `check_imports` passes; the path only runs
        # when a breakout actually forms. And `_safe_strategy` CATCHES the
        # raise, logs it and continues, so the board showed a stale skip label
        # ("position open — managing") instead of a crash. A gate that reads
        # source text, a checker that imports the module, and a dashboard that
        # reads plan rows were ALL blind to it simultaneously.
        from strategy.base_strategy import OptionsSignal as Signal
        c = self.contract
        sig = Signal(
            strategy_name=strategy_name,
            setup_type=f"breakout_{self.direction}",
            direction=self.direction,
            option_side=self.side,
            underlying_entry=float(self.price_now),
            underlying_stop=float(self.stop),
            underlying_target=float(self.target),
            orb_range_high=float(getattr(self.orb, "orb_high", 0.0) or 0.0),
            orb_range_low=float(getattr(self.orb, "orb_low", 0.0) or 0.0),
            strike=c.strike, expiry=getattr(c, "expiry", ""),
            entry_premium=c.mark, contract=c,
            # 🔴 r91 — THE SIZING INPUT THE 1-R RULE NEEDS, same as the ORB's.
            # `underlying_stop` is the break candle's extreme in POINTS; this
            # converts it to PREMIUM so `stop_premium()` is the structure stop.
            # ⚠️ PARITY IS THE POINT HERE: Breakout exists to be the ORB
            # without the retest, so a sizing input the ORB supplies and this
            # does not would make the A/B a comparison of two sizers.
            entry_delta=getattr(c, "delta", None),
        )
        sig.is_breakout = True
        # 🔑 THE ORB'S SIZING, BY SUPPLYING THE GEOMETRY RATHER THAN BY BEING
        # NAMED. RiskManager.size_for's own docstring: *"Geometry is a sub-rule
        # of long_debit, selected by the caller SUPPLYING orb_width /
        # orb_stop_distance rather than by naming ORB. A second strategy that
        # wants risk-normalised sizing supplies the geometry; it does not get
        # added to a list somewhere that later rots."* Breakout is that second
        # strategy. ⚠️ The flag is explicit because the hunt and the runaway
        # ALSO carry orb_range_high/low — keying on the field would silently
        # re-size two strategies that never asked for it.
        sig.sizes_on_geometry = True
        sig.breakout_edge = self.edge
        sig.breakout_target_src = self.target_src
        sig.disarms_retest = False          # the ORB keeps its own arm
        logger.info("[breakout] FIRE %s — %s", self.direction, self.trade_line())
        return self.tick.take(sig)


class BreakoutPlan:
    name = "Breakout"

    def __init__(self, store=None):
        from strategy.breakout import Breakout as _Spec
        self.planner = Plan(self.name, _Spec.PLAN_CHECKS, self_ledgers=True)
        self._store = store

    def _store_(self):
        if self._store is not None:
            return self._store
        try:
            from data.derived_store import get_derived_store
            return get_derived_store()
        except Exception:                                       # noqa: BLE001
            return None

    # ── the search ────────────────────────────────────────────────────────
    def prepare(self, *, spec, orb, price_now, now_et, chain=None, df_1m=None,
                flow_conn=None, symbol: str = "", **_ignored) -> BreakoutPreparation:
        from strategy import breakout as B

        t = self.planner.tick(price_now)
        prep = BreakoutPreparation(t, spec)
        prep.price_now, prep.orb = _f(price_now), orb

        # ── the window. DORMANT writes one row and goes quiet (r41) ─────────
        hm = _hm(now_et)
        if hm is None or not (_et(B.EARLIEST_ET) <= hm < _et(B.LATEST_ET)):
            t.dormant("entry_window",
                      f"outside {B.EARLIEST_ET}-{B.LATEST_ET} ET — observing only")
            return prep
        prep.cond("entry_window", None, True)

        px = prep.price_now
        if px is None or df_1m is None or len(df_1m) < 2:
            t.starved("price" if px is None else "df_1m")
            return prep

        # ── the range, and whether it is one ───────────────────────────────
        hi, lo = _f(getattr(orb, "orb_high", None)), _f(getattr(orb, "orb_low", None))
        width = (hi - lo) if (hi and lo and hi > lo) else None
        wpct = (width / px) if (width and px) else None
        t.check("range_width_pct", wpct, None)
        prep.cond("orb_range", wpct, B.accepts("orb_range", wpct))

        # ── nothing live inside it (r39 retires them TRAVERSED) ────────────
        board = self._board(px, hi, lo)
        inside = [l for l in (board.get("above", []) + board.get("below", []))
                  if hi and lo and lo <= float(l.get("price") or 0) <= hi]
        prep.cond("range_clean", float(len(inside)),
                  B.accepts("range_clean", float(len(inside))))

        # ── THE BREAK: a CLOSED bar's CLOSE beyond the edge (r5) ───────────
        bar = df_1m.iloc[-2]
        bc = _f(bar.get("close") if hasattr(bar, "get") else bar["close"])
        direction = ("long" if (hi and bc and bc > hi)
                     else "short" if (lo and bc and bc < lo) else "")
        prep.direction = direction
        prep.side = "call" if direction == "long" else "put" if direction == "short" else ""
        prep.edge = hi if direction == "long" else lo if direction == "short" else None
        prep.break_close = bc
        t.check("break_dir", None, None, note=direction or "none")
        t.check("break_close_px", bc, None)
        prep.cond("break_close", bc, bool(direction))

        # volume multiple — RECORDED, NEVER GATED (measured useless, n=736)
        try:
            ob = df_1m.iloc[:5]
            base = float(ob["volume"].mean()) if "volume" in ob else 0.0
            bv = _f(bar.get("volume") if hasattr(bar, "get") else bar["volume"]) or 0.0
            t.check("vol_multiple", (bv / base) if base > 0 else None, None)
        except Exception:                                       # noqa: BLE001
            t.check("vol_multiple", None, None)

        # ── the three a stop run cannot manufacture ────────────────────────
        imb, tag = self._flow(flow_conn, symbol)
        t.check("flow_imbalance", imb, None)
        t.check("flow_tagged", tag, None)
        signed = (imb if direction == "long" else -imb) if imb is not None else None
        prep.cond("flow_commit", signed,
                  bool(signed is not None and tag is not None
                       and B.accepts("flow_commit", signed)
                       and B.accepts("flow_tagged", tag)))

        reg = self._regime()
        t.check("regime", reg, None)
        prep.cond("gamma_regime", reg, B.accepts("gamma_regime", reg))

        dep = self._depth(flow_conn, symbol)
        t.check("depth_ratio", dep, None)
        prep.cond("depth_thin", dep, B.accepts("depth_thin", dep))

        # ── the structure: stop, risk, reach, room ─────────────────────────
        bhi = _f(bar.get("high") if hasattr(bar, "get") else bar["high"])
        blo = _f(bar.get("low") if hasattr(bar, "get") else bar["low"])
        prep.stop = blo if direction == "long" else bhi
        prep.risk = abs(bc - prep.stop) if (bc and prep.stop) else None

        pool = self._pool(board, px, direction)
        prep.pool_price = pool[0] if pool else None
        prep.pool_name = pool[1] if pool else None
        prep.pool_dist_r = ((abs(prep.pool_price - bc) / prep.risk)
                            if (pool and prep.risk and prep.risk > 0 and bc) else None)
        t.check("pool_price", prep.pool_price, None)
        t.check("pool_name", None, None, note=str(prep.pool_name or "open air"))
        t.check("pool_dist_r", prep.pool_dist_r, None)
        prep.cond("room_to_run", prep.pool_dist_r,
                  bool(pool is None or B.accepts("room_to_run", prep.pool_dist_r or 0)))

        # the reach: the NEARER of the measured move and the pool's near edge
        measured = (bc + width) if (direction == "long" and bc and width) else \
                   (bc - width) if (direction == "short" and bc and width) else None
        t.check("reach_measured", measured, None)
        t.check("reach_pool", prep.pool_price, None)
        prep.target, prep.target_src = self._reach(direction, measured, prep.pool_price)

        # ── EVERY BAR MUST CLEAR, OR NO PLAN GOES FORWARD ──────────────────
        if prep.unmet:
            return self._route(prep, t, B)

        # ── the structural bars: a contract, an R that clears the floor ────
        from strategy.orb_plan import select_contract
        prep.contract = select_contract(chain, direction, prep.target) if chain else None
        t.check("contract", None, prep.contract is not None)
        if prep.contract is None:
            t.refuse("contract", "no listed strike with a live quote at the reach")
            return prep
        prep.premium = _f(getattr(prep.contract, "mark", None))
        t.check("premium", prep.premium, bool(prep.premium and prep.premium > QUOTE_FLOOR))
        if not prep.premium or prep.premium <= QUOTE_FLOOR:
            t.refuse("premium", "the contract has no live quote")
            return prep
        reach = abs((prep.target or bc) - bc)
        prep.r = (reach / prep.risk) if (prep.risk and prep.risk > 0) else None
        t.check("r", prep.r, B.accepts("r", prep.r))
        t.check("stop_survivable", prep.risk, bool(prep.risk and prep.risk > 0))
        t.check("target", prep.target, prep.target is not None)
        if not B.accepts("r", prep.r):
            t.refuse("r", f"R {prep.r:.2f} outside acceptance "
                          f"{B.acceptance('r')}" if prep.r else "R unmeasurable")
            return prep

        # ══ THE TRIGGER, AND IT IS COMPOUND ═══════════════════════════════
        # Operator, 2026-09-18: *"the plan will say IF ALL OF THOSE CONDITIONS
        # ARE STILL TRUE and price reaches X, then everything is satisfied."*
        # The settled bars are facts and stay decided. The PERSISTENT ones are
        # live state and are re-read on the tick that fires — a regime can flip
        # and a book can refill between the plan and the fill, and a trade taken
        # on expired evidence is the fakeout this strategy exists to avoid.
        prep.persist = tuple(spec.PERSISTENT)
        t.check("persist_ok", float(len(prep.persist)), True,
                note="must still hold at execution: " + ", ".join(prep.persist))
        prep.trigger, prep.invalidation = prep.edge, prep.edge
        t.anchor(trigger=prep.trigger, invalidation=prep.invalidation)
        t.debit_directional(prep.premium, getattr(prep.contract, "delta", None),
                            getattr(prep.contract, "gamma", None),
                            prep.risk, reach,
                            invalidation=prep.invalidation, trigger=prep.trigger)
        prep.ready, prep.verdict = True, "TAKE"
        t.check("verdict", None, None, note="TAKE")
        t.note(f"all {len(spec.CONDITIONS)} conditions true — {prep.trade_line()}")
        return prep

    # ── the router: a refusal that names the trade that SHOULD take it ─────
    def _route(self, prep, t, B):
        """Not every failure is the same failure.

        🔑 THE HARVEST SHAPE IS SPECIFIC: a pool sitting where the stops are,
        and the tape or the book saying the level is being defended rather than
        given up. That is not "no trade" — it is the SWEEP's trade, or the
        HUNT's, and the plan says so with `permit()` rather than going quiet.
        ⚠️ WAIT IS THE DEFAULT. Only the named shape defers; anything else is
        an ordinary DECLINE, because a permission issued on a shrug is worse
        than silence.
        """
        # ⚠️ THE FADE ROUTE READS THE FITTED DIAL, NOT THE LIVE ACCEPTANCE.
        # While acceptance is "any" every pool distance clears room_to_run, so
        # asking "did room_to_run fail?" would never route a harvest to the
        # sweep. The ROUTING question is "is a pool sitting in the path?", which
        # is a fact about the tape and not an acceptance band.
        pooled = (prep.pool_dist_r is not None
                  and prep.pool_dist_r < B.FITTED_ROOM_MIN_R)
        # 🔴 THIS READ `prep.unmet` UNTIL r59, WHICH MADE THE FADE ROUTE DEAD
        # FOR THE WHOLE RESEARCH WINDOW. With acceptance at "any" NOTHING is
        # ever unmet, so `fading` was permanently False and DEFER->HUNT /
        # DEFER->SWEEP could not fire — the twin of the `pooled` bug fixed
        # beside it, caught only because the operator said he wanted the
        # breakout and the hunt tailored for BOTH a real break and a fakeout
        # grab. Routing reads the FITTED dials, like `pooled` does.
        _reg = (prep.conditions.get("gamma_regime") or (None,))[0]
        _dep = (prep.conditions.get("depth_thin") or (None,))[0]
        fading = (not B.accepts_fitted("gamma_regime", _reg)
                  or not B.accepts_fitted("depth_thin", _dep))
        if pooled and fading and prep.direction and prep.pool_price:
            # price will REACH the pool and stop there -> the hunt has a target
            # it never gives way at all -> the sweep fades the level
            reached = "flow_commit" not in prep.unmet
            prep.defer_to = "LiquidityHunt" if reached else "SweepCreditSpread"
            prep.defer_side = ("put" if prep.direction == "long" else "call") \
                if not reached else prep.side
            prep.defer_level = prep.pool_price
            prep.verdict = "DEFER"
            prep.defer_why = (f"breakout bars failed as a HARVEST: pool "
                              f"{prep.pool_name} at {prep.pool_price:.2f} "
                              f"({prep.pool_dist_r:.2f}R), unmet={','.join(prep.unmet)}")
            t.check("verdict", None, None, note=f"DEFER->{prep.defer_to}")
            t.check("defer_to", None, None, note=prep.defer_to)
            logger.info("[breakout] DEFER -> %s  %s", prep.defer_to, prep.defer_why)
            t.permit(prep.defer_side, prep.defer_level, source=self.name,
                     why=prep.defer_why)
            return prep
        t.check("verdict", None, None, note="WAIT")
        t.hold(f"waiting on: {', '.join(prep.unmet)}")
        return prep

    # ── readers, each failing to None rather than raising ─────────────────
    def _board(self, px, hi, lo) -> dict:
        try:
            from derived.levels import board_for
            return board_for(self._store_(), self._symbol(), px, hi, lo) or {}
        except Exception as exc:                                # noqa: BLE001
            logger.debug("[breakout] board unavailable: %s", exc)
            return {}

    @staticmethod
    def _symbol() -> str:
        try:
            return str(getattr(config, "INSTRUMENT", "") or "")
        except Exception:                                       # noqa: BLE001
            return ""

    @staticmethod
    def _flow(conn, symbol):
        if conn is None:
            return None, None
        try:
            from analysis.order_flow import aggression
            a = aggression(conn, symbol or BreakoutPlan._symbol())
            return (_f((a or {}).get("imbalance")), _f((a or {}).get("tagged_frac")))
        except Exception as exc:                                # noqa: BLE001
            logger.debug("[breakout] aggression unavailable: %s", exc)
            return None, None

    @staticmethod
    def _regime():
        try:
            from derived.gamma_regime import regime
            return _f(regime())
        except Exception as exc:                                # noqa: BLE001
            logger.debug("[breakout] regime unavailable: %s", exc)
            return None

    @staticmethod
    def _depth(conn, symbol):
        """Depletion as a signed ratio: positive = thinning ahead of price."""
        if conn is None:
            return None
        try:
            from analysis.order_flow import depth
            d = depth(conn, symbol or BreakoutPlan._symbol()) or {}
            now, then = _f(d.get("depth_now")), _f(d.get("depth_before"))
            if now is None or not then:
                return None
            return (then - now) / then
        except Exception as exc:                                # noqa: BLE001
            logger.debug("[breakout] depth unavailable: %s", exc)
            return None

    @staticmethod
    def _pool(board, px, direction):
        """The nearest NAMED level ahead of the break, or None for open air."""
        side = board.get("above" if direction == "long" else "below", []) or []
        for l in side:
            p = _f(l.get("near_edge") if "near_edge" in l else l.get("price"))
            if p is None:
                continue
            return p, str(l.get("provenance") or "level")
        return None

    @staticmethod
    def _reach(direction, measured, pool):
        """The NEARER of the measured move and the pool — the operator's ruling.

        *"even a fakeout eventually has to go where the orders are resting"* — a
        measured move projecting THROUGH a resting shelf projects through the
        orders that will stop it.
        """
        if measured is None:
            return (pool, "pool") if pool is not None else (None, "")
        if pool is None:
            return measured, "measured_move"
        nearer = min(measured, pool) if direction == "long" else max(measured, pool)
        return nearer, ("pool" if nearer == pool else "measured_move")
