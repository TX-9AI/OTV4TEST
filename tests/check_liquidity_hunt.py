#!/usr/bin/env python3
"""
tests/check_liquidity_hunt.py  v1.0
v1.0  2026-09-10  OTV4TEST r12 — THE LIQUIDITY HUNT AND THE HANDOFF GRANT, ON
      HYPOTHETICALS (PLAN_SPEC §37). Real plan, real exit engine, real slot rule,
      a DerivedStore fixture for the levels.

  H1   bias = the nearer live level measured from the RANGE EDGE (above vs below)
  H2   A1: a close out on the bias side -> fires, target = the level, runway known
  H3   a far-side break -> "broke AWAY from the liquidity", not traded, recorded
  H4   A2: the far-side break CLOSES BACK INSIDE -> fires from the far boundary
  H5   one hunt per break key
  H6   exit: the target WICKED with the close short of it -> off, GRANT written
  H7   the target ACCEPTED (close beyond) -> no wick exit; hold (over-delivered)
  H8   thesis dead: a close back through the ENTRY boundary (A2: the far one), not the 50
  H9   slot: an open hunt is NOT blocking; an open ORB does not block a hunt entry
  H10  the grant: live -> consumed on fire / expired after TTL, both recorded

Born red at r11: every H (no module).
Run:  python3 tests/check_liquidity_hunt.py
"""
import os
import sqlite3
import sys
import tempfile
import time
import types

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)
FAILED = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILED.append(name)


def _frame(rows, start="09:40"):
    import pandas as pd
    return pd.DataFrame([{"open": o, "high": h, "low": l, "close": c} for o, h, l, c in rows],
                        index=pd.date_range(f"2026-09-10 {start}", periods=len(rows), freq="1min"))


class _G:
    def __init__(s, k, prem, delta, gamma):
        s.strike, s.mark, s.ask, s.bid = float(k), prem, prem + 0.02, prem - 0.02
        s.delta, s.gamma, s.theta, s.expiry, s.open_interest, s.symbol = delta, gamma, -0.04, "x", 100, f"O{k}"


