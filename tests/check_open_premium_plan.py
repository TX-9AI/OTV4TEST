#!/usr/bin/env python3
"""
tests/check_open_premium_plan.py  v1.1
v1.1  2026-10-03  OTV4TEST r204 (PREM.2) — RENAMED to tests/check_orcs.py. This file is a SHIM for one landing only
      (the lander runs its checks before it deletes): it runs check_orcs.py and returns its verdict. r205
      removes it.
v1.0  2026-10-03  OTV4TEST r203 (PREM.1) — the opening premium spread plan's gate (now tests/check_orcs.py).

Run:  python3 tests/check_open_premium_plan.py   (exit 0 green, 1 red)
"""
import os
import runpy

if __name__ == "__main__":
    runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_orcs.py"), run_name="__main__")
