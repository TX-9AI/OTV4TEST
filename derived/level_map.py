"""
derived/level_map.py  v1.2
v1.2  2026-09-18  OTV4TEST r39 (LVL.13) — A CLUSTER OF EXTREMES IS ONE ZONE, AND
      ITS WIDTH IS MEASURED, NOT STORED. Operator, 2026-09-17: *"When session
      extremes, by recency first, cluster in close proximity I want the extremes
      of the outermost (highest, lowest) of the cluster to count as a touch when
      the nearest part of the zone is tested, and breached when the furthest part
      of the cluster is accepted beyond… I'm thinking an area defined by the
      region several 1-day wicks occupy in a concurrent time frame."*
      🔑 THE WIDTH IS THE INSTRUMENT'S OWN MEDIAN LARGER-SIDE HOURLY WICK,
      recomputed every board. Measured 2026-09-18 on three symbols: the wick
      holds at 31-37% of the median hourly RANGE while the same wick as a
      percent of spot spans FOUR-FOLD across them. A stored percentage would
      have been wrong on MU by roughly 4x, which is why nothing here is a
      constant. Operator: *"the width ruling is sound as a one size fits most."*
      ⚠️ `zones()` MERGES TO A FIXED POINT, and that is not fussiness. The first
      cut made one pass over a sorted list and printed `719.70-722.13` beside a
      SEPARATE `721.89` — a price inside another zone's span, because a merge
      can widen a zone past a neighbour already passed. It now re-sorts and
      re-merges until nothing changes, so the partition cannot depend on the
      order levels arrived in.
      ⚠️ NO WIDTH FAILS OPEN, one zone per level — a board with no tape is the
      pre-zone board, never an empty one.
v1.1  2026-09-18  OTV4TEST r36 — THE LEVEL BOARD IS BUILT FROM THE HOURLY TAPE,
      EXCLUSIVELY, AND IT REACHES TWELVE WEEKS INSTEAD OF NINE DAYS.
      Operator, reading his own 1D chart against the live board: three of his
      five levels above spot did not exist in the ledger at all. Cause: this
      read 1m, and retention keeps 1m for FIVE DAYS while keeping 1h for SIXTY.
      Not missing data — UNREAD data (§39.2).
      🔴 DAILY BARS WERE TRIED FIRST AND RULED OUT. They cannot see overnight:
      merged `1d` missed the true 24h low by $2.33 on average and $9.13 at worst,
      because DXFeed aggregates a daily candle over trading hours and the `_EXT`
      daily bar is a near-copy of the RTH one. Operator: *"the outside RTH levels
      are the ones I'm most expecting to get swept."* `daily_levels` and
      `load_daily` were written, measured, and DELETED in the same revision.
      ⚠️ AND THE DAILY READER HAD A DEFECT WORTH REMEMBERING even though it was
      deleted: it took the trading date from the stamp's ET date. DXFeed stamps a
      daily candle at 00:00 UTC OF ITS TRADING DATE, so converting to ET rolled
      every level back one session. Proven wrong 7 of 7 against the 1m tape. The
      operator's rule is TIME FIRST, so a board dated one session early is
      ordered wrong — it would not have been cosmetic.
v1.0  2026-09-14  OTV4TEST r29 (LVL.8, LVL.9) — LEVELS ARE BUILT FROM THE TAPE.
      Operator, 2026-09-14: *"Levels are session extremes that held. Starting
      from spot, map the most recent up/down levels going backwards in time and
      further up/down from the recent ones. A level is spent if it didn't hold &
      price accepted through it."* And: *"Straight from the tape I want you to
      properly construct the levels."*

      WHY. The ledger could only ADD. Nothing retired a level for being old
      (LVL.8), a wick "broke" a ladder rung in the mapper while the operator's
      rule spends a level only on ACCEPTANCE, and rows from dead producers
      (the r5 `fork1h/*` rails, the pre-r19 `1h upper tine` pool rows) stayed
      live forever. Measured on the box at 09:10 ET: 619 of 624 rows live, back
      to 09-08, including Wednesday's frozen fork rails at 705.99/716.08/726.17.

      THREE PURE STEPS, NO STORE, NO CLOCK OF ITS OWN:
        1. `closed_sections(df)` — every CLOSED session's high and low, with the
           bar each printed on. The session clock is the mapper's, imported, not
           re-declared (Asia 00-08 UTC, London 08-13 UTC, NY = RTH at hour
           granularity by the ET date): one definition of a session.
        2. `spent_at(...)` — the first moment price ACCEPTED through a level:
           `accept_closes` CONSECUTIVE closed 1m bars beyond it, after it formed.
           A wick through is not acceptance and does not spend it (r3/r18).
        3. `walk(levels, spot)` — from spot outward: the newest held extreme
           above, then each older one only if it is FURTHER up than the last
           kept; the same below. A held level nearer than a newer one is not
           deleted — it is simply not on the walk until the newer one is spent.

      ⚠️ THE WALK IS A VIEW, NOT A STATE. It depends on spot, so it is computed
      at read. What is STORED is the biography: formed, held, spent.
      ⚠️ A SECTION THE TAPE DOES NOT FULLY COVER IS NOT A LEVEL (mapper A2.1):
      an extreme that cannot be proven is not admitted at a wrong price.

      THE RULINGS THIS IMPLEMENTS, ALREADY ON RECORD (read, not re-asked):
      fork PLAN_SPEC §31.1 — *"Age does not matter. A previously held extreme is
      enough"*; spent = the breach ACCEPTED, two closes beyond. Mainline PLAN_SPEC
      §38 / LVL.3 — one board all plans read, newest first, each rung further out,
      *"we go back as far as we go and we map the levels with what we have"*,
      nothing in memory, tines never stored. Mainline LVL.17 — the tape is walked,
      and history seeds DURABILITY, never an EVENT.
      ⚠️ NO PRINT FILTER, BY RULING (2026-09-14): *"The highest high of the session
      that held, or the lowest low."* A lone print that price never accepted
      through is a held extreme.
"""

