"""
strategy/open_premium_plan.py  v1.1
v1.1  2026-10-03  OTV4TEST r204 (PREM.2) — RENAMED to strategy/orcs_plan.py. This file is an EMPTY SHIM for one
      landing only: the lander runs its checks before it deletes, so the old name must still import while
      r204 lands. Nothing imports it. r205 removes it.
v1.0  2026-10-03  OTV4TEST r203 (PREM.1) — the opening premium spread plan (now ORCS; see strategy/orcs_plan.py).
"""
from strategy.orcs_plan import *          # noqa: F401,F403
