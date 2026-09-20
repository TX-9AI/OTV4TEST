"""
derived/indicators.py  v4.1
Owns `indicator_series`. Tier 1 — path-dependent values.

v4.1  2026-09-20  OTV4TEST r69 (IND.1) — THE PER-TIMEFRAME LOOP HAD NEVER RUN.
      `list(trend.votes)` on a Dict yields its KEYS, so every vote was a string,
      every `getattr(vote,"timeframe")` was None, and the loop skipped all of
      them. 0 of 18,529 rows ever carried an EMA and every row was
      `interval='primary'`. One line: `.values()`. FORWARD-ONLY — history stays
      null. Gated by tests/check_indicator_votes.py.

v4.0  2026-08-22  See docs/DERIVED_STORES.md.

ADX, ATR, EMAs and VWAP. All four share one property: **recomputation is not
idempotent.** Each depends on where its window started, so the number an engine
sees can differ from the number it saw an hour ago for reasons that have
nothing to do with the market.

🔴 THIS IS NOT THEORETICAL. Friday 2026-08-21's rejection logs show ADX
swinging 16 -> 48 on the same symbols across ticks. Some of that is real. Some
may be window artifact, and **there is currently no way to tell** — nothing
keeps the series to compare against. `adx_at_entry` is a column on every trade
and `CONT_BREAKOUT_MIN_ADX` is a live gate, so if there is a recompute wobble,
both the gate and the study are contaminated by it. This table is what makes
that answerable.

🔴 VWAP STORES ITS ACCUMULATORS, NOT JUST THE VALUE. Sum(p*v), Sum(v) and the
anchor they started from. VWAP is cumulative from a FIXED anchor, so it is the
one value where a wrong window does not produce noise — it produces a
different indicator that still looks like a smooth line near price. Nothing
about it looks broken. The accumulators are what make it verifiable later.

⚠️ THE VW.1 SCAR: five wrong layers of analysis, because VWAP orientation was
RECONSTRUCTED after the fact instead of recorded when it happened. Storing the
series turns that class of investigation into a lookup.

⚠️ READS WHAT THE ENGINES ALREADY COMPUTED. This does not re-derive ADX from
bars — `trend_engine` and `volatility_engine` already did that this tick, and
computing it twice would give two numbers for one moment, which is the exact
disease. It records THEIR values.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from derived.base import DerivedEngine

logger = logging.getLogger(__name__)


def _f(v) -> Optional[float]:
    """Float or None. NEVER 0.0 as a fallback — see the module docstring."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f          # NaN -> None, not 0.0


