#!/usr/bin/env python3
"""
tests/check_market_calendar.py  v1.0
v1.0  2026-09-07  r307 / DEP.13 — THE HARDCODED LIST IS VERIFIED ARITHMETIC,
NOT TRUSTED TRANSCRIPTION.

`utils/market_calendar.US_MARKET_HOLIDAYS` is a hand-pasted set, by operator
ruling: *"If we know the standard days, then hard code them. I can manually
account for 1-offs."* Hardcoding keeps the rules off the live path — a box does
a set lookup and evaluates nothing.

🔑 BUT A HARDCODED LIST IS A TRANSCRIPTION, AND TRANSCRIPTIONS HAVE TYPOS. This
regenerates every standard closure from the NYSE rules and fails if ONE date
disagrees. The rules live HERE, in a control-only checker (WA §34), so they are
verified on every land and never imported by anything that trades.

⚠️ A WRONG DATE IN THAT LIST IS THE DANGEROUS DIRECTION. The calendar fails
toward trading for dates it does not know — but a date wrongly PRESENT is an
explicit close, and the fleet sits out a real session. Silent, and it looks
exactly like a quiet tape. That asymmetry is why this check exists at all.

⚠️ AD_HOC_CLOSURES IS EXCLUDED FROM THE COMPARISON BY CONSTRUCTION. Presidential
funerals, 9/11, Sandy — no algorithm produces them, so requiring the generator
to reproduce them would make this check permanently red and then ignored. It is
subtracted, and its contents are REPORTED so a hand-added date is visible rather
than silently trusted.

Run:  python3 tests/check_market_calendar.py
"""
from __future__ import annotations

import datetime as d
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import market_calendar as mc                          # noqa: E402

F: list = []


def check(n, ok, det=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {n}" + (f"  — {det}" if det else ""))
    if not ok:
        F.append(n)


# ── the NYSE rules, as arithmetic ───────────────────────────────────────────
def _nth(y, m, wd, n):
    x = d.date(y, m, 1)
    x += d.timedelta((wd - x.weekday()) % 7)
    return x + d.timedelta(7 * (n - 1))


def _last(y, m, wd):
    x = d.date(y, m + 1, 1) - d.timedelta(1)
    return x - d.timedelta((x.weekday() - wd) % 7)


def _easter(y):
    """Anonymous Gregorian computus — exact, no dependency."""
    a = y % 19
    b, c = divmod(y, 100)
    e, f = divmod(b, 4)
    g = (8 * b + 13) // 25
    h = (19 * a + b - e - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * f + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l) // 433
    mo = (h + l - 7 * m + 90) // 25
    da = (h + l - 7 * m + 33 * mo + 19) % 32
    return d.date(y, mo, da)


def _observed(x):
    # ⚠️ NYSE's rule, not the federal one. Columbus Day and Veterans Day are
    # federal holidays and the exchange TRADES — a generic `holidays` package
    # would close on both.
    if x.weekday() == 5:
        return x - d.timedelta(1)
    if x.weekday() == 6:
        return x + d.timedelta(1)
    return x


def rules_for(y: int) -> set:
    return {x.isoformat() for x in {
        _observed(d.date(y, 1, 1)), _nth(y, 1, 0, 3), _nth(y, 2, 0, 3),
        _easter(y) - d.timedelta(2), _last(y, 5, 0),
        _observed(d.date(y, 6, 19)), _observed(d.date(y, 7, 4)),
        _nth(y, 9, 0, 1), _nth(y, 11, 3, 4), _observed(d.date(y, 12, 25)),
    }}


def main() -> int:
    print("\ncheck_market_calendar\n")
    listed = set(mc.US_MARKET_HOLIDAYS) - set(mc.AD_HOC_CLOSURES)
    lo, hi = mc.coverage()

    generated = set()
    for y in range(lo, hi + 1):
        generated |= rules_for(y)
    # An observed close can land in the prior year (NYD on a Saturday), so the
    # boundary year's spill-in is generated too and then trimmed to range.
    generated |= rules_for(hi + 1)
    generated = {x for x in generated if lo <= int(x[:4]) <= hi}
    listed_in = {x for x in listed if lo <= int(x[:4]) <= hi}

    check("C1  every hardcoded date is produced by the rules",
          not (listed_in - generated), f"unexplained: {sorted(listed_in - generated)}")
    check("C2  every rule-produced date is in the list",
          not (generated - listed_in), f"missing: {sorted(generated - listed_in)}")
    check("C3  coverage runs at least 5 years ahead of today",
          hi >= d.date.today().year + 5, f"covers {lo}-{hi}")
    check("C4  the 2027-12-31 spill-in is present (NYD 2028 is a Saturday)",
          "2027-12-31" in listed)
    # ⚠️ REPORTED, NOT ASSERTED. A hand-added closure is the operator's call;
    # this makes it visible so it cannot accumulate unnoticed.
    print(f"  NOTE  AD_HOC_CLOSURES: {sorted(mc.AD_HOC_CLOSURES) or 'none'}")
    check("C5  ad-hoc entries are real dates",
          all(len(x) == 10 and x[4] == "-" for x in mc.AD_HOC_CLOSURES))

    print()
    if F:
        print(f"check_market_calendar: FAIL ({len(F)}): {', '.join(F)}")
        return 1
    print(f"check_market_calendar: ALL PASS — {len(listed_in)} closures "
          f"{lo}-{hi}, all reproduced from the rules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
