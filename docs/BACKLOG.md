# BACKLOG.md — OTV4TEST — v0.3

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

### Runaway — the second trade untangled (PLAN_SPEC §30)

| id | item | state |
|---|---|---|
| **RUN.6** | ⬜ **PARTICIPATION IS NOT WIRED INTO THE STRENGTH READ.** §30.3 names three components; only pace and acceptance are measured at acceptance. The prints stream (aggressor side, r64) and `tape_at_level` exist but are not reachable from the strategy path; `runaway_plan.prepare(participation=...)` accepts the value and records None. Wire it as a dial, then re-read the band prior. | 🔲 OPEN |
| **RUN.7** | ⬜ **WOULD-HAVE-FLOORED WATCH.** The runaway has no premium stop by ruling; `exit_engine` records `_would_have_floored` the first time the old 20% floor would have fired while the thesis held. After the first sessions: how many trades, and did the structure exits recover them or not? A percent under the structure is a question, not a bar, until this is read. | 🔲 OPEN |
| **RUN.8** | ⬜ **THE FIZZLE PRIORS ARE UNMEASURED.** "Two events, or one event plus one dial", the 0.5× range-contraction line and the acc_recent < 0.5 read are declared priors; every read lands on the record (`_fizzle_read`). Score them against RAN (not 5% green) once fires exist; kill, keep, or codify. | 🔲 OPEN |
| **SWP.0** | ⬜ **THE SWEEP CREDIT SPREAD IS NEXT.** Its trigger is the REJECTED fact (§30.1); its thesis is the level holds to the close; the condor forms from a second rejection on the other side. The afternoon-only gate is a clock standing in for the handoff (§30.5) and stays until the handoff has fired on real tape. | 🔲 OPEN |

### Repo hygiene found on the way

| id | item | state |
|---|---|---|
| **HYG.1** | ⬜ **`analysis/trade_readiness.py::_combine` IS UNBOUND.** pyflakes over the tree (FORK_BRIEF §3.7) found `_combine` defined NESTED inside `ramp()` (indentation) and called five times at module level — a NameError on every readiness path, masked because the engine is log-only and import-guarded in main.py. Two more undefined names sit in tests (`check_management_plan.py:302 esrc`, `scrub_headers.py:285 s2`). Not fixed in r2 (not the asked-for change); a `check_undefined_names.py` gate (undefined-name only, never unused-import) is the fix's companion. | 🔲 OPEN |
| **HYG.2** | ⬜ **DOC STRIP — PROPOSED, NOT RULED.** FORK_BRIEF §3.6 proposes removing `ROADMAP.md`, `PORT_STATE.md`, `INHERITED_FINDINGS.md`, `HANDOFF.md`, `VISION.md` (mainline history with no fork consumer). `BACKLOG.md` was ruled: restarted blank (this file). The rest await the operator; deletion is a revision with a ledger row, and `FILE_MAP.md` is checked for links first. | 🔲 OPEN |
| **HYG.3** | ⬜ **`tests/check_ledger_parity.py` READS THE FROZEN LEDGER.** It opens `docs/GENESIS.md` (mainline, frozen here) and this backlog; on the fork the revision it should reconcile against is `docs/GENESIS-TEST.md`. Not run by the lander today; repoint before relying on it. | 🔲 OPEN |

---

## PART 2 — CLOSED

| id | item | closed |
|---|---|---|
| **ORB.3** | The runaway carried velocity stall through the shared evaluator. Closed OTV4TEST r3: the runaway's exit list is its own (§30.4) and the stall is off it. | r3 |

---

## PART 3 — CHANGELOG

**v0.3 — 2026-09-08 — OTV4TEST r4 — devtools 2.0: the box menu catches up with control.**
The otv1-era break-glass menu is replaced by a registry-rendered menu in
control's shape (numbers assigned at display time; cite by label). Ported to
run LOCALLY: SENSORS (the same SQL over this box's own derived_store.db and
feed_store.db, with an ET date prompt), DEBUG / LOGS, and the R SUITE via the
fork's own tests/*.py through their `--db` escape hatch on trades.db (the box
is masked from S3). New sensors: PLAN ROWS (the per-tick narrative) and LEVEL
EVENTS (the rejection fact). Fleet wrangling is deliberately absent. LAND and
BAKE now sit under GIT & LAND — the numbers moved; the labels did not.

**v0.2 — 2026-09-08 — OTV4TEST r3 — the rejection fact, the runaway spec, RUN.6–8 and SWP.0 opened, ORB.3 closed.**
The level engine emits WICKED / REJECTED / ACCEPTED on closed 1m bars (one close
back inside on a shallow pierce, two on a deep); the runaway is re-specced
(PLAN_SPEC §30): arm on the accepted 50, strength once at acceptance, band from
strength, one per break on any exit with re-validation on actual, no premium
stop, exits handoff → thesis → fizzle → trail → theta → backstop. ORB gains the
handoff exit (§29 amendment). devtools 40 auto-selects a lone archive; 41 bakes.

**v0.1 — 2026-09-08 — OTV4TEST r2 — THE FORK'S BACKLOG STARTS BLANK (v0.x: fork-numbered, never mainline's); ORB.1–3, HYG.1–3 opened.**
Opened alongside the first rewire: the ORB spec and its plan contract agreed
with the operator part by part (PLAN_SPEC §29) and built — `strategy/orb_plan.py`
selects from 09:35, the strategy fires on its bars with the plan's variables,
the stale re-arm and the ATR floor deleted by ruling, velocity stall out of the
ORB exit path, ORB asked every tick and observing silently outside its window.