class IndicatorEngine(DerivedEngine):
    name = "indicators"
    table = "indicator_series"
    min_interval_s = 0.0                  # cheap: it only records

    def __init__(self, store=None, symbol: str = ""):
        super().__init__(store)
        self.symbol = symbol
        # VWAP accumulators, per (symbol, session-anchor).
        self._pv: float = 0.0
        self._v: float = 0.0
        self._anchor_ms: Optional[int] = None
        self._last_bar_ms: Optional[int] = None

    # ── VWAP: accumulate rather than recompute ──────────────────────────
    def _accumulate_vwap(self, df_1m) -> tuple:
        """Fold new 1m bars into the running sums. Returns (vwap, pv, v, anchor).

        ⚠️ FOLDS ONLY BARS NEWER THAN THE LAST ONE SEEN. Re-folding the whole
        frame each tick would double-count volume and drift the VWAP upward in
        a way that looks entirely plausible.
        ⚠️ RESETS ON A NEW SESSION ANCHOR. A VWAP that silently carries
        yesterday's accumulators into today is the wrong-window failure this
        table exists to expose.
        """
        if df_1m is None or getattr(df_1m, "empty", True):
            return None, None, None, None
        try:
            idx = df_1m.index
            day0 = idx[-1].normalize()
            anchor_ms = int(day0.timestamp() * 1000)
            if self._anchor_ms != anchor_ms:      # new session -> new anchor
                self._pv, self._v = 0.0, 0.0
                self._anchor_ms = anchor_ms
                self._last_bar_ms = None
            for ts, row in df_1m.iterrows():
                ms = int(ts.timestamp() * 1000)
                if ms < anchor_ms:
                    continue                       # belongs to a prior session
                if self._last_bar_ms is not None and ms <= self._last_bar_ms:
                    continue                       # already folded
                h, l, c = _f(row.get("high")), _f(row.get("low")), _f(row.get("close"))
                v = _f(row.get("volume"))
                if None in (h, l, c) or v is None or v <= 0:
                    continue
                typical = (h + l + c) / 3.0
                self._pv += typical * v
                self._v += v
                self._last_bar_ms = ms
            if self._v <= 0:
                return None, None, None, self._anchor_ms
            return (self._pv / self._v, self._pv, self._v, self._anchor_ms)
        except Exception as exc:                                # noqa: BLE001
            logger.debug("vwap accumulate skipped: %s", exc)
            return None, None, None, self._anchor_ms

    def derive(self, ctx: dict) -> int:
        store = self._store
        if store is None:
            return 0
        trend = ctx.get("trend")
        vol = ctx.get("vol")
        sym = self.symbol or ctx.get("symbol") or ""
        if not sym:
            return 0
        now = time.time()

        vwap, pv, v, anchor = self._accumulate_vwap(ctx.get("df_1m"))

        rows = []
        # One row per timeframe the trend engine voted on, so ADX is recorded
        # PER FRAME rather than only the primary — the per-frame values are
        # what a later study needs to see disagreement.
        # 🔴 r69 — `TrendState.votes` IS A DICT, AND `list(a_dict)` YIELDS ITS KEYS.
        # This read `list(trend.votes)`, so `votes` was a list of the timeframe
        # STRINGS ('5m', '15m', ...). The loop below then asks each string for
        # `.timeframe`, gets None, and `continue`s EVERY iteration — so `rows`
        # stayed empty on every tick and the fallback below wrote the four EMAs
        # as None. MEASURED: 0 of 18,529 rows in this table have ever carried an
        # `ema_fast`, and EVERY row is `interval='primary'`.
        # 🔑 SO THE PER-FRAME LOOP HAS NEVER ONCE EXECUTED, which costs more than
        # the EMAs: its own comment says it exists "so ADX is recorded PER FRAME
        # rather than only the primary — the per-frame values are what a later
        # study needs to see disagreement." That disagreement signal has never
        # been recorded at all.
        # ⚠️ AND THE 2026-08-24 FIX BELOW MASKED IT PERMANENTLY. That change
        # keyed the fallback on the OUTCOME so a gap shows up as thin rows
        # rather than no rows — correct, and it worked: a row appears every
        # tick, so nothing ever looked broken. The SYMPTOM was fixed and the
        # CAUSE was never found. Thin plausible data instead of an error is the
        # class this repo keeps paying for.
        votes = list(trend.votes.values()) if trend and getattr(trend, "votes", None) else []
        if votes:
            for vote in votes:
                tf = getattr(vote, "timeframe", None)
                if not tf:
                    continue
                rows.append((
                    sym, tf, now, self._last_bar_ms,
                    _f(getattr(vote, "adx", None)),
                    _f(getattr(vol, "atr_current", None)),
                    _f(getattr(vol, "atr_normalized", None)),
                    _f(getattr(vote, "ema_fast", None)),
                    _f(getattr(vote, "ema_mid", None)),
                    _f(getattr(vote, "ema_slow", None)),
                    _f(getattr(vote, "ema_anchor", None)),
                    _f(vwap), _f(pv), _f(v), anchor,
                ))
        # 🔴 THE FALLBACK ASKED THE WRONG QUESTION — found live 2026-08-24.
        # It was `if votes: ... else: <primary row>`, so it fired only when the
        # list was EMPTY. But `TrendVote.timeframe` DEFAULTS TO "" and the loop
        # above does `if not tf: continue` — so a non-empty list of votes that
        # all lack a timeframe skipped every row, took the `if` branch, and
        # left `rows` EMPTY. `_write` returns 0 on an empty list without
        # touching the database: no exception, no write failure, nothing to
        # grep. `indicator_series` held ZERO ROWS on all fifteen boxes while
        # forks, levels and surface filled normally on the same pass.
        # 🔑 KEY THE FALLBACK ON THE OUTCOME, NOT THE INPUT. The original
        # comment states the intent exactly — "a gap in the trend engine shows
        # up as thin rows rather than as no rows at all" — and asking "were
        # there votes?" instead of "did we produce a row?" defeated it.
        if not rows:
            rows.append((
                sym, "primary", now, self._last_bar_ms,
                _f(getattr(trend, "primary_adx", None)) if trend else None,
                _f(getattr(vol, "atr_current", None)),
                _f(getattr(vol, "atr_normalized", None)),
                None, None, None, None,
                _f(vwap), _f(pv), _f(v), anchor,
            ))
        return store.append_indicators(rows)
