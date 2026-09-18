"""
execution/position_manager.py  v5.2
v5.2  2026-09-18  OTV4TEST r51 (BRK.1) — Breakout joins the table: 09:35-11:30,
      cap 1, blocking nothing and blocked by nothing. Same window as the ORB it
      is born from and the hunt it is measured against.
v5.1  2026-09-18  OTV4TEST r42 — `logging_state()`: the BINARY AND THE GATE for
      every strategy, from ONE walk of the table. `main.py` used to ask
      `eligible_now()` for the list and `why_not()` per refused strategy for the
      reason — two calls, the same facts passed twice, and nothing making them
      agree. Pass one fact differently to the second and the board names a gate
      that did not refuse: wrong in the log and unfalsifiable from it.
      `eligible_now()` is now a thin view over it, so "eligible" and "why not"
      are two readings of one object rather than two computations.
      ⚠️ STILL PURE, AND DELIBERATELY SO. Nothing is remembered here. The
      operator's "say it once" rule lives in `strategy/plan.py` because
      deduplication is a property of the thing that WRITES ROWS — the only
      thing that knows what it already wrote. A gate that remembered would stop
      being a function of its Facts, and `check_admission.py` could no longer
      drive all 47 combinations without a tick loop or a store.
v5.0  2026-09-17  OTV4TEST r35 — THE ONE AND ONLY POSITION MANAGER: IT KNOWS WHAT
      IS OPEN AND IT DECIDES WHAT MAY OPEN. Operator, 2026-09-17: *"attempt_new_entry
      is a position manager function"*, and earlier, *"the gates for our 1 and only
      position manager"*. Admission was seven mechanisms in four files — an early
      return in main (`is_halted`), a second one (`session_guard.can_enter`), a
      TICK-LOOP BRANCH (`has_open_position`), a hardcoded exemption predicate here,
      a bare dispatch cascade whose ORDER was load-bearing, a window inside each
      plan file, and `_one_per_session_used`. Nothing enumerated them, which is why
      the TCS's 14:00 window shut for twenty-four revisions unnoticed.
      🔴 THE TABLE IS THE OPERATOR'S, AND IT INVERTS THE OLD MODEL. A single GLOBAL
      position slot used to block everything with two hardcoded exemptions.
      **Nothing blocks anything now.** *"To the greatest extent possible I do not
      want to set a maximum number of open positions, and many times this may lead
      to CONFLICTING theses at play simultaneously. That is OK! I WANT sweep to be
      able to fire while we have an active runaway in progress. We will rely on the
      runaway to exit gracefully using ITS OWN stops."* The only structural limit is
      MAX OPEN OF THIS TYPE; there is no cap on the total.
      🔑 THE CONDOR RULES FALL OUT OF THE TYPE CAPS WITH NO SPECIAL CASE: sweep = 2
      permits sweep+sweep, TCS = 1 makes TCS+TCS impossible, TCS+sweep is two types.
      Nothing here knows the word "condor".
      ⚠️ IT ANSWERS, IT DOES NOT DRIVE. `eligible_now()` returns the strategies that
      may be ASKED; `main_loop` does the asking, the plan selects, the strategy
      confirms, execution acts. A position manager that called a plan would be the
      first backwards edge in the one-way flow this repo's isolation depends on.
      ⚠️ IT DOES NOT OWN ORDER PLACEMENT. `session_guard`: *"ORDER PLACEMENT IS NOT
      GATED HERE AT ALL — it is refused at the two order choke points, which check
      `is_rth()` themselves. A gate that says 'no' is not what stops a fill; the
      choke point is."* That separation is a SAFETY PROPERTY and survives intact.
v4.9  2026-09-10  OTV4TEST r12 — has_blocking_position(): THE LIQUIDITY HUNT BLOCKS
      NOTHING (PLAN_SPEC §37), the butterfly's rule applied to a second strategy,
      so the hunt and the ORB run the same break side by side.
v4.8  2026-08-31  r197 — has_blocking_position(): A BUTTERFLY BLOCKS NOTHING.
      r161 exempted it from the single-position rule on ENTRY; nothing made
      that reciprocal, so an open butterfly still threw the box into the
      second-leg-only branch. Cost three boxes their whole credit session on
      2026-08-31. Credit remains blocked by an open ORB or runaway debit —
      that is correct and untouched.
v4.7  2026-08-30  r195 — AN ORB EXIT CANCELS THE STANDING OFFER'S
      REMAINDER BEFORE RE-ARMING THE ENGINE. A partly-filled offer left
      the rest working after ANY exit the supervisor's trigger list did
      not name. The setup ending is the trigger; the exit reason is not.
v4.6  2026-08-27  r167: manage_open_position asks strategy/management.py's
      decide() first; for a covered record its intent (CLOSE / TRAIL / HOLD)
      is executed through the same _execute_exit and trail persistence as
      before. Uncovered records (ORB, ADOPTED, tents, formed condors) go to
      exit_engine.evaluate() exactly as before.
v4.5  2026-08-27  r166: the fetched premium is stamped on the record
      (`current_premium`) so the management plan reads the same number the
      exit engine just decided on.
v4.4  2026-08-27  r161: add_open_position() — append without replacing, for
      the butterfly firing alongside an open vertical.
v4.3  2026-08-24  r99 — flatten_all HOLDS credit verticals until
      VERTICAL_HOLD_TO_ET (15:45). It ran from 15:40 over every record and
      closed them with the debits; the 15:45 hold existed only in
      _evaluate_condor_leg, which the flatten window never reached.
v4.2  2026-08-25  r65 EXORCISM: every mention of the retired classification
      system removed - identifiers, comments, docstrings, schema. The word
      does not appear in this tree. Full accounting: REMOVAL_LOG (delivery).

Open-position tracking, pricing and lifecycle.

v4.1  2026-08-20  AUDIT F9: mark filters gain a 1e6 ceiling - NaN was already
      excluded (NaN > 0 is False) but a finite-absurd mark closed positions
      on phantom prints. Fail direction: None -> tick skipped.
v4.0  2026-08-19  Ported from options_trader_v3 at the OTV4 split.

INHERITED DOCTRINE
MEASUREMENTS AND CONSTRAINTS CARRIED FROM v3 - NOT A CHANGELOG.
Dated release framing and trivia are stripped; what remains is the
reasoning behind the thresholds, the design guarantees, and the
defects that recur when forgotten. WORKING_AGREEMENT 32 requires
this block be read before the file is edited.

execution/position_manager.py — v3.4 — AUDIT A2.2: expose the open condor-leg
SWALLOW T1: this file's silent handler(s) now announce
        themselves once. Behaviour unchanged in every case; only the silence
        was the defect.
        count for the orphan announcement. The F5 warning was wired to a call
        site that cannot run while a leg is open (attempt_new_entry sits
        behind has_open_position, which reads the same DB), so it could never
        fire. The manage branch announces instead, counting from the records
        this manager already holds - no second DB read on the hot path.
v3.2 — AUDIT F6 pairing: price a spread by
        STRUCTURE, not by is_condor_leg. main v6.9 stops stamping
        is_condor_leg=1 onto TC.6 records, and this module's premium fetch
        keyed on exactly that flag (or strategy=="IronCondorStrategy") — so
        without this change a TC.6 record would silently fall to the
        single-leg pricing path. is_credit_vertical() reads only persisted
        columns (strategy / setup_type), so condor legs, both TC.6 row
        generations, and the rolled broken wing all price as short-long.
        Ships in the SAME commit as main v6.9, deliberately.
v3.1 — VEL.1 stashes current_delta
        alongside current_theta: breakeven velocity is |theta|/(|delta|*1440),
        so theta alone cannot answer whether the position is gaining or
        bleeding. Manages the single open options position.
remove the dead PAPER_FILL_SLIPPAGE_PCT import (audit
        defect T). This module has never priced a paper fill — entry pricing
        lives in entry_engine/main and exit pricing in exit_engine, both now
        via execution/limit_ladder. The unused import falsely implied this
        file was a third friction call site. Import-only change.
thread df_5m to exit_engine.evaluate() so trails can
        anchor to 5-minute FVGs (exit_engine v3.8 runner refinements). 1m is
        untouched and remains the structure-stop/BOS timeframe.
BOOK ONLY ON CONFIRMED FILL. _execute_exit() now consumes
        the FillResult from place_exit_order(): it books P&L ONLY when
        fill.confirmed is True and uses fill.fill_price (the ACTUAL close price
        — simulated mark in paper, broker fill in live), never the mark we
        passed nor entry-as-fallback. An unconfirmed result books NOTHING and
        leaves the row OPEN (anti-orphan invariant) so flatten_all's 15:45->16:00
        retry can act. Kills the hard-close $0.00 bookings. flatten_all still
        passes a chain (now supplied by handle_hard_close) so paper has a real
        mark to simulate against.
F5 FIX: trail updates now write to the trail_stop column
        via update_trail_stop() instead of overwriting stop_premium/update_stop.
        stop_premium stays the immutable entry-time -25% floor, so the exit
        engine's floor checks and exit_reason labels are truthful again.
v3.0 — original release
pass df_1m to exit_engine.evaluate() for strategy-aware
        ORB range violation and BOS exits
use live chain marks in paper mode for accurate P&L display;
        butterfly mark computed from lower + upper - 2×center legs
notify ORB engine when an ORB trade closes so it re-arms
        and watches for the next breakout attempt this session
        exits can fire for butterfly and condor leg positions
multi-position support for legged condors: hold up to two
        verticals at once (condor ONLY; every other strategy stays single),
        manage each independently, mark a leg as short_mark - long_mark, and
        invert P&L sign for credit spreads.
add remove_record() for the broken-wing roll (drops the old
        untested vertical when it is rolled).
pass realized P&L into record_win/record_loss so the risk
        manager can track NET daily P&L for the daily loss halt.
set_open_positions(): resume a recovered SET of open rows
        wholesale (1 normally, 2 for a legged condor) so startup recovery
        manages exactly the rows that survived stale-orphan reconciliation
        without dropping a condor leg.
flatten_all(): durable, complete forced close for the 15:45
        hard cutoff. Routes EVERY open record (all condor legs) through the full
        _execute_exit accounting so the DB row is actually marked closed and P&L
        booked — replacing main.py's old direct place_exit_order() that submitted
        an order but never wrote status='closed'. Returns trade_ids that failed
        to close so the caller can retry/escalate.
_fetch_current_premium PAPER fallback fixed: on a chain miss
        it returned the ENTRY premium, so any exit taken during a chain gap booked
        exit==entry (P&L=$0) — a real loss recorded as a scratch, and the exit
        logic blinded to the true premium. Now returns the LAST-KNOWN mark
        (update_current_premium), surrendering to entry only if never priced.
_execute_exit P&L is now credit-signed for an adopted SHORT
        (is_short_position), not just condor legs — so flatten_all/normal exits
        book a broker-adopted short's realized P&L with the correct sign.
repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.
"""

