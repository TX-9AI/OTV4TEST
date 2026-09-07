#!/usr/bin/env python3
"""
tests/check_r_ledger_width.py  v1.0
v1.0  2026-09-07  r296 — THE LAND GATE FOR THE 78-CHARACTER RULE.

🔴 WHY A CHECK AND NOT A CAREFUL EDIT. The first cut of r296 picked field
widths by hand and the rows still came out 80: `_fmt` returns a fixed SEVEN
characters and `{x:>5}` PADS WITHOUT TRUNCATING, so a field declared 5 wide
rendered 7. The bug was not the number chosen — it was that the row width
DEPENDED ON THE DATA, and a layout that holds only while the values stay small
breaks on the first big day, which is the day you most want to read it.

So this gate RENDERS the report and MEASURES every line (WA §21 — reading the
format string proves nothing about what it emits). W2 drives values wide
enough to overflow every column at once; a hand-checked layout passes W1 and
fails W2.

Run:  python3 tests/check_r_ledger_width.py
"""
from __future__ import annotations
import contextlib, io, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import r_ledger                                                  # noqa: E402

RULE = 78
F: list = []
def check(n, ok, d=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {n}" + (f"  — {d}" if d else ""))
    if not ok: F.append(n)

def _rows(mix):
    out = []
    for st, side, n, p in mix:
        for i in range(n):
            out.append(dict(pnl_usd=p if i % 2 else -abs(p) / 2, entry_premium=1.0,
                mfe_premium=2.0, mae_premium=0.6, contracts=1, is_short_position=0,
                strategy=st, option_side=side, status="closed",
                exit_reason="orb_structure_stop: 1m close 9"))
    return out

def widths(rows):
    b = io.StringIO()
    with contextlib.redirect_stdout(b):
        r_ledger.render(rows)
    return b.getvalue()

def main() -> int:
    print("\ncheck_r_ledger_width\n")
    ordinary = widths(_rows([("RunawayContinuation", "call", 12, 150.0),
                             ("GEXPinButterfly", "call", 2, -287.0),
                             ("ORBStrategy", "put", 10, -92.0)]))
    over = [(len(l), l) for l in ordinary.splitlines() if len(l) > RULE]
    check(f"W1  every line fits {RULE} on ordinary data", not over,
          f"max={max(len(l) for l in ordinary.splitlines())}"
          + (f"; worst: {over[0][1][:50]}" if over else ""))

    # W2 — THE ONE THAT MATTERS. Values wide enough to burst every column:
    # a six-figure average, a long strategy name, an extreme capture ratio.
    huge = widths(_rows([("RunawayContinuationHandoffXL", "call", 6, 987654.0),
                         ("SweepCreditSpread", "put", 6, 123456.0)]))
    over2 = [(len(l), l) for l in huge.splitlines() if len(l) > RULE]
    check(f"W2  still fits {RULE} when every value overflows its column",
          not over2,
          f"max={max(len(l) for l in huge.splitlines())}"
          + (f"; worst: {over2[0][1][:50]}" if over2 else ""))

    # W3 — the marker is gone from the OUTPUT, not from the source.
    check("W3  `THIN` no longer renders", "THIN" not in ordinary)

    # W4 — THE MARKER WENT, THE THRESHOLD STAYED. R must still be suppressed
    # on a bucket below MIN_N: that is a refusal to compute, not a label, and
    # an R off two trades is worse than no R at all.
    thin = widths(_rows([("GEXPinButterfly", "call", 2, 100.0)]))
    row = [l for l in thin.splitlines() if "GEXPinButterfly" in l][0]
    check("W4  MIN_N still suppresses R on a thin bucket",
          "\u2014" in row, row.strip()[:56])

    # W5 — _col truncates rather than merely padding. The actual defect.
    check("W5  _col TRUNCATES, it does not merely pad",
          r_ledger._col("+$1,234,567", 6) == "+$1,23"
          and r_ledger._col("2.0", 6) == "   2.0",
          f"{r_ledger._col('+$1,234,567', 6)!r}")

    print()
    if F:
        print(f"check_r_ledger_width: FAIL ({len(F)}): {', '.join(F)}")
        return 1
    print("check_r_ledger_width: ALL PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
