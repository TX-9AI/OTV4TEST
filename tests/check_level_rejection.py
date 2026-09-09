#!/usr/bin/env python3
"""
tests/check_level_rejection.py  v1.0
v1.0  2026-09-08  OTV4TEST r3 — THE REJECTION FACT, ON HYPOTHETICALS.

Drives the REAL `LevelEngine.derive()` against an in-memory DerivedStore with
hand-built closed 1m bars around one resistance level (prev_day_high 710.00)
and one support (prev_day_low 700.00). Wicks are tests, closes are acceptance;
one close back inside on a shallow pierce, two on a deep one (operator,
2026-09-08). Pierce bands come from the sweep's own ceiling.

  L1  wick 0.10% above, close inside            -> WICKED shallow AND REJECTED, same bar
  L2  wick 0.50% above, close inside            -> WICKED deep, NOT rejected yet
  L2b next bar closes inside                    -> REJECTED (closes_back=2)
  L3  deep wick, then a CLOSE beyond            -> pierce cleared, no REJECTED
  L4  wick 1.2% above (beyond the relaxed band) -> WICKED beyond, never REJECTED
  L5  the same closed bar seen twice            -> emitted once
  L6  support mirror: shallow wick BELOW 700    -> REJECTED on the bar
  L7  `latest_rejection()` returns L6's row, filtered by kind
  L8  two closes beyond on the 5m close         -> level retired, ACCEPTED event
  L9  a rejection on a RETIRED level            -> nothing (finished levels don't compete)

Born red at OTV4TEST r2: `level_event` table absent, `_derive_events` absent.
Run:  python3 tests/check_level_rejection.py
"""
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

FAILED = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILED.append(name)


class _Liq:
    prev_day_high = 710.00
    prev_day_low = 700.00
    pools = []


def _df1(rows, start="09:40"):
    import pandas as pd
    return pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c} for o, h, l, c in rows],
        index=pd.date_range(f"2026-09-08 {start}", periods=len(rows), freq="1min"))


def _df5(close):
    import pandas as pd
    return pd.DataFrame([{"open": close, "high": close, "low": close, "close": close}],
                        index=pd.date_range("2026-09-08 09:35", periods=1, freq="5min"))


