#!/usr/bin/env python3
"""
utils/market_calendar.py  v1.0
v1.0  2026-09-07  r304 / DEP.9 — ONE HOLIDAY CALENDAR FOR THE WHOLE PROGRAM.

Surfaced 2026-09-07, Labor Day: the market was shut, the orchestrator and the
morning brief knew it, the bots were correctly left down — and devtools item 35
refused a bake as *"inside RTH"*. Two clocks, one question, and only one
consulted a calendar. `utils/time_utils.is_rth()` tested `weekday() >= 5` and a
09:30–16:00 window, nothing else, and `entries_open()` wraps it — which r102
made the universal floor every order site sits behind. **On a market holiday
the trading path believed the market was open.**

🔴 THE FAIL-SAFE DIRECTION IS THE OPPOSITE OF `shadow/trading_day.py`'s, AND
THAT IS THE MOST IMPORTANT LINE IN THIS FILE. That module's own header reasons:
*"a wrong 'holiday' just means shadow doesn't observe that day (no harm); a
missed holiday means it observes an empty tape (harmless noise), never a
trade."* For the TRADING clock the asymmetry inverts:

  · a WRONG holiday — a real session listed here — means THE FLEET DOES NOT
    TRADE. Silent, total, and it looks exactly like a quiet tape.
  · a MISSED holiday means the fleet is armed against a closed market. No
    data arrives, no order fills, and the blind-alert fires. Harmless.

**So this must fail toward TRADING, always.** An unlisted date is a trading
day. There is deliberately NO expiry guard that starts refusing once the list
runs out: a forgotten refresh must cost a few pointless armed mornings, never
a silent dark fleet. `coverage()` exists so staleness is VISIBLE instead of
being enforced.

⚠️ THIS IS THE ONLY HOLIDAY LIST IN otv4. `shadow/trading_day.py` imports it
rather than keeping its own — that copy is where these dates came from, and two
lists meaning one thing is the drift this repo keeps finding. day_trader_pro
has its own `market_calendar.py` on the control side; the repos cannot import
each other, so they are two copies by necessity, and DEP.11 records the
obligation to refresh both together.

⚠️ HALF DAYS ARE NOT MODELLED. The day after Thanksgiving and Christmas Eve
close at 13:00 ET. They are TRADING days, so this correctly returns True, and
nothing here shortens the session — a strategy holding to 15:45 on a 13:00
close is a real question and it is filed as DEP.12 rather than guessed at.

Run:  python3 utils/market_calendar.py            # today's verdict
      python3 utils/market_calendar.py --selftest
"""
from __future__ import annotations

import datetime as _dt
import sys
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# NYSE full-day closes (observed dates). Refresh each year — see coverage().
US_MARKET_HOLIDAYS = {
    # 2026
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # MLK Jr. Day
    "2026-02-16",  # Presidents' Day
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
    "2026-06-19",  # Juneteenth
    "2026-07-03",  # Independence Day (observed; Jul 4 is Sat)
    "2026-09-07",  # Labor Day
    "2026-11-26",  # Thanksgiving
    "2026-12-25",  # Christmas
    # 2027
    "2027-01-01",  # New Year's Day
    "2027-01-18",  # MLK Jr. Day
    "2027-02-15",  # Presidents' Day
    "2027-03-26",  # Good Friday
    "2027-05-31",  # Memorial Day
    "2027-06-18",  # Juneteenth (observed; Jun 19 is Sat)
    "2027-07-05",  # Independence Day (observed; Jul 4 is Sun)
    "2027-09-06",  # Labor Day
    "2027-11-25",  # Thanksgiving
    "2027-12-24",  # Christmas (observed; Dec 25 is Sat)
}


def coverage() -> tuple:
    """(first_year, last_year) the list actually covers."""
    years = sorted({int(d[:4]) for d in US_MARKET_HOLIDAYS})
    return (years[0], years[-1]) if years else (0, 0)


def is_covered(d: _dt.date | None = None) -> bool:
    """Is this date inside the years the list knows about?

    ⚠️ A CALLER MAY REPORT THIS. NOTHING MAY REFUSE ON IT. See the header:
    refusing outside coverage would turn a forgotten refresh into a dark fleet.
    """
    d = d or _dt.datetime.now(ET).date()
    lo, hi = coverage()
    return lo <= d.year <= hi


def is_trading_day(d: _dt.date | None = None) -> bool:
    """True if the US equity market holds a full or half session on `d`.

    Weekends are closed. Listed holidays are closed. EVERYTHING ELSE IS OPEN —
    including dates beyond the list's coverage, deliberately.
    """
    d = d or _dt.datetime.now(ET).date()
    if d.weekday() >= 5:
        return False
    return d.isoformat() not in US_MARKET_HOLIDAYS


def _selftest() -> int:
    F = []

    def ck(n, ok, det=""):
        print(f"  {'PASS' if ok else 'FAIL'}  {n}" + (f"  — {det}" if det else ""))
        if not ok:
            F.append(n)

    D = _dt.date
    ck("M1  Labor Day 2026-09-07 is NOT a trading day",
       not is_trading_day(D(2026, 9, 7)))
    ck("M2  the next weekday IS", is_trading_day(D(2026, 9, 8)))
    ck("M3  Saturday is not", not is_trading_day(D(2026, 9, 5)))
    # 🔴 M4 IS THE ONE THAT MATTERS. A date past the list must be TRADING.
    ck("M4  a date BEYOND coverage is a TRADING day — fails toward trading",
       is_trading_day(D(2035, 3, 14)) and not is_covered(D(2035, 3, 14)),
       "a forgotten refresh costs armed mornings, never a dark fleet")
    ck("M4b and a weekend beyond coverage is still closed",
       not is_trading_day(D(2035, 3, 17)))
    ck("M5  coverage() reports the real range", coverage() == (2026, 2027),
       str(coverage()))
    ck("M6  a half day is a TRADING day (sessions are not modelled)",
       is_trading_day(D(2026, 11, 27)), "DEP.12")
    print()
    if F:
        print(f"market_calendar selftest: FAIL ({len(F)})")
        return 1
    print("market_calendar selftest: ALL PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    t = _dt.datetime.now(ET).date()
    lo, hi = coverage()
    print(f"{t}  trading_day={is_trading_day(t)}  covered={is_covered(t)} "
          f"({lo}-{hi})")
    raise SystemExit(0 if is_trading_day(t) else 1)
