"""
strategy/volt_strategy.py  v1.0
v1.0  2026-09-20  OTV4TEST r72 — VOLT, THE CONTROL ARM'S SPEC.

THE SPEC IS FOUR BARS AND A FIRE. Everything that searches, selects or sizes
lives in `strategy/volt_plan.py` (PLAN_SPEC §10). This module declares what
must be true when price arrives and builds the signal — no chain, no strike
arithmetic, no thresholds of its own.

🔑 WHAT MAKES IT A CONTROL — read this before adding anything.
Its whole value is the SHORTNESS of the gate list. The moment VOLT acquires a
third gate it stops answering the question it was built for, which is whether
the gated strategies' gates are worth their cost. If a condition looks like it
belongs here, it belongs in a NEW strategy, not in this one.

⚠️ NO CONVICTION, NO CONFLUENCE SCORING, NO GRADE. `conviction` has no reader
in the decision path (pinned by tests/check_conviction_removed.py) and a
`setup_grade` is exactly the kind of thing whose absence is being measured.

NOTHING HERE IS AN EDGE CLAIM. VOLT is expected to be roughly break-even at
best — the direction read measured 68.8% against a 66.7% breakeven on a
0.5:1.0 geometry, and that margin is inside the noise a 12-cell search
produces. It is a YARDSTICK, and a yardstick that quietly acquired an edge
would be a broken yardstick.
"""
from __future__ import annotations

import logging
from typing import Optional

import config
from strategy.base_strategy import BaseOptionsStrategy, OptionsSignal
from strategy.volt_plan import VoltPlan, VOL_MULT

logger = logging.getLogger(__name__)

# ── EVERY GATE, NAMED AND CATEGORISED (WA §36) ──────────────────────────────
# The spec adds NO selection of its own — it re-checks that what the plan
# prepared is still executable. That emptiness of SELECTION is the point.
GATES = {
    "MAX_LOSS_PCT": "FOUNDATIONAL",   # the catastrophic cap; universal, never VOLT's
}

MAX_LOSS_PCT = float(getattr(config, "MAX_LOSS_PCT", 0.25))


class VoltStrategy(BaseOptionsStrategy):
    """VOLT — two gates: direction, and rising volume. Nothing else."""

    def __init__(self):
        super().__init__()
        self.plan = VoltPlan()

    @property
    def name(self) -> str:
        return "VOLT"

    # ══════════════════════════════════════════════════════════════════════
    def generate_signal(self, *, chain=None, price_now=None, df_1m=None,
                        now_et: str = "", vol_state=None, macro=None,
                        already_open: bool = False,
                        symbol: str = "") -> Optional[OptionsSignal]:
        """Ask the plan, then check the declared bars. Returns a signal or None."""
        if price_now is None or chain is None:
            return None

        prep = self.plan.prepare(chain=chain, price_now=float(price_now),
                                 df_1m=df_1m, now_hhmm=now_et,
                                 already_open=already_open)

        # ── THE BARS. All four must be true; the plan already wrote the row.
        #    1 the plan reached a prepared state (window + both gates passed)
        #    2 a contract was selected and quoted
        #    3 the structure stop is a real distance from price
        #    4 the budget buys at least one contract
        if not prep.ready:
            return None
        if prep.contract is None or not prep.premium or prep.premium <= 0:
            return None
        if not prep.risk_px or prep.risk_px <= 0:
            return None
        if prep.size_provisional < 1:
            return None

        contract = prep.contract
        # 🔑 THE TARGET IS THE STOP DISTANCE MIRRORED. No fitted multiple, and
        # deliberately the same convention `PlanTick.debit_directional` uses
        # when no target is passed — the structure sets both ends.
        target = (float(price_now) + prep.risk_px if prep.direction == "long"
                  else float(price_now) - prep.risk_px)

        signal = OptionsSignal(
            strategy_name     = self.name,
            setup_type        = f"VOLT {prep.direction.title()}",
            direction         = prep.direction,
            option_side       = prep.side,
            underlying_entry  = float(price_now),
            underlying_stop   = prep.stop,
            underlying_target = target,
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
        # ⚠️ underlying_stop_is_thesis — the STRUCTURE is the thesis. If price
        # closes through it the reason for the trade is gone, which is a
        # different statement from "the premium fell 25%", and the exit engine
        # reads this flag to tell them apart.
        signal.underlying_stop_is_thesis = True

        # notes describe; none of them authorises
        self._add_confluence(signal,
                             f"VOLT: {prep.direction} (close {prep.price:.2f} vs "
                             f"session open {prep.session_open:.2f})")
        self._add_confluence(signal,
                             f"volume {prep.vol_ratio:.2f}x baseline "
                             f"(>= {VOL_MULT:g}x declared prior)")
        logger.info("STRATEGY: VOLT %s %s @ %.2f  stop %.2f (R %.2f)  vol %.2fx  size %d",
                    prep.direction, prep.side, price_now, prep.stop,
                    prep.risk_px, prep.vol_ratio, prep.size_provisional)
        return signal