from __future__ import annotations

import sqlite3

from datetime import datetime, timezone
from typing import List, Optional

import numpy as np
import pandas as pd

from analysis.liquidity_mapper import LiquidityMapper

SIDE_HIGH, SIDE_LOW = "high", "low"


TAPE_INTERVAL = "1h"   # r36 — the level board's one granularity


def _utc_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(df.index)
    return idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")


def closed_sections(df: pd.DataFrame, now_utc: Optional[datetime] = None) -> List[dict]:
    """Every session the 1m tape FULLY covers and that has CLOSED.

    -> [{date, label, start, end, high, high_ts, low, low_ts}], oldest first.
    `now_utc` defaults to the last bar; a section is closed when a bar stamped
    at/after its end exists or `now_utc` is past its end.
    """
    if df is None or len(df) == 0:
        return []
    idx = _utc_index(df)
    frame_start, frame_end = idx[0], idx[-1]
    now_ts = pd.Timestamp(now_utc).tz_convert("UTC") if now_utc is not None else frame_end
    mapper = LiquidityMapper.__new__(LiquidityMapper)
    order = ("Asia", "London", "NY")
    out = []
    for d in sorted({x for x in idx.date}):
        for label, h0, h1 in mapper._sections_for(d):
            start = pd.Timestamp(datetime(d.year, d.month, d.day, h0, tzinfo=timezone.utc))
            end = pd.Timestamp(datetime(d.year, d.month, d.day, h1, tzinfo=timezone.utc))
            if frame_start > start:
                continue                       # left-truncated: unprovable
            if max(frame_end, now_ts) < end:
                continue                       # still forming
            m = (idx >= start) & (idx < end)
            if not m.any():
                continue                       # no tape (weekend, holiday)
            sd = df[m]
            hi_i = int(sd["high"].to_numpy().argmax())
            lo_i = int(sd["low"].to_numpy().argmin())
            sidx = idx[m]
            out.append({"date": d, "label": label, "start": start, "end": end,
                        "high": float(sd["high"].iloc[hi_i]), "high_ts": sidx[hi_i],
                        "low": float(sd["low"].iloc[lo_i]), "low_ts": sidx[lo_i]})
    out.sort(key=lambda s: (s["date"], order.index(s["label"])))
    return out


