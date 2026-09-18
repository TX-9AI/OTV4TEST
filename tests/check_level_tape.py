#!/usr/bin/env python3
"""
tests/check_level_tape.py  v1.1
THE LEVEL BOARD IS BUILT FROM THE HOURLY TAPE, EXCLUSIVELY (OTV4TEST r36).

v1.1  2026-09-18  OTV4TEST r39 — T6 WENT RED ON CORRECT CODE, AND THE REFLEX FIX
      WOULD HAVE BLINDED IT. It matched a FIXED 1400-CHARACTER SLICE taken from
      the `in_range` lambda. r39 inserted the zone-traversal rule between that
      lambda and the retirement it guards; the opening-range rule was untouched
      and fully bound, and T6 failed anyway. A canary keyed to a MAGIC DISTANCE
      fires on any insertion above its target, and the obvious repair is to
      raise 1400 until it passes — which is §20's loosened canary, and every
      future insertion buys another raise until the window is wide enough to
      catch nothing. Re-anchored on the BINDING: the `if` that actually reads
      `in_range(lvl_price)`, found wherever it sits.
      ⚠️ AND IT WAS MUTATION-TESTED RATHER THAN ASSUMED, because a re-anchored
      canary that no longer fires is worse than the false red it replaced.
      Four mutants against a CONTROL that must come back clean: dropping the
      `in_range` term, dropping the tine exemption, and renaming TRAVERSED are
      each CAUGHT; inserting forty filler lines above the guard PASSES, which
      is the false red this revision removed.
v1.0  2026-09-18  OTV4TEST r36 — born red at r35 (1006003), where `load_tape`
      reads `interval='1m'` and `daily_levels`/`load_daily` exist.

WHY THE HOUR. Retention keeps 1m for FIVE DAYS and 1h for SIXTY
(`RETENTION_DAYS`), so the board reached nine days back while twelve weeks of
hourly history sat unread in the same store. Measured 2026-09-17 against the
operator's own 1D chart: three of his five levels above spot were not in the
ledger at all. Operator: *"use 1-hr as far back as you can"*, then *"use the
hour exclusively"*.

WHAT IS PINNED:
  T1   `load_tape` reads the HOUR by default, and nothing in the level path
       asks for 1m
  T2   an hourly bar's high/low IS the extreme of its hour — merged 1h equals
       merged 1m on the 24-hour high AND low, every day both series cover
  T3   the sections stay hour-granular, so an hourly bar lands in exactly one
       section with no straddle
  T4   the DAILY source is GONE — it could not see overnight, which is the one
       thing the operator said matters most
  T5   the rejection fact is NOT on this tape: `_derive_events` reads `df_1m`
  T6   the opening-range rule still retires a level inside the range, and still
       exempts a tine
  T7   reach — the board sees further back than 1m retention could ever allow
"""
import os
import sqlite3
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILED, RAN = [], []


def check(name, ok, detail=""):
    RAN.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILED.append(name.split()[0])


