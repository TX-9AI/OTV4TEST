# HANDOFF_NOW — a one-time note for the thread that starts 2026-09-13

**Delete this file once it has been read.** `docs/HANDOFF.md` is the standing
brief and does not change; this is the state and the open items as of r17, so
the next thread does not have to re-derive them. Everything below is read from
the repo or measured on the box — where it is a ruling owed rather than a fact
found, it says so.

## Where things stand

HEAD is **r17**. The six trades and the condor management plan are specced and
built (PLAN_SPEC §29–§38); the **liquidity hunt** (§37) is the newest and has
never had a clean week. The predecessor is **not** frozen — it moved r324→r364
under another agent, so PORT_MANIFEST is a merge map now, not a one-way list.

Monday is **HUNT.1's first real week**. Two things were fixed specifically so
that week is readable: the level board (r15 — before it, the PDH/PDL/R-ladder
could not leave the ledger at all) and `option_symbol` on the entry row (r17 —
before it, no single-leg fill joined `quote_series`). Both are forward-only.
Nothing before Monday counts as hunt evidence.

## Read these first, in this order, on Monday

1. The hunt's 09:35 row — is there a level in play, which side is the bias,
   what is the distance in EM. `board_state` is a check: `no_store`, `no_range`,
   no fork and no level that side are four different answers.
2. A1 vs A2 — which entry fired, and for a far-side break that did not fail,
   the "broke AWAY from the liquidity" row. That row is the sample for the
   operator's fake-out read and costs nothing.
3. TRADES TAKEN — `LiquidityHunt` beside `ORB` on the same range.
4. If a target was wicked: the grant line, fired or expired. An expired grant
   is a finding, not a miss.

## Open items worth acting on

**Deadline-shaped (before or during the week)**

- **HUNT.2** — `sig.handoff_grant` is set at `main.py` and read nowhere, so
  "the sweep's fill carries the grant" is intent, not record. The lifecycle is
  in `bot.log` at INFO (issue, expiry, fire), and `bot.log` is neither rotated
  nor purged, so the week is answerable by a hand-join — but the row should
  carry it. Small, and it makes the week's best question answerable properly.
- **HUNT.3** — the grant path is the one `_execute_condor_leg` call site with
  no `_can_open_credit_spread` in front of it. Every bar the sweep owns still
  applies; what it bypasses is the pairing geometry. **A ruling is owed, not a
  defect found** — ask the operator before changing it.

**Small, ruled, not yet done**

- **TCS.1** — the nickel close on the TCS. The 2026-08-14 no-nickel ruling was
  *measured* (EV held to expiry) and stands in code; a later untangle listed a
  nickel in passing without revisiting that measurement. One ruling, one line.
- **LVL.2** — `sweep_plan` and `tcs_plan` test `kind == "resistance"` as a
  *side*; the hunt compares prices. Not wrong today (both also compare price),
  but it is a trap after a level is crossed, and it should be settled before
  otv5 inherits it.
- **BFLY.2** — split the butterfly's `prepare()` into `butterfly_plan.py` for
  parity with the other five. A tidy, not a behaviour.
- **CND.2** — the tent code (`check_and_execute_tent`, `_tent_breached`,
  `_execute_tent`, `_tent_close_all`, `_evaluate_tent`) has had no caller since
  r11. A dead branch reads as live; delete it with the port.
- **PRE.2** — mainline r341 and r344 are still unassessed. r345 was checked and
  ruled out by reading (`_close_vertical` here hardcodes BUY_TO_CLOSE).
- **PRE.3** — `level_event` exists here and nowhere on mainline: no table, no
  push stage, no retention row. Infrastructure, so it belongs to the control
  agent, not this box — but it is the by-absence exposure at a supersede.
- **LAY.2** — `deploy/` now holds installers, units and ops scripts together.
  Fine for one box; otv5 may want them split. Decide at the port.

**Priors with no sample yet** — each is a number I chose, recorded on every
row, and none has been scored: `REJECTION_FRESH_BARS` (3, sweep),
`ACCEPT_FRESH_BARS` (3, TCS), `SMOOTH_WINDOW`/`PERSIST_TICKS` (12/8,
butterfly), `HANDOFF_TTL_TICKS` (8). **TCS.2** stands as the operator's
instruction: if the TCS never fires or fires too loosely, the EM gate is the
first suspect either way — read `em_outside_by` on fires and `outside_by` on
declines before touching anything else.

**Ugly but honest** — the DECISIONS panel still shows
`RunawayContinuation/manage NOT ASKED — dispatch gap`. It is a real management
row gap, pre-dating the untangle, and it is flagged STALE by the reader rather
than hidden. Worth fixing; not urgent.

## Three habits this repo runs on

- **The plan decides, the strategy executes.** A strategy holds no chain and
  picks no strike. If a new trade needs a chain read, it belongs in the plan.
- **Every tick writes a row.** A NO PLAN or NOT ASKED for an in-window strategy
  is a wiring defect, not a market condition (PLAN_SPEC §33). Four empty
  answers stay distinct; silence never reads as clearance.
- **Hypotheticals are born red.** A check that passes the moment it is written
  proved nothing. Drive real code on hand-built ticks, watch it fail against
  the old tree, then fix.

## Two failures this repo has already paid for

- A checker wrote its fixture into the box's **live** `trades.db` and the bot
  resumed a phantom position (r13). The lander now runs every CHECK with
  `OT_TRADES_DB`/`OT_DERIVED_DB` on scratch files — do not undo that.
- A checker asserted "no store" by unsetting a singleton that lazily opens the
  real store on a box; it passed in a sandbox and failed on the first land.
  **The box is not the sandbox.**
