#!/usr/bin/env python3
"""tests/check_level_map.py — v1.3
v1.3  2026-09-23 — OTV4TEST r110. Pinned to LEVEL_SOURCE="legacy": the book is now the default path (see the pin below). And the r106 venv bootstrap, so it runs under the lander's system python3.
v1.2  2026-09-17 — OTV4TEST r33. M9 AND M12 ASSERTED CONTRACTS THAT RULINGS
      REPLACED, AND ARE REWRITTEN RATHER THAN LOOSENED. M9's second half required
      `"_lm.walk(" in src` — the sweep running its OWN walk — which is exactly what
      check_level_source S2 now REFUSES; two gates asserting opposite things, and
      this was the stale one (M9b inverts it, the created_ts half stays because the
      walk needs a formation time). M12 pinned r30's STALE_VWAP sweep for a
      producer r33 deleted: VWAP is not a level, no reader has ever seen a
      `dynamic` row, so M12 now pins that none is left LIVE and none is minted,
      and M12b that a legacy row from a pre-r33 store is retired.
v1.1  2026-09-14 — OTV4TEST r30. M10-M12, from reading r29's noon bake on the box: a
      confirmed legacy row kept `timeframe='session'`, so it would retire once the
      tape stopped reaching it (M10, M11 — Saturday's purge); r29 claimed to retire
      stale VWAP ids and skipped them, 515 live (M12). All three born red at 0c3b01b.
THE LEVELS ARE BUILT FROM THE TAPE, AND THE LEDGER HOLDS ONLY WHAT THE TAPE HOLDS.

v1.0  2026-09-14 — OTV4TEST r29 (LVL.8, LVL.9). Operator: *"Levels are session
      extremes that held. Starting from spot, map the most recent up/down levels
      going backwards in time and further up/down from the recent ones. A level is
      spent if it didn't hold & price accepted through it."* Fork PLAN_SPEC §31.1,
      mainline §38 / LVL.3 / LVL.17.

🔑 THE FIXTURE IS THE BOX'S OWN TAPE, NOT A HAND-BUILT ONE (§0.4):
`tests/fixtures/qqq_1m_20260914.tape` is QQQ + QQQ_EXT 1m, exported read-only from
this box's feed_store.db, 09-08 20:38 → 09-14 09:28 ET. Expected values below were
read off that tape, and the legacy rows seeded into the scratch ledger are the
shapes measured live at 09:10 ET (fork1h rail, 1h tine row, `(R2)` pool, bare
`asia` row).

  M0  derived/level_map exists and levels v5.0 takes `level_tape`
  M1  sessions: London 09-14 high 715.42 at 08:26 ET, low 701.16 — no print filter (ruling)
  M2  a wick does not spend (715.42 held); two closes beyond do (Asia Low 09-14 703.27, 04:57 ET —
      beyond the engine's own 0.15% close tolerance; 04:29 without it, verified by hand off the tape)
  M3  the walk from 703.32: up 715.42, 717.68, 719.70, 720.06 (newest first, further out); down 701.16
  M4  reconcile retires the ghosts: fork1h/*, 1h tine, (R2) pool -> NOT_A_LEVEL
  M4b ...a legacy row the tape holds (asia 714.75) is KEPT and its created_ts is the print's bar
  M4c ...a legacy row the tape shows spent (asia 703.27) -> ACCEPTED_THROUGH at 04:57 ET, and NO event (history never fires)
  M4d ...a session row formed BEFORE the tape begins is kept (the book reaches further than the tape)
  M5  the board walks: above the 702.50-704.00 range 715.42 first; below 701.16
  M6  a restart (new engine, same store) un-retires nothing
  M7  a FRESH acceptance on the live tape emits ACCEPTED and retires the level
  M8  no tape (None) retires nothing
  M9  live_levels carries created_ts; the sweep plan walks it
  M10 a confirmed legacy row gets its dated timeframe (session:2026-09-14), not just its time
  M11 ...and so stays live when the tape is trimmed past its session (Saturday's purge)
  M12 stale VWAP ids retire STALE_VWAP; the current VWAP row stays live
Born red at 2a346c4 (r28): no derived/level_map, no reconcile, board unwalked.
Run:  python3 tests/check_level_map.py
"""
import os
import sys
import tempfile
import time

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

# r106 IDIOM — THE LANDER RUNS CHECKS UNDER SYSTEM `python3`, NOT THE VENV, and
# this file reaches pandas/numpy, which live only in the venv (3.14, the same
# ABI as system python3 on this box — measured 2026-09-23). Index 1: the venv
# beats /usr/lib/python3/dist-packages while the repo root still wins. Without
# it this checker could not be DECLARED as a CHECK — it failed under the lander
# on `No module named 'pandas'` while passing by hand.
import glob as _glob
for _sp in _glob.glob(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   "venv", "lib", "python*", "site-packages")):
    if _sp not in sys.path:
        sys.path.insert(1, _sp)

