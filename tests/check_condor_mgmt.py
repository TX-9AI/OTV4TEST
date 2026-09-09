#!/usr/bin/env python3
"""
tests/check_condor_mgmt.py  v1.0
v1.0  2026-09-09  OTV4TEST r10 — THE CONDOR MANAGEMENT PLAN (PLAN_SPEC §35).

  C1  tested by WICK: the closed bar's high reaches the short call, close inside -> call tested
  C2  a close BEYOND the short is not "tested" (it is the tent's breach) -> None from classify
  C3  no wick to either short -> None (the proximity rule does not fire when a frame is given)
  C4  no frame -> the proximity fallback still works
  C5  a lone call vertical's management row names the complement it waits on (a sweep below)
  C6  IronCondorStrategy is not an entry: main.py's dispatch skips it with the reason
  C7  the final-form (tent) floor is 15% from the structure AS FORMED, not cumulative credit

Born red at r9 on C2 (proximity said "tested") and C5 (no complement named).
Run:  python3 tests/check_condor_mgmt.py
"""
import os
import sqlite3
import sys
import types

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)
FAILED = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILED.append(name)


def _frame(rows, start="13:00"):
    import pandas as pd
    return pd.DataFrame([{"open": o, "high": h, "low": l, "close": c} for o, h, l, c in rows],
                        index=pd.date_range(f"2026-09-09 {start}", periods=len(rows), freq="1min"))


def main():
    from strategy.condor_roll import classify_tested
    legs = [{"option_side": "call", "short_strike": 720.0, "long_strike": 722.0},
            {"option_side": "put", "short_strike": 712.0, "long_strike": 710.0}]
    t, u = classify_tested(legs, 716.0, df_1m=_frame([(719.4, 720.3, 719.2, 719.8), (719.8, 720.0, 719.6, 719.9)]))
    check("C1 wick to the short call, close inside -> call TESTED", t is legs[0] and u is legs[1])
    t, u = classify_tested(legs, 720.6, df_1m=_frame([(719.4, 720.9, 719.2, 720.6), (720.6, 720.8, 720.4, 720.7)]))
    check("C2 a CLOSE beyond the short is breached, not tested -> None", t is None)
    t, u = classify_tested(legs, 719.5, df_1m=_frame([(719.0, 719.6, 718.8, 719.5), (719.5, 719.7, 719.3, 719.6)]))
    check("C3 price near but no wick to the short -> None (no proximity with a frame)", t is None)
    t, u = classify_tested(legs, 719.5)
    check("C4 no frame -> the proximity fallback still says call tested", t is legs[0])

    # C5: the lone-vertical row names the complement from the sweep plan's last preparation
    from strategy import plan as P
    class St:
        def __init__(s): s.conn = sqlite3.connect(":memory:"); s.conn.row_factory = sqlite3.Row
        def commit(s): s.conn.commit()
    st = St(); P.ensure_tables(st); P.bind_store(st)
    import strategy.sweep_plan as sp
    class _C:
        def __init__(s, k, m): s.strike, s.mark = float(k), m
    cand = sp.Candidate({"level_id": "x", "price": 713.5, "kind": "support", "provenance": "london"})
    cand.short, cand.long, cand.credit, cand.width, cand.r, cand.richness = _C(713, 0.4), _C(712, 0.21), 0.19, 1.0, 0.23, 0.19
    fake = types.SimpleNamespace(nearest_below=cand, nearest_above=None)
    sp.LAST_PREP = fake
    from strategy.iron_condor_strategy import IronCondorStrategy
    IC = IronCondorStrategy()
    class _PM:
        def get_open_records(self):
            return [{"option_side": "call", "short_strike": 720.0, "long_strike": 722.0,
                     "is_credit_vertical": 1, "status": "open", "trade_id": "c1", "strategy": "SweepCreditSpread"}]
    P.begin_tick(1.0)
    out = IC.manage(_PM(), None, 716.0)
    P.close_tick(st, "TST")
    r = st.conn.execute("SELECT verdict, reason FROM plan_tick WHERE strategy='CondorManagement' ORDER BY rowid DESC LIMIT 1").fetchone()
    check("C5 a lone call vertical's row names the complement: a sweep REJECTED below, with the structure",
          out == "LONE" and r and r["verdict"] == "HOLD" and "sweep REJECTED below" in r["reason"]
          and "713/712P" in r["reason"], str(dict(r) if r else None)[:160])

    msrc = open(os.path.join(_root, "main.py"), encoding="utf-8").read()
    check("C6 IronCondorStrategy is retired as an entry (dispatch names the reason)",
          "retired as a" in msrc and 'slot claimed by {signal.strategy_name}")\n    elif DIRECTIONAL_ONLY:\n        _plan_skip("IronCondorStrategy"' not in msrc)

    # C7 — the final-form floor is measured from the structure AS FORMED, not cumulative credit
    import datetime as _dt
    from zoneinfo import ZoneInfo
    import execution.exit_engine as XE
    _rdt, _rhc = XE.datetime, XE.is_hard_close_time
    class _F(_dt.datetime):
        @classmethod
        def now(cls, tz=None): return _dt.datetime(2026, 9, 9, 14, 0, tzinfo=ZoneInfo("US/Eastern"))
    XE.datetime = _F; XE.is_hard_close_time = lambda: False
    try:
        xe = XE.ExitEngine(paper_trading=True)
        rec = {"trade_id": "t1", "strategy": "IronCondorStrategy", "setup_type": "tent", "is_tent": 1,
               "option_side": "put", "entry_premium": 1.00, "final_form_basis": 1.00, "cumulative_credit": 3.40,
               "contracts": 1, "status": "open", "stop_premium": 1.15}
        d_hold = xe._evaluate_tent(dict(rec), 1.10)
        d_exit = xe._evaluate_tent(dict(rec), 1.16)
        check("C7 the tent floor is 15% from the structure AS FORMED (basis 1.00 -> 1.15), not 15% of cumulative 3.40",
              (not d_hold.should_exit) and d_exit.should_exit and "as formed" in str(d_exit.exit_reason),
              str(d_exit.exit_reason))
        csrc = open(os.path.join(_root, "strategy", "condor_roll.py"), encoding="utf-8").read()
        check("C7b the tent record's floor basis is the as-formed cost, cumulative credit kept alongside",
              "entry_premium=form_basis" in csrc and "cumulative_credit=cum" in csrc)
    finally:
        XE.datetime, XE.is_hard_close_time = _rdt, _rhc

    print()
    if FAILED:
        print(f"FAIL — {len(FAILED)} check(s): {FAILED}"); return 1
    print("PASS — check_condor_mgmt"); return 0


if __name__ == "__main__":
    sys.exit(main())