def main():
    from data.derived_store import DerivedStore
    from derived.levels import LevelEngine, SHALLOW_PIERCE_PCT, DEEP_PIERCE_PCT

    import tempfile
    store = DerivedStore(path=os.path.join(tempfile.mkdtemp(), "derived.db"))
    eng = LevelEngine(store, "TEST")

    def tick(rows, start, price=705.0, close5=705.0):
        ctx = {"symbol": "TEST", "price": price, "liq_map": _Liq(), "vol": None,
               "df_1m": _df1(rows, start), "df_5m": _df5(close5)}
        eng.derive(ctx)
        return [e["event"] + ":" + e["depth"] for e in eng.last_events
                if e["kind"] == "resistance"], eng.last_events

    check("L0 bands read from the sweep's ceiling (0.25% / 0.75%)",
          abs(SHALLOW_PIERCE_PCT - 0.0025) < 1e-9 and abs(DEEP_PIERCE_PCT - 0.0075) < 1e-9)

    # L1 shallow: wick to 710.71 (0.10%), close 709.60 inside
    ev, _ = tick([(709.20, 710.71, 709.00, 709.60), (709.60, 709.80, 709.40, 709.70)], "09:40")
    check("L1 shallow pierce -> WICKED and REJECTED on the same closed bar",
          ev == ["WICKED:shallow", "REJECTED:shallow"], str(ev))

    # L2 deep: wick to 713.55 (0.50%), close inside
    ev, _ = tick([(709.50, 713.55, 709.30, 709.80), (709.80, 710.00, 709.50, 709.70)], "09:42")
    check("L2 deep pierce -> WICKED deep only", ev == ["WICKED:deep"], str(ev))
    ev, raw = tick([(709.80, 710.00, 709.50, 709.70), (709.70, 709.90, 709.40, 709.60)], "09:43")
    rej = [e for e in raw if e["event"] == "REJECTED"]
    check("L2b next close inside -> REJECTED with closes_back=2",
          ev == ["REJECTED:deep"] and rej and rej[0]["closes_back"] == 2, str(ev))

    # L3 deep wick then a close BEYOND clears it
    ev, _ = tick([(709.50, 713.55, 709.30, 709.80), (709.80, 710.00, 709.50, 709.70)], "09:44")
    check("L3pre deep WICKED", ev == ["WICKED:deep"], str(ev))
    ev, _ = tick([(709.80, 712.00, 709.70, 711.80), (711.80, 712.10, 711.60, 711.90)], "09:45")
    check("L3 a close beyond clears the pierce — no REJECTED", ev == [], str(ev))

    # L4 beyond the relaxed band
    ev, _ = tick([(709.00, 718.60, 708.90, 709.50), (709.50, 709.70, 709.30, 709.60)], "09:47")
    check("L4 wick 1.2% above -> WICKED beyond, never rejected",
          ev == ["WICKED:beyond"], str(ev))
    ev, _ = tick([(709.50, 709.70, 709.30, 709.60), (709.60, 709.80, 709.40, 709.70)], "09:48")
    check("L4b ...and the next close inside does not reject it", ev == [], str(ev))

    # L5 the same closed bar twice
    n_before = store.conn.execute("SELECT COUNT(*) FROM level_event").fetchone()[0]
    ev, _ = tick([(709.20, 710.71, 709.00, 709.60), (709.60, 709.80, 709.40, 709.70)], "09:50")
    ev2, _ = tick([(709.20, 710.71, 709.00, 709.60), (709.60, 709.80, 709.40, 709.70)], "09:50")
    n_after = store.conn.execute("SELECT COUNT(*) FROM level_event").fetchone()[0]
    check("L5 the same closed bar seen twice is emitted once",
          ev == ["WICKED:shallow", "REJECTED:shallow"] and ev2 == [] and n_after == n_before + 2,
          f"{ev} then {ev2}; rows {n_before}->{n_after}")

    # L6 support mirror
    _, raw = tick([(700.60, 700.80, 699.40, 700.50), (700.50, 700.70, 700.30, 700.60)], "09:52")
    sup = [e["event"] for e in raw if e["kind"] == "support"]
    check("L6 shallow wick BELOW support -> REJECTED on the bar",
          sup == ["WICKED", "REJECTED"], str(sup))

    # L7 the reader
    r = store.latest_rejection("TEST", 0.0, kind="support")
    check("L7 latest_rejection() returns the support rejection, price 700, depth shallow",
          r is not None and r["price"] == 700.0 and r["depth"] == "shallow"
          and r["kind"] == "support", str(r))
    r2 = store.latest_rejection("TEST", 0.0, kind="resistance")
    check("L7b ...and the resistance one separately", r2 is not None and r2["price"] == 710.0)
    check("L7c a since_ts in the future returns None",
          store.latest_rejection("TEST", 9e12) is None)

    # L8 two 5m closes beyond -> retired + ACCEPTED event
    tick([(711.0, 711.5, 710.8, 711.2), (711.2, 711.6, 711.0, 711.3)], "09:55", close5=711.2)
    _, raw = tick([(711.3, 711.8, 711.1, 711.5), (711.5, 711.9, 711.2, 711.6)], "09:57", close5=711.5)
    acc = [e for e in raw if e["event"] == "ACCEPTED" and e["kind"] == "resistance"]
    retired = store.conn.execute("SELECT retired_reason FROM level_ledger WHERE price=710.0").fetchone()
    check("L8 two closes beyond -> level retired ACCEPTED_THROUGH, ACCEPTED event written",
          bool(acc) and retired and retired[0] == "ACCEPTED_THROUGH", f"acc={bool(acc)} {retired}")

    # L9 rejection on a retired level is nothing
    ev, _ = tick([(709.20, 710.71, 709.00, 709.60), (709.60, 709.80, 709.40, 709.70)], "09:59")
    check("L9 a wick at a RETIRED level emits nothing", ev == [], str(ev))

    print()
    if FAILED:
        print(f"FAIL — {len(FAILED)} check(s): {FAILED}")
        return 1
    print("PASS — check_level_rejection")
    return 0


if __name__ == "__main__":
    sys.exit(main())
