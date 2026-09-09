#!/usr/bin/env python3
"""
tests/check_sweep_plan.py  v1.0
v1.0  2026-09-09  OTV4TEST r5 — THE SWEEP VERTICAL'S EXITS, ON HYPOTHETICALS
      (PLAN_SPEC §31.4), through the REAL `ExitEngine._evaluate_condor_leg`.
      The entry side (levels from the store, the REJECTED trigger, the anchor
      on the level, freshness, depth, spent) is pinned in check_plan_prepares
      S1–S9 and T4–T7.

  E1   two closed 1m bars beyond the pool -> sweep_breach_accepted (the level is spent)
  E2   one close beyond, then back -> HOLD (a wick is a test, one close is not acceptance)
  E3   the 15%-of-risk stop fires BEFORE the breach read when the premium says so first
       (operator: "2 minutes into a dead thesis could rack up some serious losses")
  E4   the nickel close at 0.05
  E5   a TCS vertical is untouched by the sweep's breach rule (setup_type routes it)
  X1   trade_logger marks the level SPENT only on the breach exit, not on a stop-out

Born red at r4: E1 (no breach exit), X1 (spent on any stop-out).
Run:  python3 tests/check_sweep_plan.py
"""
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

FAILED = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILED.append(name)


def _frame(closes, start="10:40"):
    import pandas as pd
    return pd.DataFrame([{"open": c, "high": c + 0.1, "low": c - 0.1, "close": c} for c in closes],
                        index=pd.date_range(f"2026-09-09 {start}", periods=len(closes), freq="1min"))


def main():
    import datetime as _dt
    from zoneinfo import ZoneInfo
    import execution.exit_engine as XE
    ET = ZoneInfo("US/Eastern")
    _real_dt, _real_hc = XE.datetime, XE.is_hard_close_time

    class _Frozen(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return _dt.datetime(2026, 9, 9, 10, 45, tzinfo=ET)
    XE.datetime = _Frozen
    XE.is_hard_close_time = lambda: False
    try:
        xe = XE.ExitEngine(paper_trading=True)
        xe._condor_sibling_open = lambda *a, **k: False
        xe._sync_stop_suppression = lambda *a, **k: None
        # a put credit spread sold against a floor at 96.00: 95/92.5, credit 1.30, width 2.5
        base = {"trade_id": "sw-1", "strategy": "SweepCreditSpread", "setup_type": "sweep_credit_spread",
                "direction": "long", "option_side": "put", "entry_premium": 1.30, "contracts": 1,
                "status": "open", "stop_premium": 1.48, "target_premium": 0.0, "trail_activation": 0.0,
                "underlying_entry": 96.6, "underlying_stop": 0.0, "pool_price": 96.0, "spread_width": 2.5,
                "is_credit_vertical": 1, "entry_time": "2026-09-09T10:32:00"}
        # E1: two closes below 96 -> breach accepted (premium still under the stop)
        d = xe._evaluate_condor_leg(dict(base), 1.40, df_1m=_frame([96.4, 95.9, 95.8, 95.85]))
        check("E1 two closes beyond the pool -> sweep_breach_accepted",
              d.should_exit and "sweep_breach_accepted" in str(d.exit_reason), str(d.exit_reason))
        # E2: one close beyond, the next back inside -> hold
        d = xe._evaluate_condor_leg(dict(base), 1.40, df_1m=_frame([96.4, 95.9, 96.2, 96.3]))
        check("E2 one close beyond, then back -> HOLD (one close is not acceptance)",
              not d.should_exit, str(d.exit_reason))
        # E3: premium through the 15%-of-risk stop first — the floor answers before the breach read
        # risk = width - credit = 1.20; stop = 1.30 + 0.15*1.20 = 1.48
        d = xe._evaluate_condor_leg(dict(base), 1.50, df_1m=_frame([96.4, 95.9, 95.8, 95.85]))
        check("E3 the 15%-of-risk stop precedes the breach read (both true; the stop names it)",
              d.should_exit and "condor_stop" in str(d.exit_reason), str(d.exit_reason))
        # E4: the nickel close
        d = xe._evaluate_condor_leg(dict(base), 0.05, df_1m=_frame([96.4, 96.5, 96.6, 96.7]))
        check("E4 spread worth 0.05 -> nickel_close", d.should_exit and "nickel_close" in str(d.exit_reason),
              str(d.exit_reason))
        # E5: a TCS vertical does not read the sweep's breach rule
        tcs = dict(base, trade_id="tc-1", strategy="TrendCreditSpread", setup_type="trend_credit_spread",
                   underlying_stop=0.0)
        d = xe._evaluate_condor_leg(tcs, 1.40, df_1m=_frame([96.4, 95.9, 95.8, 95.85]))
        check("E5 a TCS vertical is not exited by the sweep's breach rule",
              not (d.should_exit and "sweep_breach" in str(d.exit_reason)), str(d.exit_reason))
    finally:
        XE.datetime, XE.is_hard_close_time = _real_dt, _real_hc

    # X1: spent only on the breach exit (source pin on the hook, plus the rule)
    src = open(os.path.join(_root, "database", "trade_logger.py"), encoding="utf-8").read()
    check("X1 trade_logger marks SPENT only on sweep_breach_accepted",
          '"sweep_breach_accepted" in str(exit_reason' in src and "stopped out" not in
          src.split('"sweep_breach_accepted"')[1][:400])

    print()
    if FAILED:
        print(f"FAIL — {len(FAILED)} check(s): {FAILED}")
        return 1
    print("PASS — check_sweep_plan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