# v1.3 (2026-09-23, OTV4TEST r110) — THIS CHECKER PINS THE LEGACY LEVEL ENGINE.
# derived/levels v6.0 routes derive() to the level book by default (LVL.15 step
# 2), and the book replaces the rules pinned here with the operator's final
# definitions. The legacy path still exists as the rollback setting until step
# 5 deletes it, so this checker keeps guarding THAT code rather than being
# bent to fit the book; the book path is gated by check_level_engine_book.
try:
    import derived.levels as _legacy_pin
    _legacy_pin.LEVEL_SOURCE = "legacy"
except Exception:                                               # noqa: BLE001
    pass                                   # the checker's own import reports it
FAILED, RAN = [], []
TAPE = os.path.join(_root, "tests", "fixtures", "qqq_1m_20260914.tape")
ET = "America/New_York"


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    RAN.append(name)
    if not ok:
        FAILED.append(name)


def _tape():
    import pandas as pd
    df = pd.read_csv(TAPE, comment="#")
    df.index = pd.to_datetime(df.pop("ts_epoch_ms"), unit="ms", utc=True)
    return df


class _Orb:
    orb_high, orb_low = 704.00, 702.50


def _et(ts):
    return ts.tz_convert(ET).strftime("%m-%d %H:%M")


def main():
    try:
        from derived import level_map as lm
    except ImportError as exc:
        check("M0 derived/level_map exists", False, str(exc))
        print(f"\nRED — {len(FAILED)} of {len(RAN)} failed")
        return 1
    import pandas as pd
    from data.derived_store import DerivedStore
    from derived.levels import LevelEngine
    check("M0 derived/level_map exists and levels v5.0 takes level_tape",
          hasattr(LevelEngine, "_tape_sources"))

    df = _tape()
    L = lm.session_levels(df, accept_closes=2, tol_pct=0.0015)
    by = {l["name"]: l for l in L}
    lh, ll = by.get("London High 09-14"), by.get("London Low 09-14")
    check("M1 London 09-14 high 715.42 at 08:26 ET and low 701.16 (no print filter, by ruling)",
          lh is not None and ll is not None and abs(lh["price"] - 715.416) < 1e-6
          and _et(lh["formed_ts"]) == "09-14 08:26" and abs(ll["price"] - 701.16) < 1e-6,
          f"{lh and (lh['price'], _et(lh['formed_ts']))} {ll and ll['price']}")
    al = by.get("Asia Low 09-14")
    check("M2 a wick does not spend; two closes beyond do",
          lh is not None and lh["spent_ts"] is None and al is not None
          and al["spent_ts"] is not None and _et(al["spent_ts"]) == "09-14 04:57",
          f"london high spent={lh and lh['spent_ts']} asia low spent={al and al['spent_ts'] and _et(al['spent_ts'])}")
    w = lm.walk([l for l in L if l["spent_ts"] is None], 703.32)
    up = [round(l["price"], 2) for l in w["up"]]
    dn = [round(l["price"], 2) for l in w["down"]]
    check("M3 the walk from 703.32: newest first, each older level further out",
          up == [715.42, 717.68, 719.7, 720.06] and dn == [701.16], f"up={up} down={dn}")

    # ── the engine against a scratch ledger seeded with the live shapes ─────
    store = DerivedStore(path=os.path.join(tempfile.mkdtemp(), "derived.db"))
    now = time.time()
    legacy = [
        ("QQQ:fork1h/lower:705.99", 705.994, "support", "fork1h/lower", "1h", now - 5 * 86400),
        ("QQQ:1h upper tine:716.20", 716.2, "high", "1h upper tine", "1h", now - 3 * 86400),
        ("QQQ:PDH (R2):717.68", 717.68, "resistance", "PDH (R2)", "1h", now - 3600),
        ("QQQ:asia:714.75", 714.75, "resistance", "asia", "session", now - 3600),
        ("QQQ:asia:703.27", 703.27, "support", "asia", "session", now - 3600),
        ("QQQ:ny:730.00", 730.0, "resistance", "ny", "session:2026-09-04",
         pd.Timestamp("2026-09-04 14:00", tz="UTC").timestamp()),
    ]
    for lid, p, k, prov, tf, cr in legacy:
        store.upsert_level((lid, "QQQ", p, k, prov, tf, cr, 0, None, 0, None, None, 0))
    store.commit()

    d1 = df.tail(60).copy()
    d1.index = d1.index.tz_convert(ET)
    ctx = {"symbol": "QQQ", "price": 703.32, "vol": None, "orb": _Orb(),
           "df_1m": d1, "level_tape": df}
    eng = LevelEngine(store, "QQQ")
    eng.derive(ctx)
    store.commit()
    row = {r[0]: r for r in store.conn.execute(
        "SELECT level_id, retired_ts, retired_reason, created_ts FROM level_ledger")}
    ghosts = ["QQQ:fork1h/lower:705.99", "QQQ:1h upper tine:716.20", "QQQ:PDH (R2):717.68"]
    check("M4 reconcile retires the ghosts as NOT_A_LEVEL",
          all(row[g][2] == "NOT_A_LEVEL" for g in ghosts), str([row[g][2] for g in ghosts]))
    a = row.get("QQQ:asia:714.75")
    formed = by["Asia High 09-14"]["formed_ts"].timestamp()
    check("M4b a legacy row the tape holds is kept, created_ts = the print's bar",
          a is not None and a[1] is None and abs(float(a[3]) - formed) < 1.0,
          f"{a}")
    s = row.get("QQQ:asia:703.27")
    ev = store.conn.execute("SELECT count(*) FROM level_event WHERE level_id='QQQ:asia:703.27'").fetchone()[0]
    check("M4c a spent legacy row -> ACCEPTED_THROUGH at 04:57 ET, and no event",
          s is not None and s[2] == "ACCEPTED_THROUGH"
          and _et(pd.Timestamp(float(s[1]), unit="s", tz="UTC")) == "09-14 04:57" and ev == 0,
          f"{s} events={ev}")
    o = row.get("QQQ:ny:730.00")
    check("M4d a session row formed before the tape begins is kept", o is not None and o[1] is None, f"{o}")

    b = eng.board(703.32, 704.00, 702.50)
    check("M5 the board walks: above 715.42 first, below 701.16",
          b["state"] == "ok" and [round(x["price"], 2) for x in b["above"]][:1] == [715.42]
          and [round(x["price"], 2) for x in b["below"]] == [701.16],
          f"above={[round(x['price'], 2) for x in b['above']]} below={[round(x['price'], 2) for x in b['below']]}")

    retired_before = {r[0] for r in store.conn.execute(
        "SELECT level_id FROM level_ledger WHERE retired_ts IS NOT NULL")}
    eng2 = LevelEngine(store, "QQQ")
    eng2.derive(ctx)
    store.commit()
    still = {r[0] for r in store.conn.execute(
        "SELECT level_id FROM level_ledger WHERE retired_ts IS NOT NULL")}
    check("M6 a restart un-retires nothing", retired_before <= still,
          f"un-retired: {sorted(retired_before - still)}")

    # M7 — a fresh acceptance above 715.42 appended to the live tape
    t0 = pd.Timestamp(now - 180, unit="s", tz="UTC").floor("min")
    ext = pd.DataFrame({"open": [715.0, 716.5, 716.6], "high": [716.0, 716.9, 716.9],
                        "low": [714.9, 716.2, 716.3], "close": [715.9, 716.7, 716.8]},
                       index=[t0, t0 + pd.Timedelta(minutes=1), t0 + pd.Timedelta(minutes=2)])
    df7 = pd.concat([df, ext])
    d7 = df7.tail(60).copy()
    d7.index = d7.index.tz_convert(ET)
    eng2.derive(dict(ctx, price=716.8, df_1m=d7, level_tape=df7))
    store.commit()
    lid = "QQQ:london:715.42"
    r7 = store.conn.execute("SELECT retired_reason FROM level_ledger WHERE level_id=?", (lid,)).fetchone()
    e7 = store.conn.execute("SELECT count(*) FROM level_event WHERE level_id=? AND event='ACCEPTED'",
                            (lid,)).fetchone()[0]
    check("M7 a fresh acceptance emits ACCEPTED and retires the level",
          r7 is not None and r7[0] == "ACCEPTED_THROUGH" and e7 >= 1, f"{r7} events={e7}")

    live_before = store.conn.execute("SELECT count(*) FROM level_ledger WHERE retired_ts IS NULL").fetchone()[0]
    LevelEngine(store, "QQQ").derive(dict(ctx, level_tape=None))
    store.commit()
    live_after = store.conn.execute("SELECT count(*) FROM level_ledger WHERE retired_ts IS NULL").fetchone()[0]
    check("M8 no tape retires nothing", live_after >= live_before, f"{live_before} -> {live_after}")

    lv = store.live_levels("QQQ")
    src = open(os.path.join(_root, "strategy", "sweep_plan.py"), encoding="utf-8").read()
    # r33 — M9's SECOND HALF PINNED THE DEFECT. It asserted `"_lm.walk(" in src`
    # — the sweep running its OWN walk — which is exactly what the operator ruled
    # out on 2026-09-17 ("every trade that relies on levels gets it from the same
    # place") and what check_level_source S2 now REFUSES. Two gates asserting
    # opposite things; this is the stale one. The first half still matters and
    # stays: the walk needs a formation time, so `live_levels` must carry it.
    check("M9 live_levels carries created_ts — the walk needs a formation time",
          bool(lv) and all("created_ts" in x for x in lv), f"{len(lv)} live")
    check("M9b the sweep reaches the ONE board, it does not walk privately (r33)",
          "board_for(" in src and "_lm.walk(" not in src.split('"""', 2)[-1],
          "sweep -> board_for")

    # ── r30 — M10-M12, a fresh ledger so M7's mutations do not leak in ──────
    store2 = DerivedStore(path=os.path.join(tempfile.mkdtemp(), "derived.db"))
    for lid, p, k, prov, tf, cr in [
        ("QQQ:asia:714.75", 714.75, "resistance", "asia", "session", now - 3600),
        ("QQQ:london:720.06", 720.06, "resistance", "london", "session", now - 3600),
        ("QQQ:vwap:700.00", 700.0, "dynamic", "vwap", "session", now - 7200),
        ("QQQ:vwap:705.00", 705.0, "dynamic", "vwap", "session", now - 60),
    ]:
        store2.upsert_level((lid, "QQQ", p, k, prov, tf, cr, 0, None, 0, None, None, 1 if prov == "vwap" else 0))
    store2.commit()

    class _Vol:
        vwap = 705.0
    ctx2 = dict(ctx, vol=_Vol(), level_tape=df)
    LevelEngine(store2, "QQQ").derive(ctx2)
    store2.commit()
    tf10 = store2.conn.execute("SELECT timeframe, retired_ts FROM level_ledger WHERE level_id='QQQ:asia:714.75'").fetchone()
    check("M10 a confirmed legacy row gets its dated timeframe", tf10 is not None and tf10[0] == "session:2026-09-14"
          and tf10[1] is None, f"{tf10}")
    trimmed = df[df.index >= pd.Timestamp("2026-09-10 12:00", tz="UTC")]
    LevelEngine(store2, "QQQ").derive(dict(ctx2, level_tape=trimmed))
    store2.commit()
    r11 = store2.conn.execute("SELECT timeframe, retired_ts, retired_reason FROM level_ledger WHERE level_id='QQQ:london:720.06'").fetchone()
    check("M11 a confirmed level stays live when the tape no longer reaches its session",
          r11 is not None and r11[1] is None, f"{r11}")
    v = {r[0]: r for r in store2.conn.execute(
        "SELECT level_id, retired_ts, retired_reason FROM level_ledger WHERE provenance='vwap'")}
    # r33 — M12 IS REWRITTEN, NOT LOOSENED, AND THE REASON IS A RULING.
    # r30's M12 pinned "stale VWAP ids retire STALE_VWAP; the CURRENT one stays
    # live" — a contract that only makes sense while VWAP is a level. The
    # operator ruled on 2026-09-17 that it is not one and never was: no reader
    # has ever seen a `kind="dynamic"` row, because every accessor filters
    # `kind IN ('support','resistance')`. The producer is gone and the 855 rows
    # were deleted. So the thing to pin is the OPPOSITE: nothing mints one, and
    # a row from a pre-r33 store does not survive as live.
    # the fixture SEEDS two legacy vwap ids on purpose (they are what r30's
    # STALE_VWAP sweep was written against), so the assertion is not "no rows"
    # — it is that the derive LEAVES NONE LIVE and mints no new one.
    check("M12 VWAP is not a level: no dynamic row is left live, and none is minted",
          all(r[1] is not None for r in v.values()) and len(v) == 2,
          f"vwap rows: {[(k, r[2]) for k, r in sorted(v.items())]}")
    store2.conn.execute(
        "INSERT INTO level_ledger (level_id, symbol, price, kind, provenance, timeframe,"
        " created_ts, touch_count, retired_ts) VALUES"
        " ('QQQ:vwap:701.00','QQQ',701.0,'dynamic','vwap','session',1,0,NULL)")
    store2.commit()
    LevelEngine(store2, "QQQ").derive(ctx2)
    store2.commit()
    leg = store2.conn.execute(
        "SELECT retired_ts, retired_reason FROM level_ledger"
        " WHERE level_id='QQQ:vwap:701.00'").fetchone()
    check("M12b a legacy dynamic row from a pre-r33 store is retired, not left live",
          leg is not None and leg[0] is not None, f"{leg}")

    print()
    if FAILED:
        print(f"RED — {len(FAILED)} of {len(RAN)} failed: {', '.join(FAILED)}")
        return 1
    print(f"GREEN — {len(RAN)} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
