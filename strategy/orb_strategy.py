"""
strategy/orb_strategy.py  v4.6
v4.6  2026-09-08  OTV4TEST r2 — THE STRATEGY IS THE SPEC; THE PLAN SELECTS.
      Agreed with the operator part by part on 2026-09-08 (PLAN_SPEC §29).
      `generate_signal()` no longer touches the chain, picks a strike, prices
      a contract or reads ATR: it asks `strategy/orb_plan.py` for this tick's
      preparation and fires ONLY when every declared bar is met, with the
      plan's stop, strike, contract, premium and floor. What moved out:
      `get_chain_fetcher().select_orb_strike(...)` (now `orb_plan.select_contract`,
      parity-pinned), the target/50% arithmetic (the engine's own numbers are
      read, never recomputed), and the plan row (the plan writes it every tick
      from 09:35, both sides priced, so "why did ORB not fire" has an answer
      before the retest rather than after). DELETED BY RULING: the ATR floor
      (`ORB_ATR_FLOOR_PCT`) — "makes no sense" for this setup; ORB has no ATR
      read. The liquidity/VWAP/Fed-day items stay as NOTES on the signal (r193:
      recorded, never gating). New kwargs `now_hhmm` and `offer_working` are
      the two facts only main.py knows. `self.planner` is still the same Plan
      object, now owned by the ORBPlan, so W2 and the board see no change.
v4.5  2026-09-04  r235 — 🔴 THE GATE ASKS "HAS THIS CONFIRMATION
      FIRED", NOT "HAS ANY". `confirmation_spent()` is EXTRACTED to module
      level so the checker drives it rather than a copy (C.23). `>=` not `==`,
      so an out-of-order restore fails SHUT; and the `_c > 0` guard means the
      latch does not depend on the state gate for its correctness.
v4.4  2026-09-01  r207 — ONE CONFIRMATION, ONE ORDER, AND THE GEOMETRY COMES
      FROM THE ENGINE. This file gated on `orb.state` ALONE, so anything
      holding an OPEN_* object fired every tick it was asked. On 2026-09-01
      QQQ took two ORB shorts off one confirmation because main.py held a
      stale ORBData across the manage→entry seam and this gate had nothing
      else to say no with. It now refuses a confirmation whose
      `order_placed` latch is set, which is true in paper and live alike.
      The signal also carries `orb_stop_distance_px` — the boundary-to-wick
      distance frozen at the break — so the sizer stops recomputing it from
      the live price at the entry seam.
v4.3  2026-08-30  r193 — POOL IN PATH IS RECORD-ONLY. A named pool within
      BEYOND_TP_ADJUSTMENT_WIDTHS past the 100% target used to PULL the
      target to that pool. Operator's ruling: record it, do not let it move
      the trade. Detection, the counted clusters and the notes all stay, so
      the effect can be studied later; the target is now the pure measured
      move. ⚠️ The pull was a grading-era survivor that CHANGED WHAT THE
      TRADE DOES while reading like an annotation.
v4.2  2026-08-26  r146 — RECORDED THROUGH THE PLAN, ZERO HURDLES. Operator,
      2026-08-26: *"Include orb in that, zero hurdles."* The three refusals
      this file makes AFTER the engine confirms (no contract, zero premium,
      ATR below the reachable floor) and the fire itself now write a
      plan_tick row through `self.planner` (strategy/plan.py, `record_only`).
      ⚠️ NOTHING GATES. `executable()` is never called on this plan; no R
      hurdle, no geometry, no window is applied to ORB. The 2026-08-25 ruling
      — *"leave orb alone. That one can't get encumbered with extra hurdles"*
      — stands; this is narration of decisions the file already made, so
      "why did ORB not fire this morning" has an answer in the table. The
      engine-state-not-confirmed case is recorded by main.py, which is the
      only place that knows the engine was not asked.
v4.1  2026-08-25  r65 EXORCISM: every mention of the retired classification
      system removed - identifiers, comments, docstrings, schema. The word
      does not appear in this tree. Full accounting: REMOVAL_LOG (delivery).


v4.0  2026-08-19  Ported from options_trader_v3 at the OTV4 split.

INHERITED DOCTRINE
MEASUREMENTS AND CONSTRAINTS CARRIED FROM v3 - NOT A CHANGELOG.
Dated release framing and trivia are stripped; what remains is the
reasoning behind the thresholds, the design guarantees, and the
defects that recur when forgotten. WORKING_AGREEMENT 32 requires
this block be read before the file is edited.

strategy/orb_strategy.py — ORB break-and-retest signal generation.
v3.0 — original release
populate orb_range_high/low on signal so exit_engine
        can apply strategy-aware ORB stop logic
update state check for orb_engine v1.1 rename:
        CONFIRMED_LONG/SHORT -> OPEN_LONG/SHORT
repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.
Liquidity-aware ORB logic:
RULE 1 — Named level IS the break level (catalyst, not obstacle):
  If the ORB high/low sits within 0.15% of a named pool (PDH, PDL, session H/L),
  and the break direction is THROUGH that level, this is a high-quality setup.
  The sweep of that level IS the ORB catalyst. Add confluence, don't penalize.
RULE 2 — Named level in path between entry and 50% TP (hard reduce):
  A named pool sitting between entry and the trail-activation level is a known
  reversal zone. Require at least one extra confluence factor, OR block.
RULE 3 — Named level just beyond 100% TP (adjust target, don't block):
  If a named pool sits within 0.5 ORB-widths past the 100% TP, move the target
  to that pool price rather than projecting past it.
v-namelevels (2026-07-28) — the liquidity gate NAMES the levels it blocks on.
        Was: "Named pool in fakeout zone (entry->50%TP): 1 named level(s)." — a bare
        count, unauditable. On 2026-07-28 this gate held the AVGO ORB short for SIX
        consecutive ticks (13:42:15 -> 13:43:30, 90s) starting the same tick the
        retest confirmed; the trade finally filled at 372.11 — 1.4pt below the
        confirmation and 0.5pt off the absolute low — then reversed and stopped out
        (-$135.50). The block never said WHAT it blocked on. Now logs name@price for
        every pool in the fakeout zone plus entry/50%TP/direction, and carries
        named_in_path_detail / unnamed_in_path_detail on the result for callers.
        NOTE: this is OBSERVABILITY ONLY — the gate behaviour is unchanged. What the
        block SHOULD do (skip / trade-to-pool / enter reduced) is still open.
"""