import logging
from dataclasses import dataclass, field
from typing import Mapping, Optional, List

import pandas as pd

from database.trade_logger import TradeRecord, get_trade_logger
from strategy.structure import (is_credit_vertical as _is_credit_vertical,
                                is_tent as _is_tent)
from execution.exit_engine import get_exit_engine, ExitDecision
from data.tasty_client import get_client, TastyClientError
from risk.risk_manager import get_risk_manager
from notifications.alert_manager import get_alert_manager
import config
from config import PAPER_TRADING, CONTRACT_MULTIPLIER


def _stash_quote(record, bid: float, ask: float) -> None:
    """r105 — put a two-sided quote on the record for the exit ladder.

    ⚠️ IN-MEMORY, NOT A COLUMN. It is read on the same tick it is written and
    is meaningless one tick later; persisting a stale quote would be worse than
    having none. A missing stash makes the exit post at mark, which is exactly
    the pre-r105 behaviour.
    """
    try:
        if ask and ask > 0:
            record["_exit_bid"] = round(float(bid), 4)
            record["_exit_ask"] = round(float(ask), 4)
    except (TypeError, ValueError):
        pass


def _vertical_close_due() -> bool:
    """r99 — True once credit verticals are due to close. Reads config at call
    time so a test can pin the clock; fails toward FLATTEN on any error."""
    try:
        from config import VERTICAL_HOLD_TO_ET, VERTICAL_HOLD_TO_CLOSE
        from utils.time_utils import now_et
        if not VERTICAL_HOLD_TO_CLOSE:
            return True
        _n = now_et()
        return (_n.hour, _n.minute) >= tuple(VERTICAL_HOLD_TO_ET)
    except Exception:                                          # noqa: BLE001
        return True

logger = logging.getLogger(__name__)
_WARNED_LEG_COUNT: set = set()   # SWALLOW T1: warn once on an unreadable count


