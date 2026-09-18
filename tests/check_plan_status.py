#!/usr/bin/env python3
"""
tests/check_plan_status.py  v1.0
EVERY PLAN IS WORKING OR INACTIVE, AND INACTIVE SAYS SO ONCE.

v1.0  2026-09-18  OTV4TEST r41 — born red at r40 (a3ff8b9), where `close_tick`
      wrote a NOT ASKED row for every idle plan on EVERY tick.

THE OPERATOR'S RULING, 2026-09-18, verbatim:
  *"Because we know a plan is inactive outside its window, I don't need 10k rows
  explaining why. I just need 1, so I'm aware it at least 'Knows' — each plan
  should have a current status as either 'working' or 'inactive' and if it's
  working, I want per tick logging. If inactive it should just say that, once,
  until it becomes active."*

⚠️ THE ASSERTION IS A ROW COUNT ACROSS TICKS, NOT A STRING IN ONE ROW. The
defect is repetition, so a checker that reads a single tick cannot see it: the
row it finds is correct every time. S3 runs FIVE ticks in one state and demands
exactly ONE row — which is the only shape that fails on the old code.
"""
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("OT_TRADES_DB", os.path.join(tempfile.mkdtemp(), "t.db"))
os.environ.setdefault("OT_DERIVED_DB", os.path.join(tempfile.mkdtemp(), "d.db"))
FAILED, RAN = [], []


def check(name, ok, detail=""):
    RAN.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILED.append(name.split()[0])


def guard(name, fn, detail=""):
    try:
        ok, det = fn(), detail
    except Exception as exc:                                    # noqa: BLE001
        ok, det = False, f"{type(exc).__name__}: {exc}"
    check(name, ok, det)
    return ok


class _St:
    def __init__(s):
        s.conn = sqlite3.connect(":memory:")
        s.conn.row_factory = sqlite3.Row

    def commit(s):
        s.conn.commit()


def main():
    from strategy import plan as P

    st = _St()
    P.ensure_tables(st)
    P.bind_store(st)

    def fresh():
        P.REGISTRY.clear()
        # ⚠️ TOLERANT ON PURPOSE: at the older HEAD there is no `_STATUS`, and
        # a setup helper that raises turns a BORN-RED proof into a traceback —
        # the fault this repo has now shipped three times (r32, r37, r39).
        getattr(P, "_STATUS", {}).clear()
        st.conn.execute("DELETE FROM plan_tick")
        P.Plan("TrendCreditSpread", ("age",))

    def tick(n, reason=None, wrote=False):
        P.begin_tick(float(n))
        if wrote:
            # a WORKING plan speaks for itself
            P.write_row(st, "TST", float(n), "TrendCreditSpread", "ARMED", "working")
            P.REGISTRY["TrendCreditSpread"]._last = (P.tick_now()[0], "ARMED", "working")
        elif reason:
            P.skipped("TrendCreditSpread", reason)
        P.close_tick(st, "TST")

    def rows():
        return [(r["verdict"], r["reason"]) for r in st.conn.execute(
            "SELECT verdict, reason FROM plan_tick WHERE strategy='TrendCreditSpread'"
            " ORDER BY ts_epoch")]

    # ── S1/S2/S3 — the ruling itself ───────────────────────────────────────
    fresh()
    for n in range(1, 6):
        tick(n, reason="inactive — window: outside 11:30-15:00")
    r = rows()
    guard("S1 an INACTIVE plan writes exactly ONE row across five identical ticks",
          lambda: len(r) == 1, f"{len(r)} row(s) — the old board wrote 5")
    guard("S2 and the status it reports is INACTIVE, not 'NOT ASKED'",
          lambda: r and r[0][0] == "INACTIVE", f"verdict={r[0][0] if r else '-'}")
    guard("S2b the one row still carries the NAMED GATE",
          lambda: r and "window" in (r[0][1] or ""), f"{r[0][1][:50] if r else '-'}")

    # ── S4 — a WORKING plan keeps per-tick logging ─────────────────────────
    fresh()
    for n in range(10, 15):
        tick(n, wrote=True)
    rw = rows()
    guard("S4 a WORKING plan still writes EVERY tick — five ticks, five rows",
          lambda: len(rw) == 5, f"{len(rw)} row(s)")
    guard("S4b and the board reports it as working",
          lambda: P.plan_status("TrendCreditSpread") == "working")

    # ── S5 — the transition back re-announces ──────────────────────────────
    fresh()
    tick(20, reason="inactive — window: outside 11:30-15:00")
    tick(21, reason="inactive — window: outside 11:30-15:00")
    tick(22, wrote=True)                       # becomes active
    tick(23, reason="inactive — window: outside 11:30-15:00")
    r5 = rows()
    guard("S5 inactive -> working -> inactive announces the second inactive AGAIN",
          lambda: [x[0] for x in r5] == ["INACTIVE", "ARMED", "INACTIVE"],
          f"{[x[0] for x in r5]}")

    # ── S6 — a DIFFERENT reason is a state change, not a repeat ────────────
    fresh()
    tick(30, reason="inactive — window: outside 11:30-15:00")
    tick(31, reason="inactive — window: outside 11:30-15:00")
    tick(32, reason="inactive — cap: catastrophic cap broken")
    r6 = rows()
    guard("S6 inactive for a DIFFERENT reason writes again — a cap break is not noise",
          lambda: len(r6) == 2 and "cap" in r6[1][1],
          f"{len(r6)} row(s)")

    # ── S7 — the status is exposed, not merely internal ────────────────────
    guard("S7 plan_status() answers working/inactive/unknown",
          lambda: P.plan_status("TrendCreditSpread") == "inactive"
          and P.plan_status("NeverHeardOfIt") == "unknown")

    # ── S8 — main.py names the gate so no table strategy hits the default ──
    src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    guard("S8 admission names the refusing gate for every strategy it refuses",
          lambda: "why_not(" in src and 'f"inactive — {_v.gate}: {_v.why}"' in src,
          "otherwise an out-of-window plan reads as a dispatch-gap DEFECT")

    print()
    if FAILED:
        print(f"RED — {len(FAILED)} of {len(RAN)} failed: {', '.join(FAILED)}")
        return 1
    print(f"GREEN — {len(RAN)} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
