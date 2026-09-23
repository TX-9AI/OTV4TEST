#!/usr/bin/env python3
"""
tests/check_rails_book.py  v1.0
THE FORK'S RAILS ON THE OPERATOR'S DEFINITIONS — driven through derive().

v1.0  2026-09-23  OTV4TEST r114. Born RED at the r113 engine, whose rails still
      ran the old tine branch (0.15% close tolerance, depth-graded WICKED/REJECTED,
      no notion of a fork being invalidated).

The operator, 2026-09-23: "Any interaction that doesn't cause the fork object to
destruct is a touch. A breech is an event that invalidates the fork."

  R1 a wick that REACHES a rail exactly and closes back inside is a touch ->
     REJECTED on the rail's id (the old path needed the wick strictly beyond)
  R2 a wick past the rail that closes back inside is a touch, pierce recorded
  R3 a 1m close beyond the rail by 0.05% (inside the OLD 0.15% tolerance) and the
     next open beyond -> the fork is INVALIDATED: an INVALIDATED row, no rails from
     tines_now, and the board reads fork "absent"
  R4 §22: a restarted engine on the same store does not resurrect that fork
  R5 a fork with a NEW identity (new anchors) serves rails again
  R6 no WICKED rows are written for rails (the old branch does not run)
  R7 identity survives the rolling frame: the same fork one bar later (every
     anchor idx - 1, prices unchanged) is still invalidated — r19 keyed on idx
"""
from __future__ import annotations

import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# the r106 venv bootstrap: the lander runs CHECKs under system python3 (no pandas)
import glob as _glob
for _sp in _glob.glob(os.path.join(ROOT, "venv", "lib", "python*", "site-packages")):
    if _sp not in sys.path:
        sys.path.insert(1, _sp)

FAILED, RAN = [], []
WORK = tempfile.mkdtemp(prefix="chk_rails-")
os.environ["OT_FEED_DB"] = os.path.join(WORK, "empty_feed.db")      # no tape: the book stays quiet


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


def fake_forks(anchor=100.0):
    """A flat 1h fork: upper 102, median 100, lower 98 (slope 0), identity by anchor."""
    fork = types.SimpleNamespace(
        slope=0.0, direction="up",
        p0=types.SimpleNamespace(idx=1.0, price=anchor - 2), p1=types.SimpleNamespace(idx=5.0, price=anchor + 2),
        p2=types.SimpleNamespace(idx=9.0, price=anchor - 2),
        upper_at=lambda i: 102.0, median_at=lambda i: 100.0, lower_at=lambda i: 98.0)
    return types.SimpleNamespace(last_forks={"1h": fork}, last_idx={"1h": 20.0})


_MIN = [0]


def step(eng, o, h, l, c, price=None):
    """One closed 1m bar through derive(): df_1m[-2] is the bar, [-1] is the forming one."""
    import pandas as pd
    _MIN[0] += 1
    t0 = pd.Timestamp("2026-09-23 12:00", tz="America/New_York") + pd.Timedelta(minutes=_MIN[0])
    df = pd.DataFrame({"open": [o, c], "high": [h, c], "low": [l, c], "close": [c, c]},
                      index=[t0, t0 + pd.Timedelta(minutes=1)])
    eng.derive({"symbol": "QQQ", "price": price or c, "df_1m": df})


def rows(store, ev=None):
    q = "SELECT level_id, event, round(pierce_pct, 6), depth FROM level_event"
    return store.conn.execute(q + (" WHERE event=?" if ev else ""), ((ev,) if ev else ())).fetchall()


def new_engine(store=None, anchor=100.0):
    from data.derived_store import DerivedStore
    import derived.levels as L
    store = store or DerivedStore(tempfile.mktemp(dir=WORK, prefix="d-", suffix=".db"))
    return L.LevelEngine(store, "QQQ", forks=fake_forks(anchor)), store


def _r1():
    eng, st = new_engine()
    step(eng, 101.5, 102.00, 101.4, 101.6)                  # the wick REACHES 102 exactly, closes inside
    rj = [r for r in rows(st, "REJECTED") if r[0] == "QQQ:fork1h/upper:0.00"]
    return (len(rj) == 1 and rj[0][2] == 0.0), f"upper-rail REJECTED rows {rj}"


