#!/usr/bin/env python3
"""
tests/check_sweep_excursion.py  v1.2
v1.2  2026-09-23  OTV4TEST r110 — pinned to LEVEL_SOURCE="legacy": the book is now the default path. And the r106 venv bootstrap, so it runs under the lander's system python3.
THE PIERCE IS HOW FAR PRICE WENT, NOT THE WICK OF THE BAR THAT CLOSED BACK.

v1.1  2026-09-18  OTV4TEST r49 — `guard()` takes a CALLABLE detail. Its `detail`
      argument was evaluated BEFORE the predicate ran, so any detail computed
      from state the predicate sets printed STALE — a failing check reporting
      the opposite of its own finding. Rendered after the predicate now.
v1.0  2026-09-18  OTV4TEST r44 — born red at r43, where `_derive_events`
      `continue`d past every bar that traded beyond a level without closing
      back, so the pierce was only ever measured on the reclaim bar.

🔴 THE FIXTURE IS THE TRADE WE MISSED. Operator, 2026-09-18, watching a sweep of
QQQ london 716.38 on his own chart: *"That was fucking textbook and we sat out."*
The real bars:

    10:16   low 715.90  close 715.96      <- 49c through; did NOT close back
    10:17   low 715.89  close 716.35      <- still 3c under the level
    10:18   low 716.31  close 716.57      <- the reclaim

    level 716.383 · TRUE pierce 0.493 pts = 0.0688%
                    RECORDED  0.073 pts = 0.0102%   (the 10:18 wick alone)
                    sweep floor 0.02%  ->  refused as "a touch, not a sweep"

⚠️ THE BIAS RAN AGAINST THE BEST SETUPS, WHICH IS WHY THIS IS NOT COSMETIC. A
one-bar wick-and-reclaim measured correctly. A REAL grab — price under the level
for two or three bars while stops are taken — always reported the SHALLOWEST bar
of the sequence. The more convincing the sweep, the shallower the number.
MEASURED over 182 banked REJECTED events: 58 had a true excursion >1.5x the
recorded pierce, and 23 were refused as too shallow when the excursion cleared
the floor.

⚠️ E1 IS DRIVEN, NOT GREPPED. It feeds the three real bars through the real
engine and reads the emitted event, because the defect was a `continue` — and no
string match can see a branch that was never taken.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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

# v1.2 (2026-09-23, OTV4TEST r110) — THIS CHECKER PINS THE LEGACY LEVEL ENGINE.
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
os.environ.setdefault("OT_TRADES_DB", os.path.join(tempfile.mkdtemp(), "t.db"))
os.environ.setdefault("OT_DERIVED_DB", os.path.join(tempfile.mkdtemp(), "d.db"))
FAILED, RAN = [], []


def check(name, ok, detail=""):
    RAN.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILED.append(name.split()[0])


def guard(name, fn, detail=""):
    """Run a predicate; a MISSING symbol is a RED LINE, never a traceback.

    ⚠️ `detail` MAY BE A CALLABLE, AND OFTEN MUST BE. A plain string argument is
    evaluated BEFORE `fn()` runs, so any detail computed from state the predicate
    sets is stale — r49's N8 printed "no fire-then-return" on a FAILING check,
    which is the diagnostic saying the opposite of the truth. Pass a lambda to
    have it rendered AFTER the predicate.
    """
    try:
        ok = fn()
    except Exception as exc:                                    # noqa: BLE001
        check(name, False, f"{type(exc).__name__}: {exc}")
        return False
    try:
        det = detail() if callable(detail) else detail
    except Exception:                                           # noqa: BLE001
        det = ""
    check(name, ok, det)
    return ok


LVL = 716.38          # the level the operator watched get swept (prev_day_low)
# (open, high, low, close) — QQQ 1m, 2026-09-18, his own tape
SWEEP = [(716.43, 716.46, 715.90, 715.96),      # 10:16  49c through, NO close back
         (715.96, 716.39, 715.89, 716.35),      # 10:17  still 3c under the level
         (716.34, 716.59, 716.31, 716.57)]      # 10:18  the reclaim
TOUCH = [(716.43, 716.46, 716.31, 716.57)]      # one shallow bar, no excursion behind it


class _Liq:
    """The level source. `prev_day_low` is the support under test."""
    prev_day_high = 999.00
    prev_day_low = LVL
    pools = []


def _df1(rows, n):
    import pandas as pd
    return pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c} for o, h, l, c in rows[:n]],
        index=pd.date_range("2026-09-18 10:16", periods=n, freq="1min"))


def _df5(close):
    import pandas as pd
    return pd.DataFrame([{"open": close, "high": close, "low": close, "close": close}],
                        index=pd.date_range("2026-09-18 10:15", periods=1, freq="5min"))


def run(bars):
    """Drive the REAL `LevelEngine.derive()` bar by bar; return emitted events.

    ⚠️ THE REAL CONSTRUCTOR, NOT `__new__` WITH STUBS. My first cut built the
    engine with `__new__` and stubbed `_sources`/`tines_now`, and it emitted
    NOTHING — the stubs were wrong and the silence looked like the fix failing
    rather than the fixture failing. `check_level_rejection` already had the
    right shape: a real engine, a real store, a liq_map that supplies the level,
    and `derive()` fed one closed bar at a time. Reused rather than reinvented.
    """
    import tempfile as _tf
    from data.derived_store import DerivedStore
    from derived.levels import LevelEngine
    store = DerivedStore(path=os.path.join(_tf.mkdtemp(), "r.db"))
    eng = LevelEngine(store, "TST")
    out = []
    # `_derive_events` judges df.iloc[-2], so feeding n+1 bars judges bar n-1.
    for n in range(2, len(bars) + 2):
        rows = bars[:n] if n <= len(bars) else bars + [bars[-1]]
        eng.derive({"symbol": "TST", "price": float(rows[-1][3]), "liq_map": _Liq(),
                    "vol": None, "df_1m": _df1(rows, len(rows)), "df_5m": _df5(rows[-1][3])})
    for r in store.conn.execute(
            "SELECT event, price, pierce_pct, depth, bar_close FROM level_event"
            " WHERE symbol='TST' ORDER BY rowid"):
        out.append({"event": r[0], "price": r[1], "pierce_pct": r[2],
                    "depth": r[3], "bar_close": r[4]})
    return out, None


def main():
    ev, err = run(SWEEP)
    if err:
        check("E0 the engine runs on the fixture", False, f"{type(err).__name__}: {err}")
        print(f"\nRED — {len(FAILED)} of {len(RAN)} failed")
        return 1
    rej = [e for e in ev if e.get("event") == "REJECTED"]
    wick = [e for e in ev if e.get("event") == "WICKED"]
    deepest = max([float(e.get("pierce_pct") or 0) for e in ev], default=0.0)

    guard("E1 the sweep is recorded at ALL", lambda: bool(ev), f"{len(ev)} event(s)")
    guard("E2 the pierce is the EXCURSION (0.0688%), not the reclaim wick (0.0102%)",
          lambda: deepest > 0.0005,
          f"deepest recorded {deepest*100:.4f}%  (reclaim-only would be 0.0102%)")
    guard("E3 and it CLEARS the sweep's 0.02% floor — the trade we sat out",
          lambda: deepest >= 0.0002,
          f"{deepest*100:.4f}% vs 0.0200% minimum")
    guard("E4 a WICKED/REJECTED pair is still emitted on the reclaim bar",
          lambda: bool(wick) and bool(rej))

    # ⚠️ AND IT MUST NOT INVENT DEPTH. A single shallow bar that closes back has
    # no excursion behind it, so it must still measure as the touch it is.
    ev2, err2 = run(TOUCH)
    d2 = max([float(e.get("pierce_pct") or 0) for e in ev2], default=0.0)
    guard("E5 a genuine one-bar TOUCH is still shallow — no depth invented",
          lambda: err2 is None and d2 < 0.0002,
          f"{d2*100:.4f}% (must stay under the 0.0200% floor)")

    # the cap exists and is overridable
    from derived import levels as L
    guard("E6 a cap bounds the excursion — a breakdown is not a sweep",
          lambda: isinstance(L.EXCURSION_MAX_BARS, int) and L.EXCURSION_MAX_BARS >= 1,
          f"EXCURSION_MAX_BARS={getattr(L, 'EXCURSION_MAX_BARS', None)}")

    print()
    if FAILED:
        print(f"RED — {len(FAILED)} of {len(RAN)} failed: {', '.join(FAILED)}")
        return 1
    print(f"GREEN — {len(RAN)} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
