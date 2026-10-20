"""
analysis/reentry.py  v1.0
v1.0  2026-10-19  OTV4TEST r306 (RENT.2) — A PREMIUM EXIT IS NOT A PLACE TO GET BACK IN FOR 20 SECONDS.
      The operator, 2026-10-12 10:34 ET: "A good place to get out cannot be a good place to get in and vice versa";
      2026-10-19 16:15 ET: "the exit proceeding the outlier was the problem, not the entry"; 20:17 ET: "Yes" to
      building the 20 s gate after PREMIUM exits only.
      EVIDENCE (/var/tmp/a7_study, PREREG.md frozen 20:01 ET before any validation run, a7s.py sha 8e47eeed26c6):
      a directional entry with a same-side exit earlier the same ET day (any strategy), blocked when the exit was a
      PREMIUM exit and the gap is <= 20 s: fit QQQ 09-01..10-04 23 blocked -9,313 (biggest winner cut +874);
      UNSEEN QQQ 10-05..10-19 10 blocked -2,344; UNSEEN SPX-TEST 3 blocked -1,270 (no winner cut); the top winner of
      each set kept. A 20 s wait after EVERY exit cut +3,920 (a re-entry after a market exit); momentum alone FAILED
      unseen. Hold-through (the first contract's own warehouse quotes): within 20 s holding was no better than the
      re-entry (QQQ -10,905 vs -10,545; SPX -1,680 vs -1,270) - the same trade bought back across the spread.
      THE NUMBER IS THE MEASURED PLATEAU, NOT A REASON: 20-30 s score alike; 60 s cuts the 09-23 +9,510 (44 s after a
      +10.4% premium trail exit). Said here so nobody widens it believing it is principled.

A PREMIUM exit (the option's own price, not a market reading): exit_reason starting trail_stop_hit | orb_trail_stop |
hard_stop | stop_ | premium_stop | volt_premium_floor | post_target_trail - the study's frozen classifier, verbatim.
Every other exit is a MARKET exit and never gates (a market exit read the market; the study found a wait after one
cut winners).
The book is trades.db (decisions read books): the latest closed single-leg directional trade on the SAME side whose
exit_time is today (ET) and not after now, ANY strategy. Unreadable -> allowed, and the row says why (fail open).
A ctx with no "commitment" key is not a tick (main's loop always sets it, COMMIT.2's rule): not gated, NOT recorded,
so a checker driving the funnel never writes into the box's live data/counterfactual.
Rows: data/counterfactual/reentry_gate.jsonl - every directional entry with a same-side exit in the last 900 s, with
the would-be order, so the old rule (no gate) and any other wait are replayable.
"""
import datetime as _dt
import logging
import re
import sqlite3
import time
from typing import Optional

from analysis.commitment import DIRECTIONAL, _et_date, _row, side_of

logger = logging.getLogger(__name__)

WAIT_S = 20.0
RECORD_WINDOW_S = 900.0
PREMIUM_EXIT = re.compile(r"^(trail_stop_hit|orb_trail_stop|hard_stop|stop_|premium_stop|volt_premium_floor|"
                          r"post_target_trail)")


def is_premium_exit(reason) -> bool:
    return bool(PREMIUM_EXIT.match(str(reason or "")))


def last_same_side_exit(db_path: str, side: str, now: float) -> Optional[dict]:
    """The latest closed single-leg directional trade on `side` that exited today (ET) at or before `now`.
    -> {"trade_id", "strategy", "exit_time", "exit_reason", "age_s"} or None. Raises on an unreadable book."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    try:
        rows = conn.execute(
            "SELECT trade_id, strategy, exit_time, exit_reason FROM trades WHERE status='closed' "
            "AND exit_time IS NOT NULL AND direction=? AND coalesce(is_butterfly,0)=0 "
            "AND coalesce(is_condor_leg,0)=0 ORDER BY exit_time DESC LIMIT 50", (side,)).fetchall()
    finally:
        conn.close()
    day = _et_date(now)
    for tid, strat, x, why in rows:
        try:
            xs = _dt.datetime.fromisoformat(x).timestamp()
        except Exception:                                        # noqa: BLE001
            continue
        if xs > now + 1e-6 or _et_date(xs) != day:
            continue
        return {"trade_id": tid, "strategy": strat, "exit_time": x, "exit_reason": why, "age_s": round(now - xs, 3)}
    return None


def gate(signal, ctx, *, mode: str, paper: bool, contracts=None, now: Optional[float] = None) -> bool:
    """RENT.2 - True when the entry must NOT be placed: a directional entry within WAIT_S of a same-side PREMIUM exit,
    mode 'trade', on a PAPER box. Unreadable -> allowed. NEVER raises (an error allows)."""
    try:
        name = str(getattr(signal, "strategy_name", "") or "")
        if mode == "off" or name not in DIRECTIONAL:
            return False
        if not isinstance(ctx, dict) or "commitment" not in ctx:
            logger.debug("[reentry] %s: no tick state on ctx - not gated, not recorded", name)
            return False
        import config                                            # noqa: PLC0415
        t = time.time() if now is None else float(now)
        side = side_of(signal)
        prev, why = None, ""
        if side not in ("long", "short"):
            why = f"no side for direction {getattr(signal, 'direction', None)!r}"
        else:
            try:
                prev = last_same_side_exit(config.DB_PATH, side, t)
            except Exception as exc:                             # noqa: BLE001
                why = f"trades.db unreadable: {exc}"
        if why:
            logger.info("[reentry] %s %s allowed - %s (RENT.2 fails open)", name, side, why)
            _row("reentry_gate.jsonl", {"at": round(t, 3), "strategy": name, "side": side, "mode": mode,
                                        "decision": "allowed", "why_unread": why})
            return False
        if prev is None or prev["age_s"] > RECORD_WINDOW_S:
            return False
        premium = is_premium_exit(prev["exit_reason"])
        hit = premium and prev["age_s"] <= WAIT_S
        effective = mode if (mode != "trade" or paper) else "log"
        block = bool(hit and effective == "trade")
        _row("reentry_gate.jsonl", {
            "at": round(t, 3), "strategy": name, "side": side, "mode": mode, "effective": effective,
            "decision": ("BLOCKED" if block else ("would_block" if hit else "allowed")),
            "wait_s": WAIT_S, "prev": dict(prev, premium=premium),
            "order": {"strike": getattr(signal, "strike", None),
                      "option_side": getattr(signal, "option_side", None),
                      "premium": getattr(signal, "entry_premium", None),
                      "contracts": contracts,
                      "underlying_entry": getattr(signal, "underlying_entry", None),
                      "underlying_stop": getattr(signal, "underlying_stop", None),
                      "price": ctx.get("price")}})
        if block:
            logger.info("[reentry] BLOCKED %s %s - %.1f s after a same-side PREMIUM exit (%s %s: %s) < %.0f s "
                        "(RENT.2; recorded with the would-be order)", name, side, prev["age_s"], prev["strategy"],
                        str(prev["trade_id"])[:8], str(prev["exit_reason"])[:40], WAIT_S)
        elif hit:
            logger.info("[reentry] would block %s %s - %.1f s after a premium exit, mode %s (RENT.2)",
                        name, side, prev["age_s"], effective)
        return block
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[reentry] gate error - entry allowed: %s", exc)
        return False