import logging
from typing import Optional

from strategy.base_strategy import BaseOptionsStrategy, OptionsSignal
# ⚠️ `_n` renders an absent value as "n/a" and never raises — the ORB sequence
# below prints levels that can legitimately be None before the range forms.
from strategy.orb_plan import ORBPlan
from analysis.orb_engine import ORBData
from analysis.market_state import MarketState
from analysis.volatility_engine import VolatilityState
from analysis.liquidity_mapper import LiquidityMap
from data.options_chain import OptionsChain
from data.macro_data import MacroSnapshot
from config import FED_DAY_ORB_BOOST, MAX_LOSS_PCT

logger = logging.getLogger(__name__)

# OTV4TEST r2 — `ORB_ATR_FLOOR_PCT` IS DELETED BY RULING (operator, 2026-09-08:
# the ATR floor "makes no sense" for this setup). It was the runaway's
# reachability study (0.05% ATR) glued onto ORB as a feasibility veto at r36;
# the range width and the impulsive candle already say what the tape is doing.
# The runaway keeps its own floor; this strategy has no ATR read at all.

# ── GATE CATEGORIES AS DATA (WA §36) ───────────────────────────────────────
# ⚠️ ORB HAS NO SELECTION GATES AND THEREFORE NOTHING TO RELAX. Every condition
# is either the setup itself or a veto. That is why it does not import
# `relaxed` - and why the relaxed toggle cannot loosen the one strategy with a
# positive record. **The break and retest are the trade; there is no worse
# version of them to fire on.**
GATES = {
    # OTV4TEST r2 — no FEASIBILITY entry: the ATR floor is deleted (above).
    # FOUNDATIONAL, all tested inline with no knob:
    #   the ORB engine armed (a break AND a retest: wick back inside the range,
    #     body still outside - `low < orb_high and body_low >= orb_high`)
    #   direction from the ORB state
    #   this confirmation has not already produced an order (r207/r235)
    #   the liquidity path to target is a NOTE, not a gate (r193)
}

