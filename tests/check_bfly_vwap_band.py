#!/usr/bin/env python3
"""tests/check_bfly_vwap_band.py  v1.0
A PIN AT TODAY'S VWAP MEETS THE BUTTERFLY'S CONCENTRATION CONDITION (BFLY.5).

v1.0  2026-09-13  OTV4TEST r25. Operator: "VWAP replaces the floor if the pin is
      w/in a predefined portion of VWAP" — "W/in 20% of the expected move,
      expressed as 10% above, 10% below." The VWAP is the bot's own
      midnight-ET-anchored one (indicator_series 'primary'), read through
      `anchors.vwap_now()`, which refuses a prior session's anchor or a stale bar.

🔑 HOP 0 (WORKING_AGREEMENT §21): every case DRIVES the real
`GEXPinButterflyStrategy.generate_signal` against a real DerivedStore in a temp
file holding real indicator_series rows, and reads the verdict off the plan row
it wrote. The fixture ladder is check_plan_prepares' `calls_good`: pin 101,
spot 99, EM 4.12 at the pinned 12:30 clock, so the band is ±0.41.

  W1  conc 0.15 (under the 0.25 floor), today's fresh VWAP 0.20 from the pin
      -> TAKE, and the row says the floor was WAIVED and by how much
  W2  the same with VWAP 1.00 away -> HOLD waiting on pin_concentration, the
      row naming the distance
  W3  a VWAP anchored to a PRIOR session, 0.10 from the pin -> no waiver
      (the engine writes Friday's VWAP all weekend)
  W4  today's anchor but a bar ten minutes old -> no waiver (a stalled feed)
  W5  no VWAP row at all -> no waiver, and the row says there was no VWAP
  W6  control: conc 0.60 meets the floor on its own; no waiver is claimed
  W7  the distance is recorded on the tick as `pin_vwap_dist`, waived or not
  A4  `anchors.vwap()` reads the 'primary' interval the engine actually writes

Born red at r24 (577ceb1) on W1-W5, W7 and A4: no waiver exists there, so W1 holds
instead of taking and no row names a VWAP distance or why there is none, and
vwap() queried '1m'. W6 is the control, green on both sides.
Run:  python3 tests/check_bfly_vwap_band.py
"""
import os
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)
os.environ.setdefault("OT_PAPER_TRADING", "1")
_fails = []
ET = ZoneInfo("America/New_York")


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))
    if not cond:
        _fails.append(label)


class _Store:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")

    def commit(self):
        self.conn.commit()


class _C:
    def __init__(self, k, bid, ask):
        self.strike, self.bid, self.ask = float(k), float(bid), float(ask)
        self.mark = (bid + ask) / 2
        self.delta, self.gamma, self.theta = 0.2, 0.01, -0.03
        self.expiry, self.open_interest = "x", 100
        self.symbol = f"C{k}"


class _Chain:
    def __init__(self, calls):
        self.puts, self.calls = [], list(calls)


class _GEX:
    def __init__(self, conc):
        self.gex_environment, self.pin_strike, self.pin_concentration = "PINNING", 101.0, conc


