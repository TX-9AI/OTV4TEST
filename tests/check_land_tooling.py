#!/usr/bin/env python3
"""
tests/check_land_tooling.py  v1.0
v1.0  2026-09-08  OTV4TEST r1 — THE FORK'S LANDER AND ITS GATE ACTUALLY WORK.

This repo is segregated from control, so it carries its own copy of
`tools/land.sh` and `tools/check_land_discipline.py`. Nothing on the fleet
checks them and nothing on control can reach them. This does.

🔴 WHY THIS FILE EXISTS AS A FILE, rather than a `CHECK` line with a flag.
`land.sh` runs each declared check as `python3 "$chk"` — **quoted**, so the
whole line is one path and a CHECK CANNOT CARRY ARGUMENTS. Declaring
`CHECK tools/check_land_discipline.py --selftest` therefore fails under the
lander and PASSES BY HAND, which is the worst shape of red: it reads as a flaky
test rather than a wiring mistake. Found in rehearsal, 2026-09-08. The lander's
own header warns about that exact shape for a different cause (r279's nested
`LAND_ARCHIVE` leak), which is why it is named here rather than worked around
quietly.

⚠️ IT EXERCISES THE TOOLING'S JOB, NOT ITS PRESENCE. Asserting the files exist,
or that `--ledger` appears in the source, would hand out a green light on a
broken lander — the pytest-bootstrap lesson from mainline. So: the discipline
checker's own selftest is RUN, `land.sh` is PARSED, and the ledger argument is
exercised through argparse rather than grepped for.

Run:  python3 tests/check_land_tooling.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILED = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILED.append(name)


def main():
    land = os.path.join(ROOT, "tools", "land.sh")
    disc = os.path.join(ROOT, "tools", "check_land_discipline.py")

    check("T0 the fork carries its own lander and gate",
          os.path.exists(land) and os.path.exists(disc),
          f"land.sh={os.path.exists(land)} discipline={os.path.exists(disc)}")
    if FAILED:
        print("\nRED — the tooling is absent; nothing below can run")
        return 1

    # T1 — the lander parses. Same class as SH.1 on mainline, where four shell
    # scripts aborted on a syntax error for fourteen days and nothing noticed.
    r = subprocess.run(["bash", "-n", land], capture_output=True, text=True)
    check("T1 tools/land.sh parses", r.returncode == 0,
          (r.stderr.strip().splitlines() or [""])[-1])

    # T2 — the discipline gate's OWN selftest, executed.
    r = subprocess.run([sys.executable, disc, "--selftest"],
                       capture_output=True, text=True, cwd=ROOT)
    check("T2 check_land_discipline --selftest passes", r.returncode == 0,
          (r.stdout.strip().splitlines() or [""])[-1])

    # T3 — `--ledger` is a real argument, CONSUMED, with the mainline default.
    # ⚠️ THE FIRST CUT OF THIS CHECK GREPPED `--help` FOR THE DEFAULT and was
    # red against a working tool, because argparse does not print defaults
    # unless the help string asks. The tool now says `%(default)s` — and the
    # second assertion below proves the argument is ACTED ON rather than merely
    # accepted, by pointing it at a ledger that does not exist and requiring
    # the tool to say so.
    r = subprocess.run([sys.executable, disc, "--help"],
                       capture_output=True, text=True, cwd=ROOT)
    check("T3 --ledger is offered and shows the mainline default",
          "--ledger" in r.stdout and "docs/GENESIS.md" in r.stdout,
          "not in --help output")

    r = subprocess.run([sys.executable, disc, "--repo", ROOT, "--rev", "r1",
                        "--ledger", "docs/NO-SUCH-LEDGER.md"],
                       capture_output=True, text=True, cwd=ROOT)
    _saw = [l for l in (r.stdout + r.stderr).splitlines()
            if "NO-SUCH-LEDGER" in l]
    check("T3b and the path is actually consumed, not ignored",
          bool(_saw), (_saw[0].strip()[:70] if _saw
                       else "the tool never mentioned the ledger it was handed"))

    # T4 — this repo's ledger exists and is NOT the inherited one. The fork
    # numbers from r1; docs/GENESIS.md is frozen lineage and must never gain a
    # row here. A fork row landing in the mainline ledger is the cross-repo
    # ambiguity DOC.17 was on mainline, in the other direction.
    fork_ledger = os.path.join(ROOT, "docs", "GENESIS-TEST.md")
    check("T4 docs/GENESIS-TEST.md exists", os.path.exists(fork_ledger))

    inherited = os.path.join(ROOT, "docs", "GENESIS.md")
    if os.path.exists(inherited) and os.path.exists(fork_ledger):
        head = open(inherited, encoding="utf-8").read()
        # the inherited ledger's last row must still be a MAINLINE revision;
        # if a fork row landed there, the LEDGER line in a land.spec was wrong.
        rows = [l for l in head.splitlines() if l.startswith("| **r")]
        last = rows[-1] if rows else ""
        check("T5 the inherited GENESIS.md has not gained a fork row",
              "r322" in last or "r3" in last.split("|")[1],
              f"last row: {last[:60]}")

    print()
    if FAILED:
        print(f"RED — {len(FAILED)} failed: {', '.join(FAILED)}")
        return 1
    print("GREEN — the fork's land tooling runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