def spent_at(df: pd.DataFrame, price: float, side: str, formed_ts,
             accept_closes: int = 2, tol_pct: float = 0.0) -> Optional[pd.Timestamp]:
    """The close of the bar that completed acceptance through `price`, or None.

    A HIGH is spent by `accept_closes` consecutive 1m CLOSES above it; a LOW by
    that many below it — counted only on bars AFTER the one it formed on.
    """
    if df is None or len(df) == 0:
        return None
    idx = _utc_index(df)
    after = idx > pd.Timestamp(formed_ts).tz_convert("UTC")
    closes = df["close"].to_numpy()[after]
    if len(closes) == 0:
        return None
    tol = price * float(tol_pct or 0.0)          # the level engine's own close tolerance
    beyond = closes > price + tol if side == SIDE_HIGH else closes < price - tol
    run = 0
    stamps = idx[after]
    for i, b in enumerate(beyond):
        run = run + 1 if b else 0
        if run >= max(1, int(accept_closes)):
            return stamps[i]
    return None


def session_levels(df: pd.DataFrame, now_utc: Optional[datetime] = None,
                   accept_closes: int = 2, tol_pct: float = 0.0) -> List[dict]:
    """Every closed session's high and low as a level with its biography.

    -> [{name, label, date, side, price, formed_ts, spent_ts}] — `spent_ts` None
    means it HELD through the end of the tape.
    """
    out = []
    for s in closed_sections(df, now_utc):
        for side in (SIDE_HIGH, SIDE_LOW):
            price, formed = s[side], s[f"{side}_ts"]
            out.append({
                "name": f"{s['label']} {'High' if side == SIDE_HIGH else 'Low'} {s['date']:%m-%d}",
                "label": s["label"], "date": s["date"], "side": side,
                "price": price, "formed_ts": formed,
                "spent_ts": spent_at(df, price, side, formed, accept_closes, tol_pct),
            })
    return out


def zone_width(df: pd.DataFrame) -> Optional[float]:
    """The instrument's own MEDIAN HOURLY WICK — the zone width, computed, never
    stored (r39, operator's ruling 2026-09-18: *"continuously"*).

    🔑 WHY A COMPUTED WIDTH AND NOT A CONSTANT. It self-calibrates per symbol and
    per volatility regime, so there is no number to go stale and nothing to tune.
    §31 barely applies: this is not a fitted parameter, it is a measured property
    of the tape that moves when the tape moves.

    🔴 MEASURED ON THREE INSTRUMENTS, 2026-09-18, and the RATIO is what
    replicates — not the percentage:
        QQQ  878 bars   wick 0.64 / range 1.73 = 37%   (0.089% of spot)
        MU   595 bars   wick 3.45 / range 9.95 = 35%   (0.362% of spot)
        SPX  284 bars   wick 5.62 / range 18.04 = 31%  (0.073% of spot)
    Percent-of-spot spans FOUR-FOLD across them, so storing the width that way —
    which is what I proposed first — would have given MU a zone four times too
    tight. The wick/range ratio holds at 31-37% across prices of 717, 953 and
    7686. That is why this returns a MEASUREMENT and not a fraction of spot.

    ⚠️ "ONE SIZE FITS MOST", IN THE OPERATOR'S WORDS, AND THE LIMIT IS NAMED.
    On a THIN board the width barely matters — SPX held 12 levels, all NY, and
    the board was identical from half the median wick to twice it. It is on a
    DENSE board that the choice does work, which is where it was measured (QQQ,
    43 held levels, where 0.50 and 0.64 give different answers).
    ⚠️ AND THE SPX LEG IS THINNER THAN IT LOOKS: its warehouse hourly bars are
    July-August backfills only, because `s3_push` advances a high-water mark on
    the bar's own timestamp and never re-pushes a mutable row (PRE.5). Replicated
    cleanly on QQQ and MU; on SPX's older data only.

    -> the width, or None when the frame cannot support one.
    """
    if df is None or len(df) == 0:
        return None
    o = df["open"].to_numpy(); c = df["close"].to_numpy()
    h = df["high"].to_numpy(); l = df["low"].to_numpy()
    body_hi = np.maximum(o, c); body_lo = np.minimum(o, c)
    wick = np.maximum(h - body_hi, body_lo - l)
    wick = wick[np.isfinite(wick) & (wick >= 0)]
    if wick.size == 0:
        return None
    w = float(np.median(wick))
    return w if w > 0 else None


