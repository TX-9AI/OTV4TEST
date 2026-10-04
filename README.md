# OTV4TEST — the plan/strategy untangle, in isolation

**`README.md` v2.3 · 2026-10-03 (OTV4TEST r227) — what this repo is, how it is laid out, how work lands. Supersedes the mainline README (v1.1) the fork inherited.**

**What this repo is.** A fork of `TX-9AI/options_trader_v4` (from `e955020`, mainline r322)
where the trading path is being re-wired so that **plans decide and strategies execute** —
the division of labour the operator designed and the predecessor never quite coded.
It runs on one segregated box (the QQQ TEST instance: no fleet tag, S3 masked, its own
lander and ledger) and trades paper head-to-head against the predecessor's QQQ instance on
the same tape. If it demonstrates a superior edge, its changes port forward — to the
predecessor as fixes (already in progress, `docs/PORT_MANIFEST.md`) and to **otv5** as the
layout.

**The layering** (the operator's words, `docs/FORK_BRIEF.md`): information layers off the
feed (IL1 primary, IL2 derived; IL3, the shadow observer, was deleted at r125) → a decision layer where each
**plan** searches the chain and the levels for the nearest setup that would clear the
strategy's bars, ahead of time → an execution layer where the **strategy** fires when price
action satisfies the plan's completed vectors. A strategy holds no chain and picks no strike.

## The trades (`docs/TRADES.md` §0 is the as-running roster; `docs/PLAN_SPEC.md` holds each spec)

| trade | state | plan | strategy | spec |
|---|---|---|---|---|
| Runaway (momentum) | ON | `strategy/runaway_plan.py` | `strategy/runaway_continuation.py` | §30 |
| Breakout | ON | `strategy/breakout_plan.py` | `strategy/breakout.py` (the spec) | TRADES §7 |
| Liquidity hunt | ON | `strategy/liquidity_hunt.py` | same file | §37 |
| ORCS (opening range credit spread) | ON, paper only | `strategy/orcs_plan.py` | `strategy/orcs.py` | §41 |
| GEX pin butterfly | ON | inside `strategy/gex_pin_butterfly.py` | same file | §32 |
| ATP butterfly | off (`OT_ATP_BUTTERFLY=1`) | `strategy/atp_butterfly_plan.py` | same file | §39 |
| VOLT | off (`OT_VOLT=1`) | `strategy/volt_plan.py` | `strategy/volt_strategy.py` | TRADES §8 |
| ORB break + retest | retired (`OT_ORB_TRADE=1`); the opening-range ENGINE stays | `strategy/orb_plan.py` | `strategy/orb_strategy.py` | §29 |
| Sweep credit spread | retired 2026-10-03 (`OT_SWEEP_CS=1`) | `strategy/sweep_plan.py` | `strategy/sweep_credit_spread.py` | §31 |
| Trend credit spread | retired 2026-10-03 (`OT_TCS_ACTIVE=1`) | `strategy/tcs_plan.py` | `strategy/trend_credit_spread.py` | §34 |
| Condor (a management plan, not an entry) | moot while both credit entries are retired | `strategy/iron_condor_strategy.py::manage` + `strategy/condor_roll.py` | — | §35 |

Two primitives the plans share: **the rejection fact** (`derived/levels.py` emits
WICKED / REJECTED / ACCEPTED on closed 1m bars for every live level, the 1h tines
included; §30.1) and **the handoff grant** (`execution/handoff.py`; §37.2). Anchors —
derivatives recorded on every plan row, never decided on — are §36.

## Layout

```
main.py            the bot (systemd: optionsbot)        config.py        every declared value
status.py  query.py  configure.sh                       the three the operator runs by hand
devtools.sh        the box menu (registry-rendered)      setup_ec2.sh     first-boot provisioning
push.sh  pull_today_ohlc.sh  bootstrap.example.sh        requirements.txt floors for a fresh venv
analysis/  data/  database/  derived/  execution/  notifications/  risk/
strategy/          plans and strategies                  utils/  warehouse/
tools/             land.sh (the lander), boot_sweep, agent_watch, last_session, readers
                   (eod_summary, debug_status, plan_board) and studies
deploy/            systemd units and their installers, snapshot, the fleet push
tests/             hypotheticals — every check_*.py drives real code on hand-built ticks
handoffs/          advisories sent to the mainline
docs/              PLAN_SPEC · TRADES · WORKING_AGREEMENT · GENESIS-TEST (this fork's ledger)
                   · GENESIS (frozen lineage) · BACKLOG · HANDOFF · FILE_MAP · WRITE_MAP
                   · FEED_MANIFOLD · DERIVED_STORES · FIRST_BOOT · PORT_MANIFEST
                   · superseded snapshots: FORK_BRIEF, ROADMAP, PORT_STATE
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

`query.py` (menu: query.py) — trades, then DECISIONS: one row per plan saying what it
is waiting on, or which bar refused it, or that it fired; plans outside their window are
hushed on the readers but recorded. `status.py` for the live position. The sensors
in the menu read the derived stores directly (plan rows, level events, anchors).
A NO PLAN or NOT ASKED for an in-window strategy is a wiring defect, not a market fact.

---

## Changelog

**v2.3 — 2026-10-03 — OTV4TEST r227.** Breakout and VOLT point at their new sections, TRADES §7 and §8.

**v2.2 — 2026-10-03 — OTV4TEST r226.** The trade table is the roster as it runs (r187, r204): Runaway, Breakout, Hunt, ORCS and the pin butterfly on; ATP and VOLT off; the ORB trade, the sweep and the TCS retired. `shadow/` is gone (r125). The layout block matches the tree: the three hand-run files at the root, the lander in `tools/`, every doc named.

**v2.1 — 2026-09-17 — OTV4TEST r34.** `status.py`, `query.py` and `configure.sh` are named at the REPO ROOT again. r14 moved them out in the root cleanup, sorting by file type rather than by role — the operator runs all three by hand and the root is where he looks for them. Paths only; nothing about the repo changed.

**v2.0 — 2026-09-11 — OTV4TEST r14.** Supersedes the inherited mainline README.
