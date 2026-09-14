"""
derived/anchors.py  v1.1
v1.1  2026-09-13  OTV4TEST r25 — THE VWAP READ WAS DEAD, AND ONE ANCHOR NOW DECIDES.
      🔴 `vwap()` queried interval '1m', which indicator_series has NEVER held —
      the engine writes 'primary' only — so it returned None on every call and
      `anchor_vwap_minus_pin` was null on 723 of 723 of Friday's butterfly rows.
      Re-pointed to 'primary'. ⚠️ THE FIRST ANCHOR PROMOTED TO A DECISION INPUT,
      on the operator's ruling (BFLY.5): `vwap_now()` feeds the butterfly's VWAP
      band. It is a SEPARATE reader because "latest row" is not "now": the
      engine keeps writing the last session's VWAP after the close (Sunday
      evening's rows carry Friday's 715.45, anchored Friday midnight). So it
      returns a value only when the row is anchored at TODAY's midnight ET and
      its bar is fresh; anything else is None with the reason, never a stale
      number. `vwap()` stays record-only and unfiltered.
v1.0  2026-09-09  OTV4TEST r12 — ANCHORS: DERIVATIVES RECORDED ON THE PLAN ROW,
      NEVER DECIDED ON. Operator: *"record in our newly crafted plans, not to
      decide, but to see if they offer fitting anchors we can tie to later."*
      Every plan stamps 3–5 of these on its row every tick as record-only
      checks (verdict None), so an anchor is scored against fires, declines
      AND holds — fire_snapshot alone could only ever see the fires.

      Every read is best-effort and returns None when the store, table or
      row is absent; a None is a fact about coverage, not a failure. Nothing
      here raises into a plan.

      READS (all from stores that already exist):
        charm_at / vanna_at / gex_at (strike)  — surface_series, latest row
        vwap ()                                 — indicator_series (primary), latest
        vwap_now (now)                          — the same, ONLY if today's and fresh
        fork_dir (tf)                           — fork_series, latest built
        nearest_tine (price)                    — level_ledger fork1h/* live
        aggressor_share (level, band, secs)     — prints: buy share of size
                                                  within ±band of level, last N s
        gex_between (lo, hi)                    — surface_series sum in [lo, hi]
        oi_at (strike, chain)                   — from the chain in hand
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def _store():
    try:
        from data.derived_store import get_derived_store
        return get_derived_store()
    except Exception:                                           # noqa: BLE001
        return None


def _sym() -> str:
    try:
        from config import INSTRUMENT
        return str(INSTRUMENT)
    except Exception:                                           # noqa: BLE001
        return ""


def _q(sql, args=()):
    st = _store()
    if st is None:
        return []
    try:
        with st._lock:
            return st.conn.execute(sql, args).fetchall()
    except Exception:                                           # noqa: BLE001
        return []


def _surface_row(strike: float):
    if strike is None:
        return None
    rows = _q("SELECT charm, vanna, gex FROM surface_series WHERE symbol=? AND ABS(strike-?)<0.01 "
              "ORDER BY ts_epoch DESC LIMIT 1", (_sym(), float(strike)))
    return rows[0] if rows else None


def charm_at(strike) -> Optional[float]:
    r = _surface_row(strike)
    return float(r[0]) if r and r[0] is not None else None


def vanna_at(strike) -> Optional[float]:
    r = _surface_row(strike)
    return float(r[1]) if r and r[1] is not None else None


def gex_at(strike) -> Optional[float]:
    r = _surface_row(strike)
    return float(r[2]) if r and r[2] is not None else None


def gex_between(lo, hi) -> Optional[float]:
    if lo is None or hi is None:
        return None
    rows = _q("SELECT strike, gex, MAX(ts_epoch) FROM surface_series WHERE symbol=? AND strike BETWEEN ? AND ? "
              "GROUP BY strike", (_sym(), float(min(lo, hi)), float(max(lo, hi))))
    vals = [float(r[1]) for r in rows if r[1] is not None]
    return sum(vals) if vals else None


def vwap() -> Optional[float]:
    rows = _q("SELECT vwap FROM indicator_series WHERE symbol=? AND interval='primary' ORDER BY ts_epoch DESC LIMIT 1",
              (_sym(),))
    return float(rows[0][0]) if rows and rows[0][0] is not None else None


# Friday 09-11, 1,479 RTH rows: written every 15 s, the bar trailing the write by
# at most 63 s. 180 s is three missed bars — a stalled feed, not a slow tick.
VWAP_MAX_BAR_AGE_S = 180.0


def vwap_now(now: Optional[float] = None,
             max_bar_age_s: float = VWAP_MAX_BAR_AGE_S) -> Tuple[Optional[float], str]:
    """(vwap, why) — the bot's midnight-ET-anchored VWAP for TODAY, or (None, reason).

    A decision input (the butterfly's VWAP band), so it FAILS CLOSED: a missing
    row, a null value, a prior session's anchor or a stale bar each return None
    and say which."""
    # zoneinfo, not utils.time_utils.ET: that is pytz, and .replace(hour=0) on a
    # pytz datetime keeps the AFTERNOON's offset, an hour wrong on a DST day.
    ET = ZoneInfo("America/New_York")
    now = time.time() if now is None else float(now)
    rows = _q("SELECT vwap, bar_ts_ms, vwap_anchor_ms FROM indicator_series WHERE symbol=? "
              "AND interval='primary' ORDER BY ts_epoch DESC LIMIT 1", (_sym(),))
    if not rows:
        return None, "no VWAP row in indicator_series"
    v, bar_ms, anchor_ms = rows[0]
    if v is None:
        return None, "the latest VWAP row is null"
    midnight = datetime.fromtimestamp(now, ET).replace(hour=0, minute=0, second=0, microsecond=0)
    if anchor_ms is None or abs(float(anchor_ms) / 1000.0 - midnight.timestamp()) > 1.0:
        return None, "the latest VWAP is anchored to a prior session, not today's midnight ET"
    if bar_ms is None or now - float(bar_ms) / 1000.0 > max_bar_age_s:
        return None, f"the latest VWAP bar is older than {max_bar_age_s:.0f}s — stale"
    return float(v), ""


def fork_dir(tf: str = "15m") -> Optional[str]:
    rows = _q("SELECT direction FROM fork_series WHERE symbol=? AND interval=? AND built=1 "
              "ORDER BY ts_epoch DESC LIMIT 1", (_sym(), tf))
    return str(rows[0][0]) if rows and rows[0][0] else None


def nearest_tine(price) -> Optional[float]:
    """Signed distance (points) from price to the nearest live 1h tine; None without a fork."""
    if price is None:
        return None
    rows = _q("SELECT price FROM level_ledger WHERE symbol=? AND provenance LIKE 'fork1h/%' AND retired_ts IS NULL",
              (_sym(),))
    if not rows:
        return None
    return min((float(r[0]) - float(price) for r in rows), key=abs)


def aggressor_share(level, band: float = 0.05, secs: int = 300) -> Optional[float]:
    """Buy-side share of print SIZE within ±band (fraction of level) in the last secs.
    Reads feed_store.db's prints (aggressor_side is the venue's tag)."""
    if level is None:
        return None
    try:
        import sqlite3
        import config
        path = getattr(config, "FEED_DB_PATH", None) or getattr(config, "FEED_STORE_PATH", None)
        if not path:
            import os
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "feed_store.db")
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        lo, hi = float(level) * (1 - band), float(level) * (1 + band)
        since = time.time() - secs
        rows = conn.execute("SELECT aggressor_side, SUM(size) FROM prints WHERE symbol=? AND ts_epoch>=? "
                            "AND price BETWEEN ? AND ? GROUP BY aggressor_side", (_sym(), since, lo, hi)).fetchall()
        conn.close()
        tot = sum(float(r[1] or 0) for r in rows)
        if tot <= 0:
            return None
        buy = sum(float(r[1] or 0) for r in rows if str(r[0] or "").upper().startswith("B"))
        return round(buy / tot, 4)
    except Exception:                                           # noqa: BLE001
        return None


def oi_at(strike, chain) -> Optional[int]:
    if chain is None or strike is None:
        return None
    try:
        for c in list(getattr(chain, "calls", []) or []) + list(getattr(chain, "puts", []) or []):
            if abs(float(getattr(c, "strike", 0) or 0) - float(strike)) < 0.01:
                return int(getattr(c, "open_interest", 0) or 0)
    except Exception:                                           # noqa: BLE001
        pass
    return None


def stamp(t, **items) -> None:
    """Write record-only checks (verdict None) on a PlanTick. Names are
    prefixed `anchor_` so readers can filter them out of the verdict row."""
    _dir = {"bullish": 1.0, "up": 1.0, "bearish": -1.0, "down": -1.0}
    for k, v in items.items():
        try:
            if isinstance(v, str):
                v = _dir.get(v.lower())
            t.check(f"anchor_{k}", None if v is None else float(v), None)
        except Exception:                                       # noqa: BLE001
            pass