# ══ ADMISSION ══════════════════════════════════════════════════════════════
# ── the strategies this box runs, by their dispatch names ───────────────────
ORB = "ORBStrategy"
RUNAWAY = "RunawayContinuation"
HUNT = "LiquidityHunt"
BREAKOUT = "Breakout"
SWEEP = "SweepCreditSpread"
TCS = "TrendCreditSpread"
GEXFLY = "GEXPinButterfly"
ATPFLY = "ATPButterfly"


@dataclass(frozen=True)
class AdmissionRule:
    """One strategy's admission terms. §36: every field here is SELECTION —
    the operator toggles them as the data arrives. None of them is foundational;
    the FEASIBILITY gate is the catastrophic cap, which is universal."""
    window: tuple                       # ((sh, sm), (eh, em)), half-open [start, end)
    max_open_of_type: int               # concurrent positions OF THIS TYPE
    max_tries_per_session: Optional[int] = None      # None = unlimited
    # 🔑 NAMED SETS, NOT BOOLEANS. The operator asked for the blocking gates to
    # be toggleable "to name which strategies will fill those gates", so a future
    # rule is a name added to a set rather than an edit to a conditional.
    # BOTH DIRECTIONS ARE EVALUATED, so a pairing can be expressed from either
    # end and a half-configured matrix cannot silently do nothing.
    blocks: frozenset = field(default_factory=frozenset)      # I block these from opening
    blocked_by: frozenset = field(default_factory=frozenset)  # these block me


# ── THE TABLE. Operator's specification, 2026-09-17. ────────────────────────
# ⚠️ EVERY WINDOW IS HALF-OPEN [start, end): at 11:30:00 the ORB is OUT and the
# TCS is IN — no overlap, no gap, and no tick that belongs to both or neither.
# ⚠️ EVERY `blocks` / `blocked_by` IS EMPTY BY RULING. Nothing blocks anything.
_DEFAULT_RULES = {
    ORB:     AdmissionRule(((9, 35), (11, 30)), max_open_of_type=1),
    RUNAWAY: AdmissionRule(((9, 35), (11, 30)), max_open_of_type=1),
    HUNT:    AdmissionRule(((9, 35), (11, 30)), max_open_of_type=1),
    # r51 (BRK.1) — the 5-minute opening-range break taken WITHOUT a retest.
    # Same window as the ORB it is born from and the hunt it competes with,
    # because all three read the same opening range. ⚠️ NOTHING BLOCKS IT AND IT
    # BLOCKS NOTHING — the operator ruled the blocking paradigm out entirely
    # (r50): *"every trade to be 'right' in its own time… I don't see any reason
    # to stop it from firing if it cleared the bar, even if the thesis is the
    # opposite of an existing open trade."* The head-to-head against ORB and the
    # hunt is the POINT, and hierarchy would destroy the counterfactual that
    # makes it readable.
    BREAKOUT: AdmissionRule(((9, 35), (11, 30)), max_open_of_type=1),
    # the credit window was widened to 15:00 by the operator on 2026-09-17
    SWEEP:   AdmissionRule(((9, 35), (15, 0)), max_open_of_type=2),   # 2: it forms a condor
    TCS:     AdmissionRule(((11, 30), (15, 0)), max_open_of_type=1),  # 1: TCS+TCS is in conflict
    # the GEX fly's cutoff was raised from 14:00 to 15:00 by the operator
    GEXFLY:  AdmissionRule(((12, 0), (15, 0)), max_open_of_type=1, max_tries_per_session=1),
    ATPFLY:  AdmissionRule(((11, 30), (15, 0)), max_open_of_type=1, max_tries_per_session=1),
}


def rules() -> dict:
    """The table, with `config.ADMISSION_RULES` overlaid when present.

    🔑 TOGGLED WITHOUT A REVISION. The operator: *"I want to be able to toggle
    those granular details LATER. For instance, after we have enough data, I will
    toggle it back to only 1 butterfly trade at a time."* An override names a
    strategy and any subset of its fields; everything unnamed keeps the default,
    so a partial override cannot blank a rule by omission."""
    out = dict(_DEFAULT_RULES)
    ov = getattr(config, "ADMISSION_RULES", None) or {}
    for name, patch in ov.items():
        base = out.get(name)
        if base is None or not isinstance(patch, dict):
            continue
        out[name] = AdmissionRule(
            window=tuple(patch.get("window", base.window)),
            max_open_of_type=int(patch.get("max_open_of_type", base.max_open_of_type)),
            max_tries_per_session=patch.get("max_tries_per_session", base.max_tries_per_session),
            blocks=frozenset(patch.get("blocks", base.blocks)),
            blocked_by=frozenset(patch.get("blocked_by", base.blocked_by)),
        )
    return out


@dataclass(frozen=True)
class Facts:
    """Everything admission depends on, gathered by the caller.

    ⚠️ FACTS, NOT OBJECTS — passing values rather than the risk manager and the
    position manager is what keeps this pure, and what lets a checker drive every
    combination without a tick loop or a store."""
    strategy: str
    now_et: tuple                        # (hour, minute)
    trading_day: bool = True
    orb_established: bool = False
    cap_intact: bool = True
    past_hard_close: bool = False
    open_by_strategy: Mapping[str, int] = field(default_factory=dict)
    tries_used: int = 0


@dataclass(frozen=True)
class Verdict:
    admitted: bool
    gate: str = ""
    why: str = ""

    def __bool__(self) -> bool:
        return self.admitted


def _within(now: tuple, window: tuple) -> bool:
    (sh, sm), (eh, em) = window
    t = now[0] * 60 + now[1]
    return (sh * 60 + sm) <= t < (eh * 60 + em)      # half-open, deliberately