def main():
    from derived import level_map as lm
    src_map = open(os.path.join(ROOT, "derived", "level_map.py"), encoding="utf-8").read()
    src_lv = open(os.path.join(ROOT, "derived", "levels.py"), encoding="utf-8").read()

    # ── T1 — the hour is the default, and nothing asks for 1m ───────────────
    check("T1 load_tape defaults to the HOUR",
          getattr(lm, "TAPE_INTERVAL", None) == "1h"
          and lm.load_tape.__defaults__ and lm.load_tape.__defaults__[0] == "1h",
          f"TAPE_INTERVAL={getattr(lm, 'TAPE_INTERVAL', None)!r}")

    # scoped to a CALL, not a mention (§20): the changelog says "1m" on purpose
    check("T1b no level-path call asks for the 1m interval",
          "interval='1m'" not in src_map and 'interval="1m"' not in src_map,
          "no 1m literal in a query")

    # ── T4 — the daily source is gone, by ruling ────────────────────────────
    check("T4 the DAILY source is removed — it cannot see overnight",
          not hasattr(lm, "daily_levels") and not hasattr(lm, "load_daily"),
          "daily_levels/load_daily absent")

    # ── T5 — the rejection fact keeps its minute ────────────────────────────
    ev = src_lv[src_lv.index("def _derive_events"):]
    ev = ev[:ev.index("\n    def ", 10)] if "\n    def " in ev[10:] else ev
    check("T5 the rejection fact reads df_1m, NOT the level tape",
          'ctx.get("df_1m")' in ev and "level_tape" not in ev,
          "WICKED/REJECTED/ACCEPTED stay on the closed MINUTE")

    # ── T3 — sections are hour-granular, so an hourly bar cannot straddle ───
    from analysis.liquidity_mapper import LiquidityMapper
    import datetime as _dt
    secs = LiquidityMapper._sections_for(LiquidityMapper.__new__(LiquidityMapper),
                                         _dt.date(2026, 9, 17))
    check("T3 every section boundary is a whole UTC hour",
          all(isinstance(h0, int) and isinstance(h1, int) for _, h0, h1 in secs),
          str([(n, h0, h1) for n, h0, h1 in secs]))

    # ── the real store: T2, T7 ──────────────────────────────────────────────
    db = os.path.join(ROOT, "data", "feed_store.db")
    if not os.path.exists(db):
        check("T2 skipped — no feed store on this box", True, "not a box")
        print()
        return 1 if FAILED else 0

    tape = lm.load_tape(db, "QQQ")
    check("T7 the board reaches further back than 1m retention allows (5 days)",
          tape is not None and (tape.index[-1] - tape.index[0]).days > 30,
          f"{(tape.index[-1]-tape.index[0]).days} days of tape" if tape is not None else "no tape")

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)

    # T2 — EACH HOURLY BAR AGAINST ITS OWN HOUR OF 1m, which is the only
    # comparison that means anything. The first cut bucketed by UTC DAY and
    # reported 4 of 7 days "mismatched" — true, but it could not say WHICH bar
    # was wrong, and a day-level answer hid that the errors were all in one
    # direction (narrower range = an unfinished bar).
    # 🔴 THIS IS THE CHECK THAT CAUGHT A REAL CORRUPTION. On 2026-09-18 a seed
    # wrote S3 hourly bars over locally-complete ones with INSERT OR REPLACE,
    # and 369 of 1,265 were PARTIAL — pushed mid-hour, so `19:00 UTC` on 09-16
    # read 705.46/704.08 when the true hour was 706.02/700.00. A level at
    # 700.00 that price turned at was invisible. The rule the data demands:
    # a bar is accepted only if its object was pushed at or after its hour ENDED.
    rows = con.execute(
        "SELECT c.symbol, c.ts_epoch_ms, c.high, c.low, m.mh, m.ml, m.n FROM candles c"
        " JOIN (SELECT symbol, (ts_epoch_ms/3600000)*3600000 h, MAX(high) mh, MIN(low) ml,"
        "              COUNT(*) n FROM candles"
        "       WHERE symbol IN ('QQQ','QQQ_EXT') AND interval='1m'"
        "       GROUP BY symbol, h) m"
        "   ON m.symbol=c.symbol AND m.h=c.ts_epoch_ms"
        " WHERE c.symbol IN ('QQQ','QQQ_EXT') AND c.interval='1h'").fetchall()
    # an hour the 1m tape only partly covers cannot judge the hourly bar
    judged = [r for r in rows if r[6] >= 30]
    bad = [r for r in judged if r[2] < r[4] - 0.02 or r[3] > r[5] + 0.02]
    con.close()
    check("T2 every hourly bar is at least as wide as its own hour of 1m — no PARTIAL bars",
          judged and not bad,
          f"{len(judged)} bars judged, {len(bad)} narrower than the minute truth"
          + (f" e.g. {bad[0][0]} {bad[0][2]:.2f}/{bad[0][3]:.2f} vs {bad[0][4]:.2f}/{bad[0][5]:.2f}" if bad else ""))

    # ── T6 — the opening-range rule survives, tines still exempt ────────────
    # ⚠️ THE FIRST CUT OF T6 MATCHED THE DOCSTRING, NOT THE CODE — §21 again,
    # in a checker. `levels.py` explains the rule at :204 and implements it at
    # :811, and a 600-char slice from the prose contains the word TRAVERSED
    # while containing none of the logic. Anchored on the CODE now.
    # 🔴 AND ITS SECOND CUT BROKE ON CORRECT CODE AT r39, WHICH IS THE SAME
    # LESSON ONE LAYER IN. It took a FIXED 1400-CHARACTER SLICE from the
    # `in_range` lambda. r39 inserted the zone-traversal rule between that
    # lambda and the retirement it guards — the rule was untouched and fully
    # bound, and T6 went red anyway. A canary keyed to a MAGIC DISTANCE fires
    # on any insertion above its target, and the reflex fix is to raise 1400
    # until it passes, which is §20's loosened-canary exactly. It is anchored
    # on the BINDING now — the `if` that actually reads `in_range(lvl_price)`,
    # located wherever it sits — so inserting code above it cannot move it.
    m6 = re.search(
        r'if kind in \("support", "resistance"\)[^\n]*\n(?:[^\n]*\n){0,3}?'
        r'[^\n]*in_range\(lvl_price\)[^\n]*\n(?:[^\n]*\n){0,4}?'
        r'[^\n]*st\["reason"\] = "TRAVERSED"', src_lv)
    check("T6 a level inside the opening range is retired TRAVERSED, tines exempt",
          bool(m6) and "not self._is_tine(prov)" in m6.group(0),
          "r5's rule, asserted against the binding that enforces it")

    print()
    if FAILED:
        print(f"RED — {len(FAILED)} of {len(RAN)} failed: {', '.join(FAILED)}")
        return 1
    print(f"GREEN — {len(RAN)} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