def main():
    from strategy import plan as P
    import strategy.gex_pin_butterfly as bf
    from derived import anchors as A
    from data.derived_store import DerivedStore
    from utils.time_utils import ET as _ET_pin

    st = _Store()
    P.bind_store(st)
    os.environ["OT_RELAXED_ENTRY"] = "0"
    bf.ENABLED = True
    bf.EARLIEST_ET, bf.LATEST_ET = "09:30", "16:00"
    bf.PERSIST_TICKS = 1
    _em_real = bf.expected_move
    _fixed_now = bf.datetime(2026, 8, 27, 12, 30, tzinfo=_ET_pin)
    bf.expected_move = lambda u, iv, now=None: _em_real(u, iv, now=_fixed_now)

    calls_good = [_C(k, m - 0.005, m + 0.005) for k, m in
                  ((99, 2.55), (100, 1.70), (101, 1.00), (102, 0.70), (103, 0.45), (104, 0.30))]
    common = dict(price_now=99.0, now_et="12:30", atm_iv=0.90)
    now = time.time()
    midnight = datetime.fromtimestamp(now, ET).replace(hour=0, minute=0, second=0, microsecond=0)
    today_ms = int(midnight.timestamp() * 1000)
    prior_ms = int((midnight - timedelta(days=1)).timestamp() * 1000)

    def _store_with(vwap=None, anchor_ms=today_ms, bar_age_s=30.0):
        ds = DerivedStore(path=os.path.join(tempfile.mkdtemp(), "derived.db"))
        if vwap is not None:
            ds.append_indicators([("TST", "primary", now - 5, int((now - bar_age_s) * 1000),
                                   None, None, None, None, None, None, None,
                                   float(vwap), None, None, anchor_ms)])
        A._store = lambda: ds
        A._sym = lambda: "TST"
        return ds

    tick_ts = [30.0]

    def _run(conc, **kw):
        _store_with(**kw)
        B = bf.GEXPinButterflyStrategy()
        B.planner.symbol = "TST"
        tick_ts[0] += 1.0
        P.begin_tick(tick_ts[0])
        sig = B.generate_signal(gex=_GEX(conc), chain=_Chain(calls_good), **common)
        row = st.conn.execute("SELECT verdict, reason FROM plan_tick WHERE strategy=? AND ts_epoch=?",
                              ("GEXPinButterfly", tick_ts[0])).fetchone()
        dist = st.conn.execute("SELECT value FROM plan_check WHERE strategy=? AND ts_epoch=? "
                               "AND check_name='pin_vwap_dist'", ("GEXPinButterfly", tick_ts[0])).fetchone()
        return sig, (row or ("", "")), (dist[0] if dist else None)

    sig, row, dist = _run(0.15, vwap=100.8)
    check("W1 conc under the floor, pin 0.20 from today's VWAP (band ±0.41) -> TAKE, the waiver named",
          sig is not None and row[0] == "TAKE" and "WAIVED" in row[1] and "100.80" in row[1],
          f"{row[0]}: {row[1][:160]}")
    check("W7 the pin-to-VWAP distance is on the tick as pin_vwap_dist",
          dist is not None and abs(dist - 0.20) < 1e-6, f"pin_vwap_dist={dist}")

    sig, row, dist = _run(0.15, vwap=100.0)
    check("W2 VWAP 1.00 from the pin -> HOLD waiting on pin_concentration, distance named",
          sig is None and row[0] == "HOLD" and "pin_concentration" in row[1] and "1.00 off" in row[1],
          f"{row[0]}: {row[1][-140:]}")

    sig, row, _ = _run(0.15, vwap=100.9, anchor_ms=prior_ms)
    check("W3 a PRIOR session's VWAP 0.10 from the pin waives nothing",
          sig is None and row[0] == "HOLD" and "WAIVED" not in row[1] and "prior session" in row[1],
          f"{row[0]}: {row[1][-140:]}")

    sig, row, _ = _run(0.15, vwap=100.9, bar_age_s=600.0)
    check("W4 today's VWAP on a bar ten minutes old waives nothing",
          sig is None and row[0] == "HOLD" and "WAIVED" not in row[1] and "stale" in row[1],
          f"{row[0]}: {row[1][-140:]}")

    sig, row, dist = _run(0.15)
    check("W5 no VWAP row -> no waiver, and the row says there was no VWAP",
          sig is None and row[0] == "HOLD" and "no VWAP" in row[1] and dist is None,
          f"{row[0]}: {row[1][-140:]}")

    sig, row, _ = _run(0.60, vwap=95.0)
    check("W6 control: conc 0.60 meets the floor alone -> TAKE, no waiver claimed",
          sig is not None and row[0] == "TAKE" and "WAIVED" not in row[1], f"{row[0]}: {row[1][:120]}")

    _store_with(vwap=715.35)
    check("A4 anchors.vwap() reads the 'primary' interval the engine writes", A.vwap() == 715.35,
          f"vwap()={A.vwap()}")

    print()
    if _fails:
        print(f"FAILED {len(_fails)}: {', '.join(_fails)}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