def main():
    from strategy import plan as P
    class St:
        def __init__(s): s.conn = sqlite3.connect(":memory:"); s.conn.row_factory = sqlite3.Row
        def commit(s): s.conn.commit()
    st = St(); P.ensure_tables(st); P.bind_store(st)
    from data.derived_store import DerivedStore
    import strategy.liquidity_hunt as LH
    from execution import handoff as H
    ds = DerivedStore(path=os.path.join(tempfile.mkdtemp(), "derived.db"))
    LH._symbol_of = lambda: "TST"
    now = time.time()
    # range 100.00-101.00; PDH 102.50 (1.50 above the edge), london low 97.00 (3.00 below) -> bias LONG
    ds.upsert_level(("TST:prev_day:102.50", "TST", 102.5, "resistance", "prev_day", "day", now - 3600, 0, None, 0, None, None, 1))
    ds.upsert_level(("TST:london:97.00", "TST", 97.0, "support", "london", "session", now - 3600, 0, None, 0, None, None, 1))
    orb = types.SimpleNamespace(orb_high=101.0, orb_low=100.0)
    calls = [_G(101, 0.95, 0.46, 0.05), _G(102, 0.48, 0.30, 0.058), _G(103, 0.20, 0.17, 0.04), _G(104, 0.10, 0.08, 0.02)]
    chain = types.SimpleNamespace(calls=calls, puts=[])
    hunt = LH.LiquidityHunt(); hunt._store = ds; hunt.planner.symbol = "TST"
    LH.FINISHED.clear(); H.reset()

    def row():
        r = st.conn.execute("SELECT verdict, reason FROM plan_tick WHERE strategy='LiquidityHunt' ORDER BY rowid DESC LIMIT 1").fetchone()
        return (r["verdict"], r["reason"] or "") if r else ("", "")

    def tick(n, px, frame, hhmm="09:41"):
        P.begin_tick(n)
        sig = hunt.generate_signal(orb=orb, price_now=px, now_et=hhmm, atr_pct=0.14, chain=chain, df_1m=frame, atm_iv=0.25)
        P.close_tick(st, "TST")
        return sig, row()

    # H1 + inside the range: waiting
    sig, r = tick(1.0, 100.5, _frame([(100.4, 100.7, 100.3, 100.5), (100.5, 100.6, 100.4, 100.55)], "09:40"))
    check("H1 bias LONG: PDH 1.50 above the edge beats the london low 3.00 below; inside -> waiting on A1 or A2",
          sig is None and r[0] == "HOLD" and "bias LONG" in r[1] and "waiting on: A1" in r[1], r[1][:150])
    # H2 A1
    sig, r = tick(2.0, 101.3, _frame([(100.9, 101.4, 100.8, 101.3), (101.3, 101.5, 101.2, 101.4)], "09:42"))
    check("H2 A1: a close out ABOVE -> fires long, target PDH 102.50, runway known, entry boundary = the range high",
          sig is not None and sig.direction == "long" and sig.underlying_target == 102.5 and sig.underlying_stop == 101.0
          and sig.hunt_entry == "A1" and r[0] == "TAKE", f"sig={sig and (sig.direction, sig.underlying_target, sig.hunt_entry)} {r[0]}")
    # H5 one per break
    sig, r = tick(2.5, 101.4, _frame([(101.3, 101.5, 101.2, 101.4), (101.4, 101.6, 101.3, 101.5)], "09:43"))
    check("H5 the same break does not hunt twice", sig is None and "one per break" in r[1], r[1][-60:])
    # H3 far-side break (fresh hunt object, same store)
    hunt2 = LH.LiquidityHunt(); hunt2._store = ds; hunt2.planner.symbol = "TST"; LH.FINISHED.clear()
    def tick2(n, px, frame, hhmm="09:45"):
        P.begin_tick(n)
        sig = hunt2.generate_signal(orb=orb, price_now=px, now_et=hhmm, atr_pct=0.14, chain=chain, df_1m=frame, atm_iv=0.25)
        P.close_tick(st, "TST")
        return sig, row()
    sig, r = tick2(3.0, 99.7, _frame([(100.1, 100.2, 99.6, 99.7), (99.7, 99.9, 99.6, 99.8)], "09:45"))
    check("H3 a close out BELOW (away from the liquidity) -> not traded, named as a fake-out candidate",
          sig is None and r[0] == "HOLD" and "AWAY" in r[1], r[1][-120:])
    # H4 A2: the fake fails — a close back inside -> fire from the far boundary (100.00)
    sig, r = tick2(4.0, 100.2, _frame([(99.8, 100.3, 99.7, 100.2), (100.2, 100.4, 100.1, 100.3)], "09:47"))
    check("H4 A2: the fake fails (close back inside) -> fires long from the FAR boundary 100.00, target 102.50",
          sig is not None and sig.hunt_entry == "A2" and sig.underlying_stop == 100.0 and sig.underlying_target == 102.5
          and abs(sig.run_at_entry - 2.3) < 1e-6, f"sig={sig and (sig.hunt_entry, sig.underlying_stop, sig.run_at_entry)} {r[1][-80:]}")

    # exits
    import datetime as _dt
    from zoneinfo import ZoneInfo
    import execution.exit_engine as XE
    _rdt, _rhc = XE.datetime, XE.is_hard_close_time
    class _F(_dt.datetime):
        @classmethod
        def now(cls, tz=None): return _dt.datetime(2026, 9, 10, 10, 0, tzinfo=ZoneInfo("US/Eastern"))
    XE.datetime = _F; XE.is_hard_close_time = lambda: False
    try:
        xe = XE.ExitEngine(paper_trading=True)
        xe._theta_bleed = lambda *a, **k: False
        xe._rejected_handoff = lambda *a, **k: ""
        base = {"trade_id": "h1", "strategy": "LiquidityHunt", "setup_type": "liquidity_hunt_A2", "direction": "long",
                "option_side": "call", "entry_premium": 0.48, "contracts": 1, "status": "open", "stop_premium": 0.0,
                "target_premium": 0.0, "trail_activation": 0.0, "underlying_entry": 100.2, "underlying_stop": 100.0,
                "underlying_target": 102.5, "orb_range_high": 101.0, "orb_range_low": 100.0, "entry_time": "2026-09-10T09:47:00"}
        H.reset()
        d = xe._evaluate_orb(dict(base), 0.9, _frame([(102.1, 102.6, 102.0, 102.3), (102.3, 102.4, 102.2, 102.35)], "10:05"))
        g = H.live("SweepCreditSpread")
        check("H6 the target WICKED (high 102.6, close 102.3) -> off, and a grant to the sweep is live",
              d.should_exit and "hunt_target_wicked" in str(d.exit_reason) and g is not None and g["level"] == 102.5
              and g["side"] == "call", str(d.exit_reason)[:100])
        d = xe._evaluate_orb(dict(base), 1.2, _frame([(102.3, 102.9, 102.2, 102.8), (102.8, 103.0, 102.7, 102.9)], "10:07"))
        check("H7 the target ACCEPTED (close beyond) -> no wick exit; the runaway's hold logic keeps it",
              not (d.should_exit and "hunt_target_wicked" in str(d.exit_reason)), str(d.exit_reason))
        d = xe._evaluate_orb(dict(base), 0.4, _frame([(100.3, 100.4, 99.7, 99.8), (99.8, 99.9, 99.7, 99.85)], "10:09"))
        check("H8 thesis dead: a close back through the ENTRY boundary (100.0), inside-the-range prices do not trip the 50",
              d.should_exit and ("thesis_dead" in str(d.exit_reason) or "backstop" in str(d.exit_reason)), str(d.exit_reason)[:100])
        d = xe._evaluate_orb(dict(base, trade_id="h1-fresh"), 0.5, _frame([(100.4, 100.7, 100.3, 100.6), (100.6, 100.8, 100.5, 100.7)], "10:11"))   # a fresh id: the trail state is per trade
        check("H8b ...and a bar inside the range above the entry boundary holds", not d.should_exit, str(d.exit_reason))
    finally:
        XE.datetime, XE.is_hard_close_time = _rdt, _rhc
    # H9 the slot
    from execution.position_manager import PositionManager
    pm = PositionManager.__new__(PositionManager)
    pm._open_records = [{"strategy": "LiquidityHunt", "is_liquidity_hunt": 1, "status": "open"}]
    check("H9 an open hunt is not a blocking position", not pm.has_blocking_position())
    pm._open_records = [{"strategy": "ORBStrategy", "status": "open"}]
    check("H9b an open ORB still blocks the credit side (unchanged)", pm.has_blocking_position())
    # H10 the grant lifecycle
    H.reset(); g = H.grant("LiquidityHunt", "SweepCreditSpread", 102.5, "call", ttl=2)
    check("H10 a fresh grant is live", H.live("SweepCreditSpread") is g)
    H.tick(); H.tick(); H.tick()
    check("H10b ...expires after its TTL, recorded, no longer live", g["expired"] and H.live("SweepCreditSpread") is None)
    H.reset(); g2 = H.grant("LiquidityHunt", "SweepCreditSpread", 102.5, "call", ttl=8); H.tick(); H.consume(g2)
    check("H10c ...or is consumed on the sweep's fire, with the tick it fired on", g2["fired"] and g2.get("fired_tick") == 1)
    print()
    if FAILED:
        print(f"FAIL — {len(FAILED)} check(s): {FAILED}"); return 1
    print("PASS — check_liquidity_hunt"); return 0


if __name__ == "__main__":
    sys.exit(main())
