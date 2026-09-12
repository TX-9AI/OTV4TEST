#!/usr/bin/env python3
"""
tests/check_level_rejection.py  v1.2
v1.2  2026-09-12  OTV4TEST r15 — L10 pools by side, L11 tines never stored / dead fork empty,
      L12 the board contract. Born red at r14 on L10, L11 and L12.
v1.1  2026-09-08  OTV4TEST r5 — T1–T3: the 1h tines as moving levels keyed on the
      tine, the tine rule (a bottom tine is never a ceiling), and TRAVERSED
      retirement of any level inside the opening range.
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

    # ── r5: tines as moving levels, the tine rule, the opening-range rule ──
    class _Fork:
        direction = "bullish"
        def upper_at(self, i): return 712.0 + 0.1 * i
        def median_at(self, i): return 706.0 + 0.1 * i
        def lower_at(self, i): return 702.0 + 0.1 * i
    class _FE:
        last_forks = {"1h": _Fork()}
        last_idx = {"1h": 10}
    eng2 = LevelEngine(store, "TEST", forks=_FE())
    def tick2(rows, start, price=705.0, orb=None):
        ctx = {"symbol": "TEST", "price": price, "liq_map": _Liq(), "vol": None,
               "df_1m": _df1(rows, start), "df_5m": _df5(price), "orb": orb}
        eng2.derive(ctx)
        return [(e["provenance"], e["event"], e["kind"]) for e in eng2.last_events
                if e["provenance"].startswith("fork1h/")]
    # upper tine at 713.0 (712 + 0.1*10): a shallow wick through it, close inside
    ev = tick2([(712.5, 713.4, 712.3, 712.8), (712.8, 713.0, 712.6, 712.9)], "10:10")
    check("T1 the 1h upper tine is a RESISTANCE level: shallow wick -> WICKED + REJECTED on the tine",
          ("fork1h/upper", "WICKED", "resistance") in ev and ("fork1h/upper", "REJECTED", "resistance") in ev,
          str(ev))
    ids = [r[0] for r in store.conn.execute("SELECT level_id FROM level_event WHERE provenance='fork1h/upper'")]
    check("T1b ...keyed on the tine, not the price", ids and all(i.endswith(":0.00") for i in ids), str(ids[:2]))
    # lower tine at 703.0: a wick UP through it is not an event (the tine rule)
    ev = tick2([(702.4, 703.6, 702.2, 702.7), (702.7, 702.9, 702.5, 702.8)], "10:12", price=702.7)
    check("T2 tine rule: a wick UP through the LOWER tine emits nothing",
          not any(p == "fork1h/lower" for p, _, _ in ev), str(ev))
    ev = tick2([(703.4, 703.6, 702.4, 703.3), (703.3, 703.5, 703.1, 703.4)], "10:14", price=703.3)
    check("T2b ...a wick DOWN through it is a support rejection",
          ("fork1h/lower", "REJECTED", "support") in ev, str(ev))
    # opening range: a level inside 704.5-706.5 is retired TRAVERSED
    class _Orb: orb_low, orb_high = 704.5, 706.5
    class _Liq2(_Liq): prev_day_high = 705.5
    ctx = {"symbol": "TEST", "price": 705.0, "liq_map": _Liq2(), "vol": None,
           "df_1m": _df1([(705.0, 705.2, 704.8, 705.1), (705.1, 705.3, 704.9, 705.2)], "10:16"),
           "df_5m": _df5(705.0), "orb": _Orb()}
    eng3 = LevelEngine(store, "TEST")
    eng3.derive(ctx)
    r = store.conn.execute("SELECT retired_reason FROM level_ledger WHERE price=705.5 AND provenance='prev_day'").fetchone()
    check("T3 a level inside the opening range is retired TRAVERSED", r and r[0] == "TRAVERSED", str(r))
    ev3 = [e for e in eng3.last_events if e["price"] == 705.5]
    check("T3b ...and emits no events", ev3 == [], str(ev3))

    # ── r15: the two defects the OTV4 thread found (mainline r364), on the fork ──
    class _Pool:
        def __init__(s, name, price, kind): s.name, s.price, s.kind, s.timeframe = name, price, kind, "day"
    class _Liq3(_Liq):
        pools = [_Pool("PDH", 108.0, "high"), _Pool("PDL", 92.0, "low"), _Pool("NY High (R1)", 103.0, "high")]
    eng4 = LevelEngine(store, "TST4")
    eng4.derive({"symbol": "TST4", "price": 100.0, "liq_map": _Liq3(), "vol": None,
                 "df_1m": _df1([(100.0, 100.2, 99.8, 100.1), (100.1, 100.3, 99.9, 100.2)], "10:20"),
                 "df_5m": _df5(100.0), "orb": None})
    kinds = {r[0]: r[1] for r in store.conn.execute("SELECT provenance, kind FROM level_ledger WHERE symbol='TST4'")}
    check("L10 pools are classified by SIDE at write: PDH/R1 above price -> resistance, PDL below -> support (was high/low, invisible)",
          kinds.get("PDH") == "resistance" and kinds.get("NY High (R1)") == "resistance" and kinds.get("PDL") == "support", str(kinds))
    check("L10b ...and live_levels() now returns the ladder",
          {l["provenance"] for l in store.live_levels("TST4")} >= {"PDH", "PDL", "NY High (R1)"})
    # L11: a tine is never stored; a dead fork yields nothing on the next read
    class _FE2:
        last_forks = {"1h": _Fork()}; last_idx = {"1h": 10}
    eng5 = LevelEngine(store, "TST5", forks=_FE2())
    eng5.derive({"symbol": "TST5", "price": 705.0, "liq_map": _Liq(), "vol": None,
                 "df_1m": _df1([(705.0, 705.2, 704.8, 705.1), (705.1, 705.3, 704.9, 705.2)], "10:30"),
                 "df_5m": _df5(705.0), "orb": None})
    n_tine_rows = store.conn.execute("SELECT COUNT(*) FROM level_ledger WHERE symbol='TST5' AND provenance LIKE 'fork1h/%'").fetchone()[0]
    check("L11 a tine is NEVER a stored level (no fork1h/* row in the ledger)", n_tine_rows == 0, str(n_tine_rows))
    tn = eng5.tines_now(705.0)
    check("L11b tines_now serves the rails with a rate while the fork is built",
          len(tn) == 3 and {x["provenance"] for x in tn} == {"fork1h/upper", "fork1h/median", "fork1h/lower"}
          and all("bars_to_contact" in x for x in tn), str([(x["provenance"], x["price"]) for x in tn]))
    _FE2.last_forks.pop("1h"); _FE2.last_idx.pop("1h")
    check("L11c ...and a DEAD fork yields nothing on the next read — no stale row, no stale encounter",
          eng5.tines_now(705.0) == [])
    # L12: the board
    eng6 = LevelEngine(store, "TST4")
    bd = eng6.board(100.0, orb_high=101.0, orb_low=99.0)
    check("L12 board: held levels beyond the range ordered outward, count never padded, four distinct empties",
          bd["state"] == "ok" and [x["provenance"] for x in bd["above"]] == ["NY High (R1)", "PDH", "prev_day"]
          and [x["provenance"] for x in bd["below"]] == ["PDL"] and bd["count"] == {"above": 3, "below": 1, "tines": 0}
          and bd["fork"] == "absent", str({k: bd[k] for k in ("state", "count", "fork")}))
    check("L12b board with no range -> no_range, not an empty ladder", eng6.board(100.0, None, None)["state"] == "no_range")
    check("L12c board with no store -> no_store", LevelEngine(None, "X").board(100.0, 101.0, 99.0)["state"] == "no_store")

    print()
    if FAILED:
        print(f"FAIL — {len(FAILED)} check(s): {FAILED}")
        return 1
    print("PASS — check_level_rejection")
    return 0


if __name__ == "__main__":
    sys.exit(main())
