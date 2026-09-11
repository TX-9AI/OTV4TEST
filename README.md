# OTV4TEST — the plan/strategy untangle, in isolation

**`README.md` v2.0 · 2026-09-11 (OTV4TEST r14) — what this repo is, how it is laid out, how work lands. Supersedes the mainline README (v1.1) the fork inherited.**

**What this repo is.** A fork of `TX-9AI/options_trader_v4` (from `e955020`, mainline r322)
where the trading path is being re-wired so that **plans decide and strategies execute** —
the division of labour the operator designed and the predecessor never quite coded.
It runs on one segregated box (the QQQ TEST instance: no fleet tag, S3 masked, its own
lander and ledger) and trades paper head-to-head against the predecessor's QQQ instance on
the same tape. If it demonstrates a superior edge, its changes port forward — to the
predecessor as fixes (already in progress, `docs/PORT_MANIFEST.md`) and to **otv5** as the
layout.

**The layering** (the operator's words, `docs/FORK_BRIEF.md`): information layers off the
feed (IL1 primary, IL2 derived, IL3 the shadow observer) → a decision layer where each
**plan** searches the chain and the levels for the nearest setup that would clear the
strategy's bars, ahead of time → an execution layer where the **strategy** fires when price
action satisfies the plan's completed vectors. A strategy holds no chain and picks no strike.

## The six trades, as specced here (`docs/PLAN_SPEC.md`)

| trade | plan | strategy | spec |
|---|---|---|---|
| ORB break + retest | `strategy/orb_plan.py` | `strategy/orb_strategy.py` | §29 |
| Runaway (momentum) | `strategy/runaway_plan.py` | `strategy/runaway_continuation.py` | §30 |
| Sweep credit spread | `strategy/sweep_plan.py` | `strategy/sweep_credit_spread.py` | §31 |
| GEX pin butterfly | inside `strategy/gex_pin_butterfly.py` (BFLY.2) | same file | §32 |
| Trend credit spread | `strategy/tcs_plan.py` | `strategy/trend_credit_spread.py` | §34 |
| Condor (a management plan, not a strategy) | `strategy/iron_condor_strategy.py::manage` + `strategy/condor_roll.py` | — | §35 |
| Liquidity hunt (beside the ORB, never in its slot) | `strategy/liquidity_hunt.py` | same file | §37 |

Two primitives the plans share: **the rejection fact** (`derived/levels.py` emits
WICKED / REJECTED / ACCEPTED on closed 1m bars for every live level, the 1h tines
included; §30.1) and **the handoff grant** (`execution/handoff.py`; §37.2). Anchors —
derivatives recorded on every plan row, never decided on — are §36.

## Layout

```
main.py            the bot (systemd: optionsbot)        config.py        every declared value
devtools.sh        the box menu (registry-rendered)      setup_ec2.sh     first-boot provisioning
requirements.txt   floors for a fresh venv
analysis/  data/  database/  derived/  execution/  notifications/  risk/  shadow/
strategy/          plans and strategies                  utils/  warehouse/
tools/             operator readers (status, query, eod_summary, debug_status) and studies
deploy/            systemd units, installers, push/snapshot/configure, the lander's twin
tests/             hypotheticals — every check_*.py drives real code on hand-built ticks
docs/              PLAN_SPEC · TRADES · WORKING_AGREEMENT · GENESIS-TEST (this fork's ledger)
                   · GENESIS (frozen lineage) · FORK_BRIEF · PORT_MANIFEST · BACKLOG
```

## How work lands

Every revision is a tarball with a `land.spec` (`REPO` markers, `BASE`, `REV`, `LEDGER
docs/GENESIS-TEST.md`, `DESC`, `POS`/`NEG` content assertions, `CHECK` lines). The box menu's
**LAND** runs the archive's own `land.sh`: base must match HEAD, content gate, every CHECK
(on scratch stores — a checker can never reach the live DB), maps regenerated, a ledger
row appended, the discipline gate, commit, push. **BAKE** pulls, proves the tree imports,
restarts. Cite revisions by prefix: `OTV4TEST r14`, never a bare `r14`.

The rules are `docs/WORKING_AGREEMENT.md`. The one that governs everything else: no claim
without a source — read, queried, told, or inferred, and said which.

## Reading a session

`tools/query.py` (menu: query.py) — trades, then DECISIONS: one row per plan saying what it
is waiting on, or which bar refused it, or that it fired; plans outside their window are
hushed on the readers but recorded. `tools/status.py` for the live position. The sensors
in the menu read the derived stores directly (plan rows, level events, anchors).
A NO PLAN or NOT ASKED for an in-window strategy is a wiring defect, not a market fact.
