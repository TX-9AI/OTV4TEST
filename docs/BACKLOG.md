# BACKLOG.md — OTV4TEST — v0.1

**The fork's own backlog. Started BLANK on 2026-09-08 by the operator's ruling:**
*"If you think we could benefit from a backlog it should start BLANK and be
specific to this repo."* Mainline's 3,986-line backlog is not this file and is
not carried; it lives in `TX-9AI/options_trader_v4` where its items are worked.

Same rules as mainline (WORKING_AGREEMENT §18): ships in every archive, one
row per item, a title bump and a PART 3 entry per delivery. Revisions are cited
as `OTV4TEST rN`, never a bare `rN`. States (the LAST cell, which `check_ledger_parity` reads): 🔲 OPEN · ◐ built/pushed, not yet
proven on the box · ✅ closed · ⬛ dead.

**BUILT ≠ PUSHED ≠ BAKED** — and on this box the third means running on the
isolated QQQ instance with the operator watching the plan ledger daily.

---

## PART 1 — OPEN

### ORB — the first trade untangled (PLAN_SPEC §29)

| id | item | state |
|---|---|---|
| **ORB.1** | ⬜ **PROVE IT FIRES ON THE BOX.** The rewired ORB (OTV4TEST r2) has run on hypotheticals only. Acceptance (FORK_BRIEF §6): a live session in which every fire reads back against its plan row — stop = the impulsive candle's extreme, strike at ±width, the size the sizer produced against the provisional size the row showed. A null result is a result: a session of `HOLD PREPARED … waiting on: retest` with no retest is the tape, not a defect. Read `plan_tick` for `ORBStrategy` after the first session. | 🔲 OPEN |
| **ORB.2** | ⬜ **TWO SELECTION VALUES CARRIED, NOT RULED.** `strategy/orb_plan.py` declares `QUOTE_FLOOR = 0.05` (contracts marked at a nickel or less are not candidates) and `DELTA_BIAS = "lower"` (an equidistant tie goes further OTM). Both were silent inside `select_orb_strike` and are now readable values, parity-pinned so what the plan picks is what e955020 picked. The operator asked which strikes the plan should look for and agreed the rule; these two edges were named and not decided. Keep, change, or drop — one number each. | 🔲 OPEN |
| **ORB.3** | ⬜ **THE RUNAWAY STILL CARRIES VELOCITY STALL THROUGH THE SHARED EVALUATOR.** `exit_engine._evaluate_orb` serves both `ORBStrategy` and `RunawayContinuation`; r2 removed the stall for ORB records only (operator: keep all but 5). Whether the runaway keeps it is the runaway's conversation — recorded here so the shared path is not forgotten when that trade is untangled. | 🔲 OPEN |

### Repo hygiene found on the way

| id | item | state |
|---|---|---|
| **HYG.1** | ⬜ **`analysis/trade_readiness.py::_combine` IS UNBOUND.** pyflakes over the tree (FORK_BRIEF §3.7) found `_combine` defined NESTED inside `ramp()` (indentation) and called five times at module level — a NameError on every readiness path, masked because the engine is log-only and import-guarded in main.py. Two more undefined names sit in tests (`check_management_plan.py:302 esrc`, `scrub_headers.py:285 s2`). Not fixed in r2 (not the asked-for change); a `check_undefined_names.py` gate (undefined-name only, never unused-import) is the fix's companion. | 🔲 OPEN |
| **HYG.2** | ⬜ **DOC STRIP — PROPOSED, NOT RULED.** FORK_BRIEF §3.6 proposes removing `ROADMAP.md`, `PORT_STATE.md`, `INHERITED_FINDINGS.md`, `HANDOFF.md`, `VISION.md` (mainline history with no fork consumer). `BACKLOG.md` was ruled: restarted blank (this file). The rest await the operator; deletion is a revision with a ledger row, and `FILE_MAP.md` is checked for links first. | 🔲 OPEN |
| **HYG.3** | ⬜ **`tests/check_ledger_parity.py` READS THE FROZEN LEDGER.** It opens `docs/GENESIS.md` (mainline, frozen here) and this backlog; on the fork the revision it should reconcile against is `docs/GENESIS-TEST.md`. Not run by the lander today; repoint before relying on it. | 🔲 OPEN |

---

## PART 2 — CLOSED

_(none yet)_

---

## PART 3 — CHANGELOG

**v0.1 — 2026-09-08 — OTV4TEST r2 — THE FORK'S BACKLOG STARTS BLANK (v0.x: fork-numbered, never mainline's); ORB.1–3, HYG.1–3 opened.**
Opened alongside the first rewire: the ORB spec and its plan contract agreed
with the operator part by part (PLAN_SPEC §29) and built — `strategy/orb_plan.py`
selects from 09:35, the strategy fires on its bars with the plan's variables,
the stale re-arm and the ATR floor deleted by ruling, velocity stall out of the
ORB exit path, ORB asked every tick and observing silently outside its window.
