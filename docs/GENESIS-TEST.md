# GENESIS-TEST.md — the OTV4TEST revision ledger

**This is the fork's ledger. `docs/GENESIS.md` beside it is FROZEN.**

`OTV4TEST` was populated on 2026-09-08 by pushing a full clone of
`TX-9AI/options_trader_v4` — 3,050 objects, complete history — to a new private
repo. Every revision in the inherited `docs/GENESIS.md` describes work that
landed on the **mainline fleet**, and it is kept unedited as the lineage record
of exactly where this fork came from. Nothing appends to it here.

Revisions made **in this repo** are numbered from **r1** and land here.

⚠️ **THE NUMBERING RESTARTS AND THAT IS DELIBERATE.** A fork revision is not a
fleet revision, and continuing mainline's sequence would make `r323` ambiguous
across two repos and two behaviours. When a rewire is proven and merges back,
the mainline revision that carries it gets its own mainline number and cites
the OTV4TEST revision by name — `OTV4TEST r7`, never a bare `r7`. That is the
same cross-repo citation discipline that produced a checker defect on mainline
(DOC.17, 2026-09-08: `check_ledger_parity` read `dtp rNNN` as its own numbers
and was quiet on 28 of 31 collisions purely by luck). Prefix the repo. Always.

⚠️ **APPEND-ONLY, AND THE LANDER DOES THE APPENDING.** `tools/land.sh` writes
one row per revision from the half's `DESC`, before `git add`, so the row ships
inside the commit it describes. Do not hand-edit a row to fix a mistake —
supersede it with a later row. The one exception mainline arrived at, after the
operator's ruling on 2026-09-08, is a **correction to the ledger itself**, which
may ship in an archive because `BASE` refuses a stale clone.

⚠️ **WHAT A FORK REVISION IS FOR.** This repo exists to prove PLAN_SPEC §10 —
the plan searches and selects, the strategy declares bars and confirms. A row
here should say what was rewired, what the plan now selects that the strategy
used to, and what evidence says it can fire. See `docs/FORK_BRIEF.md`.

| rev | what landed |
|---|---|
| **r1** | r1 - THE FORK GETS ITS OWN LANDER, ITS OWN LEDGER AND ITS CHARTER. OTV4TEST was populated on 2026-09-08 by pushing a full clone of TX-9AI/options_trader_v4 (3050 objects, complete history) to a new private repo, with a repo-scoped deploy key so the box can push here and reach nothing else. This revision makes the fork self-sufficient off control. tools/land.sh v1.11 gains LEDGER in the land.spec, naming the ledger a half appends to - absent means docs/GENESIS.md so every mainline half is byte-for-byte unaffected, and this repo passes docs/GENESIS-TEST.md. A MISSING LEDGER NOW REFUSES rather than skipping the append - until now the append ran only if the file existed, so a typo would have committed with NO ledger row and reported success, violating section 35 silently inside the tool that enforces it. tools/check_land_discipline.py v1.2 gains --ledger to match, defaulting to GENESIS.md. docs/GENESIS-TEST.md is the fork ledger, numbered from r1; the inherited docs/GENESIS.md is FROZEN as the lineage record of where this fork came from and nothing appends to it here. THE NUMBERING RESTARTS DELIBERATELY - a fork revision is not a fleet revision, and a merge back cites OTV4TEST rN by name and never a bare rN, which is the exact cross-repo discipline whose absence produced DOC.17 on mainline where a checker read the other repo numbers as its own and was quiet on 28 of 31 collisions purely by luck. devtools.sh v4.3 gains item 40, LAND a tarball from home, which runs the ARCHIVE'S land.sh rather than the repo's copy so a delivery that fixes the lander is landed by the lander it ships and a fresh box bootstraps by the same path it uses forever after. docs/FORK_BRIEF.md is the charter for the rewire - the measured current boundary where the strategy selects and the plan merely evaluates, the PLAN_SPEC section 10 target where the plan searches and selects and the strategy declares bars and confirms, the ledger vocabulary of none available, decline with the bar named and the gap measured, and setup selected, the isolation configuration, and the acceptance test which is CAN IT FIRE and never P and L. KNOWN COST RECORDED NOT SOLVED - land.sh and check_land_discipline.py now exist in TWO repos because the fork box cannot reach control; they are identical as shipped and day_trader_pro needs the same change landed or they drift, and the drift would sit in the tool that gates everything else. |