BREAK_LEVEL_PROXIMITY_PCT   = 0.0015
NAMED_IN_PATH_ORB_WIDTHS    = 1.5
BEYOND_TP_ADJUSTMENT_WIDTHS = 0.5


def confirmation_spent(orb) -> bool:
    """Has THIS confirmation already produced an order?

    🔴 r235 — EXTRACTED SO THE CHECKER DRIVES IT AND NOT A COPY (C.23). As
    an inline comparison it was untestable, and a test that re-implements the
    arithmetic it pins tests itself — the r181 sizing checker stayed green for
    two days doing exactly that.
    ⚠️ `>=`, NOT `==`. If a seq were ever restored out of order from a
    persisted snapshot, `==` would fail OPEN and re-fire; `>=` fails shut.
    ⚠️ AND `_c > 0` MATTERS: before any confirmation both are 0, and 0 >= 0
    would refuse a setup that has never fired. The state gate already blocks
    that case, but a latch that depends on ANOTHER gate for its correctness is
    one refactor away from being wrong.
    """
    _c = int(getattr(orb, "confirmation_seq", 0) or 0)
    _o = int(getattr(orb, "order_placed_seq", 0) or 0)
    return _c > 0 and _o >= _c


def _confirmed_epoch(orb) -> float:
    """`confirmed_at` as an epoch, or 0.0. Never raises: this feeds an
    observation, and an observation must not break an entry."""
    raw = str(getattr(orb, "confirmed_at", "") or "").strip()
    if not raw:
        return 0.0
    try:
        from datetime import datetime as _dt
        return _dt.fromisoformat(raw).timestamp()
    except Exception:                                          # noqa: BLE001
        return 0.0