def decide(f: Facts, table: Optional[dict] = None) -> Verdict:
    """ADMIT, or the FIRST gate that refuses.

    THE THREE UNIVERSALS ARE ASKED ONCE, FOR EVERY STRATEGY, and they are the
    operator's own list: is today a trading day, is the ORB range established,
    is the catastrophic cap unbroken. The hard close rides with them.
    ⚠️ THE VIX CRISIS GATE IS GONE, and that is a ruling, not an omission.
    Operator, 2026-09-17: *"VIX crisis — get rid of it. That is major
    opportunity."* It previously refused every new entry on `macro`'s say-so.
    """
    table = table if table is not None else rules()

    # ── the universals ──────────────────────────────────────────────────────
    if not f.trading_day:
        return Verdict(False, "trading_day", "not a trading day")
    if not f.orb_established:
        # the universal floor for EVERY strategy: nothing trades inside the
        # opening range, and the ORB itself cannot be read before it exists.
        return Verdict(False, "orb_range", "opening range not established yet")
    if not f.cap_intact:
        return Verdict(False, "catastrophic_cap", "catastrophic cap reached — no new entries")
    if f.past_hard_close:
        return Verdict(False, "hard_close", "past the 15:45 ET hard close")

    rule = table.get(f.strategy)
    if rule is None:
        # ⚠️ FAILS CLOSED (§22). An unknown strategy is not admitted by default;
        # a new trade joins the table deliberately or it does not trade.
        return Verdict(False, "unknown_strategy", f"{f.strategy} has no admission rule")

    # ── the per-strategy terms ──────────────────────────────────────────────
    if not _within(f.now_et, rule.window):
        (sh, sm), (eh, em) = rule.window
        return Verdict(False, "window",
                       f"{f.strategy} is outside {sh:02d}:{sm:02d}-{eh:02d}:{em:02d} ET")

    if rule.max_tries_per_session is not None and f.tries_used >= rule.max_tries_per_session:
        return Verdict(False, "tries_per_session",
                       f"{f.strategy} has used its {rule.max_tries_per_session} attempt(s)")

    if int(f.open_by_strategy.get(f.strategy, 0)) >= rule.max_open_of_type:
        return Verdict(False, "max_open_of_type",
                       f"{rule.max_open_of_type} {f.strategy} already open")

    # ── the blocking matrix, BOTH directions, empty by ruling ───────────────
    open_now = {s for s, n in f.open_by_strategy.items() if int(n) > 0}
    hit = open_now & set(rule.blocked_by)
    if hit:
        return Verdict(False, "blocked_by", f"{f.strategy} is blocked by {sorted(hit)[0]} being open")
    for other in sorted(open_now):
        other_rule = table.get(other)
        if other_rule is not None and f.strategy in other_rule.blocks:
            return Verdict(False, "blocks", f"{other} is open and blocks {f.strategy}")

    return Verdict(True, "", "admitted")


def gates() -> tuple:
    """Every gate this can refuse on, in order — so admission can be ENUMERATED
    by a reader, a report and a checker instead of rediscovered.
    ⚠️ The absence of this list is why the seven layers were never counted."""
    return ("trading_day", "orb_range", "catastrophic_cap", "hard_close",
            "unknown_strategy", "window", "tries_per_session",
            "max_open_of_type", "blocked_by", "blocks")


