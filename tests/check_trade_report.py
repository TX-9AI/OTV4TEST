#!/usr/bin/env python3
"""
tests/check_trade_report.py  v1.0
MAINLINE'S TRADE REPORTS ON THIS BOX'S trades.db — driven as the menu runs them.

v1.0  2026-09-23  OTV4TEST r119. Born with tests/trade_report.py (absent at r118).

The operator, 2026-09-23: "let's get those reports borrowed, repurposed & added
to our devtools menu. You can retire our current one option 35 — I hate it."

Every case runs the REAL script as a subprocess on a scratch trades.db built by
the REAL TradeLogger schema, exactly as devtools.sh calls it.

  T1 the breakdown counts closed trades only: an OPEN row is not a trade
  T2 a VOID row is EXCLUDED and the exclusion is printed, by trade_id
  T3 read-only: the database's bytes are unchanged, and --no-json writes
     no reports/ directory
  T4 the trade list renders entry times in ET (13:54 UTC -> 09:54)
  T5 fees are priced (tests/fees.py beside it), never n/a on a known row
  T6 a missing database is a loud tool fault, rc 1 — not an empty book
  T7 the menu: item 35 is TRADE BREAKDOWN, 36 TRADES TAKEN, both run
     tests/trade_report.py, and the old SQL dump (entered_utc) is gone
"""
from __future__ import annotations

import glob as _glob
import hashlib
import os
import re
import sqlite3
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
for _sp in _glob.glob(os.path.join(ROOT, "venv", "lib", "python*", "site-packages")):   # r106 bootstrap
    if _sp not in sys.path:
        sys.path.insert(1, _sp)

FAILED, RAN = [], []
WORK = tempfile.mkdtemp(prefix="chk_trade_report-")
REPORT = os.path.join(ROOT, "tests", "trade_report.py")


def check(name, ok, detail=""):
    RAN.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILED.append(name.split()[0])


def build_db() -> str:
    from database.trade_logger import TradeLogger
    path = os.path.join(WORK, "trades.db")
    TradeLogger(db_path=path)                                    # the real schema
    rows = [
        # trade_id, strategy, setup_type, direction, entry_time, exit_time, contracts,
        # entry_premium, exit_premium, stop_premium, pnl_usd, status, exit_reason
        ("t-win", "Breakout", "breakout_short", "short", "2026-09-22T13:54:00+00:00",
         "2026-09-22T13:58:00+00:00", 10, 1.00, 1.30, 0.86, 300.0, "closed", "trail_stop_hit pnl=30%"),
        ("t-loss", "VOLT", "VOLT Long", "long", "2026-09-22T14:10:00+00:00",
         "2026-09-22T14:12:00+00:00", 5, 2.00, 1.72, 1.72, -140.0, "closed", "hard_stop_14% pnl=-14%"),
        ("t-void", "ORBStrategy", "ORB Long", "long", "2026-09-22T15:00:00+00:00",
         "2026-09-22T15:01:00+00:00", 1, 1.00, 1.00, 0.75, 0.0, "closed", "VOID: test fixture"),
        ("t-open", "Breakout", "breakout_long", "long", "2026-09-22T15:30:00+00:00",
         None, 3, 1.00, None, 0.86, None, "open", None),
    ]
    c = sqlite3.connect(path)
    c.executemany("INSERT INTO trades (trade_id, symbol, strategy, setup_type, direction, entry_time, "
                  "exit_time, contracts, entry_premium, exit_premium, stop_premium, pnl_usd, status, "
                  "exit_reason, paper_trade) VALUES (?, 'QQQ', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)", rows)
    c.commit(); c.close()
    return path


def run(*args):
    env = dict(os.environ, OT_TRADES_DB=os.path.join(WORK, "unused.db"))
    p = subprocess.run([sys.executable, REPORT, *args], capture_output=True, text=True,
                       cwd=WORK, env=env, timeout=120)
    return p.returncode, p.stdout + p.stderr


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    try:
        db = build_db()
    except Exception as exc:                                    # noqa: BLE001
        check("T0 the fixture database builds from TradeLogger", False, f"{type(exc).__name__}: {exc}")
        return finish()
    before = sha(db)
    rc, out = run("--db", db, "--no-json")
    m = re.search(r"TRADE BREAKDOWN — (\d+) closed trades", out)
    check("T1 the breakdown counts the two closed trades, not the open one",
          rc == 0 and m is not None and m.group(1) == "2", f"rc {rc}; header {m.group(0) if m else None}")
    check("T2 the VOID row is excluded and named", "1 VOID row(s) EXCLUDED: t-void" in out,
          next((l.strip() for l in out.splitlines() if "VOID" in l), "no VOID line"))
    check("T3 read-only: the database is byte-identical and no reports/ was written",
          sha(db) == before and not os.path.exists(os.path.join(ROOT, "reports"))
          and not os.path.exists(os.path.join(WORK, "reports")),
          f"db unchanged {sha(db) == before}")
    rc4, out4 = run("--db", db, "--no-json", "--rows-only")
    line = next((l for l in out4.splitlines() if " BRK " in l), "")
    check("T4 the trade list renders ET: 13:54 UTC reads 09:54", rc4 == 0 and "09-22 09:54" in line,
          line.strip() or out4[-200:])
    frow = next((l for l in out.splitlines() if l.strip().startswith("Breakout")), "")
    check("T5 the FEES column is priced, not n/a", frow != "" and "n/a" not in frow
          and re.search(r"-\d+\.\d\d", frow.split()[-1] if frow.split() else "") is not None, frow.strip())
    rc6, out6 = run("--db", os.path.join(WORK, "nope.db"), "--no-json")
    check("T6 a missing database is rc 1 and says PATH DOES NOT EXIST",
          rc6 == 1 and "PATH DOES NOT EXIST" in out6, f"rc {rc6}")

    src = open(os.path.join(ROOT, "devtools.sh"), encoding="utf-8").read()
    block = src[src.index("\nMENU=(") + 1:]                  # the array, not the comment naming it
    items = re.findall(r'^\s*"ITEM\|([^"]*)\|(\w+)"', block[:block.index("\n)")], re.M)
    n35 = items[34] if len(items) > 34 else ("", "")
    n36 = items[35] if len(items) > 35 else ("", "")
    wired = all(re.search(rf"^{fn}\(\)\s*{{[^\n]*_trade_report", src, re.M) for fn in ("trade_breakdown", "trades_taken"))
    check("T7 menu 35 = TRADE BREAKDOWN, 36 = TRADES TAKEN, both on trade_report.py; the SQL dump is gone",
          n35[1] == "trade_breakdown" and n36[1] == "trades_taken" and wired
          and "tests/trade_report.py" in src and "entered_utc" not in src,
          f"35 {n35[1]}; 36 {n36[1]}; wired {wired}; old dump present {'entered_utc' in src}")
    return finish()


def finish():
    import shutil
    shutil.rmtree(WORK, ignore_errors=True)
    print()
    if FAILED:
        print(f"RED — {len(FAILED)} of {len(RAN)} failed: {', '.join(FAILED)}")
        return 1
    print(f"GREEN — {len(RAN)} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
