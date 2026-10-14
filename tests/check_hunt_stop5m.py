#!/usr/bin/env python3
"""
tests/check_hunt_stop5m.py  v1.0
v1.0  2026-10-14  OTV4TEST r285 (HUNT.8) — THE HUNT'S THESIS LINE IS THE FARTHER OF ITS BOUNDARY AND THE 5m SWING.

THE OPERATOR, 2026-10-14 11:47 ET: "Yes, we have to" (the 5m structure stop for the Hunt as
for Breakout). 10-14 09:58: a right-way Hunt short died at 10:03 on a 1m close of 737.28
back through its 736.90 boundary; QQQ then fell to 732.4. MEASURED
(/var/tmp/structure_hold_1014/v2_hunt.txt, n21, 1m close): -16.3 R -> -5.5 R.

DRIVES THE REAL ExitEngine._runaway_thesis_exits on a scratch feed store (1m frame
handed in, 5m candles in the store) and a scratch counterfactual dir.

  H1  a short whose 5m swing (101.00) is above its boundary (100.00): a 1m close of
      100.50 (through the boundary, under the swing) keeps the trade - not thesis-dead,
      not the 1m fizzle read, not the boundary backstop           (RED before)
  H2  a close beyond the 5m line (101.40) IS thesis-dead, naming the 5m line
  H3  never nearer: a 5m swing INSIDE the boundary leaves the boundary deciding
  H4  a 5m bar ending after the entry time never counts
  H5  OT_HUNT_STOP5M=log: the boundary decides (100.50 is dead) and the 5m line is recorded
  H6  an unreadable feed store keeps the boundary (100.50 is dead), never raises
  H7  counterfactual: a 'line' row per trade, and 'old_line_would_exit' /
      'fizzle_would_exit' rows when the old rules would have ended a trade the 5m
      line keeps                                                  (RED before)
  H8  config: unset -> trade; off/log honoured; junk -> log, refused by name
"""
import glob as _glob
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

for _sp in _glob.glob(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   "venv", "lib", "python*", "site-packages")):
    if _sp not in sys.path:
        sys.path.insert(1, _sp)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SCRATCH = tempfile.mkdtemp(prefix="chk_hunt_s5_", dir="/var/tmp")
for k, v in (("OT_TRADES_DB", "trades.db"), ("OT_DERIVED_DB", "derived.db"), ("OT_RESTING_DB", "resting.db"),
             ("OT_FEED_DB", "feed.db"), ("OT_COUNTERFACTUAL_DIR", "cf"), ("OT_SIGNAL_JOURNAL_DIR", "sj")):
    os.environ[k] = os.path.join(SCRATCH, v)
os.environ.pop("OT_HUNT_STOP5M", None)
FAILED, RAN = [], []
ET = "America/New_York"


def check(name, ok, detail=""):
    RAN.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILED.append(name.split()[0])


def guard(name, fn):
    try:
        ok, det = fn()
    except Exception as exc:                                    # noqa: BLE001
        ok, det = False, f"{type(exc).__name__}: {exc}"
    check(name, bool(ok), det)


def _o(day):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return int(datetime(day.year, day.month, day.day, 9, 30, tzinfo=ZoneInfo(ET)).timestamp() * 1000)


def _write_feed(day):
    o = _o(day)
    c = sqlite3.connect(os.environ["OT_FEED_DB"])
    c.execute("CREATE TABLE IF NOT EXISTS candles (symbol TEXT NOT NULL, interval TEXT NOT NULL, "
              "ts_epoch_ms INTEGER NOT NULL, open REAL, high REAL, low REAL, close REAL, "
              "volume REAL, PRIMARY KEY (symbol, interval, ts_epoch_ms))")
    rows = {"H5W": [(0, 101.00, 100.00), (5, 100.60, 99.80), (10, 103.00, 99.50)],   # 09:40 bucket ends after a 09:42 entry
            "H5T": [(0, 99.90, 99.50), (5, 99.95, 99.40)]}                            # every high inside the boundary
    for sym, bars in rows.items():
        for m, h, l in bars:
            c.execute("INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?)",
                      (sym, "5m", o + m * 60_000, h - 0.1, h, l, l + 0.1, 5000.0))
    c.commit()
    c.close()


def _df(day, last_close):
    """A 1m frame: bars 09:42..09:50 with tiny wicks; iloc[-2] closes at `last_close`."""
    import pandas as pd
    o = _o(day)
    rows = []
    for m in range(12, 21):
        cl = last_close if m == 19 else 99.70
        rows.append((o + m * 60_000, cl, cl + 0.01, cl - 0.01, cl, 1000.0))
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.pop("ts"), unit="ms", utc=True).dt.tz_convert(ET)
    return df


def _rec(day, sym, tid):
    from datetime import datetime, timezone
    return {"trade_id": tid, "symbol": sym, "strategy": "LiquidityHunt", "direction": "short",
            "underlying_stop": 100.00, "underlying_entry": 99.70, "orb_range_high": 100.00,
            "orb_range_low": 99.00, "entry_premium": 1.00,
            "entry_time": datetime.fromtimestamp((_o(day) + 12 * 60_000 + 5_000) / 1000, timezone.utc).isoformat()}