class PositionManager:
    """
    Manages the bot's single open position (one trade at a time).
    Fetches live option premium, evaluates exits, and closes when triggered.
    """

    def __init__(self, paper_trading: bool = PAPER_TRADING):
        self.paper_trading = paper_trading
        self._open_records: List[TradeRecord] = []
        self._trade_logger = get_trade_logger()

    def open_condor_leg_count(self) -> int:
        """Open condor legs among the records this manager holds (A2.2).

        Counts from `_open_records` when loaded (the manage branch runs right
        after they are), falling back to the DB on a cold call. Returns 0 on
        any error: this feeds an ANNOUNCEMENT, and the occupancy guards
        elsewhere already fail closed - a missed log line costs less than a
        crashed tick."""
        try:
            recs = self._open_records or self._trade_logger.get_open_trades()
            return sum(1 for r in recs if r.get("is_condor_leg"))
        except Exception as exc:                               # noqa: BLE001
            # ⚠️ SWALLOW T1, 2026-08-17 — THIS RETURNED 0 SILENTLY, AND 0 IS THE
            # PERMISSIVE ANSWER. "No condor legs open" is what a caller checks
            # before opening another; a failed COUNT therefore reads as CLEAR TO
            # PROCEED. That is the F5 shape exactly — an unreadable input
            # granting permission it never established.
            # The count is left at 0 (callers treat a raise as fatal and this
            # runs on the tick path) but it is NO LONGER SILENT: a box that
            # cannot count its own open legs must be visible before it acts on
            # the answer.
            if not _WARNED_LEG_COUNT:
                _WARNED_LEG_COUNT.add(1)
                logger.warning(
                    "[legs] could not count open condor legs (%s) - reporting 0, "
                    "which reads as NO LEGS OPEN to every caller. If a leg IS "
                    "open, deferral and sibling checks are running blind.", exc)
            return 0

    @staticmethod
    def _is_liquidity_hunt(record) -> bool:
        """OTV4TEST r12 — the liquidity hunt runs in PARALLEL with the ORB and
        never blocks (PLAN_SPEC §37); reads the ROW, like the butterfly."""
        try:
            return bool(record.get("is_liquidity_hunt", 0)) or \
                str(record.get("strategy") or "") == "LiquidityHunt"
        except Exception:                                       # noqa: BLE001
            return False

    @staticmethod
    def _is_butterfly(record) -> bool:
        """A GEX pin butterfly. Reads the ROW, not the strategy name.

        ⚠️ The column is the fact; `strategy` is a label that has been
        rewritten before. `is_butterfly` is set at the record builder and is
        what every other consumer keys on.
        """
        try:
            return bool(record.get("is_butterfly", 0))
        except Exception:                                       # noqa: BLE001
            return False

    # ══ ADMISSION, ANSWERED FROM THE STATE THIS OBJECT ALREADY HOLDS ══════
    def open_by_strategy(self) -> dict:
        """{strategy: open count} across the records this manager holds.

        Counts from `_open_records` when loaded, falling back to the DB on a cold
        call — the same shape as `open_condor_leg_count`, deliberately.
        ⚠️ FAILS CLOSED, AND THAT IS THE OPPOSITE OF THE LEG COUNT'S CHOICE. An
        empty dict reads to `decide()` as NOTHING IS OPEN, which is the PERMISSIVE
        answer — the F5 shape that swallow T1 was written about. So a failure
        raises rather than returning {}: a box that cannot count its own open
        positions must not be told it is clear to open another."""
        recs = self._open_records
        if not recs:
            recs = self._trade_logger.get_open_trades()
        out: dict = {}
        for r in (recs or []):
            name = (r.get("strategy") if isinstance(r, dict) else getattr(r, "strategy", "")) or ""
            if name:
                out[name] = out.get(name, 0) + 1
        return out

    def logging_state(self, now_et: tuple, *, trading_day: bool = True,
                      orb_established: bool = False, cap_intact: bool = True,
                      past_hard_close: bool = False,
                      tries_used: Optional[Mapping[str, int]] = None,
                      table: Optional[dict] = None) -> dict:
        """{strategy: (active: bool, gate: str, why: str)} — ONE PASS, ONE TRUTH.

        ACTIVE   — the plan is asked this tick and logs per tick.
        INACTIVE — not asked; `gate` NAMES the rule that refused it
                   ("window", "max_open_of_type", "tries_per_session",
                   "catastrophic_cap", "orb_range", "blocked_by", …).

        🔑 WHY THIS REPLACED TWO CALLS. `main.py` used to ask `eligible_now()`
        for the LIST and then `why_not()` per refused strategy for the REASON —
        two calls, the same facts passed twice, and nothing making them agree.
        That is a seam: pass a slightly different fact to the second call and
        the board reports a gate that is not the one that actually refused,
        which is unfalsifiable from the log. One call, one object, and they
        cannot diverge.

        ⚠️ STILL PURE. This is `decide()` over the whole table and NOTHING IS
        REMEMBERED — same facts in, same map out. That purity is the reason
        `check_admission.py` can drive all 47 combinations with no tick loop and
        no store, and it is why the "say it once" half of the operator's ruling
        lives in `strategy/plan.py` and NOT here: deduplication is a property of
        the thing that WRITES ROWS, which is the only thing that knows what it
        already wrote. A gate that remembered would stop being testable.
        """
        tbl = table if table is not None else rules()
        tried = dict(tries_used or {})
        openmap = self.open_by_strategy()
        out: dict = {}
        for name in tbl:
            v = decide(Facts(strategy=name, now_et=now_et, trading_day=trading_day,
                             orb_established=orb_established, cap_intact=cap_intact,
                             past_hard_close=past_hard_close,
                             open_by_strategy=openmap,
                             tries_used=int(tried.get(name, 0))), tbl)
            out[name] = (bool(v.admitted), v.gate, v.why)
        return out

    def eligible_now(self, now_et: tuple, **kw) -> list:
        """The strategies that MAY BE ASKED this tick, in table order.

        🔑 IT ANSWERS, IT DOES NOT DRIVE. The caller iterates this list and asks
        each plan; this never reaches into `strategy/`. That is what keeps the
        one-way flow intact — position manager feeds the plans, the plans feed
        the strategies.
        ⚠️ A THIN VIEW OF `logging_state()` SINCE r42, deliberately: when the
        list and the reasons came from two separate walks of the table they
        could disagree about the same tick. There is one walk now and this is
        a filter over its result, so "eligible" and "why not" are two readings
        of one object rather than two computations.
        """
        return [n for n, (ok, _g, _w) in self.logging_state(now_et, **kw).items() if ok]

    def why_not(self, strategy: str, now_et: tuple, **kw):
        """The Verdict for ONE strategy — the named gate that refused it.

        For the journal and the operator, so a row can say WHICH gate rather
        than "blocked". Same inputs as `eligible_now`, one strategy."""
        kw.setdefault("open_by_strategy", self.open_by_strategy())
        return decide(Facts(strategy=strategy, now_et=now_et, **kw))

    def has_blocking_position(self) -> bool:
        """Does an open position BLOCK a new entry? A butterfly never does.

        🔑 r197 — THE RECIPROCAL OF r161, WHICH WAS ONLY EVER BUILT ONE WAY.
        r161 exempted the butterfly from the single-position rule ON ENTRY
        (operator: *"I want it to be able to fire regardless if any other open
        trades are found"*, TRADES.md §3: *"no position slot, no capital, no
        competition"*). But `has_open_position()` still counted it, so a
        butterfly took no slot going IN and occupied one once it was THERE.

        ⚠️ MEASURED COST, 2026-08-31, the first live-fleet session: three
        boxes — MU, NFLX, TSLA — held 09:45 butterflies and every one sat in
        the second-leg-only branch when the credit windows opened at 11:30.
        `CondorManagement=HOLD(no credit verticals open)` on all three, so
        nothing credit-side was open to justify it. One rare opportunistic
        trade removed three boxes from the credit side for the whole session.

        ⚠️ WHAT THIS DOES **NOT** CHANGE, and the operator was explicit: credit
        entries stay blocked while an ORB or runaway DEBIT is open. That block
        is correct and untouched. The only thing that stops counting is the
        butterfly. A box may hold a butterfly PLUS one other thing — never a
        butterfly plus a directional debit plus a credit leg.
        """
        # ⚠️ HYDRATE FIRST. On a fresh process `_open_records` is empty until
        # something reloads it, so asking this before `has_open_position()`
        # would answer "nothing blocks" on a box that restarted holding an ORB
        # position — and let a credit trade open against it.
        self.has_open_position()
        return any(not (self._is_butterfly(r) or self._is_liquidity_hunt(r))
                   for r in self._open_records)

    def has_open_position(self) -> bool:
        if self._open_records:
            return True
        # Fresh process (restart): reload any open trades from the DB.
        trades = self._trade_logger.get_open_trades()
        if trades:
            self._open_records = trades
            return True
        return False

    def set_open_position(self, record: TradeRecord):
        """Single-position strategies (ORB, sweep, butterfly): exactly one."""
        self._open_records = [record]

    def set_open_positions(self, records: List[TradeRecord]):
        """Resume managing a recovered SET of open positions (one for normal
        strategies, two for a legged condor). Replaces the active set wholesale.
        Used by startup recovery so the first tick manages exactly the rows that
        survived stale-orphan reconciliation — without dropping a condor leg."""
        self._open_records = list(records)

    def flatten_all(self, reason: str, chain=None) -> List[str]:
        """Force-close EVERY open record through the full exit accounting.

        Unlike a bare exit_engine.place_exit_order() (which submits/simulates an
        order but never marks the DB row closed), this routes each record through
        _execute_exit() so status='closed', P&L, the exit alert, trail cleanup
        and ORB re-arm all happen — the row is genuinely, durably closed. Closes
        ALL records (both condor legs), not just the first. If a live mark can't
        be fetched, books at entry premium as a last resort so the row still
        closes rather than surviving as an orphan (P&L approximate — logged).

        Returns the list of trade_ids that FAILED to close (empty == fully flat),
        so the 15:45 caller can retry each tick and escalate.
        """
        if not self._open_records:
            self._open_records = self._trade_logger.get_open_trades()

        failed: List[str] = []
        held: List[str] = []
        for record in list(self._open_records):
            trade_id = record.get("trade_id", "")
            # 🔴 r99 — CREDIT VERTICALS HOLD TO VERTICAL_HOLD_TO_ET (15:45).
            # This loop ran from 15:40 (FLATTEN_WINDOW_OPEN) over EVERY record,
            # so the operator's 2026-08-13 ruling — "5 more minutes of
            # exponentially rising profit curve" — was documented in config
            # and enforced nowhere on this path. A held vertical is still
            # MANAGED in that window (main.py runs a manage pass); it is not
            # flattened. Fail direction: a bad clock read -> flatten (the
            # pre-r99 behaviour), never an overnight orphan.
            if _is_credit_vertical(record) and not _vertical_close_due():
                held.append(trade_id)
                continue
            premium = self._fetch_current_premium(record, chain=chain)
            if premium is None:
                premium = float(record.get("entry_premium", 0.0) or 0.0)
                logger.warning(
                    f"Flatten {trade_id[:8]}: no live mark — booking at entry "
                    f"premium (P&L approximate) so the row still closes."
                )
            decision = ExitDecision(should_exit=True, exit_reason=reason)
            if self._execute_exit(record, decision, premium):
                self._open_records = [r for r in self._open_records
                                      if r.get("trade_id") != trade_id]
            else:
                failed.append(trade_id)
                logger.error(f"Flatten FAILED for {trade_id[:8]} — will retry")
        if held:
            logger.info("Flatten: %d credit vertical(s) HELD to 15:45 per "
                        "VERTICAL_HOLD_TO_ET (%s)", len(held),
                        ",".join(t[:8] for t in held))
        return failed

    def add_condor_leg(self, record: TradeRecord):
        """A condor vertical: appends rather than replacing."""
        self._open_records.append(record)

    def add_open_position(self, record: TradeRecord):
        """r161 — the GEX pin butterfly is exempt from the single-position rule
        (operator, 2026-08-27: *"I want it to be able to fire regardless if
        any other open trades are found … If it can achieve all that, it's
        earned an entry."* TRADES.md §3: *"no position slot, no capital, no
        competition."*). Appends; NEVER replaces — `set_open_position` would
        silently drop the vertical already under management."""
        tid = record.get("trade_id") if hasattr(record, "get") else None
        if tid and any(r.get("trade_id") == tid for r in self._open_records):
            return
        self._open_records.append(record)

    def get_open_record(self) -> Optional[TradeRecord]:
        return self._open_records[0] if self._open_records else None

    def get_open_records(self) -> List[TradeRecord]:
        return list(self._open_records)

    def remove_record(self, trade_id: str):
        """Drop a record from active management (used by the broken-wing roll
        when it closes the old untested vertical)."""
        self._open_records = [r for r in self._open_records
                              if r.get("trade_id") != trade_id]

    def manage_open_position(self,
                              df_1m: Optional[pd.DataFrame] = None,
                              chain=None,
                              df_5m: Optional[pd.DataFrame] = None,
                              vol_state=None, trend=None) -> bool:
        """Manage every open position this tick. Normally one; for a legged
        condor there can be two verticals open at once, each managed
        independently (a tested side exits on its own; the untested side
        stays)."""
        if not self._open_records:
            self._open_records = self._trade_logger.get_open_trades()
            if not self._open_records:
                return False

        still_open: List[TradeRecord] = []
        for record in list(self._open_records):
            if self._manage_one(record, df_1m, chain, df_5m, vol_state, trend):
                still_open.append(record)
        self._open_records = still_open
        return len(self._open_records) > 0

    def _manage_one(self, record: TradeRecord,
                    df_1m: Optional[pd.DataFrame],
                    chain,
                    df_5m: Optional[pd.DataFrame] = None,
                    vol_state=None, trend=None) -> bool:
        """Manage one record. Returns True if it should remain open."""
        trade_id = record["trade_id"]

        current_premium = self._fetch_current_premium(record, chain)
        if current_premium is None:
            logger.warning(
                f"Could not fetch premium for {trade_id[:8]} — skipping tick"
            )
            return True

        self._trade_logger.update_current_premium(trade_id, current_premium)
        # r166 — the management plan reads the record, not the DB
        record["current_premium"] = current_premium

        exit_eng = get_exit_engine(self.paper_trading)
        # ── r167 — THE MANAGEMENT PLAN DECIDES FIRST for the records it covers
        # (runaway, butterfly, a lone sweep/TCS vertical). It asserts the
        # declared spec conditions itself (15% floor / hard stop, the breach
        # stops, target, nickel) and reaches the engine's calculators (50%
        # trail, tightening after 100%, theta bleed, velocity stall) through
        # evaluate(); its intent is executed below by the SAME _execute_exit.
        # ORB, ADOPTED, tents and formed condors: the engine decides as ever.
        decision = None
        try:
            from strategy.management import get_management_plan
            _intent = get_management_plan().decide(
                record, current_premium, df_1m=df_1m, open_records=self._open_records,
                current_price=record.get("current_price"),
                ctx={"df_5m": df_5m, "vol": vol_state, "trend": trend,
                     "derived_engines": getattr(self, "_derived_engines", None) or []},
                exit_engine=exit_eng)
            if _intent is not None:
                decision = _intent.to_exit_decision()
        except Exception as _mp_err:                            # noqa: BLE001
            logger.warning(f"management plan decide() failed for {trade_id[:8]}: "
                           f"{_mp_err} — the exit engine decides")
            decision = None
        if decision is None:
            decision = exit_eng.evaluate(record, current_premium, df_1m=df_1m, df_5m=df_5m,
                                         vol_state=vol_state, trend=trend)

        if decision.new_trail_stop is not None:
            # v3.1: trail persists in its OWN column. stop_premium is the
            # immutable -25% floor — overwriting it with the trail made the
            # exit engine's floor checks fire at the trail level and mislabel
            # every trail exit as a hard stop (F5).
            self._trade_logger.update_trail_stop(trade_id, decision.new_trail_stop)
            record["trail_stop"] = decision.new_trail_stop

        if decision.should_exit:
            closed = self._execute_exit(record, decision, current_premium)
            return not closed   # drop if closed; keep (retry) if the order failed

        logger.debug(
            f"Position [{trade_id[:8]}]: "
            f"premium=${current_premium:.2f} "
            f"pnl={decision.current_pnl_pct:.1%} "
            f"(${decision.current_pnl_usd:+.2f})"
        )
        return True

    def _fetch_current_premium(self, record: TradeRecord,
                                chain=None) -> Optional[float]:
        """
        Fetch current mark price for the option(s).
        Uses chain if available — even in paper mode for accurate P&L display.
        Butterfly mark = lower + upper - 2×center.
        Falls back to entry premium in paper mode if chain unavailable.
        
        AUDIT F9 (2026-08-20): the filters were `mark > 0` — NaN was
        excluded (NaN > 0 is False) but 1e12 sailed through, and a
        finite-absurd mark CLOSES a live position on a phantom print
        (stop or target, either way a booked exit nobody chose). The
        excursion tracker already rejects > 1e6; the DECISION path now
        applies the same ceiling. Fail direction: None → tick skipped →
        no decision on garbage.
        """
        is_butterfly = bool(record.get("is_butterfly", False))

        if chain is not None:
            try:
                side           = record.get("option_side", "call")
                contracts_list = chain.calls if side == "call" else chain.puts

                # v3.2 (AUDIT F6): structure-derived, matching exit_engine
                # v4.21's dispatch — pricing and routing must never disagree
                # about what a record IS.
                # ── r106 — THE TENT PRICES ACROSS TWO CHAINS ────────────────
                # short + same-type wing + an OPPOSITE-type hedge, so the hedge
                # is not in `contracts_list` at all. Value = what it costs to
                # close: buy back the short, sell both longs.
                if _is_tent(record):
                    _sc = next((c for c in contracts_list
                                if c.strike == record.get("short_strike", 0)
                                and 0 < c.mark < 1e6), None)
                    _lc = next((c for c in contracts_list
                                if c.strike == record.get("long_strike", 0)
                                and 0 < c.mark < 1e6), None)
                    _other = chain.puts if side == "call" else chain.calls
                    _hc = next((c for c in _other
                                if c.strike == record.get("lower_strike", 0)
                                and 0 < c.mark < 1e6), None)
                    if None not in (_sc, _lc, _hc):
                        _stash_quote(
                            record,
                            bid=max(0.0, (getattr(_sc, "bid", 0.0) or 0.0)
                                    - (getattr(_lc, "ask", 0.0) or 0.0)
                                    - (getattr(_hc, "ask", 0.0) or 0.0)),
                            ask=max(0.0, (getattr(_sc, "ask", 0.0) or 0.0)
                                    - (getattr(_lc, "bid", 0.0) or 0.0)
                                    - (getattr(_hc, "bid", 0.0) or 0.0)))
                        return _sc.mark - _lc.mark - _hc.mark
                    return None      # a leg we cannot see is not a price

                if _is_credit_vertical(record):
                    short_s = record.get("short_strike", 0)
                    long_s  = record.get("long_strike",  0)
                    _sc = next((c for c in contracts_list if c.strike == short_s and 0 < c.mark < 1e6), None)
                    _lc = next((c for c in contracts_list if c.strike == long_s  and 0 < c.mark < 1e6), None)
                    short_m = _sc.mark if _sc is not None else None
                    long_m  = _lc.mark if _lc is not None else None
                    if short_m is not None and long_m is not None:
                        # ── r105 — STASH THE STRUCTURE'S BID/ASK FOR THE EXIT
                        # LADDER. The exit path has only ever received a MARK,
                        # so it could post at mark and nothing else; a ladder
                        # needs a two-sided quote. CLOSING a short vertical is a
                        # BUY of the spread: we pay short.ask - long.bid at the
                        # touch and receive short.bid - long.ask at the far
                        # side. Built conservatively, per leg, never from the
                        # combined mark ± a guess (limit_ladder v1.1's lesson:
                        # "the shade was guesswork about a spread we cannot
                        # see" — now we can see it).
                        _stash_quote(
                            record,
                            bid=max(0.0, (getattr(_sc, "bid", 0.0) or 0.0)
                                    - (getattr(_lc, "ask", 0.0) or 0.0)),
                            ask=max(0.0, (getattr(_sc, "ask", 0.0) or 0.0)
                                    - (getattr(_lc, "bid", 0.0) or 0.0)))
                        return short_m - long_m   # current spread value (credit basis)
                elif is_butterfly:
                    lower_s  = record.get("lower_strike",  0)
                    center_s = record.get("center_strike", 0)
                    upper_s  = record.get("upper_strike",  0)
                    lower_m  = next((c.mark for c in contracts_list if c.strike == lower_s  and 0 < c.mark < 1e6), None)
                    center_m = next((c.mark for c in contracts_list if c.strike == center_s and 0 < c.mark < 1e6), None)
                    upper_m  = next((c.mark for c in contracts_list if c.strike == upper_s  and 0 < c.mark < 1e6), None)
                    if None not in (lower_m, center_m, upper_m):
                        return lower_m + upper_m - 2 * center_m
                else:
                    strike = record.get("strike", 0)
                    match  = next(
                        (c for c in contracts_list if c.strike == strike and 0 < c.mark < 1e6),
                        None
                    )
                    if match:
                        # r105 — the single-leg quote, for the exit ladder.
                        _stash_quote(record,
                                     bid=float(getattr(match, "bid", 0.0) or 0.0),
                                     ask=float(getattr(match, "ask", 0.0) or 0.0))
                        # stash live theta so the exit engine's theta-bleed
                        # detector can see it (single-leg longs only)
                        record["current_theta"] = float(getattr(match, "theta", 0.0) or 0.0)
                        # VEL.1 — the velocity stall check needs DELTA as well:
                        # breakeven velocity is |theta| / (|delta| * 1440), so
                        # theta alone cannot answer "is this position gaining or
                        # bleeding right now". Same stash, same guard.
                        record["current_delta"] = float(getattr(match, "delta", 0.0) or 0.0)
                        return match.mark
            except Exception:
                pass

        if self.paper_trading:
            # LAST-KNOWN MARK, not entry (v2.1). Falling back to entry premium
            # here fabricated a $0 P&L on ANY exit taken while the chain was
            # momentarily unavailable — a real -$818 loss was booked as breakeven
            # at the 15:45 hard close (CRM 2026-07-09, exit recorded == entry).
            # It also blinded the exit logic (a position that "looks like entry"
            # can't trip a stop/target/trail). Use the last live mark that was
            # stored via update_current_premium every good tick; only surrender to
            # entry if we have literally never priced it, and log it so it's never
            # silent.
            last_mark = record.get("current_premium") or 0.0
            if last_mark > 0:
                return last_mark
            logger.warning(
                f"{str(record.get('trade_id',''))[:8]}: no chain and no prior "
                f"mark — falling back to entry premium (P&L may be understated)"
            )
            return record.get("entry_premium", 0.0)

        client = get_client()
        try:
            if is_butterfly:
                lower_sym  = record.get("lower_symbol",  "")
                center_sym = record.get("center_symbol", "")
                upper_sym  = record.get("upper_symbol",  "")

                lower_mark  = self._get_option_mark(client, lower_sym)
                center_mark = self._get_option_mark(client, center_sym)
                upper_mark  = self._get_option_mark(client, upper_sym)

                if None in (lower_mark, center_mark, upper_mark):
                    return None
                return lower_mark + upper_mark - 2 * center_mark
            else:
                symbol = record.get("option_symbol", "")
                return self._get_option_mark(client, symbol)

        except Exception as e:
            logger.error(f"Premium fetch error: {e}")
            return None

    def _get_option_mark(self, client, symbol: str) -> Optional[float]:
        if not symbol:
            return None
        try:
            data  = client.get(f"/market-data/quotes/{symbol}")
            quote = data.get("data", {})
            bid   = float(quote.get("bid", 0) or 0)
            ask   = float(quote.get("ask", 0) or 0)
            if bid > 0 and ask > 0:
                return (bid + ask) / 2
            return float(quote.get("mark", 0) or quote.get("last", 0) or 0) or None
        except Exception:
            return None

    def _execute_exit(self, record: TradeRecord,
                       decision: ExitDecision,
                       current_premium: float) -> bool:
        """Place the exit and book P&L ONLY on a confirmed fill. Returns True if
        the position genuinely closed, False if not (caller retries).

        v3.4: booking is gated on FillResult.confirmed and uses the ACTUAL fill
        price, not the mark we passed in. In paper the simulated fill price
        equals the mark; in live it is the broker's real fill. An unconfirmed
        result books NOTHING and leaves the row open — the anti-orphan invariant.
        current_premium is the last-known mark, passed to the exit engine as the
        paper fill price / live context.
        """
        trade_id = record["trade_id"]

        exit_eng = get_exit_engine(self.paper_trading)
        fill     = exit_eng.place_exit_order(record, decision.exit_reason,
                                             mark_price=current_premium)

        if not fill.confirmed:
            logger.error(f"Exit NOT confirmed for {trade_id[:8]} "
                         f"({fill.detail or 'no fill'}) — position stays OPEN, will retry")
            return False

        fill_price = fill.fill_price
        if fill_price is None:
            # confirmed with no price should be impossible; refuse to book fiction.
            logger.error(f"Exit for {trade_id[:8]} confirmed but no fill_price — "
                         f"refusing to book; will retry")
            return False

        entry_prem    = record["entry_premium"]
        contracts     = record["contracts"]
        # Credit/short positions profit when the premium FALLS, so the P&L sign
        # is inverted vs a debit (long) trade. This covers condor legs AND an
        # adopted short leg (is_short_position) discovered at the broker.
        credit_signed = (bool(record.get("is_condor_leg"))
                         or record.get("strategy") == "IronCondorStrategy"
                         or bool(record.get("is_short_position")))
        if credit_signed:
            pnl_per_share = entry_prem - fill_price
        else:
            pnl_per_share = fill_price - entry_prem
        pnl_usd       = pnl_per_share * contracts * CONTRACT_MULTIPLIER

        # v4.0: carry the excursion through to the book. `_track_excursion`
        # fills these on the record every tick inside `exit_engine.evaluate`;
        # a parameter nothing passes is a column nothing fills, which is the
        # `open_interest` failure exactly - a declared field with no producer.
        _exc = {k: record.get(k) for k in
                ("mfe_premium", "mfe_bars", "mae_premium", "mae_bars")
                if record.get(k) is not None} if isinstance(record, dict) else None
        self._trade_logger.log_exit(
            trade_id    = trade_id,
            exit_price  = fill_price,
            pnl_usd     = pnl_usd,
            exit_reason = decision.exit_reason,
            excursion   = _exc or None,
        )

        risk_mgr = get_risk_manager()
        if pnl_usd >= 0:
            risk_mgr.record_win(pnl_usd)
        else:
            risk_mgr.record_loss(pnl_usd)

        get_alert_manager().send_exit_alert(
            trade_id      = trade_id,
            setup_type    = record.get("setup_type", ""),
            exit_premium  = fill_price,
            entry_premium = entry_prem,
            pnl_usd       = pnl_usd,
            contracts     = contracts,
            reason        = decision.exit_reason,
        )

        exit_eng.clear_trail(trade_id)

        # ── Re-arm ORB engine if this was an ORB trade ─────────────────────────
        # Allows the engine to watch for another breakout attempt this session
        # rather than treating one trade as the end of the ORB opportunity.
        if "ORB" in record.get("strategy", ""):
            # 🔴 r195 — THE REMAINDER DIES WITH THE TRADE, AND IT MUST GO FIRST.
            # A standing offer can be partly filled: 4 of 10 fill, the position
            # opens, and this exit closes it. The other 6 are STILL WORKING at
            # the broker. The supervisor's triggers (fully filled / past the
            # 50% TP / structure stop / EOD) do not cover an exit on
            # theta_bleed, the velocity stall, the trail or the 15:45 flatten
            # — so those 6 would keep standing with no position behind them
            # while the engine re-armed onto a new setup with different
            # geometry. Operator: a re-arm cancels any previous offer, because
            # a new impulsive candle has a different high and low and so a
            # different offer composition.
            # ⚠️ BEFORE the re-arm, not after: once the engine re-arms it has
            # forgotten this setup, and nothing left knows which offer belonged
            # to it.
            try:
                from execution import resting_orders as _ro
                _ro.cancel_all_working(
                    f"position closed: {decision.exit_reason}",
                    paper=self.paper_trading)
            except Exception as e:                              # noqa: BLE001
                logger.error("Could not cancel the standing offer remainder "
                             "(%s) — it may still fill and would then be an "
                             "UNMANAGED position", e)
            try:
                from analysis.orb_engine import get_orb_engine
                get_orb_engine().notify_position_closed()
            except Exception as e:
                logger.warning(f"Could not re-arm ORB engine: {e}")

        logger.info(
            f"✅ Position closed: {trade_id[:8]} "
            f"exit=${current_premium:.2f} "
            f"pnl=${pnl_usd:+.2f} "
            f"reason={decision.exit_reason}"
        )
        return True


# Singleton
_position_manager: Optional[PositionManager] = None


def get_position_manager(paper_trading: bool = PAPER_TRADING) -> PositionManager:
    global _position_manager
    if _position_manager is None:
        _position_manager = PositionManager(paper_trading)
    return _position_manager
