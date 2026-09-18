"""
derived/levels.py  v5.4
Owns `level_ledger` and `level_event`. Tier 3 — stateful; the object has a biography.
v5.4  2026-09-18  OTV4TEST r44 — THE PIERCE IS THE EXCURSION, NOT THE RECLAIM
      BAR'S WICK. `_derive_events` skipped every bar that traded beyond a level
      without closing back, so depth was measured on the ONE bar that closed
      back. ⚠️ THE BIAS RAN AGAINST THE BEST SETUPS: a one-bar wick measured
      correctly, a REAL grab always reported the shallowest bar of the sequence.
      Operator's case, 09-18 london 716.38: true 0.0688%, recorded 0.0102% —
      refused as "a touch, not a sweep" against a floor it cleared by 3.4x.
      MEASURED: of 182 banked REJECTED events, 58 under-reported by >1.5x and
      23 were refused when the true excursion cleared the floor.
v5.3  2026-09-18  OTV4TEST r39 (LVL.13) — THE BOARD WALKS ZONES, AND A ZONE
      HOLDING PRICE IS FINISHED. Operator, 2026-09-17: *"it's just grouping and
      only the outer members of the group declare anything"*, *"only points of
      recording interactions is at the extremes of the cluster — nothing in
      between gets to declare anything"*, and *"when we have a breach of the
      cluster everything that was a part of the cluster needs to go with it."*
      Each rung now carries TWO recording prices: `near_edge`, which takes the
      touch, and `far_edge`, which takes the breach — and `zone_ids`, so the
      breach retires every member and not just the one price was at.
      🔴 `board()` NO LONGER PRE-THINS WITH `_walked()`, AND THAT WAS THE WHOLE
      DEFECT. r29's walk keeps the nearest level per direction-step, which is
      correct for single levels and DESTRUCTIVE before grouping: measured
      2026-09-18 on the live ledger, 43 rows became 21 and the six levels stacked
      on spot (716.75 … 718.04) became ONE before any zone could see them. The
      cluster has to form from everything the ledger holds; the walk then thins
      ZONES. Cluster first, walk second.
      ⚠️ A ZONE CONTAINING PRICE IS RETIRED TRAVERSED, not reported. Operator:
      *"'one zone containing spot' isn't a zone, then. It's done — as a zone is
      defined, it's finished. There's no reclaim trade for that."* It is judged
      on a CLOSED BAR and never a tick, because r5 ruled a wick never spends a
      level and retirement has no undo. The opening-range TRAVERSED rule is
      untouched and still runs at tick rate.
v5.2  2026-09-17  OTV4TEST r33 — ONE BOARD, THE FORK BESIDE IT, AND THE LEDGER
      EMPTIED OF WHAT WAS NEVER A LEVEL.
      🔴 VWAP IS NO LONGER A SOURCE. It wrote a `kind="dynamic"` row every tick
      keyed on the PRICE, so a moving average minted a new identity each time it
      moved — 844 rows, and NO READER HAS EVER SEEN ONE, because `live_levels()`,
      `board()` and `walk()` all filter `kind IN ('support','resistance')`. It is
      r19's defect in a second costume: a MOVING object given a FROZEN horizontal
      identity. VWAP stays available at `ctx["vol"].vwap`, where the butterfly's
      own band already reads it. r30's STALE_VWAP sweep — which existed only to
      clean up after this producer — is retired with it.
      🔴 THE LEDGER WAS CLEANED IN THE SAME REVISION, on the operator's
      instruction: 855 vwap/dynamic rows and 55 fork-rail remnants DELETED
      (1,016 rows to 107). The live tradeable count was 11 before and 11 after —
      the invariant that mattered, checked either side of the delete, with the
      table dumped to `/home/ubuntu/level_ledger_backup_*.sql` first. The 63
      pre-r29 ladder rows (prev_day, PDH/PDL, R1-R3) are LEFT as history: all
      retired, none live, and they were real levels once.
      ONE BOARD FOR EVERY PLAN THAT TRADES LEVELS, AND
      THE FORK IS A SECOND PRODUCT BESIDE IT, NEVER INSIDE IT. Operator 2026-09-17:
      *"Make every fucking trade that relies on levels get it from the same place
      and include the fork when present"* and *"the fork projection is separate
      from the levels map. Those are two separate products. Both are to be
      consulted. The fork is a common informer but not mandatory if it's not
      there."* That was already the ruling at r5 — *"LEVELS IN PLAY come from the
      derived store, NEVER A PRIVATE MAP: 3 named up, 3 named down, plus the 1h
      pitchfork's tines"* — and three plans had three private compositions of it:
      the hunt through `board()`, the sweep through a local `level_map.walk()`
      with the rails APPENDED INTO the level list, and the TCS through a raw
      `live_levels()` filtered to `provenance == "ny"` with no fork at all.
      🔴 `board()` IS NOW THE ONE ACCESSOR AND ITS ORB BOUNDS ARE OPTIONAL. With
      them it answers the hunt's question unchanged (levels BEYOND the opening
      range, measured outward from the edge — r12's reach, which is the hunt's
      own design and is not touched). Without them it walks from SPOT, nearest
      first, each older level further out — the operator's rule, and the same
      `_walked()` the ORB path already used, so this merges two compositions
      rather than adding a third.
      ⚠️ THE RAILS ARE NEVER IN `above`/`below`. They stay in `tines`, with
      `fork` reading "built" or "absent" — r19's co-inform-not-conjoin, which the
      sweep had rebuilt one layer up by appending them in memory at read time.
      `walk()` now DELEGATES here so there is one implementation, not two.
v5.1  2026-09-14  OTV4TEST r30 — TWO DEFECTS IN r29, FOUND READING THE NOON BAKE.
      (1) A CONFIRMED LEGACY ROW KEPT ITS OLD `timeframe`. The reconcile stamped
      `created_ts` on a pre-r29 row the tape holds but not `timeframe`, which
      `upsert_level` never rewrites, so the 9 held rows on the box read `session`
      and not `session:YYYY-MM-DD`. The book-beyond-the-tape rule matches only
      `session:%`, so once Saturday's purge trims the 1m tape past 09-09, the held
      720.06 / 719.70 / 717.68 would have retired NOT_A_LEVEL. The kept row now
      gets its formation time AND its dated timeframe (`set_level_created`).
      (2) r29's changelog said the reconcile retires "stale VWAP ids"; it skipped
      every `dynamic` row, and 515 were live after the bake. Every VWAP id but the
      current one now retires `STALE_VWAP`. No level reader sees `dynamic` rows,
      so neither changes a trade — (1) prevents one silently losing its levels.
v5.0  2026-09-14  OTV4TEST r29 (LVL.8, LVL.9) — THE SESSION LEVELS COME FROM THE
      TAPE, AND THE LEDGER IS RECONCILED TO IT EVERY CLOSED BAR. Operator: *"Levels
      are session extremes that held. Starting from spot, map the most recent up/down
      levels going backwards in time and further up/down from the recent ones. A
      level is spent if it didn't hold & price accepted through it."* — the rulings
      already on record in fork PLAN_SPEC §31.1 and mainline §38 / LVL.3 / LVL.17.
      (1) SOURCES. When main hands `ctx["level_tape"]` (the feed store's 1m tape,
      `SYM` and `SYM_EXT` merged) the session levels are `level_map.session_levels`
      — every CLOSED Asia/London/NY section's high and low on the mapper's own
      clock — that HELD, plus ledger rows formed BEFORE the tape begins (the book
      reaches further than the purged tape; §38 *"reach is what the ledger has"*).
      The mapper's pools (PDH/PDL, `(R1)` rungs, the named ladder) are NO LONGER a
      source: they were the wick-broken ladder, and at 09:10 ET they carried a
      single 715.42 print as `London High (R1)` beside the same price as `london`.
      (2) RECONCILE, once per new tape bar: a live row that is not a held tape
      level and not older than the tape is RETIRED — `ACCEPTED_THROUGH` at the bar
      the tape shows acceptance (an `ACCEPTED` event only when that bar is fresh, so
      history never fires a trade: LVL.17), otherwise `NOT_A_LEVEL`. That retires
      the r5 `fork1h/*` rails, the pre-r19 tine rows, stale VWAP ids and every
      duplicate the old producers left, and it cannot fight a restart: nothing is
      held in memory that the tape does not re-derive.
      (3) `created_ts` IS THE BAR THE EXTREME PRINTED ON, so the board's walk can
      order newest first. (4) `board()` and `walk()` WALK: newest held level each
      side of spot, older ones only if further out, then the board keeps what
      stands beyond each opening-range edge.
      ⚠️ WITHOUT `level_tape` IN ctx THE v4.6 SOURCES RUN UNCHANGED. Only the check
      fixtures take that path (main always supplies the key, None on a dead feed,
      which yields no session levels and retires nothing). Recorded as LVL.10: the
      `check_level_rejection` fixtures must move onto a tape and that branch go.
v4.6  2026-09-13  OTV4TEST r19 — THE FORK PROJECTION IS SEPARATED FROM THE LEVEL
      BOOK. Operator, 2026-09-13: "I want the session extremes separated from the
      1-hr fork object... The job of the fork projection should be a co-informer
      and not conjoined. The projection should only persist as long as the one
      hour fork persists; if a new fork is born a new projection needs to be
      graphed and plotted. There should be no drift from when triggers fired.
      They should be recorded at the moment of the interaction and not in
      hindsight." Four changes, one per clause.
      (1) SEPARATION. `_sources()` SKIPS any pool flagged `moving`. `publish_tines`
      puts every active rail on the map as a named pool, and this loop admitted
      them into a book of HORIZONTAL levels where `_lid` bakes the price into the
      id — so ONE rail became a NEW LEDGER ROW EVERY TIME IT DRIFTED A CENT.
      Measured here: 22 simultaneously-live `1h upper tine` rows spanning 5.79
      points, none retired, including four positions of a fork that had already
      died and been superseded. Mainline reached the same fix from the other end
      (r378: "main.py also stops admitting a MOVING tine into a book of
      horizontal levels").
      ⚠️ r15 BELIEVED IT HAD CLOSED THIS and pinned it with "no fork1h/* row in
      the ledger" — but the mapper names its rails "1h upper tine", so
      `_is_tine()` was False and they entered through the POOL door. The canary
      was scoped to the name that had been REMOVED, not the one that REMAINED.
      (2) IDENTITY. `_fork_key()` is the held fork's three anchors (p0/p1/p2).
      `build_fork_contained` runs every derive, so the OBJECT is rebuilt
      constantly; the anchors are what say whether it is the same fork.
      (3) LIFETIME. On a change of `_fork_key` every tine pierce state is
      dropped. r15 dropped state only when a tine NAME vanished — and a reborn
      fork republishes the SAME three names at new prices, so that condition
      could never fire and a dead fork's interaction state was inherited by its
      successor.
      (4) NO DRIFT. `tines_now(price, minutes_back)` walks the rail back along
      its own slope, and the emitter reads it ONE BAR BACK because the extreme
      being judged is on `df.index[-2]`, the last CLOSED bar. Mainline measured
      the cost of getting this wrong (r377): for a clean touch the extreme sits
      ON the rail, so the reported depth was slope x bars_since — THE STALENESS
      OF THE TOUCH AND NOT ITS DEPTH, clearing the rejection floor on 57.9%% of
      samples from drift alone. `minutes_back=0` is byte-identical to r15.
      🔑 WHAT STAYS CONJOINED, DELIBERATELY: the rails are still READ beside the
      ledger's levels by the emitter and the board. That is the co-informing.
      What ends is the rail being STORED as though it were a level.
v4.5  2026-09-13  OTV4TEST r18 — THE ACCOUNTING RAN PER TICK, NOT PER BAR, AND
      TWO TRADES WERE FIRING ON A WORD THAT DID NOT MEAN WHAT IT SAID. `derive()`
      is called EVERY TICK and the touch/acceptance block had NO BAR GUARD AT ALL
      (the one at `_derive_events` covers only WICKED/REJECTED). Three defects,
      each proven by DRIVING this engine rather than reading it, and each fixed
      to the operator's ruling of 2026-09-13.
      (1) A TOUCH WAS A POLL. One 5m bar polled 20 times scored touch_count=20.
      On this box: QQQ:PDH (R1):717.52 logged 399 touches in a 390-bar session,
      and 566 of 607 levels (93%) logged zero. RULED: one per CLOSED BAR. The
      guard is PER LEVEL, so a level created mid-session counts from its own
      first bar instead of inheriting someone else's.
      (2) ACCEPT_CLOSES=2 COUNTED TICKS AGAINST A 5m CLOSE. The same close was
      re-read every tick, so the SECOND TICK always satisfied it — ~15 seconds
      and ONE close, not two. Operator on moving to two 5m bars: "Hell no. 10
      minutes leaves us nothing actionable, the move is already long over."
      RULED and BUILT: the accounting runs on the CLOSED 1m BAR — the same bar
      the rejection fact already used, so this engine is finally on ONE CLOCK —
      which makes the same ACCEPT_CLOSES=2 mean TWO MINUTES, deterministic
      rather than accidental, and it is a real config key now.
      (3) THE RUN NEVER RESET ON AN INSIDE CLOSE. Only a touch — within
      TOUCH_TOL_PCT — cleared `beyond`, so a close that was plainly inside left
      the run standing: two excursions NINETY MINUTES APART, price six points
      inside for an hour between them, retired the level as ACCEPTED. RULED:
      a close back inside breaks the run.
      ⚠️ WHY THIS WAS NEVER COSMETIC: the runaway ARMS on ACCEPTED (§30), the
      TCS TRIGGERS on it (§34), and acceptance RETIRES the level — pulling it
      off the very board r15 had just repaired. Nothing flagged any of it:
      every gate was green and every existing level check passed.
      🔑 SUPERSEDES r18's bar_ts fix by subsuming it: the ACCEPTED row is
      stamped with the closed 1m bar it was judged on, so the literal "5m" is
      gone for a better reason than the one r18 gave.
v4.4  2026-09-13  OTV4TEST r18 — THE ACCEPTED FACT COULD NOT SAY WHICH BAR MADE
      IT. The ACCEPTED emit site passed the literal string "5m" as `bar_ts` —
      the column whose declared job is "the CLOSED 1m bar that produced it" —
      while the WICKED and REJECTED sites both passed a real timestamp. All 10
      ACCEPTED rows on this box carried `bar_ts='5m'`; all 76 WICKED/REJECTED
      rows carried a bar. TWO CONSEQUENCES, BOTH SILENT. (1) `level_event`'s
      PRIMARY KEY is (symbol, level_id, bar_ts, event) and `insert_level_event`
      is INSERT OR IGNORE, so a SECOND acceptance of the same level was dropped
      with no error — the ledger under-reported acceptances and the under-report
      was invisible. (2) `tcs_plan` keys its once-per-event latch on
      (level_id, bar_ts); with `bar_ts` constant that latch degenerated from
      ONCE PER ACCEPTANCE to ONCE PER LEVEL FOR THE LIFE OF THE PROCESS.
      `sweep_plan` uses the identical idiom on REJECTED and was always correct —
      only the TCS's upstream fact was stamped with a constant.
      ⚠️ FRESHNESS WAS NEVER AFFECTED: `accepted_age_bars` is computed from
      `ts_epoch`, so ACCEPT_FRESH_BARS always read true. The defect is identity,
      not staleness, which is why nothing looked wrong.
      🔑 ACCEPTANCE IS JUDGED ON THE 5m CLOSE (the block above says why), so the
      stamp is the 5m bar's own timestamp — the bar that decided. The fallback
      when no frame is present carries the tick clock rather than a constant, so
      a degenerate tick can never collapse onto a key that already exists.
      FORWARD-ONLY: the 10 rows already written keep `bar_ts='5m'`.
v4.3  2026-09-12  OTV4TEST r15 — TWO LEVEL DEFECTS, mainline r364's fix ported in its
      own shape (one implementation for otv5). (1) A POOL IS CLASSIFIED BY SIDE:
      the detector wrote "high"/"low" and `live_levels()` filters
      support/resistance, so PDH/PDL and the whole R1/R2/R3 ladder were
      invisible to the hunt, the sweep and the TCS — above the live price is
      resistance, below is support, formation as the fallback. (2) A TINE IS
      NEVER STORED: `_tines()` is gone from `_sources()`; `tines_now(price)`
      computes the rails from the fork the ForkEngine holds right now (with a
      rate: `bars_to_contact`), and a dead fork yields nothing on the next read
      — there is no row to go stale. The emitter reads the tines beside the
      ledger's levels and drops their pierce state when the fork goes. (3)
      `board(price, orb_high, orb_low, limit)` — the level board the plans read
      (PLAN_SPEC §38): held levels beyond the opening range ordered outward,
      the rails, four distinct empty answers, `count` never padded.
v4.2  2026-09-08  OTV4TEST r5 — THREE RULINGS FROM THE SWEEP UNTANGLE.
      · THE 1H PITCHFORK'S TINES ARE LEVELS. Moving ones (time + slope), so
        they are keyed on the TINE, not the price: `fork1h/upper`,
        `fork1h/median`, `fork1h/lower` (the `_level_id` price part is fixed at
        0.00 for them), and the price is read at the bar from the fork the
        ForkEngine built (`forks.last_forks["1h"]`). WICKED / REJECTED /
        ACCEPTED accrue on the tine.
      · THE TINE RULE: a top tine can never be a floor, a bottom tine never a
        ceiling. Upper -> resistance only; lower -> support only; median ->
        whichever side price is on at the bar. A wick UP through the lower
        tine is not an event.
      · NO LEVEL INSIDE THE OPENING RANGE. Once the 09:30 five-minute bar has
        printed (ctx["orb"] carries orb_high/orb_low), every level with
        orb_low <= price <= orb_high is retired TRAVERSED — price has been
        through it — and leaves every consumer at once. Tines are exempt
        (they move; the rule is evaluated per bar for them instead: a tine
        inside the range at the bar emits nothing).
v4.1  2026-09-08  OTV4TEST r3 — THE REJECTION FACT, EMITTED ONCE, HERE. Before
      this the only thing in the tree that could see a wick through a pool was
      the sweep strategy's private rule; this engine read the 5m CLOSE and never
      a high or a low, so a rejection was invisible to the derived layer. Now,
      on every CLOSED 1m bar (iloc[-2], processed once per bar timestamp), for
      every live support/resistance level:
        · close beyond the level (outside tolerance)  -> `beyond` += 1; at
          ACCEPT_CLOSES (2, measured) the level retires ACCEPTED_THROUGH and
          an ACCEPTED event is written. Any pierce state is cleared.
        · wick beyond, close inside                    -> WICKED, with depth:
            shallow  pierce <= SHALLOW_PIERCE_PCT (the sweep's strict ceiling,
                     SWEEP_CS_MAX_REJECTION_PCT = 0.25%)
            deep     pierce <= DEEP_PIERCE_PCT (3x, the relaxed ceiling)
            beyond   deeper than that — the level is being TAKEN, not swept;
                     recorded, never rejected
          Operator, 2026-09-08: *"one on a shallow and 2 on a deep pierce just
          to be sure"* — closes back inside COUNT THE WICKING BAR'S OWN CLOSE.
          A shallow pierce is REJECTED on that bar; a deep pierce needs the
          next bar to close inside too. A close beyond in between clears it.
      Consumers read `DerivedStore.latest_rejection()`; nobody re-detects.
      Wicks are tests, closes are acceptance — the whole emitter is that line.

v4.0  2026-08-22  See docs/DERIVED_STORES.md.

🔴 THE OPERATOR'S RULING, 2026-08-22:
    "In a live session a touch count is a HELD level, and when it doesn't
     hold, that level is FINISHED."

A touch is a HOLD. `touch_count` is the length of a run that TERMINATES at the
break — not a score that accumulates forever.

⚠️ THE EXISTING CODE DOES NOT MODEL THIS. `LiquidityPool` carries `touch_count`
and `swept` as separate fields, so a pool can read five-touch AND swept at the
same time — the count survives its own invalidation. Here the break is a
RECORDED EVENT: `retired_ts` + `retired_reason`, after which the level is
history and stops competing for attention.

🔴 BODIES DECIDE, WICKS TEST — universal convention, operator 2026-08-22, taken
from the sweep rules whose own doctrine says it plainly:
    `closes_beyond >= ACCEPT_CLOSES` is no longer a sweep — it is a BREAKOUT.
A wick through a level is a TEST. A close through is ACCEPTANCE.
⚠️ MEASURED, NOT INVENTED: closes_beyond >= 2 blocked 64.5% of named-pool
sweeps (2026-08-15). And it already fixed this exact defect once — the old
`rejection_pct` measured wick-to-last-close and STAMPED A BREAKOUT AS A
CONFIRMED SWEEP, which is precisely the error a wick-based rule produces.

🔴 NY IS THE DANGEROUS SESSION and the operator has been bitten by it. It is
the only session that is LIVE while being traded; Asia and London are closed
and final by the time an RTH box reads them. So "store once at session close"
is WRONG for NY. The resolution is the operator's own framing: **do not read
session fields at all.** Walk outward from price and report the first level
each way WITH ITS PROVENANCE — the session becomes a LABEL ON THE ANSWER, not
the query. A still-forming NY high that is nearest above genuinely IS the level
that matters, because that is where the stops are. `is_live_session` marks it
as still forming so nothing mistakes it for settled.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from derived.base import DerivedEngine

logger = logging.getLogger(__name__)

# A close beyond by less than this is inside the noise of the level itself.
TOUCH_TOL_PCT = 0.0015
# CLOSED 1m BARS beyond required before the level is retired ACCEPTED_THROUGH.
# Inherited from the sweep rules, where it was MEASURED rather than chosen.
# ⚠️ r18 — THE UNIT USED TO BE A LIE. This counted TICKS against a 5m close,
# so the second poll of the SAME bar satisfied it: ~15 seconds, one close, not
# two. It is now what the name says — two CLOSED 1m BARS, so 2 minutes — and it
# is a real key, so the operator can drop it to 1 without a redeploy.
try:
    import config as _cfg
    ACCEPT_CLOSES = int(getattr(_cfg, "LEVEL_ACCEPT_CLOSES", 2))
except Exception:                                               # noqa: BLE001
    _cfg = None
    ACCEPT_CLOSES = 2
# v4.1 — pierce depth bands, from the sweep's own ceiling (strict / relaxed x3).
# 🔴 r18 — THIS KEY DID NOT EXIST IN config.py AND THE DEFAULT WAS WHAT RAN.
# `SWEEP_CS_MAX_REJECTION_PCT` was never defined, so every pierce band on every
# box came from the literal below — while `SWEEP_MIN_REJECTION_PCT = 0.003` sat
# in config with ZERO readers. A live threshold from a getattr default with a
# differently-named orphan beside it is the same defect the predecessor found at
# 15x; ours was 1.20x, which is why nobody saw it. The key is now DEFINED at the
# value that was already running, so this changes no behaviour and makes the
# knob real. The orphan is named in config so the next reader is not misled.
try:
    SHALLOW_PIERCE_PCT = float(getattr(_cfg, "SWEEP_CS_MAX_REJECTION_PCT", 0.0025))
except Exception:                                               # noqa: BLE001
    SHALLOW_PIERCE_PCT = 0.0025
DEEP_PIERCE_PCT = SHALLOW_PIERCE_PCT * 3.0
CLOSES_BACK = {"shallow": 1, "deep": 2}          # operator, 2026-09-08
# r44 — how many consecutive bars may sit beyond a level and still count as ONE
# sweep. A grab is fast; a level price spends twenty minutes under is broken,
# not swept. ⚠️ A PRIOR, NOT A MEASUREMENT — it wants the same study the pierce
# floor got, and it is overridable so that study can move it without a revision.
EXCURSION_MAX_BARS = int(getattr(_cfg, "LEVEL_EXCURSION_MAX_BARS", 10)) if _cfg else 10


def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def pd_ts(ts) -> float:
    """Epoch seconds of a pandas/py timestamp."""
    return float(ts.timestamp())


def board_for(store, symbol: str, price: float, orb_high=None, orb_low=None, limit: int = 3):
    """THE ONE ENTRY POINT EVERY LEVEL-TRADING PLAN CALLS (r33).

    Prefers the LIVE `LevelEngine` — it is the one holding the fork, so the
    rails only exist there — and falls back to an engine over whatever store the
    caller is bound to, which is what the checkers bind and what r13 made
    mandatory (a plan must use ITS store, never reach a global one).

    ⚠️ THIS EXISTS BECAUSE THE FALLBACK ITSELF WAS DUPLICATED. `liquidity_hunt`
    had it; the sweep and the TCS did not, and the first cut of r33 gave them a
    registry-only read that returned ZERO levels under every fixture — five
    green checks went red and that is how it was found. One composition, called
    three times, rather than three copies of the same eight lines.
    """
    eng = None
    try:
        from derived.registry import level_engine
        eng = level_engine()
    except Exception:                                           # noqa: BLE001
        eng = None
    if eng is not None and getattr(eng, "_store", None) is not None:
        return eng.board(price, orb_high, orb_low, limit)
    if store is None:
        return {"state": "no_store", "above": [], "below": [], "tines": [],
                "fork": "absent", "anchor": "spot",
                "count": {"above": 0, "below": 0, "tines": 0}}
    return LevelEngine(store, symbol, forks=None).board(price, orb_high, orb_low, limit)


def _walked(rows, price):
    """r29 — ledger rows (price, ..., created_ts last) through `level_map.walk`:
    the newest held level each side of price, older ones only if further out."""
    from derived import level_map as lm
    import pandas as _pd
    lv = [{"price": float(r[0]), "formed_ts": _pd.Timestamp(float(r[-1] or 0.0), unit="s", tz="UTC"),
           "row": r} for r in rows]
    w = lm.walk(lv, float(price))
    return [x["row"] for x in w["up"] + w["down"]]


def _level_id(symbol: str, provenance: str, price: float) -> str:
    """Stable identity so touches land on the SAME row across ticks.

    ⚠️ ROUNDED INTO THE ID ON PURPOSE. A level is a zone, not a float; without
    rounding, a price that wobbles in the fifth decimal creates a NEW level
    every tick and every one of them has touch_count=1 — which would silently
    destroy the entire premise of scoring by touches.
    """
    return f"{symbol}:{provenance}:{price:.2f}"


class LevelEngine(DerivedEngine):
    name = "levels"
    table = "level_ledger"
    min_interval_s = 0.0

    def __init__(self, store=None, symbol: str = "", forks=None):
        super().__init__(store)
        self.symbol = symbol
        self._forks = forks              # v4.2: the ForkEngine, for tine prices
        self._live: dict = {}
        self._pierce: dict = {}          # level_id -> {"depth", "pierce_pct", "closes_back", "bar_ts"}
        self._excursion: dict = {}       # r44 — level_id -> {"pierce", "bars"}:
                                         # how deep price actually went while it
                                         # was BEYOND the level and had not yet
                                         # closed back. Without this the pierce
                                         # is only ever the reclaim bar's wick.
        self._fork_seen = None           # r19: the anchors of the fork whose projection we hold
        self._last_bar_ts: str = ""
        self.last_events: list = []      # events emitted on the most recent derive()
        # r29 — tape-derived session levels, recomputed once per new tape bar
        self._tape_key = None
        self._tape_srcs: list = []       # (prov, price, kind, tf, live) held levels
        self._tape = None                # r39 — the frame itself: board() computes
                                         # the zone width from it (the instrument's
                                         # own median hourly wick), so it needs the
                                         # bars, not just the levels derived from them.
        self._formed: dict = {}          # level_id -> epoch the extreme printed

    def _sources(self, ctx: dict):
        """(provenance, price, kind, timeframe, is_live) for every known level.

        ⚠️ PROVENANCE TRAVELS WITH THE LEVEL. "Resistance at 218.40, from Asia"
        is a different trade from "resistance at 218.40, from yesterday's
        close", and today the map exposes a bare price with the origin lost.
        """
        liq = ctx.get("liq_map")
        # r33 — `vol` was read here ONLY to mint the VWAP row. VWAP is not a
        # level; the binding goes with the producer rather than sitting unused.
        out = []
        if "level_tape" in ctx:
            # r29 — THE TAPE IS THE SOURCE (see v5.0). The mapper's pools are not.
            out.extend(self._tape_sources(ctx))
            liq = None
        if liq is not None:
            for attr, prov, kind, live in (
                ("prev_day_high", "prev_day", "resistance", 0),
                ("prev_day_low", "prev_day", "support", 0),
                ("asia_session_high", "asia", "resistance", 0),
                ("asia_session_low", "asia", "support", 0),
                ("london_session_high", "london", "resistance", 0),
                ("london_session_low", "london", "support", 0),
                # NY is LIVE — flagged, never treated as settled.
                ("ny_session_high", "ny", "resistance", 1),
                ("ny_session_low", "ny", "support", 1),
            ):
                p = _f(getattr(liq, attr, None))
                if p and p > 0:
                    out.append((prov, p, kind, "1d" if "prev" in prov else "session", live))
            # r15 (mainline r364, LVL.2): a pool is classified by SIDE at write —
            # above the live price is resistance, below is support; with no price,
            # the formation ("high"→resistance). The detector wrote "high"/"low"
            # and live_levels() filters support/resistance, so PDH/PDL and the
            # whole R1/R2/R3 ladder were INVISIBLE to the hunt, the sweep and the
            # TCS (measured on mainline's warehouse, 786 rows, 2026-09-11).
            _px_now = _f(ctx.get("price"))
            for pool in (getattr(liq, "pools", None) or []):
                # 🔴 r19 — A MOVING RAIL IS NOT A LEVEL, AND IT NEVER ENTERS THIS
                # BOOK. `publish_tines` puts every active fork rail on the map as
                # a named pool with `moving=True`; this loop admitted them, and
                # `_lid` bakes the price into the id, so ONE rail became a NEW
                # LEDGER ROW EVERY TIME IT DRIFTED A CENT. Measured on this box:
                # 22 simultaneously-live `1h upper tine` rows spanning 5.79
                # points, none retired, including four positions of a fork that
                # had already died and been superseded.
                # ⚠️ r15 BELIEVED IT HAD CLOSED THIS. It removed `_tines()` from
                # this function and pinned it with "no fork1h/* row in the
                # ledger" — but the mapper's rails are named "1h upper tine",
                # so `_is_tine()` returned False and they came in through the
                # POOL door instead. A canary scoped to the name that was
                # removed, not to the one that remained (§20, one level up).
                # 🔑 THE OPERATOR'S RULE: the fork projection CO-INFORMS, it is
                # not conjoined. Session extremes are stored and have a
                # biography; the rails are a PROJECTION evaluated at a bar index
                # and are served beside the ledger by `tines_now()`, living and
                # dying with the fork that casts them.
                if getattr(pool, "moving", False):
                    continue
                p = _f(getattr(pool, "price", None))
                if p and p > 0:
                    _formed = str(getattr(pool, "kind", "") or "")
                    if _px_now and _px_now > 0:
                        _side = "resistance" if p > _px_now else "support"
                    else:
                        _side = "resistance" if _formed == "high" else "support"
                    out.append((str(getattr(pool, "name", None) or "pool"), p,
                                _side,
                                str(getattr(pool, "timeframe", "") or ""), 0))
        # r33 — VWAP IS NOT A LEVEL IN THIS LEDGER AND NO LONGER ENTERS IT.
        # Operator, 2026-09-17: get everything that does not belong out of the
        # levels ledger. It wrote a `kind="dynamic"` row every tick keyed on the
        # PRICE, so a moving average minted a new identity each time it moved —
        # 844 rows, of which NO READER HAS EVER SEEN ONE: `live_levels()`,
        # `board()` and `walk()` all filter `kind IN ('support','resistance')`,
        # and `board()`'s own docstring says VWAP is not a level a trade
        # contends with. It is the same defect r19 found in the fork rails —
        # a MOVING object given a FROZEN horizontal identity — and the fix is
        # the same one: it is not a source. VWAP remains available to any plan
        # that wants it from `ctx["vol"].vwap`, which is where it always was and
        # where the butterfly's own VWAP band already reads it (BFLY.5).
        # r15 — tines are NOT sources any more: never stored, computed at read
        # (`tines_now`); the emitter reads them beside the ledger's levels.
        return out

    # ── r29 — levels from the tape ─────────────────────────────────────────
    def _tape_sources(self, ctx: dict):
        """Held session levels off the tape plus ledger rows older than the tape.
        Recomputed and RECONCILED once per new tape bar; cached in between."""
        tape = ctx.get("level_tape")
        store = self._store
        sym = self.symbol or ctx.get("symbol") or ""
        if tape is None or len(tape) == 0 or store is None or not sym:
            return list(self._tape_srcs) if tape is not None else []
        self._tape = tape                # r39 — kept for zone_width()
        key = (str(tape.index[-1]), len(tape))
        if key == self._tape_key:
            return list(self._tape_srcs)
        from derived import level_map as lm
        levels = lm.session_levels(tape, accept_closes=ACCEPT_CLOSES, tol_pct=TOUCH_TOL_PCT)
        tape_start = float(tape.index[0].timestamp())
        srcs, formed, spent, tfs = [], {}, {}, {}
        for lv in levels:
            prov = lm.provenance(lv["label"])
            lid = self._lid(sym, prov, lv["price"])
            if lv["spent_ts"] is not None:
                spent[lid] = lv
                continue
            srcs.append((prov, lv["price"], lm.kind_of(lv["side"]), f"session:{lv['date']}", 0))
            formed[lid] = float(pd_ts(lv["formed_ts"]))
            tfs[lid] = f"session:{lv['date']}"
        held_ids = set(formed)
        # the book reaches further than the tape: rows formed before the tape
        try:
            older = store.conn.execute(
                "SELECT level_id, price, kind, provenance, timeframe, created_ts FROM level_ledger"
                " WHERE symbol=? AND retired_ts IS NULL AND timeframe LIKE 'session:%'"
                " AND created_ts < ?", (sym, tape_start)).fetchall()
        except Exception:                                       # noqa: BLE001
            older = []
        for lid, price, kind, prov, tf, created in older:
            if lid not in held_ids and lid not in spent:
                srcs.append((prov, float(price), kind, tf, 0))
                formed[lid] = float(created)
        # r33 — the VWAP id went with the producer; nothing is exempted any more.
        self._reconcile(store, sym, set(formed), formed, spent, tape, tfs=tfs)
        self._formed.update(formed)
        self._tape_srcs = srcs
        self._tape_key = key
        return list(srcs)

    def _reconcile(self, store, sym, keep: set, formed: dict, spent: dict, tape,
                   tfs: Optional[dict] = None) -> None:
        """Retire every live row the tape does not hold; stamp formation times."""
        try:
            rows = store.conn.execute(
                "SELECT level_id, price, kind, provenance, created_ts, timeframe FROM level_ledger"
                " WHERE symbol=? AND retired_ts IS NULL", (sym,)).fetchall()
        except Exception as exc:                                # noqa: BLE001
            logger.warning("[level] reconcile read failed — nothing retired: %s", exc)
            return
        now = time.time()
        fresh_after = now - 60.0 * max(3, ACCEPT_CLOSES + 1)
        retired = 0
        tfs = tfs or {}
        for lid, price, kind, prov, created, tf in rows:
            if lid in keep:
                f = formed.get(lid)
                want_tf = tfs.get(lid) or tf
                if f is not None and (created is None or abs(float(created) - f) > 1.0
                                      or want_tf != tf):
                    # r30 — formation time AND dated timeframe, or the row cannot
                    # be kept once the tape no longer reaches it
                    store.set_level_created(lid, f, want_tf)
                continue
            if kind == "dynamic":
                # r33 — r30's STALE_VWAP sweep retired every id but the current
                # one. With the producer gone nothing creates them, and the rows
                # that existed were DELETED in this revision, so this branch can
                # only ever see a row from a pre-r33 store. Retire it and let it
                # go rather than leaving a `dynamic` row live in a ledger that
                # has no reader for one.
                store.retire_level(lid, now, "NOT_A_LEVEL")
                st = self._live.get(lid)
                if st is not None:
                    st["retired"], st["reason"] = now, "NOT_A_LEVEL"
                retired += 1
                continue
            sp = spent.get(lid)
            if sp is not None:
                ts = float(pd_ts(sp["spent_ts"]))
                store.retire_level(lid, ts, "ACCEPTED_THROUGH")
                st = self._live.get(lid)
                if st is not None:
                    st["retired"], st["reason"] = ts, "ACCEPTED_THROUGH"
                if ts >= fresh_after:
                    bar_ts = str(sp["spent_ts"].tz_convert("America/New_York"))
                    self._emit(store, sym, lid, float(price), kind, prov, bar_ts, now,
                               "ACCEPTED", {"pierce_pct": 0.0, "depth": "accepted",
                                            "closes_back": 0}, None)
            else:
                store.retire_level(lid, now, "NOT_A_LEVEL")
                st = self._live.get(lid)
                if st is not None:
                    st["retired"], st["reason"] = now, "NOT_A_LEVEL"
            self._pierce.pop(lid, None)
            retired += 1
        if retired:
            logger.info("[level] reconciled to the tape — %d row(s) retired, %d held", retired, len(keep))

    def tines_now(self, price: float, minutes_back: float = 0.0):
        """The 1h fork's rails at THIS read, from the fork the ForkEngine holds
        right now — never a stored row (mainline r364, the operator's rule: "as
        long as there's a fork present, there should be a map of its points. And
        if the fork stops emitting, then the map has to go with it"). A dead
        fork yields [] on the next read; there is no row to go stale.
        A tine has a RATE: `bars_to_contact` is the convergence at a standing
        price — None when diverging, never a negative time. Kind by the tine
        rule: upper resistance, lower support, median by the side price is on."""
        fe = self._forks
        fork = (getattr(fe, "last_forks", {}) or {}).get("1h") if fe is not None else None
        if fork is None:
            return []
        idx = _f((getattr(fe, "last_idx", {}) or {}).get("1h")) or 0.0
        slope = _f(getattr(fork, "slope", None)) or 0.0
        # r19 — THE RAIL WHERE IT STOOD, NOT WHERE IT IS. `minutes_back` walks
        # the rail back along its own slope so an interaction is measured at the
        # instant it happened. The tines are parallel, so one slope moves all
        # three. Operator: "There should be no drift from when triggers fired.
        # They should be recorded at the moment of the interaction and not in
        # hindsight." Mainline measured the cost of getting this wrong (r377):
        # for a clean touch the extreme sits ON the rail, so the reported depth
        # was slope x bars_since — THE STALENESS OF THE TOUCH, NOT ITS DEPTH.
        # ⚠️ `minutes_back=0` is the live read and is byte-identical to r15's
        # behaviour, which is what keeps the board unchanged.
        back = (slope * (float(minutes_back or 0.0) / 60.0)) if slope else 0.0
        fkey = self._fork_key()
        out = []
        for name, fn in (("fork1h/upper", "upper_at"), ("fork1h/median", "median_at"),
                         ("fork1h/lower", "lower_at")):
            try:
                p = _f(getattr(fork, fn)(idx))
            except Exception:                                   # noqa: BLE001
                continue
            if not p or p <= 0:
                continue
            p = p - back
            gap = p - (price or 0.0)
            bars = None
            if slope and price:
                b = -gap / slope
                bars = round(b, 2) if b > 0 else None
            out.append({"provenance": name, "price": p,
                        # r33 — THE RAIL'S NATURE NAMES IT; ITS POSITION DECIDES
                        # WHETHER IT COUNTS THIS TICK. `side_ok` below carries the
                        # operator's rule, 2026-09-17: "lower fork tines
                        # projected below spot must inform the plan that they are a
                        # SUPPORT level, and upper fork tines projected above spot
                        # that a valid RESISTANCE exists above spot." A rail's
                        # position moves every tick, so its side is a per-tick fact.
                        # ⚠️ KIND IS NOT RELABELLED AND THAT IS DELIBERATE. r5's TINE
                        # RULE binds — a top tine can never be a floor, a bottom tine
                        # never a ceiling — so a rail on the wrong side of spot is
                        # DROPPED by `board()`, never renamed into the level it is not.
                        # The emitter reads `kind` for WICKED/REJECTED/ACCEPTED and
                        # relabelling would have made a lower rail emit resistance
                        # events the moment price fell under it (caught by
                        # check_level_rejection T2, which went red on the first cut).
                        "kind": "resistance" if name.endswith("upper") else
                                ("support" if name.endswith("lower") else
                                 ("resistance" if price and price < p else "support")),
                        "side_ok": (name.endswith("upper") and bool(price) and p > price)
                                   or (name.endswith("lower") and bool(price) and p < price)
                                   or not name.endswith(("upper", "lower")),
                        "slope_per_bar": slope, "bars_to_contact": bars,
                        "fork_key": fkey,          # r19: which projection this is
                        "minutes_back": float(minutes_back or 0.0),
                        "dist_pct": (abs(gap) / price * 100.0) if price else None})
        return out

    def board(self, price: float, orb_high=None, orb_low=None, limit: int = 3):
        """THE ONE LEVEL BOARD every plan that trades levels reads (r33).

        Two ANCHORINGS, one composition, one source:
        · `orb_high`/`orb_low` GIVEN — the held levels BEYOND the opening range,
          up to `limit` each side, ordered outward from the edge. That is the
          liquidity hunt's reach (r12: the bias is measured from the range edge)
          and it is unchanged.
        · BOUNDS OMITTED — the walk from SPOT: nearest first, each older level
          further out, `limit` each side. The operator's rule, r5 and r29:
          *"the session is a label on the answer, not the query."*

        🔴 THE FORK IS A SECOND PRODUCT, NOT A LEVEL IN THIS LIST. The rails are
        returned in `tines` with `fork` = "built"/"absent" and NEVER merged into
        `above`/`below` (r19: co-inform, do not conjoin). A caller that wants
        them consults them; a caller that does not is unaffected, and an absent
        fork is an explicit answer rather than an empty list.

        Empty answers stay distinct — no_store, no_range, no fork, none that
        side; fewer than `limit` is an answer (`count`), never padded. VWAP is
        not a level a trade contends with."""
        out = {"state": "ok", "above": [], "below": [], "tines": [], "fork": "absent",
               "anchor": "range" if (orb_high and orb_low) else "spot",
               "as_of": time.time()}
        if self._store is None or not price:
            out["state"] = "no_store"
            return out
        _ranged = bool(orb_high and orb_low and orb_high > orb_low)
        if (orb_high or orb_low) and not _ranged:
            # a HALF range is a broken input, not a spot walk — fail closed (§22)
            out["state"] = "no_range"
            return out
        try:
            rows = self._store.conn.execute(
                "SELECT price, kind, provenance, touch_count, is_live_session, level_id, created_ts"
                " FROM level_ledger WHERE symbol=? AND retired_ts IS NULL"
                " AND kind IN ('support','resistance')", (self.symbol,)).fetchall()
        except Exception:                                       # noqa: BLE001
            out["state"] = "no_store"
            return out
        # 🔴 r39 — `_walked` NO LONGER RUNS HERE, AND THAT IS THE WHOLE FIX.
        # It applies r29's rule to individual LEVELS — "the newest each side,
        # older ones only if further out" — which discards cluster members before
        # any grouping can see them. Measured 2026-09-18: 43 ledger rows became
        # 21, and the six levels stacked on spot (716.75 … 718.04) became ONE.
        # Zoning the survivors is inert. The rule still applies, at ZONE
        # granularity, in `_side()` below — group first, then walk what you
        # grouped.
        # r33 — the EDGE each side is measured from: the range when one was given,
        # otherwise spot. One sort, one formatter; only the reference moves.
        edge_up = orb_high if _ranged else price
        edge_dn = orb_low if _ranged else price
        # r39 — the per-LEVEL split is gone: the zone is the object now, and the
        # sides are taken from the zones below.
        def fmt(r, edge):
            return {"price": r[0], "kind": r[1], "provenance": r[2], "touches": r[3],
                    "live": bool(r[4]), "level_id": r[5],
                    "dist_pct": abs(r[0] - edge) / edge * 100.0}
        # ══ r39 — CLUSTER FIRST, THEN WALK THE ZONES ══════════════════════
        # Operator's spec, 2026-09-18: extremes that cluster in close proximity
        # are ONE zone, and "only the outer members of the group declare
        # anything" — a plan trades the NEAR edge, and a breach needs acceptance
        # beyond the FAR edge, which takes the whole cluster with it.
        # 🔴 THE ORDER IS THE WHOLE POINT, AND THE FIRST CUT HAD IT BACKWARDS.
        # `_walked` applies r29's rule — "the newest held level each side, older
        # ones only if further out" — which ALREADY discards most cluster members
        # before any grouping can see them. Zoning the survivors is inert: on
        # 2026-09-18 it grouped 43 levels into zones of n=1 and missed a
        # six-member cluster sitting on top of spot. TWO DEDUPLICATION RULES WERE
        # STACKED, doing different jobs. Now the zone is the object and r29's
        # walk is applied TO ZONES, at zone granularity, which is what the spec
        # implies: group, then walk what you grouped.
        # ⚠️ FAILS OPEN: no width, no grouping — every level is its own zone,
        # which is exactly the pre-r39 board.
        # ⚠️ THE IMPORT IS NOT INSIDE THE try. A failed WIDTH is a board without
        # grouping — degraded but correct, and that is what the except covers. A
        # failed IMPORT is a broken tree, and swallowing it here would leave
        # `_lmz` unbound for `_side()` below, turning a missing module into a
        # NameError raised from the middle of the walk instead of at the import.
        from derived import level_map as _lmz
        try:
            _w = _lmz.zone_width(self._tape) if getattr(self, "_tape", None) is not None else None
        except Exception as exc:                                # noqa: BLE001
            logger.warning("[level] zone width unavailable, board ungrouped: %s", exc)
            _w = None
        out["zone_width"] = _w

        import pandas as _pdz
        _lv = [{"price": float(r[0]),
                "formed_ts": _pdz.Timestamp(float(r[-1] or 0.0), unit="s", tz="UTC"),
                "row": r} for r in rows]
        _zs = _lmz.zones(_lv, _w) if _w else [
            {"lo": x["price"], "hi": x["price"], "members": [x], "seed": x} for x in _lv]

        # a zone is walked by its NEAR edge and dated by its NEWEST member, so
        # r29's rule reads exactly as it always did — one rung further out each
        # time — only the rungs are zones now.
        def _side(edge, ascending):
            reps = []
            for z in _zs:
                if ascending and z["lo"] <= edge:
                    continue
                if (not ascending) and z["hi"] >= edge:
                    continue
                near = z["lo"] if ascending else z["hi"]
                reps.append({"price": near, "formed_ts": z["seed"]["formed_ts"], "z": z})
            w2 = _lmz.walk(reps, float(edge))
            return (w2["up"] if ascending else w2["down"])

        def fmtz(rep, edge, ascending):
            z = rep["z"]
            member = min(z["members"], key=lambda m: abs(m["price"] - edge))
            d = fmt(member["row"], edge)
            d.update({"zone_lo": z["lo"], "zone_hi": z["hi"], "zone_n": len(z["members"]),
                      "near_edge": z["lo"] if ascending else z["hi"],
                      "far_edge": z["hi"] if ascending else z["lo"],
                      "zone_ids": [m["row"][5] for m in z["members"]]})
            return d

        out["above"] = [fmtz(r, edge_up, True) for r in _side(edge_up, True)[:limit]]
        out["below"] = [fmtz(r, edge_dn, False) for r in _side(edge_dn, False)[:limit]]
        # 🔴 THERE IS NO "INSIDE" ANSWER. Operator, 2026-09-18: *"one zone
        # containing spot isn't a zone, then. It's done — as a zone is defined,
        # it's finished. There's no reclaim trade for that."* A zone is a region
        # price held AWAY from; once price is inside it, its near edge has been
        # gone through and the object is spent. It is RETIRED in `derive()`
        # (TRAVERSED), not reported here — which makes r5's opening-range rule
        # one instance of a general one rather than a special case.
        out["tines"] = [t_ for t_ in self.tines_now(price) if t_.get("side_ok", True)]
        for t_ in out["tines"]:
            t_["level_id"] = self._lid(self.symbol, t_["provenance"], 0.0)
        out["fork"] = "built" if out["tines"] else "absent"
        out["count"] = {"above": len(out["above"]), "below": len(out["below"]),
                        "tines": len(out["tines"])}
        return out

    @staticmethod
    def _is_tine(prov: str) -> bool:
        return str(prov).startswith("fork1h/")

    def _fork_key(self):
        """The 1h fork's IDENTITY — its three anchors — or None if none is held.

        🔑 r19 — A NEW FORK IS A NEW PROJECTION, AND THE OLD ONE'S STATE GOES
        WITH IT. `build_fork_contained` runs every derive, so the Fork OBJECT is
        rebuilt constantly; what says whether it is the SAME fork is `p0/p1/p2`.
        ⚠️ r15's drop was keyed on the tine's NAME disappearing — and a reborn
        fork publishes the SAME three names at new prices, so the condition could
        never fire and a dead fork's pierce state was inherited by its successor.
        The operator: "if a new fork is born a new projection needs to be
        graphed and plotted."
        """
        fe = self._forks
        fork = (getattr(fe, "last_forks", {}) or {}).get("1h") if fe is not None else None
        if fork is None:
            return None
        key = []
        for a in ("p0", "p1", "p2"):
            piv = getattr(fork, a, None)
            if piv is None:
                return None
            key.append((_f(getattr(piv, "idx", None)), _f(getattr(piv, "price", None))))
        return tuple(key)

    def _lid(self, sym: str, prov: str, price: float) -> str:
        # a tine's identity is the tine; its price moves every bar
        return _level_id(sym, prov, 0.0 if self._is_tine(prov) else price)

    def derive(self, ctx: dict) -> int:
        store = self._store
        if store is None:
            return 0
        sym = self.symbol or ctx.get("symbol") or ""
        price = _f(ctx.get("price"))
        if not sym or not price:
            return 0

        # ⚠️ THE LAST CLOSED BAR DECIDES, NOT THE LIVE PRICE. Bodies decide,
        # wicks test — so acceptance is judged on a CLOSE. Using `price`
        # mid-bar would retire levels on wicks, which is the failure the
        # convention exists to prevent.
        close = price
        df = ctx.get("df_5m")
        try:
            if df is not None and not getattr(df, "empty", True):
                close = _f(df["close"].iloc[-1]) or price
        except Exception:                                       # noqa: BLE001
            pass

        # ── r18 — THE ACCOUNTING RUNS ON A CLOSED 1m BAR, NOT ON A TICK ──
        # Operator's rulings, 2026-09-13. `derive()` is called EVERY TICK and the
        # touch/acceptance block had no bar guard at all, so both counters
        # advanced ~4x a minute: one 5m bar polled 20 times scored 20 "touches",
        # and ACCEPT_CLOSES=2 was satisfied by the SECOND TICK re-reading the
        # SAME close — 15 seconds, not the two closes the constant names.
        # 🔑 THE BAR IS THE 1m CLOSE, THE SAME ONE THE REJECTION FACT USES.
        # Acceptance read `df_5m` and was the only part of this engine on a
        # different clock. Operator on two 5m bars: *"Hell no. 10 minutes leaves
        # us nothing actionable, the move is already long over."* On closed 1m
        # bars the same ACCEPT_CLOSES=2 is TWO MINUTES and is now deterministic
        # rather than accidental — and it is a real config key, so it moves
        # without a redeploy.
        acc_bar_ts, bar_close = "", None
        d1 = ctx.get("df_1m")
        try:
            if d1 is not None and len(d1) >= 2:
                acc_bar_ts = str(d1.index[-2])          # [-2] = the CLOSED bar
                bar_close = float(d1.iloc[-2]["close"])
        except Exception:                                       # noqa: BLE001
            acc_bar_ts, bar_close = "", None

        now = time.time()
        written = 0
        self.last_events = []
        orb = ctx.get("orb")
        rng_lo = _f(getattr(orb, "orb_low", None)) if orb is not None else None
        rng_hi = _f(getattr(orb, "orb_high", None)) if orb is not None else None
        in_range = (lambda p: bool(rng_lo and rng_hi and rng_lo <= p <= rng_hi))

        # ══ r39 — A ZONE THAT HOLDS PRICE IS FINISHED ═════════════════════════
        # Operator, 2026-09-18: *"one zone containing spot isn't a zone, then.
        # It's done — as a zone is defined, it's finished. There's no reclaim
        # trade for that."* A zone is a region price held AWAY from; once price
        # is inside it, its near edge has been gone through and the object is
        # spent. EVERY member retires, not just the one price crossed.
        # 🔑 THIS MAKES r5's OPENING-RANGE RULE A SPECIAL CASE OF A GENERAL ONE.
        # "Everything between orb_low and orb_high is retired TRAVERSED — price
        # has been through it" is the same statement about a different region.
        # ⚠️ JUDGED ON A CLOSED BAR, NOT A TICK, and that is deliberate. r5 ruled
        # that a wick never spends a level — bodies decide, wicks test — and
        # retirement has no undo, so a tick-rate test would let a single wick
        # into a cluster consume six levels permanently. The opening-range rule
        # stays at tick rate because its boundary is FIXED once the 09:30 bar
        # prints; a zone's boundary moves with the book, so it needs the close.
        _zone_gone: set = set()
        if bar_close:
            try:
                from derived import level_map as _lmz
                _zw = _lmz.zone_width(self._tape) if getattr(self, "_tape", None) is not None else None
                if _zw:
                    _src = [{"price": float(p), "formed_ts": self._formed.get(
                                self._lid(sym, pr, p), now)}
                            for pr, p, k, _tf, _lv in self._tape_srcs
                            if k in ("support", "resistance")]
                    for _z in _lmz.zones(_src, _zw):
                        if _z["lo"] <= bar_close <= _z["hi"]:
                            _zone_gone = {round(m["price"], 4) for m in _z["members"]}
                            break
            except Exception as exc:                            # noqa: BLE001
                logger.warning("[level] zone traversal check skipped: %s", exc)

        for prov, lvl_price, kind, tf, live in self._sources(ctx):
            lid = self._lid(sym, prov, lvl_price)
            st = self._live.get(lid)
            if st is None:
                st = {"created": self._formed.get(lid, now), "touches": 0, "beyond": 0,
                      "last_touch": None, "retired": None, "reason": None}
                self._live[lid] = st
            if st["retired"]:
                continue                       # finished — operator's ruling
            # v4.2 — NO LEVEL INSIDE THE OPENING RANGE (tines exempt: they move)
            _in_zone = round(lvl_price, 4) in _zone_gone
            if kind in ("support", "resistance") and not self._is_tine(prov) and (
                    in_range(lvl_price) or _in_zone):
                st["retired"] = now
                st["reason"] = "TRAVERSED"
                self._pierce.pop(lid, None)
                logger.info("[level] %s %s %.2f (%s) retired TRAVERSED — %s",
                            sym, kind, lvl_price, prov,
                            "price closed inside its zone" if _in_zone
                            else f"inside the opening range {rng_lo:.2f}-{rng_hi:.2f}")
                store.upsert_level((lid, sym, lvl_price, kind, prov, tf,
                                    st["created"], st["touches"], st["last_touch"],
                                    st["beyond"], st["retired"], st["reason"], int(live)))
                written += 1
                continue

            tol = lvl_price * TOUCH_TOL_PCT
            # ⚠️ ONE CLOSED BAR, ONCE — per level, so a level created mid-session
            # starts counting from ITS first bar rather than inheriting a guard.
            # Everything below this line is bar-rate; everything above is tick-rate.
            if acc_bar_ts and st.get("last_bar") != acc_bar_ts:
                st["last_bar"] = acc_bar_ts
                bc = bar_close if bar_close is not None else close
                if kind == "resistance":
                    accepted = bc > lvl_price + tol
                elif kind == "support":
                    accepted = bc < lvl_price - tol
                else:
                    accepted = False           # VWAP is crossed, not broken

                if accepted:
                    st["beyond"] += 1
                    if st["beyond"] >= ACCEPT_CLOSES:
                        st["retired"] = now
                        st["reason"] = "ACCEPTED_THROUGH"
                        self._pierce.pop(lid, None)
                        self._emit(store, sym, lid, lvl_price, kind, prov,
                                   acc_bar_ts, now, "ACCEPTED",
                                   {"pierce_pct": 0.0, "depth": "accepted",
                                    "closes_back": 0}, bc)
                elif abs(bc - lvl_price) <= tol:
                    # Held at the level — that is a TOUCH. ONE per closed bar
                    # (operator, 2026-09-13), never one per poll.
                    st["touches"] += 1
                    st["last_touch"] = now
                    st["beyond"] = 0           # the run of acceptance is broken
                else:
                    # 🔴 A CLOSE BACK INSIDE BREAKS THE RUN (operator, 2026-09-13).
                    # Until now ONLY a touch — within TOUCH_TOL_PCT of the level —
                    # reset `beyond`, so a close that was plainly, obviously inside
                    # left the run standing. Two excursions NINETY MINUTES APART,
                    # with price six points inside for an hour in between, read as
                    # "two consecutive closes beyond" and retired the level.
                    st["beyond"] = 0

            store.upsert_level((lid, sym, lvl_price, kind, prov, tf,
                                st["created"], st["touches"], st["last_touch"],
                                st["beyond"], st["retired"], st["reason"],
                                int(live)))
            written += 1
        written += self._derive_events(ctx, sym, now)
        return written

    # ── v4.1: the rejection fact, from the CLOSED 1m bar ────────────────
    def _emit(self, store, sym, lid, lvl, kind, prov, bar_ts, now, name, p, close):
        row = (sym, lid, bar_ts, now, name, lvl, kind, prov,
               float(p["pierce_pct"]), p["depth"], int(p["closes_back"]), close)
        self.last_events.append({"event": name, "level_id": lid, "price": lvl,
                                 "kind": kind, "provenance": prov, "bar_ts": bar_ts,
                                 "pierce_pct": p["pierce_pct"], "depth": p["depth"],
                                 "closes_back": p["closes_back"], "bar_close": close})
        logger.info("[level] %s %s %s %.2f (%s) pierce %.3f%% %s closes_back=%d bar=%s",
                    sym, name, kind, lvl, prov, p["pierce_pct"] * 100, p["depth"],
                    p["closes_back"], bar_ts)
        return store.insert_level_event(row) if store is not None else 0

    def _derive_events(self, ctx: dict, sym: str, now: float) -> int:
        store = self._store
        df = ctx.get("df_1m")
        try:
            if df is None or len(df) < 2:
                return 0
            bar = df.iloc[-2]
            bar_ts = str(df.index[-2])
            hi, lo, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        except Exception:                                       # noqa: BLE001
            return 0
        if bar_ts == self._last_bar_ts:
            return 0                                 # one closed bar, once
        self._last_bar_ts = bar_ts
        written = 0
        _px = _f(ctx.get("price")) or close
        # r15 — the tines are read, not stored: they join the ledger's levels here
        # for the emitter only, and vanish with the fork (their pierce state too)
        # 🔴 r19 — THE PROJECTION LIVES AND DIES WITH ITS FORK. The rails are
        # evaluated ONE BAR BACK because that is the bar whose extreme is being
        # judged: `bar`/`hi`/`lo` below come from df.index[-2], the last CLOSED
        # bar, so reading the rail at "now" measured the interaction against a
        # rail that had already moved past it.
        _tines = self.tines_now(_px, minutes_back=1.0)
        _fkey = self._fork_key()
        if _fkey != self._fork_seen:
            # A NEW FORK (or none) — the old projection's interaction state is
            # not inherited. r15 dropped state only when a tine NAME vanished,
            # and a reborn fork republishes the same three names at new prices,
            # so that condition could never fire: a dead fork's pierce state
            # lived on inside its successor's rails.
            if self._fork_seen is not None:
                logger.info("[level] 1h fork replaced — dropping %d tine pierce "
                            "state(s); a new projection starts clean",
                            sum(1 for k in self._pierce if ":fork1h/" in k))
            for k in [k for k in self._pierce if ":fork1h/" in k]:
                self._pierce.pop(k, None)
            self._fork_seen = _fkey
        srcs = [(p_, l_, k_, t_, v_) for p_, l_, k_, t_, v_ in self._sources(ctx)]
        srcs += [(t_["provenance"], t_["price"], t_["kind"], "1h", 1) for t_ in _tines]
        for prov, lvl, kind, tf, live in srcs:
            if kind not in ("support", "resistance"):
                continue                             # VWAP is crossed, not swept
            lid = self._lid(sym, prov, lvl)
            if self._is_tine(prov):
                orb = ctx.get("orb")
                lo_, hi_ = (_f(getattr(orb, "orb_low", None)), _f(getattr(orb, "orb_high", None))) if orb is not None else (None, None)
                if lo_ and hi_ and lo_ <= lvl <= hi_:
                    continue                   # a tine inside the range, this bar
            else:
                st = self._live.get(lid)
                if st is None or st["retired"]:
                    continue
            tol = lvl * TOUCH_TOL_PCT
            # the CLOSE keeps the touch tolerance (inside it is noise, as
            # derive() counts touches); the WICK does not — a wick through
            # the level is a wick through the level, and the depth bands
            # (0.25% / 0.75%) are what grade it, not the 0.15% close noise.
            # "inside" means the close is on the HELD side of the level — not
            # merely within the touch tolerance on the far side, which is a
            # bar trading beyond it (v4.2, found by T2: a bar wholly below a
            # support is not a rejection of it).
            if kind == "resistance":
                close_beyond = close > lvl + tol
                close_held = close <= lvl
                wick_beyond = hi > lvl
                pierce = (hi - lvl) / lvl if wick_beyond else 0.0
            else:
                close_beyond = close < lvl - tol
                close_held = close >= lvl
                wick_beyond = lo < lvl
                pierce = (lvl - lo) / lvl if wick_beyond else 0.0
            if close_beyond:
                # a rejection cannot survive a close through the level;
                # acceptance itself is counted by derive() on the 5m close.
                self._pierce.pop(lid, None)
                self._excursion.pop(lid, None)
                continue
            if not close_held:
                # ══ r44 — THE EXCURSION IS REMEMBERED, NOT DISCARDED ═════════
                # 🔴 THIS `continue` THREW AWAY THE SWEEP ITSELF. A bar that
                # trades beyond the level and does NOT close back is not noise —
                # it is the grab. The old code skipped it, so `pierce` was only
                # ever measured on the ONE bar that closed back, and every bar
                # of the actual excursion was lost.
                # ⚠️ THE BIAS RAN AGAINST THE BEST SETUPS. A one-bar
                # wick-and-reclaim measured correctly; a REAL liquidity grab —
                # price under the level for two or three bars while stops are
                # taken — always reported the shallowest bar of the sequence.
                # The more convincing the sweep, the shallower the number.
                # MEASURED 2026-09-18 over 182 banked REJECTED events: 58 had a
                # true excursion >1.5x what was recorded, and 23 were refused as
                # "a touch, not a sweep" when the excursion CLEARED the sweep's
                # floor. Operator's own case, 09-18 10:16-10:18 on london
                # 716.38: true pierce 0.0681%, recorded 0.0102% — 6.7x short,
                # against a 0.02% minimum it would have passed by 3.4x.
                if wick_beyond:
                    ex = self._excursion.get(lid) or {"pierce": 0.0, "bars": 0}
                    ex["pierce"] = max(float(ex["pierce"]), pierce)
                    ex["bars"] = int(ex["bars"]) + 1
                    # ⚠️ A CAP, BECAUSE A SWEEP IS FAST. A level price spends a
                    # long time beneath is not being swept, it is being broken,
                    # and carrying that depth forward would dress a breakdown up
                    # as a grab. Overridable; it wants its own measurement.
                    if ex["bars"] > EXCURSION_MAX_BARS:
                        self._excursion.pop(lid, None)
                    else:
                        self._excursion[lid] = ex
                continue
            # ── the bar CLOSED BACK: this is the reclaim ────────────────────
            ex = self._excursion.pop(lid, None)
            if ex and float(ex["pierce"]) > pierce:
                # the sweep's depth is how far price actually went, not the
                # wick of whichever bar happened to close back.
                pierce = float(ex["pierce"])
                wick_beyond = True          # it DID go beyond — on an earlier bar
            ps = self._pierce.get(lid)
            if wick_beyond:
                depth = ("shallow" if pierce <= SHALLOW_PIERCE_PCT
                         else "deep" if pierce <= DEEP_PIERCE_PCT else "beyond")
                ps = {"depth": depth, "pierce_pct": pierce, "closes_back": 1, "bar_ts": bar_ts}
                self._pierce[lid] = ps
                written += self._emit(store, sym, lid, lvl, kind, prov, bar_ts, now,
                                      "WICKED", ps, close)
            elif ps:
                ps["closes_back"] += 1
            if ps and ps["depth"] in CLOSES_BACK and ps["closes_back"] >= CLOSES_BACK[ps["depth"]]:
                written += self._emit(store, sym, lid, lvl, kind, prov, bar_ts, now,
                                      "REJECTED", ps, close)
                self._pierce.pop(lid, None)
        return written

    def walk(self, price: float, limit: int = 3):
        """The walk from SPOT — nearest first, each older level further out.

        🔴 THE OPERATOR'S OWN FRAMING: walk up from where price is until you
        hit the last session high — which could be overnight, previous day or
        previous session — and the same going down. **The session is a label on
        the answer, not the query.**

        ⚠️ DISTANCE ORDERS, TOUCH COUNT SCORES. The nearest level may be a
        one-touch artifact while the one 0.4% beyond has held five times.

        r33 — THIS DELEGATES TO `board()` AND HOLDS NO COMPOSITION OF ITS OWN.
        It was a second implementation of the same query over the same rows, and
        two implementations is how the plans came to disagree. Kept as a name
        because `main.py` and `derived/snapshot.py` call it; it returns only the
        levels, since its callers never consulted the fork.
        """
        b = self.board(price, limit=limit)
        return {"above": b.get("above", []), "below": b.get("below", [])}
