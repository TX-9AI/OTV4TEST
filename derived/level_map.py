"""
derived/level_map.py  v1.1
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