def zones(levels: List[dict], width: float) -> List[dict]:
    """Cluster held levels into ZONES — the operator's spec, 2026-09-18.

    🔴 HIS RULES, VERBATIM: *"When session extremes, by recency first, cluster in
    close proximity I want the extremes of the outermost (highest, lowest) of the
    cluster to count as a touch when the nearest part of the zone is tested, and
    breached when the furthest part of the cluster is accepted beyond"*; *"it's
    just grouping and only the outer members of the group declare anything"*;
    *"when we have a breach of the cluster everything that was a part of the
    cluster needs to go with it."*

    A zone is `{lo, hi, members, seed}`. `lo`/`hi` are its ONLY recording prices:
    a test of the NEAR edge registers the touch, acceptance beyond the FAR edge
    breaches it and retires EVERY member. Interior members declare nothing — no
    WICKED, no REJECTED, no ACCEPTED, no touch count. They are the zone's
    biography, not its voice. `seed` is the NEWEST member, because recency is the
    first discriminator.

    ⚠️ MERGED TO A FIXED POINT, AND THE FIRST CUT WAS NOT. Seeding by recency and
    growing each zone as members join makes the result depend on VISIT ORDER: a
    level assigned early can end up inside a span that widened afterwards, and
    the first version printed `719.70-722.13` beside a separate `721.89` — a
    price inside another zone. Any width chosen on that output would have been
    chosen on noise. This iterates until no two zones are within `width`, so the
    partition is unique and order cannot change it.

    ⚠️ IT IS A GROUPING, NOT A STORE. The ledger goes on recording session
    extremes exactly as it does; this decides which two of them are the live
    edges and which are absorbed.
    """
    if not levels or not width or width <= 0:
        return [{"lo": l["price"], "hi": l["price"], "members": [l], "seed": l}
                for l in sorted(levels, key=lambda x: x["price"])]
    zs = [{"lo": l["price"], "hi": l["price"], "members": [l]} for l in levels]
    changed = True
    while changed:
        changed = False
        zs.sort(key=lambda z: z["lo"])
        out: List[dict] = []
        for z in zs:
            if out and z["lo"] - out[-1]["hi"] <= width:
                out[-1]["hi"] = max(out[-1]["hi"], z["hi"])
                out[-1]["members"] += z["members"]
                changed = True
            else:
                out.append(z)
        zs = out
    for z in zs:
        z["seed"] = max(z["members"], key=lambda l: l["formed_ts"])
    return zs


def walk(levels: List[dict], spot: float) -> dict:
    """From spot outward, newest first, each older level only if further out.

    `levels` — HELD levels (spent ones excluded by the caller), each with
    `price` and `formed_ts`. -> {"up": [...], "down": [...]}, nearest first.
    """
    # ⚠️ EQUAL FORMATION TIMES HAVE NO "NEWER": within one instant the nearest
    # comes first, so every level of that instant that is further out stays on.
    newest_first = sorted(levels, key=lambda l: (-pd.Timestamp(l["formed_ts"]).value,
                                                 abs(float(l["price"]) - spot)))
    up, down = [], []
    last_up, last_dn = spot, spot
    for lv in newest_first:
        p = float(lv["price"])
        if p > spot and p > last_up:
            up.append(lv)
            last_up = p
        elif p < spot and p < last_dn:
            down.append(lv)
            last_dn = p
    up.sort(key=lambda l: float(l["price"]))
    down.sort(key=lambda l: -float(l["price"]))
    return {"up": up, "down": down}


