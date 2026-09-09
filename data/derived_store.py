"""
data/derived_store.py  v4.4
v4.4  2026-09-09  OTV4TEST r9 — `latest_event(symbol, event, since, kind)`: the
      general form of latest_rejection; the TCS reads ACCEPTED through it.
v4.3  2026-09-08  OTV4TEST r5 — `live_levels(symbol)`: the un-retired support /
      resistance levels with their current price (tines move; the ledger row
      carries the price at the last upsert). The sweep plan reads its levels
      in play from here, never from a strategy's private map.
v4.2  2026-09-08  OTV4TEST r3 — `level_event`: THE REJECTION FACT HAS A HOME.
      One row per (level, closed 1m bar) event: WICKED (wick through, close
      inside), REJECTED (the doctrine's close-back-inside count reached:
      one on a shallow pierce, two on a deep one), ACCEPTED (two closes
      beyond, the level retired). Written by derived/levels.py v4.1, read by
      `latest_rejection()` — the exit engine's handoff and, later, the sweep's
      trigger and the condor's pairing. Never purged (with level_ledger).
v4.1  2026-08-25  r65 EXORCISM: every mention of the retired classification
      system removed - identifiers, comments, docstrings, schema. The word
      does not appear in this tree. Full accounting: REMOVAL_LOG (delivery).

The derived layer's homes. Tier 1-4 of docs/DERIVED_STORES.md.

v4.0  2026-08-22  Built with the manifold.

WHAT THIS IS. `feed_store.db` holds what the WIRE said. This holds what we
CONCLUDED from it — the values that depend on HISTORY rather than only on the
current bar, and which therefore give a DIFFERENT ANSWER when recomputed.

    raw port -> home -> deriver -> DERIVED HOME -> ctx -> engine

⚠️ DERIVERS ARE CONTRIBUTORS, NEVER GATES. Operator's ruling 2026-08-22.
violated. **A missing derived value is NOT an error.** The engine trades
without it. Only RAW ports can be hard requirements. Nothing in this module may
raise into a caller's decision path.

⚠️ SEPARATE DATABASE FILE, DELIBERATELY. The feed store is written by the
candle-feed process and read by the bot; adding derived writes there would put
two writers on one SQLite file during RTH. This file is the bot's own.

⚠️ EVERY TABLE IS RECOMPUTABLE FROM RAW. If a deriver has a bug, fix it and
rebuild — history is never lost, because the raw series is kept. That property
is the entire reason the manifold keeps everything.

⚠️ ABSENCE IS RECORDED AS ABSENCE. A deriver that could not produce a value
writes NULL, never 0.0. A missing measurement and a measured zero are different
facts; conflating them is the single most expensive habit in this repo's
history (VW.1, the sweep score, the gap prior_dir).
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT = os.path.expanduser("~/options-trader/data/derived_store.db")


def derived_db_path() -> str:
    return os.environ.get("OT_DERIVED_DB", _DEFAULT)


class DerivedStore:
    """Append-only homes for derived values. Never raises into a caller."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or derived_db_path()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self._lock = threading.Lock()
        self._init_schema()

    # ── schema ──────────────────────────────────────────────────────────
    def _init_schema(self):
        c = self.conn
        # TIER 1 — path-dependent. Recomputation is not idempotent.
        # ⚠️ VWAP STORES ITS ACCUMULATORS, NOT JUST THE VALUE. Sum(p*v) and
        # Sum(v) with the anchor they started from. A VWAP rebuilt off a
        # rolling window instead of the session open is still a smooth line
        # near price — NOTHING ABOUT IT LOOKS BROKEN — which is exactly why
        # the value alone is not enough to trust later.
        c.execute("""
            CREATE TABLE IF NOT EXISTS indicator_series (
                symbol     TEXT NOT NULL,
                interval   TEXT NOT NULL,
                ts_epoch   REAL NOT NULL,
                bar_ts_ms  INTEGER,
                adx REAL, atr REAL, atr_normalized REAL,
                ema_fast REAL, ema_mid REAL, ema_slow REAL, ema_anchor REAL,
                vwap REAL, vwap_sum_pv REAL, vwap_sum_v REAL, vwap_anchor_ms INTEGER,
                PRIMARY KEY (symbol, interval, ts_epoch)
            );""")
        c.execute("CREATE INDEX IF NOT EXISTS ix_ind_ts ON indicator_series(ts_epoch)")

        # TIER 2 — regressive. Scans backward; dies on restart today.
        # ⚠️ REJECTIONS ARE ROWS TOO. Six reasons exist in pitchfork.py
        # (FRAME_TOO_SHORT, NOT_ANCHOR_TF, NO_ATR, NO_CONTAINED_WINDOW,
        # RECENCY, SEPARATION) and NONE of them reached storage or a log —
        # "no usable fork" was one message covering six different problems,
        # which is why the r59 diagnosis took two wrong turns.
        c.execute("""
            CREATE TABLE IF NOT EXISTS fork_series (
                symbol     TEXT NOT NULL,
                interval   TEXT NOT NULL,
                ts_epoch   REAL NOT NULL,
                built      INTEGER NOT NULL,        -- 1 built, 0 rejected
                reject_reason TEXT,                 -- NULL when built
                scan_depth INTEGER,
                direction  TEXT,
                p0_idx REAL, p0_price REAL,
                p1_idx REAL, p1_price REAL,
                p2_idx REAL, p2_price REAL,
                origin_idx REAL, origin_price REAL,
                slope REAL, containment REAL, span_bars INTEGER,
                upper REAL, median REAL, lower REAL,
                PRIMARY KEY (symbol, interval, ts_epoch)
            );""")
        c.execute("CREATE INDEX IF NOT EXISTS ix_fork_ts ON fork_series(ts_epoch)")

        # TIER 3 — stateful. The object has a biography.
        # 🔴 OPERATOR RULING 2026-08-22: "in a live session a touch count is a
        # held level, and when it doesn't hold, that level is FINISHED." A
        # touch is a HOLD; touch_count is the length of a run that TERMINATES
        # at the break — not a score that accumulates forever.
        # ⚠️ `retired_ts` / `retired_reason` exist so the break is a RECORDED
        # EVENT. Today `touch_count` and `swept` are separate fields, so a pool
        # can read five-touch AND swept at once — the count survives its own
        # invalidation.
        # ⚠️ BODIES DECIDE, WICKS TEST — universal, from the sweep rules:
        # `closes_beyond >= ACCEPT_CLOSES` is a BREAKOUT, not a sweep.
        # Measured: closes_beyond >= 2 blocked 64.5% of named-pool sweeps.
        c.execute("""
            CREATE TABLE IF NOT EXISTS level_ledger (
                level_id   TEXT NOT NULL PRIMARY KEY,
                symbol     TEXT NOT NULL,
                price      REAL NOT NULL,
                kind       TEXT,                    -- support / resistance
                provenance TEXT,                    -- prev_day / asia / london / ny / vwap / swing
                timeframe  TEXT,
                created_ts REAL NOT NULL,
                touch_count INTEGER DEFAULT 0,
                last_touch_ts REAL,
                closes_beyond INTEGER DEFAULT 0,
                retired_ts REAL,                    -- NULL while live
                retired_reason TEXT,                -- ACCEPTED_THROUGH / SESSION_END
                is_live_session INTEGER DEFAULT 0   -- 1 = still forming (NY)
            );""")
        c.execute("CREATE INDEX IF NOT EXISTS ix_level_sym ON level_ledger(symbol, retired_ts)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS level_event (
                symbol     TEXT NOT NULL,
                level_id   TEXT NOT NULL,
                bar_ts     TEXT NOT NULL,           -- the CLOSED 1m bar that produced it
                ts_epoch   REAL NOT NULL,
                event      TEXT NOT NULL,           -- WICKED / REJECTED / ACCEPTED
                price      REAL NOT NULL,           -- the level
                kind       TEXT,                    -- support / resistance
                provenance TEXT,
                pierce_pct REAL,                    -- wick beyond the level, fraction of price
                depth      TEXT,                    -- shallow / deep / beyond
                closes_back INTEGER,                -- closes back inside counted so far
                bar_close  REAL,
                PRIMARY KEY (symbol, level_id, bar_ts, event)
            );""")
        c.execute("CREATE INDEX IF NOT EXISTS ix_levev_sym ON level_event(symbol, ts_epoch)")

        # TIER 4 — second-order. Impossible without the greeks series.
        # 🔴 CHARM = dDelta/dt, VANNA = dDelta/dVol. Operator: "absolutely
        # indispensable." For 0DTE charm DOMINATES the afternoon — it is the
        # mechanism behind pin. Neither was computable while chain_marks
        # overwrote one row per symbol.
        c.execute("""
            CREATE TABLE IF NOT EXISTS surface_series (
                symbol      TEXT NOT NULL,
                ts_epoch    REAL NOT NULL,
                strike      REAL,
                expiry      TEXT,
                charm REAL, vanna REAL,
                gex REAL, gamma_flow REAL,
                iv REAL, iv_slope REAL,
                dt_seconds REAL, d_vol REAL,        -- the differences used
                PRIMARY KEY (symbol, ts_epoch, strike, expiry)
            );""")
        c.execute("CREATE INDEX IF NOT EXISTS ix_surf_ts ON surface_series(ts_epoch)")

        # The fire-time snapshot: everything derived at the instant a trade
        # fired, keyed to the trade. This is what makes "which derived
        # indicator separates winners from losers" a JOIN.
        # ⚠️ WRITES IN THE SAME TRANSACTION AS THE TRADE ROW. A trade with no
        # snapshot is a hole in the study; a snapshot with no trade is an
        # orphan. Either both land or neither does.
        c.execute("""
            CREATE TABLE IF NOT EXISTS fire_snapshot (
                trade_id   TEXT NOT NULL PRIMARY KEY,
                symbol     TEXT NOT NULL,
                fired_ts   REAL NOT NULL,
                payload    TEXT NOT NULL            -- JSON: every derived value, NULL where absent
            );""")
        self.conn.commit()

    # ── writers ─────────────────────────────────────────────────────────
    def _write(self, sql: str, rows) -> int:
        """Every writer funnels here. NEVER raises — see the module docstring."""
        if not rows:
            return 0
        try:
            with self._lock:
                self.conn.executemany(sql, rows)
            return len(rows)
        except Exception as exc:                                # noqa: BLE001
            logger.warning("derived write failed (%d rows): %s — the raw tape "
                           "is unaffected and this value is simply absent",
                           len(rows), exc)
            return 0

    def insert_level_event(self, row):
        """One (level, bar, event). Idempotent on the primary key."""
        return self._write(
            "INSERT OR IGNORE INTO level_event (symbol, level_id, bar_ts, ts_epoch,"
            " event, price, kind, provenance, pierce_pct, depth, closes_back, bar_close)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [row])

    def live_levels(self, symbol: str):
        """[{level_id, price, kind, provenance, timeframe, touches}] for every
        un-retired support/resistance level of `symbol`."""
        try:
            with self._lock:
                rows = self.conn.execute(
                    "SELECT level_id, price, kind, provenance, timeframe, touch_count "
                    "FROM level_ledger WHERE symbol=? AND retired_ts IS NULL "
                    "AND kind IN ('support','resistance')", (symbol,)).fetchall()
            keys = ("level_id", "price", "kind", "provenance", "timeframe", "touches")
            return [dict(zip(keys, r)) for r in rows]
        except Exception as exc:                                # noqa: BLE001
            logger.warning("live_levels read failed: %s", exc)
            return []

    def latest_rejection(self, symbol: str, since_ts: float = 0.0,
                         kind: Optional[str] = None):
        """The most recent REJECTED event — see latest_event()."""
        return self.latest_event(symbol, "REJECTED", since_ts=since_ts, kind=kind)

    def latest_event(self, symbol: str, event: str, since_ts: float = 0.0,
                     kind: Optional[str] = None):
        """The most recent level_event of `event` for `symbol` at/after
        `since_ts` (epoch), optionally only levels of `kind`. dict or None."""
        try:
            sql = ("SELECT symbol, level_id, bar_ts, ts_epoch, event, price, kind,"
                   " provenance, pierce_pct, depth, closes_back, bar_close"
                   " FROM level_event WHERE symbol=? AND event=? AND ts_epoch>=?")
            args = [symbol, str(event), float(since_ts or 0.0)]
            if kind:
                sql += " AND kind=?"
                args.append(kind)
            sql += " ORDER BY ts_epoch DESC LIMIT 1"
            with self._lock:
                r = self.conn.execute(sql, args).fetchone()
            if not r:
                return None
            keys = ("symbol", "level_id", "bar_ts", "ts_epoch", "event", "price", "kind",
                    "provenance", "pierce_pct", "depth", "closes_back", "bar_close")
            return dict(zip(keys, r))
        except Exception as exc:                                # noqa: BLE001
            logger.warning("latest_rejection read failed: %s", exc)
            return None

    def append_indicators(self, rows):
        return self._write(
            "INSERT OR IGNORE INTO indicator_series (symbol, interval, ts_epoch,"
            " bar_ts_ms, adx, atr, atr_normalized, ema_fast, ema_mid, ema_slow,"
            " ema_anchor, vwap, vwap_sum_pv, vwap_sum_v, vwap_anchor_ms)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    def append_forks(self, rows):
        return self._write(
            "INSERT OR IGNORE INTO fork_series (symbol, interval, ts_epoch,"
            " built, reject_reason, scan_depth, direction, p0_idx, p0_price,"
            " p1_idx, p1_price, p2_idx, p2_price, origin_idx, origin_price,"
            " slope, containment, span_bars, upper, median, lower)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    def append_surface(self, rows):
        return self._write(
            "INSERT OR IGNORE INTO surface_series (symbol, ts_epoch, strike,"
            " expiry, charm, vanna, gex, gamma_flow, iv, iv_slope, dt_seconds,"
            " d_vol) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    def upsert_level(self, row):
        """One level. Touch/retire updates land on the same level_id."""
        return self._write(
            "INSERT INTO level_ledger (level_id, symbol, price, kind,"
            " provenance, timeframe, created_ts, touch_count, last_touch_ts,"
            " closes_beyond, retired_ts, retired_reason, is_live_session)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(level_id) DO UPDATE SET"
            " touch_count=excluded.touch_count,"
            " last_touch_ts=excluded.last_touch_ts,"
            " closes_beyond=excluded.closes_beyond,"
            " retired_ts=excluded.retired_ts,"
            " retired_reason=excluded.retired_reason,"
            " is_live_session=excluded.is_live_session", [row])

    def write_fire_snapshot(self, trade_id: str, symbol: str, payload_json: str):
        return self._write(
            "INSERT OR REPLACE INTO fire_snapshot (trade_id, symbol, fired_ts,"
            " payload) VALUES (?,?,?,?)",
            [(trade_id, symbol, time.time(), payload_json)])

    def commit(self):
        try:
            with self._lock:
                self.conn.commit()
        except Exception:                                       # noqa: BLE001
            pass


_store: Optional[DerivedStore] = None


def get_derived_store() -> Optional[DerivedStore]:
    """Singleton. Returns None if the store cannot be opened — callers treat
    a None store as 'this value is simply not recorded', never as an error."""
    global _store
    if _store is None:
        try:
            _store = DerivedStore()
        except Exception as exc:                                # noqa: BLE001
            logger.warning("derived store unavailable: %s — derived values "
                           "will not be recorded this session", exc)
            return None
    return _store
