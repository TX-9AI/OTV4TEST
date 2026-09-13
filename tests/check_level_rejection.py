#!/usr/bin/env python3
"""
tests/check_level_rejection.py  v1.5
v1.5  2026-09-13  OTV4TEST r19 — F1/F1b/F2/F2b/F3/F3b/F4/F4b: the fork projection
      is separated from the level book. A moving rail never reaches the ledger
      (F1) while the static pool beside it still does (F1b, the control); the
      rails are served as a projection carrying their fork (F2) and vanish with
      it (F2b); the rail can be read WHERE IT STOOD (F3) with the live read
      unchanged (F3b, the control); and a NEW fork with the SAME tine names
      drops the old projection's state (F4b) while the same fork redrawn keeps
      it (F4, the control). F1, F3 and F4b born red at r18.
v1.4  2026-09-13  OTV4TEST r18 — R1/R1b/R2/R2b/R2c/R3/R3b: the operator's three
      rulings. A touch is ONE PER CLOSED BAR (a single bar polled 20x scored 20);
      ACCEPT_CLOSES counts CLOSED 1m BARS, not ticks (the second poll of one bar
      satisfied it — 15 seconds, one close); and a close back INSIDE breaks the
      run (only a touch reset it, so two excursions 90 minutes apart accepted).
      All seven born red at r17 AND at r18.
v1.3  2026-09-13  OTV4TEST r18 — L13/L13b/L13c: the ACCEPTED fact names the BAR
      that made it, and a second acceptance of the same level on a later bar is
      KEPT. The emit site passed the literal "5m" as `bar_ts`; the PK is
      (symbol, level_id, bar_ts, event) under INSERT OR IGNORE, so the second
      acceptance was dropped silently. Born red at r17 on all three.
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


def _df5(close, bar5="09:35"):
    import pandas as pd
    return pd.DataFrame([{"open": close, "high": close, "low": close, "close": close}],
                        index=pd.date_range(f"2026-09-08 {bar5}", periods=1, freq="5min"))


def main():
    from data.derived_store import DerivedStore
    from derived.levels import LevelEngine, SHALLOW_PIERCE_PCT, DEEP_PIERCE_PCT

    import tempfile
    store = DerivedStore(path=os.path.join(tempfile.mkdtemp(), "derived.db"))
    eng = LevelEngine(store, "TEST")

    def tick(rows, start, price=705.0, close5=705.0, bar5="09:35"):
        ctx = {"symbol": "TEST", "price": price, "liq_map": _Liq(), "vol": None,
               "df_1m": _df1(rows, start), "df_5m": _df5(close5, bar5)}
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

    # ── r18: L13 — THE ACCEPTED FACT NAMES THE BAR THAT MADE IT ──
    # The emit site passed the literal "5m" where `bar_ts` belongs, so every
    # ACCEPTED row in the box's ledger was stamped with a TIMEFRAME instead of
    # a BAR. Two consequences, both silent, both driven here.
    accs = store.conn.execute(
        "SELECT bar_ts FROM level_event WHERE event='ACCEPTED'").fetchall()
    check("L13 the ACCEPTED row carries a BAR, never the literal '5m'",
          bool(accs) and all(a[0] != "5m" for a in accs), str([a[0] for a in accs]))
    check("L13b ...and it is the CLOSED 1m bar the acceptance was judged on (r18: was 5m)",
          bool(accs) and all(a[0].startswith("2026-09-08 09:5") for a in accs),
          str([a[0] for a in accs]))

    # L13c THE CONSEQUENCE: level_event's PK is (symbol, level_id, bar_ts, event)
    # under INSERT OR IGNORE, so with `bar_ts` constant a SECOND acceptance of the
    # same level was dropped with no error. Two engines over one store is the real
    # case — a bake re-creates the level and it is accepted again on a later bar.
    # ⚠️ r18 — THIS FIXTURE WAS WRONG THE MOMENT THE BAR GUARD LANDED. It fed
    # both engines the SAME 1m bar timestamps, so the second acceptance collided
    # on the key the test exists to prove is no longer constant. Distinct bars now.
    import tempfile as _tf0

    class _Liq2:
        prev_day_high = 500.00
        prev_day_low = 490.00
        pools = []

    def _accept_at(eng_, m0):
        """Two CONSECUTIVE closed 1m bars beyond 500 -> one acceptance."""
        import pandas as pd
        for m in (m0, m0 + 1):
            idx = pd.date_range(f"2026-09-08 10:{m:02d}", periods=2, freq="1min")
            d1 = pd.DataFrame([{"open": 502.0, "high": 502.0, "low": 502.0, "close": 502.0}] * 2,
                              index=idx)
            eng_.derive({"symbol": "TST5", "price": 502.0, "liq_map": _Liq2(),
                         "vol": None, "df_1m": d1, "df_5m": _df5(502.0)})

    _accept_at(LevelEngine(store, "TST5"), 10)     # bars 10:10 / 10:11
    _accept_at(LevelEngine(store, "TST5"), 40)     # bars 10:40 / 10:41 — a bake later
    n = store.conn.execute(
        "SELECT COUNT(*) FROM level_event WHERE symbol='TST5' AND event='ACCEPTED'").fetchone()[0]
    check("L13c a SECOND acceptance of the same level on a later bar is KEPT, not IGNORED",
          n == 2, f"{n} ACCEPTED row(s) for TST5 — one means the primary key collapsed them")

    # ══ r18: THE OPERATOR'S THREE RULINGS, 2026-09-13 ═══════════════════
    # Each drives the REAL engine. All three FAIL at r18 (and at r17): the
    # touch/acceptance block ran per TICK against a 5m close with no bar guard.
    import tempfile as _tf

    class _L2:
        prev_day_high = 810.00
        prev_day_low = 800.00
        pools = []

    def _eng2():
        return LevelEngine(DerivedStore(path=os.path.join(_tf.mkdtemp(), "r.db")), "TST6")

    def _poll(eng_, bar1, close1, price=None):
        """One tick. `bar1` names the CLOSED 1m bar; `close1` is its close."""
        import pandas as pd
        idx = pd.date_range(f"2026-09-08 {bar1}", periods=2, freq="1min")
        d1 = pd.DataFrame([{"open": close1, "high": close1, "low": close1, "close": close1},
                           {"open": close1, "high": close1, "low": close1, "close": close1}],
                          index=idx)
        eng_.derive({"symbol": "TST6", "price": price if price is not None else close1,
                     "liq_map": _L2(), "vol": None, "df_1m": d1, "df_5m": _df5(close1)})

    # ── R1: A TOUCH IS ONE PER CLOSED BAR, NEVER ONE PER POLL ──
    e = _eng2()
    for _ in range(20):
        _poll(e, "09:40", 810.00)                     # ONE bar, polled 20 times
    tc = e._store.conn.execute(
        "SELECT touch_count FROM level_ledger WHERE price=810.0").fetchone()[0]
    check("R1 a touch is ONE PER CLOSED BAR — one bar polled 20x scores 1, not 20",
          tc == 1, f"touch_count={tc} after 20 polls of a single bar")

    # ...and genuinely distinct bars DO accrue
    e2 = _eng2()
    for m in range(40, 45):
        _poll(e2, f"09:{m}", 810.00)
    tc2 = e2._store.conn.execute(
        "SELECT touch_count FROM level_ledger WHERE price=810.0").fetchone()[0]
    check("R1b ...and five DISTINCT closed bars holding at the level score 5",
          tc2 == 5, f"touch_count={tc2}")

    # ── R2: ACCEPTANCE COUNTS CLOSED 1m BARS, NOT TICKS ──
    e3 = _eng2()
    for i in range(6):
        _poll(e3, "09:40", 812.00)                    # ONE bar beyond, polled 6x
    n = e3._store.conn.execute(
        "SELECT COUNT(*) FROM level_event WHERE event='ACCEPTED'").fetchone()[0]
    check("R2 ONE closed bar beyond, polled 6x, does NOT accept (it did at r18: 2nd tick)",
          n == 0, f"{n} ACCEPTED after 6 polls of ONE bar beyond")
    _poll(e3, "09:41", 812.00)                        # the SECOND closed bar
    n2 = e3._store.conn.execute(
        "SELECT COUNT(*) FROM level_event WHERE event='ACCEPTED'").fetchone()[0]
    check("R2b ...and the SECOND closed bar beyond accepts — ACCEPT_CLOSES means bars",
          n2 == 1, f"{n2} ACCEPTED after a second distinct bar")
    row = e3._store.conn.execute(
        "SELECT bar_ts FROM level_event WHERE event='ACCEPTED'").fetchone()
    check("R2c ...stamped with that bar, never the literal '5m'",
          row and row[0].startswith("2026-09-08 09:41"), str(row))

    # ── R3: A CLOSE BACK INSIDE BREAKS THE RUN ──
    e4 = _eng2()
    _poll(e4, "09:40", 812.00)                        # beyond  (run = 1)
    _poll(e4, "09:41", 804.00)                        # plainly INSIDE, not a touch
    _poll(e4, "09:42", 812.00)                        # beyond  (run must be 1 again)
    n3 = e4._store.conn.execute(
        "SELECT COUNT(*) FROM level_event WHERE event='ACCEPTED'").fetchone()[0]
    check("R3 a close back INSIDE breaks the acceptance run — two excursions is not acceptance",
          n3 == 0, f"{n3} ACCEPTED across two excursions split by an inside close")
    _poll(e4, "09:43", 812.00)                        # now two CONSECUTIVE
    n4 = e4._store.conn.execute(
        "SELECT COUNT(*) FROM level_event WHERE event='ACCEPTED'").fetchone()[0]
    check("R3b ...and two CONSECUTIVE closes beyond still accept",
          n4 == 1, f"{n4} ACCEPTED")

    # ══ r19: THE FORK PROJECTION IS A CO-INFORMER, NOT A LEVEL ═════════════
    # Operator, 2026-09-13: session extremes separated from the 1h fork object;
    # the projection persists only as long as the fork; a new fork gets a new
    # projection; and no drift — the interaction is recorded at the moment it
    # happened, not in hindsight.
    import tempfile as _tf2

    class _Pivot:
        def __init__(self, i, px): self.idx, self.price = i, px

    class _Fork:
        """A 1h fork. Its ANCHORS are its identity."""
        def __init__(self, base=900.0, slope=0.06, anchors=(0, 1, 2)):
            self.slope = slope
            self.p0, self.p1, self.p2 = (_Pivot(a, base + a) for a in anchors)
            self._b = base
        def upper_at(self, i):  return self._b + 6.0 + self.slope * i
        def median_at(self, i): return self._b + self.slope * i
        def lower_at(self, i):  return self._b - 6.0 + self.slope * i

    class _FE:
        def __init__(self, fork): self.last_forks = {"1h": fork} if fork else {}; self.last_idx = {"1h": 100.0} if fork else {}

    class _MovingPool:
        """What publish_tines puts on the map: a named pool flagged moving."""
        price, kind, name, timeframe, moving, is_named = 726.17, "high", "1h upper tine", "1h", True, True

    class _StaticPool:
        price, kind, name, timeframe, moving, is_named = 717.52, "high", "PDH (R1)", "1d", False, True

    class _LiqP:
        prev_day_high = 910.00
        prev_day_low  = 900.00
        pools = [_MovingPool(), _StaticPool()]

    # ── F1: a MOVING rail never reaches the horizontal book ──
    st7 = DerivedStore(path=os.path.join(_tf2.mkdtemp(), "f.db"))
    e7 = LevelEngine(st7, "TST7", forks=_FE(_Fork()))
    import pandas as _pd
    _d1 = _pd.DataFrame([{"open": 905.0, "high": 905.0, "low": 905.0, "close": 905.0}] * 2,
                        index=_pd.date_range("2026-09-08 09:40", periods=2, freq="1min"))
    e7.derive({"symbol": "TST7", "price": 905.0, "liq_map": _LiqP(), "vol": None,
               "df_1m": _d1, "df_5m": _df5(905.0)})
    provs = [r[0] for r in st7.conn.execute(
        "SELECT provenance FROM level_ledger WHERE symbol='TST7'").fetchall()]
    check("F1 a MOVING rail never enters level_ledger — the projection is not a level",
          "1h upper tine" not in provs, f"ledger holds {sorted(set(provs))}")
    check("F1b ...and the STATIC named pool beside it still does — the control",
          "PDH (R1)" in provs, f"ledger holds {sorted(set(provs))}")

    # ── F2: the projection is served beside the ledger, scoped to its fork ──
    fk = _Fork()
    e8 = LevelEngine(DerivedStore(path=os.path.join(_tf2.mkdtemp(), "g.db")), "TST8", forks=_FE(fk))
    t_live = e8.tines_now(905.0)
    check("F2 the rails are SERVED as a projection, carrying the fork they came from",
          len(t_live) == 3 and all(t.get("fork_key") is not None for t in t_live),
          f"{len(t_live)} rails, fork_key={t_live[0].get('fork_key') if t_live else None}")
    check("F2b a DEAD fork yields no projection at all — it goes with the fork",
          LevelEngine(None, "X", forks=_FE(None)).tines_now(905.0) == [])

    # ── F3: NO DRIFT — the rail where it STOOD when the extreme printed ──
    now_rail  = e8.tines_now(905.0)[0]["price"]
    back_rail = e8.tines_now(905.0, minutes_back=30.0)[0]["price"]
    drift = now_rail - back_rail
    check("F3 the rail can be read WHERE IT STOOD — 30 min back is not 'now'",
          abs(drift - fk.slope * 0.5) < 1e-9 and drift > 0,
          f"now {now_rail:.4f} vs 30m back {back_rail:.4f} — drift {drift:.4f}")
    check("F3b ...and minutes_back=0 is byte-identical to the live read (r15 unchanged)",
          e8.tines_now(905.0, minutes_back=0.0)[0]["price"] == now_rail)

    # ── F4: A NEW FORK IS A NEW PROJECTION — the old state does not survive ──
    # The interaction is REAL, not seeded: a bar wicks the upper rail and closes
    # back inside, which is what creates tine pierce state in the first place.
    def _wick(t0, hi):
        return _pd.DataFrame(
            [{"open": 905.0, "high": hi,   "low": 905.0, "close": 905.0},
             {"open": 905.0, "high": 905.0, "low": 905.0, "close": 905.0}],
            index=_pd.date_range(f"2026-09-08 {t0}", periods=2, freq="1min"))

    fe = _FE(_Fork(base=900.0, anchors=(0, 1, 2)))
    e9 = LevelEngine(DerivedStore(path=os.path.join(_tf2.mkdtemp(), "h.db")), "TST9", forks=fe)
    key_before = e9._fork_key()
    # a genuine pierce of the upper rail (~912), closing back inside
    e9.derive({"symbol": "TST9", "price": 905.0, "liq_map": _LiqP(), "vol": None,
               "df_1m": _wick("09:40", 912.9), "df_5m": _df5(905.0)})
    made = [k for k in e9._pierce if ":fork1h/" in k]
    check("F4 a real tine interaction creates projection state, and the SAME fork keeps it",
          bool(made), f"pierce keys {list(e9._pierce)}")

    # a NEW fork — DIFFERENT ANCHORS, the SAME three tine names
    fe.last_forks["1h"] = _Fork(base=920.0, anchors=(9, 10, 11))
    e9.derive({"symbol": "TST9", "price": 905.0, "liq_map": _LiqP(), "vol": None,
               "df_1m": _wick("09:42", 905.0), "df_5m": _df5(905.0)})
    check("F4b a NEW fork (new anchors, SAME tine names) drops the old projection's state",
          not [k for k in e9._pierce if ":fork1h/" in k] and e9._fork_key() != key_before,
          f"pierce keys {list(e9._pierce)}")

    print()
    if FAILED:
        print(f"FAIL — {len(FAILED)} check(s): {FAILED}")
        return 1
    print("PASS — check_level_rejection")
    return 0


if __name__ == "__main__":
    sys.exit(main())