def load_tape(db_path: str, symbol: str, interval: str = TAPE_INTERVAL) -> Optional[pd.DataFrame]:
    """Every HOURLY bar the feed store holds for `symbol`, RTH and extended merged.

    🔴 HOURLY, EXCLUSIVELY (r36, operator's ruling: *"use 1-hr as far back as you
    can"*, then *"use the hour exclusively"*). This read was 1m until r36 and
    that capped the level board at NINE DAYS, because retention keeps 1m for five
    (`RETENTION_DAYS`). Measured 2026-09-17 against the operator's own 1D chart:
    three of his five levels above spot did not exist in the ledger at all.

    ⚠️ WHY THE HOUR LOSES NOTHING THAT MATTERS HERE. An hourly bar's high/low is
    an AGGREGATE, not a sample, so it carries the true extreme of its hour.
    MEASURED on the eight days where both series are complete: merged 1h
    reproduced the merged-1m 24-hour high AND low to **0.00**, every day. And the
    mapper's sections are already hour-granular by construction — `Asia 00-08`,
    `London 08-13`, `NY 13-20` UTC, membership tested on `idx.hour` — so an hourly
    bar lands in exactly one section with no straddle and no boundary loss.

    ⚠️ WHAT IT DOES COST, STATED RATHER THAN DISCOVERED: the reconcile runs once
    per new tape bar, so a level accepted through at 10:05 now retires when the
    10:00 bar closes rather than within the minute, and the newest possible level
    is up to an hour old. The rejection FACT is unaffected — `_derive_events`
    reads `ctx["df_1m"]` and takes `df.index[-2]`, the closed MINUTE, so
    WICKED/REJECTED/ACCEPTED and the sweep's trigger keep 1m granularity. Those
    are two different jobs and only this one moved.

    ⚠️ DAILY BARS WERE TRIED AND RULED OUT, so nobody re-proposes them: they
    cannot see overnight. Merged `1d` missed the true 24h low by **$2.33 on
    average and $9.13 at worst** (09-17: daily 713.32, true 704.19), because
    DXFeed aggregates a daily candle over trading hours and the `_EXT` daily bar
    is a near-copy of the RTH one. The operator: *"the outside RTH levels are the
    ones I'm most expecting to get swept. It's imperative that we know where
    those levels sit."*

    ⚠️ TWO STREAMS, ONE TAPE. RTH bars are stored under `SYM` and the extended
    session under `SYM_EXT`; both are read and de-duplicated on the stamp.
    Read-only; None when the store is absent or empty — never an empty frame
    that reads as "no levels".
    """
    try:
        c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0)
    except Exception:                                           # noqa: BLE001
        return None
    try:
        rows = c.execute(
            "SELECT ts_epoch_ms, open, high, low, close FROM candles"
            " WHERE symbol IN (?, ?) AND interval=? AND close > 0 AND open > 0"
            " ORDER BY ts_epoch_ms", (symbol, f"{symbol}_EXT", interval)).fetchall()
    except Exception:                                           # noqa: BLE001
        return None
    finally:
        c.close()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
    df = df.drop_duplicates("ts", keep="first")
    df.index = pd.to_datetime(df.pop("ts"), unit="ms", utc=True)
    return df


def provenance(label: str) -> str:
    """The ledger's session vocabulary: `asia` / `london` / `ny` (unchanged, so
    the TCS's `provenance == "ny"` read keeps its meaning)."""
    return str(label).lower()


def kind_of(side: str) -> str:
    """Formation side: a session high is resistance, a low support."""
    return "resistance" if side == SIDE_HIGH else "support"