class ORBStrategy(BaseOptionsStrategy):
    """
    Opening Range Breakout strategy.
    Liquidity-aware: distinguishes catalyst sweeps from obstacle sweeps.
    """

    # RECORD ONLY. ORB opens its own plan_ledger rows (main.py's open_plan
    # calls stand), so `self_ledgers=True`; `record_only=True` documents that
    # its verdict is never consulted.
    # 🔴 THE WHOLE ORB SEQUENCE IS RECORDED, NOT JUST THE STATE LABEL (r153).
    # Operator, 2026-08-27: *"I want the entire ORB sequence writing to the per
    # tick log."*
    # ⚠️ WHAT WAS WRONG: the plan wrote one line — "ORB engine is
    # WAITING_FOR_BREAK/ARMED_SHORT/EXPIRED" — and nothing about the GEOMETRY
    # that produced it. UNH on 2026-08-27 logged 70 ticks ARMED_SHORT and one
    # TAKE, with no record of where the break was, how deep the retest went, or
    # what the engine was waiting for. When the operator sees a qualifying
    # break+retest on the chart and the bot does not take it, the table could
    # not say why. Every field below already exists on ORBData and was simply
    # never read.
    PLAN_CHECKS = ORBPlan.PLAN_CHECKS      # declared once, on the plan (r2)

    def __init__(self):
        # OTV4TEST r2 — the plan owns the row, the chain and the selection.
        # `self.planner` is kept as the same object so every reader that
        # asks a strategy for its Plan (check_plan_wiring W2, the board)
        # finds it where it always was.
        self.plan = ORBPlan()
        self.planner = self.plan.planner

    @property
    def name(self) -> str:
        return "ORBStrategy"

    def generate_signal(self,
                        orb: ORBData,
                        ms: MarketState,
                        vol_state: VolatilityState,
                        liq_map: LiquidityMap,
                        chain: OptionsChain,
                        macro: MacroSnapshot,
                        current_price: float,
                        now_hhmm: str = "",
                        offer_working: bool = False) -> Optional[OptionsSignal]:
        """THE SPEC. Fire when every bar the plan reports is met — and only
        with the plan's variables. This function selects nothing.

        OTV4TEST r2 — the bars (PLAN_SPEC §29.2), all read off `prep`:
          1. an impulsive candle exists and is not invalidated (ARMED_*)
          2. a retest bar has closed (OPEN_*)
          3. this confirmation has not already produced an order
          4. a contract with a live quote exists at the 100% target strike
        Nothing else. No R hurdle, no geometry, no ATR, no confluence gate.
        `ms`, `vol_state`, `liq_map` and `macro` are read for NOTES on the
        signal only (they gate nothing and may be None).
        """
        prep = self.plan.prepare(orb=orb, chain=chain, price_now=current_price,
                                 now_hhmm=now_hhmm, offer_working=offer_working)
        if not prep.ready or prep.structural or prep.starved:
            return prep.tick.already()

        t = prep.tick
        direction, option_side, contract = prep.direction, prep.side, prep.contract
        break_level = prep.boundary
        target_100, target_50 = prep.target_100, prep.target_50

        signal = OptionsSignal(
            strategy_name     = self.name,
            setup_type        = f"ORB {direction.title()}",
            direction         = direction,
            option_side       = option_side,
            underlying_entry  = current_price,
            underlying_stop   = prep.stop,          # the impulsive candle's extreme
            underlying_target = target_100,
            underlying_tp50   = target_50,
            orb_range_high    = prep.orb_high,
            orb_range_low     = prep.orb_low,
            # r207 — FROZEN AT THE BREAK, not recomputed at the fill; record only.
            orb_stop_distance_px = float(getattr(orb, "stop_distance_px", 0.0) or 0.0),
            orb_break_ts      = _confirmed_epoch(orb),
            atr_at_signal     = float(getattr(vol_state, "atr", 0.0) or 0.0),
            vix_at_signal     = float(getattr(macro, "vix", 0.0) or 0.0),
            is_fed_day        = bool(getattr(macro, "is_fed_day", False)),
            stop_loss_pct     = MAX_LOSS_PCT,
            tp_pct            = 1.0,
            strike            = contract.strike,
            expiry            = getattr(contract, "expiry", ""),
            entry_premium     = prep.premium,
            contract          = contract,
        )

        # ── NOTES — describe the setup; none of them authorises it ─────────
        self._add_confluence(signal, f"ORB break confirmed ({direction})")
        self._add_confluence(signal, "Break+retest pattern (1m body/wick rules)")
        liq_result = None
        if liq_map is not None:
            try:
                liq_result = self._analyze_liquidity(orb, liq_map, current_price,
                                                     direction, break_level)
            except Exception as exc:                            # noqa: BLE001
                logger.warning("ORB liquidity notes unavailable: %s", exc)
        if liq_result:
            if liq_result["block"]:
                logger.info("ORB pool in path (RECORDED, not a block): %s",
                            liq_result["block_reason"])
            if liq_result["break_is_named_level"]:
                self._add_confluence(signal, f"ORB break through named level "
                                             f"{liq_result['break_level_name']} — sweep catalyst")
                signal.conviction += 0.15
            if liq_result["path_clear"]:
                self._add_confluence(signal, "Liquidity path clear to target")
            if liq_result["unnamed_in_path"] > 0:
                signal.notes += (f" | {liq_result['unnamed_in_path']} unnamed liq "
                                 f"cluster(s) in path (logged, no grade impact)")
            if liq_result.get("target_adjusted"):
                # RECORDED, NOT APPLIED (r193): the target stays the measured move.
                signal.notes += (f" | Pool {liq_result['target_adj_reason']} at "
                                 f"{liq_result.get('adjusted_target', 0.0):.2f} just beyond TP "
                                 f"(RECORDED ONLY — target stays {target_100:.2f})")
        _vwap = getattr(vol_state, "price_vs_vwap", "") if vol_state is not None else ""
        if direction == "long" and _vwap == "ABOVE":
            self._add_confluence(signal, "Above VWAP — bullish bias")
        elif direction == "short" and _vwap == "BELOW":
            self._add_confluence(signal, "Below VWAP — bearish bias")
        if getattr(macro, "is_fed_day", False):
            self._add_confluence(signal, f"Fed day: {getattr(macro, 'fed_event_name', '')} "
                                         f"(+confluence)")
            signal.conviction += FED_DAY_ORB_BOOST
        signal.adx_at_signal = float(getattr(ms, "adx", 0.0) or 0.0) if ms is not None else 0.0
        signal.flat_angle_deg = float(getattr(ms, "flat_angle_deg", 0.0) or 0.0) if ms is not None else 0.0

        logger.info(
            f"🎯 ORB SIGNAL {direction.upper()}: underlying={current_price:.2f} "
            f"orb={prep.orb_low:.2f}–{prep.orb_high:.2f} width={prep.width:.2f} "
            f"option={option_side.upper()} {contract.strike} mark=${prep.premium:.2f} "
            f"delta={float(getattr(contract, 'delta', 0.0) or 0.0):.3f} "
            f"stop={prep.stop:.2f} floor={prep.floor_premium:.2f} target={target_100:.2f} "
            f"size~{prep.size_provisional} (restated at the fill) "
            f"confluence={signal.confluence_factors}"
        )
        return t.take(signal)

    # ─── Liquidity Analysis ───────────────────────────────────────────────────

    def _analyze_liquidity(self, orb, liq_map, current_price,
                            direction, break_level) -> dict:
        result = {
            "break_is_named_level": False,
            "break_level_name":     "",
            "block":                False,
            "block_reason":         "",
            "path_clear":           True,
            "named_in_path":        0,
            "unnamed_in_path":      0,
            # v-namelevels 2026-07-28: identities, not just counts. "1 named
            # level(s)" told us NOTHING when this gate held an AVGO ORB entry for
            # 6 straight ticks (90s) and the trade filled 1.4pt late at the low.
            "named_in_path_detail":   [],   # [(name, price), ...] in the fakeout zone
            "unnamed_in_path_detail": [],   # [price, ...] equal-H/L clusters (metric only)
            "target_adjusted":      False,
            "adjusted_target":      orb.target_100pct,
            "target_adj_reason":    "",
        }

        orb_width  = orb.orb_width
        target_100 = orb.target_100pct
        target_50  = orb.target_50pct

        for pool in liq_map.pools:
            if pool.swept:
                continue

            pool_price = pool.price
            is_named   = pool.is_named
            pool_name  = pool.name or "unnamed"

            prox = abs(pool_price - break_level) / max(break_level, 1)
            if is_named and prox <= BREAK_LEVEL_PROXIMITY_PCT:
                result["break_is_named_level"] = True
                result["break_level_name"]     = pool_name
                continue

            is_obstacle_kind = (
                (direction == "long"  and pool.kind == "high") or
                (direction == "short" and pool.kind == "low")
            )
            if not is_obstacle_kind:
                continue

            in_danger_zone = (
                (direction == "long"  and current_price < pool_price < target_50) or
                (direction == "short" and target_50 < pool_price < current_price)
            )
            if in_danger_zone and is_named:
                result["named_in_path"] += 1
                result["named_in_path_detail"].append((pool_name, float(pool_price)))
                result["path_clear"]     = False

            in_full_path = (
                (direction == "long"  and current_price < pool_price < target_100) or
                (direction == "short" and target_100 < pool_price < current_price)
            )
            if in_full_path and not is_named:
                # v-obs: equal-H/L (unnamed) clusters are LOW QUALITY and no longer
                # penalize the ORB — they do NOT flip path_clear. We still COUNT them
                # (metric only) so we can later study whether they matter at scale.
                # Only NAMED pools (PDH/PDL/session) affect path_clear / grade.
                result["unnamed_in_path"] += 1
                result["unnamed_in_path_detail"].append(float(pool_price))

            adj_zone_long  = (direction == "long"  and
                              target_100 < pool_price < target_100 + orb_width * BEYOND_TP_ADJUSTMENT_WIDTHS)
            adj_zone_short = (direction == "short" and
                              target_100 - orb_width * BEYOND_TP_ADJUSTMENT_WIDTHS < pool_price < target_100)

            if is_named and (adj_zone_long or adj_zone_short) and not result["target_adjusted"]:
                result["target_adjusted"]   = True
                result["adjusted_target"]   = pool_price
                result["target_adj_reason"] = pool_name

        if result["named_in_path"] > 0 and not result["break_is_named_level"]:
            result["block"]        = True
            _named = ", ".join(f"{n}@{px:.2f}" for n, px in result["named_in_path_detail"]) \
                     or "(unidentified)"
            result["block_reason"] = (
                f"Named pool in fakeout zone (entry→50%TP): "
                f"{result['named_in_path']} named level(s): {_named} "
                f"[entry={current_price:.2f} 50%TP={target_50:.2f} dir={direction}]"
            )

        return result
