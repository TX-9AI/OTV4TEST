"""
strategy/orcs.py  v1.0
v1.0  2026-10-03  OTV4TEST r204 (PREM.2) — THE OPENING RANGE CREDIT SPREAD (ORCS), THE STRATEGY (PLAN_SPEC §41).
      The operator, 2026-10-03: "I want to paper trade it Monday... Call this new one the opening range
      credit spread ORCS." And: "we get better than mark or we don't trade it."

      CONFIRMATORY, like every strategy here: strategy/orcs_plan.py locates the strikes, freezes an
      offer one cent better than the mark and watches it; this class turns each offer that FILLED ON
      THIS TICK into one credit-vertical signal priced AT THE LIMIT. It selects nothing itself.
      One spread per side per session: a side with an open ORCS leg, or a session that has already
      entered two, signals nothing (read from trades.db, fails closed).
      EXITS: none of its own. The leg is held to the scheduled end-of-day close (exit_engine);
      no premium stop, no stop at the short strike - both were measured and both made it worse.
      OFF unless config.ORCS_ENABLED (OT_ORCS=0 parks the trade; the plan still records).
"""
from __future__ import annotations

import logging

import config
from strategy import orcs_plan as _op

logger = logging.getLogger(__name__)

GATES = {}
NAME = _op.NAME


class OpeningRangeCreditSpread:
    name = NAME

    def __init__(self):
        self.plan = _op.ORCSPlan()
        self.planner = self.plan.planner
        self.PLAN_CHECKS = self.plan.PLAN_CHECKS

    def _side_used(self, side: str) -> bool:
        """True when this side may not be entered: an open ORCS leg on it, or two entered today."""
        try:
            from database.trade_logger import get_trade_logger
            tl = get_trade_logger()
            if tl.count_today(NAME) >= 2:
                return True
            return any(str(r.get("strategy") or "") == NAME and str(r.get("option_side") or "") == side
                       for r in tl.get_open_trades())
        except Exception as exc:                                # noqa: BLE001
            logger.warning("[orcs] side check failed CLOSED for %s: %s", side, exc)
            return True

    def generate_signals(self, *, price_now, now_et, chain=None, gap=None, informers=None,
                         today: str = "", now_epoch: float = 0.0) -> list:
        """Zero, one or two condor-leg-shaped signals: one per offer that filled on this tick."""
        prep = self.plan.prepare(price_now=price_now, now_et=now_et, chain=chain, gap=gap,
                                 informers=informers, today=today, now_epoch=now_epoch)
        out = []
        if not prep.fills:
            return out
        if not config.ORCS_ENABLED:
            logger.info("[orcs] %d offer(s) filled at the mark - the trade is OFF (OT_ORCS=0), recorded only",
                        len(prep.fills))
            return out
        for side, short_k, long_k, limit in prep.fills:
            if self._side_used(side):
                logger.info("[orcs] %s offer filled but the side is already used this session - no trade", side)
                continue
            short, long_c = _op.contracts_for(chain, side, short_k, long_k)
            if short is None or long_c is None:
                logger.warning("[orcs] %s offer filled but %g/%g is not on the chain now - no trade",
                               side, short_k, long_k)
                continue
            out.append(self._build_signal(side, short, long_c, float(limit), float(price_now or 0.0)))
        return out

    def _build_signal(self, side, short, long_c, credit, price_now):
        from strategy.base_strategy import OptionsSignal
        sig = OptionsSignal(strategy_name=NAME, setup_type=f"orcs_{side}", direction="neutral",
                            option_side=side, underlying_entry=price_now, underlying_stop=0.0)
        sig.is_credit_vertical = True
        sig.is_orcs = True
        sig.net_credit = credit              # THE LIMIT: one cent better than the mark, by ruling
        sig.entry_premium = credit
        if side == "call":
            sig.short_call_contract, sig.long_call_contract = short, long_c
        else:
            sig.short_put_contract, sig.long_put_contract = short, long_c
        sig.contract = short
        sig.conviction = 1.0
        sig.condor_trigger_source = "orcs"
        logger.info("[orcs] %s spread: short %g / long %g at %.2f (the limit) - held to the close, no stop",
                    side, float(short.strike), float(long_c.strike), credit)
        return sig
