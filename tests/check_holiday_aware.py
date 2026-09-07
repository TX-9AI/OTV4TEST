#!/usr/bin/env python3
"""
tests/check_holiday_aware.py  v1.0
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
    far = at(2035, 3, 14)
    check("H4  a weekday BEYOND the list's coverage IS RTH — fails toward "
          "trading",
          is_rth(far) and not mc.is_covered(far.date()),
          "a forgotten refresh must cost armed mornings, never a dark fleet")
    check("H4b a weekend beyond coverage is still closed",
          not is_rth(at(2035, 3, 17)))

    # H5 — one list, not three. shadow must not carry its own copy back.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sh = open(os.path.join(root, "shadow", "trading_day.py")).read()
    check("H5  shadow/trading_day.py IMPORTS the list, does not redefine it",
          "US_MARKET_HOLIDAYS = {" not in sh
          and "from utils.market_calendar import" in sh)
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
