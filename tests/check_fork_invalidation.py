#!/usr/bin/env python3
"""
tests/check_fork_invalidation.py  v1.0
A FORK'S DEATH IS DECIDED BY ITS BUILDER — driven through ForkEngine.derive().

v1.0  2026-09-23  OTV4TEST r115. Born RED at r114, where the breach was judged
      in the LEVEL engine and the ForkEngine went on serving the dead fork.

The operator, 2026-09-23: "I wanna make sure that the invalidation of the fork
comes from the fork builder's engine, not from a strategy-plan", "it's gone when
the engine says it's gone, not when a strategy says it's gone", and "the same
engine that declares whether there's a fork or not should decide the persistence
of the projection." And the definitions: "A breech is an event that invalidates
the fork"; "any interaction that doesn't cause the fork object to destruct is a
touch."

  F1 a rail BREACHED (1m close beyond, next 1m open beyond) -> the ForkEngine
     stops serving the fork (last_forks cleared) and writes an INVALIDATED row
  F2 the builder hands back the SAME fork next run -> refused (not served)
  F3 §22 — a restarted ForkEngine on the same store does not serve it either
  F4 a fork with a NEW identity (new anchor prices) is served
  F5 a TOUCH (wick reaches the rail, close back inside) changes nothing
  F6 identity is the anchor PRICES: the same fork with every idx shifted by one
     (the rolling frame) is still refused
  F7 the LEVEL engine seeing a breach does NOT withdraw the rails — not its call
  F8 the r114 -> r115 handover: a fork r114 invalidated (level_event) stays refused
"""
from __future__ import annotations

import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import glob as _glob                                             # r106 venv bootstrap
for _sp in _glob.glob(os.path.join(ROOT, "venv", "lib", "python*", "site-packages")):
    if _sp not in sys.path:
        sys.path.insert(1, _sp)

FAILED, RAN = [], []
WORK = tempfile.mkdtemp(prefix="chk_forkinv-")
os.environ["OT_FEED_DB"] = os.path.join(WORK, "empty_feed.db")


def check(name, ok, detail=""):
    RAN.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILED.append(name.split()[0])


def guard(name, fn):
    try:
        ok, detail = fn()
    except Exception as exc:                                    # noqa: BLE001
        ok, detail = False, f"raised {type(exc).__name__}: {exc}"
    check(name, ok, detail)


def a_fork(anchor=100.0, shift=0.0):
    """Flat rails: upper 102, median 100, lower 98; identity from the anchor prices."""
    P = lambda i, p: types.SimpleNamespace(idx=i - shift, price=p, kind="low")   # noqa: E731
    return types.SimpleNamespace(slope=0.0, direction="up", filters_passed=(),
                                 p0=P(10.0, anchor - 2), p1=P(30.0, anchor + 2), p2=P(50.0, anchor - 1),
                                 upper_at=lambda i: 102.0, median_at=lambda i: 100.0, lower_at=lambda i: 98.0)


CURRENT = {"fork": a_fork()}


def install_builder():
    """The builder returns CURRENT['fork'] for 1h and nothing for 1d."""
    from analysis import pitchfork as pf
    pf.build_fork_contained = lambda sym, df, tf, atr: CURRENT["fork"] if tf == "1h" else None
    pf.last_reject_reason = lambda: None
    pf.last_scan_depth = lambda: 0


_MIN = [0]


def run(eng, o, h, l, c):
    """One ForkEngine run with ONE newly closed 1m bar (df_1m[-2]); the frames exist."""
    import pandas as pd
    _MIN[0] += 1
    t0 = pd.Timestamp("2026-09-23 12:00", tz="America/New_York") + pd.Timedelta(minutes=_MIN[0])
    df1 = pd.DataFrame({"open": [o, c], "high": [h, c], "low": [l, c], "close": [c, c]},
                       index=[t0, t0 + pd.Timedelta(minutes=1)])
    frame = pd.DataFrame({"open": [100.0] * 30, "high": [101.0] * 30, "low": [99.0] * 30, "close": [100.0] * 30})
    eng._last_run = 0.0                                         # the 60s interval is not under test
    eng.run({"symbol": "QQQ", "data": {"1h": frame, "1d": frame}, "df_1m": df1})


def new_engine(store=None):
    from data.derived_store import DerivedStore
    from derived.forks import ForkEngine
    store = store or DerivedStore(tempfile.mktemp(dir=WORK, prefix="d-", suffix=".db"))
    return ForkEngine(store, "QQQ"), store


def breach(eng):
    run(eng, 99.0, 99.1, 97.9, 97.95)                           # closes beyond the lower rail (98)
    run(eng, 97.94, 98.0, 97.9, 97.93)                          # and opens beyond -> BREACHED


def inv_rows(st):
    return st.conn.execute("SELECT reject_reason FROM fork_series WHERE reject_reason LIKE 'INVALIDATED%'").fetchall()


def _f1():
    CURRENT["fork"] = a_fork(); eng, st = new_engine()
    run(eng, 100.0, 100.2, 99.8, 100.0)                         # served
    served_before = "1h" in eng.last_forks
    breach(eng)
    rows = inv_rows(st)
    return (served_before and "1h" not in eng.last_forks and any(r[0].startswith("INVALIDATED:") for r in rows)), \
        f"served before {served_before}; after {'1h' in eng.last_forks}; rows {rows}"