def _r2():
    eng, st = new_engine()
    step(eng, 101.5, 102.10, 101.4, 101.8)                  # past the rail by 0.10, closes back inside
    rj = [r for r in rows(st, "REJECTED") if r[0] == "QQQ:fork1h/upper:0.00"]
    want = round(0.10 / 102.0, 6)
    return (len(rj) == 1 and abs(rj[0][2] - want) < 1e-6), f"{rj} (want pierce {want})"


def _r3():
    eng, st = new_engine()
    step(eng, 101.9, 102.10, 101.9, 102.05)                 # closes 0.05% beyond — inside the old 0.15% tol
    step(eng, 102.06, 102.10, 102.00, 102.08)               # and opens beyond -> BREACHED
    inv = rows(st, "INVALIDATED")
    b = eng.board(101.0)
    return (len(inv) == 1 and eng.tines_now(101.0) == [] and b.get("fork") == "absent"), \
        f"INVALIDATED {len(inv)}; tines_now {len(eng.tines_now(101.0))}; board fork {b.get('fork')}"


def _r4():
    eng, st = new_engine()
    step(eng, 101.9, 102.10, 101.9, 102.05)
    step(eng, 102.06, 102.10, 102.00, 102.08)
    eng2, _ = new_engine(store=st)                          # a restart: same store, same fork
    step(eng2, 101.0, 101.1, 100.9, 101.0)                  # first sync restores the dead set
    return (eng2.tines_now(101.0) == []), f"rails after restart: {len(eng2.tines_now(101.0))}"


def _r5():
    eng, st = new_engine()
    step(eng, 101.9, 102.10, 101.9, 102.05)
    step(eng, 102.06, 102.10, 102.00, 102.08)
    eng._forks = fake_forks(anchor=100.5)                  # the builder produces a NEW identity
    return (len(eng.tines_now(101.0)) >= 1), f"rails on the new fork: {len(eng.tines_now(101.0))}"


def _r6():
    eng, st = new_engine()
    step(eng, 101.5, 102.10, 101.4, 101.8)
    step(eng, 98.5, 98.6, 97.9, 98.3)                      # a lower-rail touch too
    w = [r for r in rows(st, "WICKED") if "fork1h" in r[0]]
    return (not w and len(rows(st, "REJECTED")) == 2), f"WICKED rail rows {w}; REJECTED {len(rows(st, 'REJECTED'))}"


guard("R1 a wick that REACHES a rail and closes inside is a touch -> REJECTED", _r1)
guard("R2 a wick past the rail that closes back inside is a touch, pierce recorded", _r2)
guard("R3 close 0.05% beyond + next open beyond -> the fork is INVALIDATED (no old 0.15% tolerance)", _r3)
guard("R4 §22: a restarted engine does not resurrect the invalidated fork", _r4)
guard("R5 a fork with a NEW identity serves rails again", _r5)
guard("R6 no WICKED rows for rails — the old tine branch does not run", _r6)


def _r7():
    """The SAME fork one bar later: the ForkEngine's frame rolled, so every
    anchor's idx dropped by one while its price did not. Still invalidated."""
    eng, st = new_engine()
    step(eng, 101.9, 102.10, 101.9, 102.05)
    step(eng, 102.06, 102.10, 102.00, 102.08)
    f = eng._forks.last_forks["1h"]
    for a in ("p0", "p1", "p2"):
        piv = getattr(f, a)
        setattr(f, a, types.SimpleNamespace(idx=piv.idx - 1, price=piv.price, kind=getattr(piv, "kind", "")))
    return (eng.tines_now(101.0) == []), f"rails after the frame rolled one bar: {len(eng.tines_now(101.0))}"


guard("R7 the same fork a bar later (idx shifted, prices unchanged) stays invalidated", _r7)

import shutil
shutil.rmtree(WORK, ignore_errors=True)
print()
if FAILED:
    print(f"RED — {len(FAILED)} of {len(RAN)} failed: {', '.join(FAILED)}")
    sys.exit(1)
print(f"GREEN — {len(RAN)} checks")
sys.exit(0)
