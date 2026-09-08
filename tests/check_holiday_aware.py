#!/usr/bin/env python3
"""
tests/check_holiday_aware.py  v1.2
v1.2  2026-09-08  r319 / SHD.3 — H5c RUNS THE ExecCondition, BECAUSE H5 READ
      SOURCE TEXT AND WATCHED THE FLEET GO DARK. H5 asserts that
      `shadow/trading_day.py` contains the string `from utils.market_calendar
      import`. That string is precisely what broke it: an absolute package
      import in a module systemd invokes as a PLAIN SCRIPT, where `sys.path`
      carries the script's own directory and not the repo root. The import
      raised, the ExecCondition exited 1, systemd SKIPPED `shadow-start`
      (a non-zero condition is a skip, not a failure, so nothing entered a
      failed state), and all fifteen boxes wrote ZERO shadow rows on the first
      session after r304 landed. H5 was green the whole time.
      WORKING_AGREEMENT §21 one layer up — H5 asserted the MENTION of the
      import whose RESOLUTION was the defect. H5c executes the real
      ExecCondition line with the SYSTEM python from a directory OUTSIDE the
      repo and reads the exit code; H5d proves it fails for the right reason
      by checking stderr carries no traceback.
v1.1  2026-09-07  r307 - H4 DERIVES ITS out-of-coverage YEAR from coverage()
instead of hardcoding 2035. It went red the moment the list was extended to
2035 - a second copy of a constant, the same failure this session hit in a menu
prompt and a help string. Now it survives every future extension.
v1.0  2026-09-07  r304 / DEP.9 — THE TRADING CLOCK CONSULTS THE CALENDAR, AND
IT FAILS TOWARD TRADING.

Surfaced 2026-09-07, Labor Day: `is_rth()` tested `weekday() >= 5` and a time
window, nothing else, so on a market holiday it returned True and
`entries_open()` — the universal floor every order site sits behind (r102) —
said the market was open. The orchestrator and the morning brief knew better;
the trading path did not.

🔴 H4 IS THE CHECK THAT MATTERS AND IT IS NOT THE OBVIOUS ONE. The asymmetry
is: a WRONG holiday (a real session listed) means the fleet does not trade —
silent, total, and indistinguishable from a quiet tape. A MISSED holiday means
it is armed on a dead market and does nothing. So a date BEYOND the list's
coverage must read as a TRADING day. Anyone later "hardening" this by refusing
outside coverage turns a forgotten annual refresh into a dark fleet, and H4
goes red on them.

⚠️ AND IT EXECUTES `is_rth`, not the calendar. `market_calendar` has its own
selftest; what this pins is that the trading clock actually CALLS it — the
r150 lesson, where a gate read a name off an object that did not have it and
failed silently for the life of a strategy.

Run:  python3 tests/check_holiday_aware.py
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ET = ZoneInfo("America/New_York")
F: list = []


def check(n: str, ok: bool, d: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {n}" + (f"  — {d}" if d else ""))
    if not ok:
        F.append(n)


def main() -> int:
    print("\ncheck_holiday_aware\n")
    from utils.time_utils import is_rth, entries_open
    from utils import market_calendar as mc

    def at(y, m, d, hh=12, mm=0):
        return _dt.datetime(y, m, d, hh, mm, tzinfo=ET)

    check("H1  Labor Day 2026-09-07 midday is NOT RTH", not is_rth(at(2026, 9, 7)))
    check("H1b and entries are CLOSED on it", not entries_open(at(2026, 9, 7)))
    check("H2  the next weekday IS RTH", is_rth(at(2026, 9, 8)))
    check("H2b Thanksgiving 2026-11-26 is NOT RTH", not is_rth(at(2026, 11, 26)))
    check("H3  a weekend is still not RTH", not is_rth(at(2026, 9, 5)))

    # 🔴 THE ONE THAT MATTERS.
    # ⚠️ DERIVED FROM coverage(), NOT A HARDCODED YEAR. The first version used
    # 2035 and went red the moment r307 extended the list to 2035 — a second
    # copy of a constant, which is the failure this session has now hit in a
    # menu prompt, a help string and here. Pick the first weekday after the
    # last covered year and the check survives every future extension.
    _far_year = mc.coverage()[1] + 5
    far = at(_far_year, 3, 14)
    while far.weekday() >= 5:
        far += _dt.timedelta(days=1)
    check("H4  a weekday BEYOND the list's coverage IS RTH — fails toward "
          "trading",
          is_rth(far) and not mc.is_covered(far.date()),
          "a forgotten refresh must cost armed mornings, never a dark fleet")
    _sat = far
    while _sat.weekday() != 5:
        _sat += _dt.timedelta(days=1)
    check("H4b a weekend beyond coverage is still closed", not is_rth(_sat))

    # H5 — one list, not three. shadow must not carry its own copy back.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sh = open(os.path.join(root, "shadow", "trading_day.py")).read()
    check("H5  shadow/trading_day.py IMPORTS the list, does not redefine it",
          "US_MARKET_HOLIDAYS = {" not in sh
          and "from utils.market_calendar import" in sh)
    # ── 🔴 H5c — THE ExecCondition IS EXECUTED, NOT READ ──────────────────
    # `deploy/shadow-start.service` runs:
    #   ExecCondition=/usr/bin/python3 <install>/shadow/trading_day.py
    # so the test is that exact shape: SYSTEM python, absolute script path,
    # from a directory that is NOT the repo — because `WorkingDirectory=` does
    # not put the cwd on `sys.path` and does not rescue this.
    # ⚠️ 0 and 1 are BOTH legitimate (trading day / not), so the assertion is
    # that it exits CLEANLY with one of them and prints no traceback. An
    # ImportError also exits 1 — indistinguishable from "not a trading day" by
    # exit code alone, which is exactly why it went unnoticed for a session.
    import subprocess as _sp
    _script = os.path.join(root, "shadow", "trading_day.py")
    _r = _sp.run([sys.executable, _script], capture_output=True, text=True,
                 cwd=os.path.dirname(root))
    check("H5c shadow/trading_day.py RUNS as a bare script from outside the repo "
          "(the systemd ExecCondition form)",
          _r.returncode in (0, 1) and "Traceback" not in _r.stderr,
          f"exit={_r.returncode} stderr={_r.stderr.strip().splitlines()[-1] if _r.stderr.strip() else ''}")
    check("H5d and it agrees with the calendar it imports",
          _r.returncode == (0 if mc.is_trading_day() else 1),
          f"script exit={_r.returncode} "
          f"is_trading_day={mc.is_trading_day()}")

    tu = open(os.path.join(root, "utils", "time_utils.py")).read()
    check("H5b time_utils does not define a holiday set of its own",
          "US_MARKET_HOLIDAYS = {" not in tu)

    # H6 — a half day is a TRADING day; sessions are not modelled (DEP.12).
    check("H6  a half day (2026-11-27) is RTH — shortened sessions unmodelled",
          is_rth(at(2026, 11, 27)), "DEP.12")

    print()
    if F:
        print(f"check_holiday_aware: FAIL ({len(F)}): {', '.join(F)}")
        return 1
    print("check_holiday_aware: ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