def _ask(eng, day, sym, tid, close):
    return eng._runaway_thesis_exits(_rec(day, sym, tid), "short", 0.80, 1.00, -20.0, _df(day, close))


def _cf_rows():
    p = os.path.join(os.environ["OT_COUNTERFACTUAL_DIR"], "hunt_stop.jsonl")
    return [json.loads(x) for x in open(p)] if os.path.exists(p) else []


def _cfg(env):
    e = {k: v for k, v in os.environ.items() if k != "OT_HUNT_STOP5M"}
    e.update(env)
    r = subprocess.run([sys.executable, "-c", "import config; print(config.HUNT_STOP5M_MODE, "
                        "repr(getattr(config, 'HUNT_STOP5M_ENV_REFUSED', None)))"],
                       cwd=ROOT, env=e, capture_output=True, text=True, timeout=60)
    return (r.stdout.strip().splitlines() or [r.stderr.strip()[-200:]])[-1]


def main():
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        day = datetime.now(ZoneInfo(ET)).date()
        _write_feed(day)
        import config
        import execution.exit_engine as XE
        eng = XE.ExitEngine(paper_trading=True)
    except Exception as exc:                                    # noqa: BLE001
        for n in ("H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8"):
            check(f"{n} setup", False, f"{type(exc).__name__}: {exc}")
        return _tail()

    r1 = _ask(eng, day, "H5W", "t-h1", 100.50)
    guard("H1 a close of 100.50 through the 100.00 boundary but under the 101.00 5m swing keeps the trade "
          "(no thesis-dead, no fizzle, no backstop)", lambda: (r1 == "", repr(r1)))
    r2 = _ask(eng, day, "H5W", "t-h2", 101.40)
    guard("H2 a close of 101.40 beyond the 5m line IS thesis-dead, naming 101.00",
          lambda: ("hunt_thesis_dead" in (r2 or "") and "101.00" in r2, repr(r2)))
    r3 = _ask(eng, day, "H5T", "t-h3", 100.50)
    guard("H3 a 5m swing inside the boundary never tightens it: 100.50 is dead on the 100.00 boundary",
          lambda: ("hunt_thesis_dead" in (r3 or "") and "100.00" in r3, repr(r3)))
    guard("H4 the 09:40 5m bucket (high 103.00) ended after the 09:42 entry and never counts: 101.40 is dead",
          lambda: ("hunt_thesis_dead" in (r2 or ""), repr(r2)))

    saved = getattr(config, "HUNT_STOP5M_MODE", None)
    config.HUNT_STOP5M_MODE = "log"
    try:
        r5 = _ask(eng, day, "H5W", "t-h5", 100.50)
    finally:
        config.HUNT_STOP5M_MODE = saved
    rows5 = [x for x in _cf_rows() if x.get("trade_id") == "t-h5" and x.get("event") == "line"]
    guard("H5 OT_HUNT_STOP5M=log: the boundary decides (100.50 is dead) and the 5m line 101.00 is recorded",
          lambda: ("hunt_thesis_dead" in (r5 or "") and rows5 and rows5[0].get("stop_5m") == 101.00
                   and rows5[0].get("line_used") == 100.00, f"{r5!r} {rows5}"))

    feed = os.environ["OT_FEED_DB"]
    os.environ["OT_FEED_DB"] = os.path.join(SCRATCH, "absent", "feed.db")
    try:
        r6 = _ask(eng, day, "H5W", "t-h6", 100.50)
    finally:
        os.environ["OT_FEED_DB"] = feed
    guard("H6 an unreadable feed store keeps the boundary: 100.50 is dead, nothing raised",
          lambda: ("hunt_thesis_dead" in (r6 or "") and "100.00" in r6, repr(r6)))

    rows = [x for x in _cf_rows() if x.get("trade_id") == "t-h1"]
    ev = sorted(x.get("event") for x in rows)
    guard("H7 counterfactual rows for the kept trade: 'line' (101.00 used), 'old_line_would_exit', 'fizzle_would_exit'",
          lambda: (ev == ["fizzle_would_exit", "line", "old_line_would_exit"]
                   and any(x.get("line_used") == 101.00 for x in rows if x["event"] == "line"), repr(rows)))

    got = [_cfg({}), _cfg({"OT_HUNT_STOP5M": "OFF"}), _cfg({"OT_HUNT_STOP5M": "log"}), _cfg({"OT_HUNT_STOP5M": "yes"})]
    guard("H8 config: unset -> trade, OFF -> off, log -> log, junk -> log refused by name",
          lambda: (got == ["trade ''", "off ''", "log ''", "log 'yes'"], repr(got)))
    return _tail()


def _tail():
    print()
    if FAILED:
        print(f"RED — {len(FAILED)} of {len(RAN)} failed: {', '.join(FAILED)}")
        return 1
    print(f"GREEN — {len(RAN)} checks: the Hunt's thesis line is the 5m swing")
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
    sys.exit(rc)