def _f2():
    CURRENT["fork"] = a_fork(); eng, st = new_engine()
    run(eng, 100.0, 100.2, 99.8, 100.0); breach(eng)
    run(eng, 97.9, 98.0, 97.8, 97.9)                            # the builder rebuilds the SAME fork
    return ("1h" not in eng.last_forks), f"served again: {'1h' in eng.last_forks}"


def _f3():
    CURRENT["fork"] = a_fork(); eng, st = new_engine()
    run(eng, 100.0, 100.2, 99.8, 100.0); breach(eng)
    eng2, _ = new_engine(store=st)                              # a restart
    run(eng2, 100.0, 100.2, 99.8, 100.0)
    return ("1h" not in eng2.last_forks), f"served after restart: {'1h' in eng2.last_forks}"


def _f4():
    CURRENT["fork"] = a_fork(); eng, st = new_engine()
    run(eng, 100.0, 100.2, 99.8, 100.0); breach(eng)
    CURRENT["fork"] = a_fork(anchor=100.7)                      # a NEW identity
    run(eng, 100.0, 100.2, 99.8, 100.0)
    return ("1h" in eng.last_forks), f"new fork served: {'1h' in eng.last_forks}"


def _f5():
    CURRENT["fork"] = a_fork(); eng, st = new_engine()
    run(eng, 99.0, 99.2, 98.0, 98.6)                            # wick reaches 98, closes inside
    run(eng, 98.6, 98.9, 97.95, 98.4)                           # wick past 98, closes back inside
    return ("1h" in eng.last_forks and not inv_rows(st)), f"served {'1h' in eng.last_forks}; rows {inv_rows(st)}"


def _f6():
    CURRENT["fork"] = a_fork(); eng, st = new_engine()
    run(eng, 100.0, 100.2, 99.8, 100.0); breach(eng)
    CURRENT["fork"] = a_fork(shift=1.0)                         # same anchors, frame rolled one bar
    run(eng, 97.9, 98.0, 97.8, 97.9)
    return ("1h" not in eng.last_forks), f"served after the frame rolled: {'1h' in eng.last_forks}"


def _f7():
    """The level engine sees the same breach on a fork the ForkEngine still holds
    (its interval had not come round): the rails are NOT withdrawn by it."""
    from data.derived_store import DerivedStore
    import derived.levels as L
    import pandas as pd
    fe = types.SimpleNamespace(last_forks={"1h": a_fork()}, last_idx={"1h": 20.0})
    st = DerivedStore(tempfile.mktemp(dir=WORK, prefix="dl-", suffix=".db"))
    lv = L.LevelEngine(st, "QQQ", forks=fe)
    for o, h, l, c in ((99.0, 99.1, 97.9, 97.95), (97.94, 98.0, 97.9, 97.93)):
        _MIN[0] += 1
        t0 = pd.Timestamp("2026-09-23 12:00", tz="America/New_York") + pd.Timedelta(minutes=_MIN[0])
        df = pd.DataFrame({"open": [o, c], "high": [h, c], "low": [l, c], "close": [c, c]},
                          index=[t0, t0 + pd.Timedelta(minutes=1)])
        lv.derive({"symbol": "QQQ", "price": c, "df_1m": df})
    n = len(lv.tines_now(97.9))
    ev = st.conn.execute("SELECT count(*) FROM level_event WHERE event='INVALIDATED'").fetchone()[0]
    return (n == 3 and ev == 0), f"rails still served by the level engine: {n}; INVALIDATED rows it wrote: {ev}"



def _f8():
    """The r114 -> r115 handover: r114 recorded its invalidation in level_event
    with the identity as ((price, kind), ...). That fork is still refused."""
    CURRENT["fork"] = a_fork()
    eng, st = new_engine()
    import time as _t
    key = tuple((round(p_.price, 4), "low") for p_ in (CURRENT["fork"].p0, CURRENT["fork"].p1, CURRENT["fork"].p2))
    st.insert_level_event(("QQQ", "QQQ:fork1h/lower:0.00", "2026-09-23 14:42:00-04:00", _t.time(), "INVALIDATED",
                           98.0, "support", "fork1h/lower", 0.0, repr(key), 0, 97.9))
    run(eng, 100.0, 100.2, 99.8, 100.0)
    return ("1h" not in eng.last_forks), f"r114-invalidated fork served: {'1h' in eng.last_forks}"


install_builder()
guard("F1 a rail BREACHED -> the ForkEngine stops serving the fork and records INVALIDATED", _f1)
guard("F2 the builder's rebuild of the SAME fork is refused", _f2)
guard("F3 §22: a restarted ForkEngine does not serve it", _f3)
guard("F4 a NEW identity is served", _f4)
guard("F5 a touch changes nothing (served, no INVALIDATED row)", _f5)
guard("F6 identity is the anchor prices: the rolled frame's same fork stays refused", _f6)
guard("F7 the LEVEL engine seeing a breach does not withdraw the rails — not its call", _f7)
guard("F8 the r114 -> r115 handover: a fork r114 invalidated in level_event stays refused", _f8)

import shutil
shutil.rmtree(WORK, ignore_errors=True)
print()
if FAILED:
    print(f"RED — {len(FAILED)} of {len(RAN)} failed: {', '.join(FAILED)}")
    sys.exit(1)
print(f"GREEN — {len(RAN)} checks")
sys.exit(0)
