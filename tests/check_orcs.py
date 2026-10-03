#!/usr/bin/env python3
"""
tests/check_orcs.py  v1.1
v1.1  2026-10-03  OTV4TEST r204 (PREM.2) — ORCS IS A TRADE: THE FILLED OFFER BECOMES ONE PAPER SPREAD, HELD TO THE CLOSE;
      THE SWEEP AND THE TCS ARE RETIRED. Renamed from check_orcs_plan.py (r203), whose O1-O6 and O8
      still drive the plan under its new name. NEW:
  T1  the strategy turns the offer that FILLED THIS TICK into one signal priced AT THE LIMIT, on the
      frozen strikes; the next tick signals nothing
  T2  one per side: with an ORCS call leg open in trades.db the call signals nothing (the put still can);
      with config.ORCS_ENABLED off nothing is signalled
  T3  the REAL _execute_condor_leg books it in paper as OpeningRangeCreditSpread at the limit with NO stop,
      and REFUSES it in live mode
  T4  the REAL exit engine HOLDS an ORCS leg marked at ten times its credit (the same leg under the
      condor's name is stopped - the control), and closes it when the end-of-day close is due
  T5  the roll does not see two open ORCS legs as a condor
  T6  RETIRED: _safe_strategy does not call the sweep, the sweep's leg two or the TCS; each switch restores it
  T7  ORCS is in the admission table: 09:45-10:30, two of the type, not cap-exempt
v1.0  2026-10-03  OTV4TEST r203 (PREM.1) — THE OPENING PREMIUM SPREAD PLAN FINDS ITS STRIKES AND PLACES NOTHING.

  The operator, 2026-10-03: "build the plan that searches the chain for our
  trigger components' location on the chain", and "we get better than mark or
  we don't trade it."

  Drives the REAL plan with a REAL OptionsChain of OptionContracts and the
  REAL Plan / write_row on a scratch store. The expected strikes are worked by
  hand from the fixture; the expected credits are read off the fixture's own
  bid and ask.
  O1  LOCATION: each side's short is the nearest OTM strike with delta <= 0.15
      (put 746, call 754 at spot 750.20); the long is ~1% of spot further
  O2  THE IMPLIED-MOVE FLOOR BINDS: with a dear straddle the delta-qualified
      strike inside 1.25 implied moves is skipped for the next one out
  O3  PRICED AT THE MARK: credit = mid - mid; bid/ask credit recorded beside it;
      the offer rests one cent better than the mark and is written to the rows
  O4  DAY GATES: not 0DTE, a gap over the limit, an UNMEASURED gap, a tick
      before 09:45, and a tick too late for a full rest each leave no offer
  O5  THE OFFER IS FROZEN AND WATCHED: spot moves, the offer's strikes do not;
      the mark reaching the limit records filled; ten minutes unfilled expires
  O6  A RESTART CONTINUES THE OFFER: a new plan on the same store restores the
      strikes and limit from its own rows instead of re-freezing
  O8  the preliminary dials are config's, at the values the studies chose

Run:  python3 tests/check_orcs.py   (exit 0 green, 1 red)
"""
import ast
import glob as _glob
import math
import os
import sqlite3
import sys
import tempfile

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)
for _sp in _glob.glob(os.path.join(_root, "venv", "lib", "python*", "site-packages")):
    if _sp not in sys.path:                                  # r106 venv bootstrap
        sys.path.insert(1, _sp)
_S = tempfile.mkdtemp(prefix="check_orcs_")
for _k, _f in (("OT_TRADES_DB", "trades.db"), ("OT_DERIVED_DB", "d.db"), ("OT_RESTING_DB", "r.db")):
    os.environ.setdefault(_k, os.path.join(_S, _f))
os.environ.setdefault("OT_SIGNAL_JOURNAL_DIR", os.path.join(_S, "sj"))
os.environ.setdefault("OT_LOG_FILE", os.path.join(_S, "bot.log"))
os.environ.setdefault("OT_INSTRUMENT", "QQQ")

FAILED = []
DAY = "2026-10-05"


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  — {detail}"))
    if not ok:
        FAILED.append(name.split()[0])


class _Store:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def commit(self):
        self.conn.commit()


def _et(h, m):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime(2026, 10, 5, h, m, 0, tzinfo=ZoneInfo("US/Eastern"))


def _chain(spot, scale, expiry=DAY, bump=None):
    """Strikes 720..780 by $1. mark = scale*exp(-d/2.5), quoted a cent each side; delta = 0.5*exp(-d/3)."""
    from data.options_chain import OptionsChain, OptionContract
    calls, puts = [], []
    for k in range(720, 781):
        d = abs(k - spot)
        for typ, out in (("C", calls), ("P", puts)):
            m = scale * math.exp(-d / 2.5) + ((bump or {}).get((typ, k), 0.0))
            sign = 1 if typ == "C" else -1
            out.append(OptionContract(symbol=f"Q{typ}{k}", underlying="QQQ", expiry=expiry, option_type=typ,
                                      strike=float(k), bid=round(max(0.0, m - 0.01), 4), ask=round(m + 0.01, 4),
                                      mark=round(m, 4), delta=round(sign * 0.5 * math.exp(-d / 3.0), 4)))
    return OptionsChain(underlying="QQQ", expiry=expiry, spot_price=spot, calls=calls, puts=puts)


def _mid(chain, typ, k):
    c = next(x for x in (chain.calls if typ == "C" else chain.puts) if x.strike == float(k))
    return (c.bid + c.ask) / 2.0, c


def _rows(st, since=0.0):
    return {r["check_name"]: (r["value"], r["verdict"]) for r in st.conn.execute(
        "SELECT check_name, value, verdict FROM plan_check WHERE strategy='OpeningRangeCreditSpread' AND ts_epoch>=? "
        "ORDER BY ts_epoch", (since,))}


def _verdict(st):
    r = st.conn.execute("SELECT verdict, reason FROM plan_tick WHERE strategy='OpeningRangeCreditSpread' "
                        "ORDER BY ts_epoch DESC LIMIT 1").fetchone()
    return (r["verdict"], r["reason"]) if r else (None, None)


def main():
    try:
        from strategy import plan as P
        from strategy import orcs_plan as M
    except Exception as exc:                                  # noqa: BLE001
        for n in ("O1", "O2", "O3", "O4", "O5", "O6", "O8", "T1", "T2", "T3", "T4", "T5", "T6", "T7"):
            check(f"{n} (did not run)", False, f"{type(exc).__name__}: {exc}")
        print(f"\nRED — {len(FAILED)} check(s): {FAILED}")
        return 1

    GAP = {"gap_pct": 0.30, "gap_abs_pct": 0.30}
    t0 = _et(9, 45).timestamp()

    def fresh(tag):
        st = _Store(os.path.join(_S, f"{tag}.db"))
        P.bind_store(st)
        P._DORMANT.pop("OpeningRangeCreditSpread", None)
        return st, M.ORCSPlan()

    # ── O1 / O3 — location and pricing at spot 750.20, cheap straddle ───────
    st = None
    try:
        st, plan = fresh("a")
        ch = _chain(750.2, 1.0)
        P.begin_tick(t0)
        prep = plan.prepare(price_now=750.2, now_et=_et(9, 45), chain=ch, gap=GAP, today=DAY, now_epoch=t0)
        p, c = prep.sides["put"], prep.sides["call"]
        got = (p.short and p.short.strike, p.long and p.long.strike, c.short and c.short.strike, c.long and c.long.strike)
        check("O1 put 746/738 and call 754/762: nearest strike with delta <= 0.15, long ~1% further",
              got == (746.0, 738.0, 754.0, 762.0), f"located {got}")
        ms, s_ = _mid(ch, "P", 746); ml, l_ = _mid(ch, "P", 738)
        rows = _rows(st)
        want_credit, want_nat = round(ms - ml, 4), round(s_.bid - l_.ask, 4)
        check("O3 put credit is mid minus mid; bid/ask credit beside it; the offer rests one cent better",
              p.credit == want_credit and p.natural == want_nat
              and rows.get("put_credit") == (want_credit, "PASS")
              and rows.get("put_credit_natural", (None,))[0] == want_nat
              and rows.get("put_offer_limit", (None,))[0] == round(want_credit + 0.01, 2)
              and rows.get("put_offer_short", (None,))[0] == 746.0 and rows.get("put_ready", (0, ""))[1] == "PASS"
              and sorted(prep.ready) == ["call", "put"] and _verdict(st)[0] == "HOLD",
              f"credit {p.credit} want {want_credit}; natural {p.natural} want {want_nat}; "
              f"limit {rows.get('put_offer_limit')}; verdict {_verdict(st)[0]}")

        # ── O5 — frozen and watched ─────────────────────────────────────────
        t1 = t0 + 120
        P.begin_tick(t1)
        ch2 = _chain(752.2, 1.0)                              # spot moved 2 up: location moves, the offer must not
        prep2 = plan.prepare(price_now=752.2, now_et=_et(9, 47), chain=ch2, gap=GAP, today=DAY, now_epoch=t1)
        r2 = _rows(st, t1)
        moved = prep2.sides["put"].short.strike
        frozen = (r2.get("put_offer_short", (None,))[0], r2.get("put_offer_long", (None,))[0],
                  r2.get("put_offer_limit", (None,))[0])
        call_m = r2.get("call_offer_mark", (None,))[0]
        call_lim = r2.get("call_offer_limit", (None,))[0]
        # spot rose toward the call: its frozen spread got dearer and reaches the limit; the put got cheaper
        ok5a = (moved == 748.0 and frozen == (746.0, 738.0, round(want_credit + 0.01, 2))
                and call_m is not None and call_m >= call_lim
                and r2.get("call_offer_filled_mark", (0, ""))[1] == "PASS"
                and r2.get("put_offer_filled_mark", (0, ""))[1] == "FAIL")
        t2 = t0 + 11 * 60
        P.begin_tick(t2)
        plan.prepare(price_now=750.2, now_et=_et(9, 56), chain=_chain(750.2, 1.0), gap=GAP, today=DAY, now_epoch=t2)
        r3 = _rows(st, t2)
        ok5b = (r3.get("put_offer_expired", (0, ""))[1] == "PASS" and r3.get("call_offer_expired", (0, ""))[1] == "FAIL"
                and r3.get("put_offer_short", (None,))[0] == 746.0)
        check("O5 the offer stays 746/738 while spot moves; the call fills at the mark; the put expires unfilled",
              ok5a and ok5b, f"located put now {moved}, frozen {frozen}, call mark {call_m} vs {call_lim}, "
                             f"filled {r2.get('call_offer_filled_mark')}/{r2.get('put_offer_filled_mark')}, "
                             f"expired {r3.get('put_offer_expired')}/{r3.get('call_offer_expired')}")

        # ── O6 — restart inside the window ──────────────────────────────────
        P._DORMANT.pop("OpeningRangeCreditSpread", None)
        plan_b = M.ORCSPlan()
        t3 = t0 + 12 * 60
        P.begin_tick(t3)
        plan_b.prepare(price_now=753.0, now_et=_et(9, 57), chain=_chain(753.0, 1.0), gap=GAP, today=DAY, now_epoch=t3)
        o = plan_b._offers
        check("O6 a new plan on the same store restores 746/738 and 754/762 with the call still filled",
              o.get("put", {}).get("short") == 746.0 and o.get("put", {}).get("limit") == round(want_credit + 0.01, 2)
              and abs(o.get("put", {}).get("ts", 0) - t0) < 1 and o.get("call", {}).get("short") == 754.0
              and o.get("call", {}).get("filled_mark") is True and o.get("put", {}).get("filled_mark") is False,
              str(o))
    except Exception as exc:                                  # noqa: BLE001
        check("O1 (did not run)", False, f"{type(exc).__name__}: {exc}")

    # ── O2 — the implied-move floor binds ───────────────────────────────────
    try:
        st, plan = fresh("b")
        ch = _chain(750.2, 3.0)                               # straddle ~5.54 -> floor ~6.93: 746 (4.2 out) is too near
        P.begin_tick(t0)
        prep = plan.prepare(price_now=750.2, now_et=_et(9, 45), chain=ch, gap=GAP, today=DAY, now_epoch=t0)
        im = prep.im
        p, c = prep.sides["put"], prep.sides["call"]
        check("O2 with a 5.54 straddle the shorts step out to 743 and 758 (>= 1.25 implied moves)",
              im is not None and abs(im - 5.54) < 0.02 and p.short and p.short.strike == 743.0
              and c.short and c.short.strike == 758.0 and p.im_mult >= 1.25,
              f"im {im}, put {p.short and p.short.strike}, call {c.short and c.short.strike}")
    except Exception as exc:                                  # noqa: BLE001
        check("O2 (did not run)", False, f"{type(exc).__name__}: {exc}")

    # ── O4 — day gates ──────────────────────────────────────────────────────
    try:
        out = []
        for tag, kw, when, want_v, want_gate in (
                ("c", {"chain": _chain(750.2, 1.0, expiry="2026-10-06"), "gap": GAP}, (9, 45), "DECLINE", "zero_dte"),
                ("d", {"chain": _chain(750.2, 1.0), "gap": {"gap_abs_pct": 1.25}}, (9, 45), "DECLINE", "gap_abs_pct"),
                ("e", {"chain": _chain(750.2, 1.0), "gap": None}, (9, 45), "DECLINE", "gap_abs_pct"),
                ("f", {"chain": _chain(750.2, 1.0), "gap": GAP}, (9, 44), "DORMANT", "entry_window"),
                ("g", {"chain": _chain(750.2, 1.0), "gap": GAP}, (10, 21), "HOLD", "no new offer this late; watching the resting offer(s). put 746/738 delta 0.12, 0.56% out, credit 0.18 at mark; call 754/762 delta 0.14, 0.51% out, credit 0.21 at mark (implied move 1.85)")):
            st, plan = fresh(tag)
            ts = _et(*when).timestamp()
            P.begin_tick(ts)
            prep = plan.prepare(price_now=750.2, now_et=_et(*when), today=DAY, now_epoch=ts, **kw)
            v, why = _verdict(st)
            out.append((tag, v, (why or "").split(":")[0], bool(plan._offers), bool(prep.ready)))
        ok = all(v == wv and g == wg and not off and not rdy
                 for (_t, v, g, off, rdy), (wv, wg) in zip(out, (("DECLINE", "zero_dte"), ("DECLINE", "gap_abs_pct"),
                                                                ("DECLINE", "gap_abs_pct"), ("DORMANT", "entry_window"),
                                                                ("HOLD", out[-1][2]))))
        ok = ok and out[-1][2].startswith("no new offer this late")
        check("O4 not 0DTE, a 1.25% gap, an unmeasured gap, 09:44 and 10:21 each leave no offer and nothing ready",
              ok, str(out))
    except Exception as exc:                                  # noqa: BLE001
        check("O4 (did not run)", False, f"{type(exc).__name__}: {exc}")
    finally:
        P.bind_store(None)

    # ── O8 — the dials ──────────────────────────────────────────────────────
    try:
        import config as C
        got = (tuple(C.ENTRY_WINDOWS["OpeningRangeCreditSpread"][0]), tuple(C.ENTRY_WINDOWS["OpeningRangeCreditSpread"][1]), C.ORCS_SHORT_DELTA_MAX, C.ORCS_MIN_IM_MULT, C.ORCS_WING_PCT,
               C.ORCS_MIN_CREDIT, C.ORCS_MAX_GAP_PCT, C.ORCS_LIMIT_IMPROVE, C.ORCS_REST_MIN)
        want = ((9, 45), (10, 30), 0.15, 1.25, 0.01, 0.10, 0.90, 0.01, 10.0)
        check("O8 config carries the window and the seven dials, ORCS is ON, and the plan reads the same values",
              got == want and (M.ORCS_START_ET, M.ORCS_SHORT_DELTA_MAX, M.ORCS_REST_MIN) == ((9, 45), 0.15, 10.0)
              and C.ORCS_ENABLED is True, f"{got}")
    except Exception as exc:                                  # noqa: BLE001
        check("O8 (did not run)", False, f"{type(exc).__name__}: {exc}")

    # ══ r204 — the trade ═══════════════════════════════════════════════════
    try:
        import config as C
        from strategy import orcs as S
        import database.trade_logger as TLM
        from database.trade_logger import TradeLogger, make_record
        TLM._trade_logger = TradeLogger(os.path.join(_S, "trades.db"))

        def strat(tag):
            st = _Store(os.path.join(_S, f"{tag}.db"))
            P.bind_store(st)
            P._DORMANT.pop("OpeningRangeCreditSpread", None)
            return st, S.OpeningRangeCreditSpread()

        def run(sg, spot, hm, ts):
            P.begin_tick(ts)
            return sg.generate_signals(price_now=spot, now_et=_et(*hm), chain=_chain(spot, 1.0), gap=GAP,
                                       today=DAY, now_epoch=ts)

        # T1 — the fill tick
        st, sg = strat("t1")
        a = run(sg, 750.2, (9, 45), t0)                       # offers frozen: put 746/738, call 754/762
        b = run(sg, 752.2, (9, 47), t0 + 120)                 # the call's mark reaches its limit
        c = run(sg, 752.2, (9, 48), t0 + 180)
        lim = sg.plan._offers["call"]["limit"]
        ok1 = (a == [] and len(b) == 1 and c == [] and b[0].strategy_name == "OpeningRangeCreditSpread"
               and b[0].option_side == "call" and b[0].net_credit == lim
               and b[0].short_call_contract.strike == 754.0 and b[0].long_call_contract.strike == 762.0
               and _verdict(st)[0] in ("HOLD", "TAKE"))
        tk = st.conn.execute("SELECT COUNT(*) FROM plan_tick WHERE strategy='OpeningRangeCreditSpread' "
                             "AND verdict='TAKE'").fetchone()[0]
        check("T1 the fill tick yields ONE call signal at the limit on 754/762, the plan row is TAKE, then nothing",
              ok1 and tk == 1, f"signals {len(a)},{len(b)},{len(c)}; take rows {tk}; "
                               f"{b and (b[0].option_side, b[0].net_credit, lim)}")
        sig_call = b[0] if b else None

        # T2 — one per side, and the switch
        TLM._trade_logger.log_entry(make_record(
            trade_id="orcs-open-call", symbol="QQQ", strategy="OpeningRangeCreditSpread", setup_type="orcs_call",
            direction="neutral", option_side="call", strike=754.0, short_strike=754.0, long_strike=762.0,
            spread_width=8.0, credit_received=0.2, contracts=1, entry_premium=0.2, total_cost=780.0,
            max_loss=780.0, is_condor_leg=1, paper_trade=1, status="open", expiry=DAY))
        st, sg = strat("t2")
        run(sg, 750.2, (9, 45), t0)
        used = run(sg, 752.2, (9, 47), t0 + 120)              # the call fills again - but the side is used
        st, sg = strat("t2b")
        run(sg, 750.2, (9, 45), t0)
        putf = run(sg, 748.2, (9, 47), t0 + 120)              # spot falls: the PUT fills, and its side is free
        st, sg = strat("t2c")
        C.ORCS_ENABLED = False
        try:
            run(sg, 750.2, (9, 45), t0)
            off = run(sg, 748.2, (9, 47), t0 + 120)
        finally:
            C.ORCS_ENABLED = True
        check("T2 an open ORCS call leg stops the call, not the put; ORCS_ENABLED off signals nothing",
              used == [] and len(putf) == 1 and putf[0].option_side == "put" and off == [],
              f"call-with-open-call {len(used)}, put {[(x.option_side) for x in putf]}, switched off {len(off)}")
    except Exception as exc:                                  # noqa: BLE001
        check("T1 (did not run)", False, f"{type(exc).__name__}: {exc}")
        sig_call = None
    finally:
        P.bind_store(None)

    # T3 — the real executor
    try:
        os.environ["OT_PAPER_TRADING"] = "1"
        import main
        import execution.position_manager as PMM
        TLM._trade_logger = TradeLogger(os.path.join(_S, "exec", "trades.db")) if os.makedirs(
            os.path.join(_S, "exec"), exist_ok=True) is None else None
        PMM._position_manager = None

        class _Sz:
            allowed, contracts, reject_reason = True, 1, ""
            total_cost = max_loss = 0.0

        class _RM:
            def size_for(self, *a, **k): return _Sz()

        class _AM:
            def _send(self, *a, **k): pass
            def send_entry_alert(self, *a, **k): pass
        saved = (main.get_risk_manager, main.get_alert_manager, main.entries_open, main._post_credit_vertical)
        posted = []

        def _post(*a, **k):
            posted.append(1)
            raise RuntimeError("a live ORCS order reached the broker path")
        main.get_risk_manager, main.get_alert_manager, main.entries_open = (lambda: _RM()), (lambda: _AM()), (lambda: True)
        main._post_credit_vertical = _post
        try:
            state = main.BotState(); state.paper_trading = False
            main._execute_condor_leg(sig_call, state, None)
            live_rows = len(TLM._trade_logger.get_open_trades())
            state.paper_trading = True
            main._execute_condor_leg(sig_call, state, None)
        finally:
            main.get_risk_manager, main.get_alert_manager, main.entries_open, main._post_credit_vertical = saved
        rows = TLM._trade_logger.get_open_trades()
        r = rows[0] if rows else {}
        check("T3 live is REFUSED; paper books OpeningRangeCreditSpread 754/762 at the limit with stop 0",
              live_rows == 0 and not posted and len(rows) == 1 and r.get("strategy") == "OpeningRangeCreditSpread"
              and float(r.get("entry_premium") or 0) == sig_call.net_credit and float(r.get("stop_premium") or 0) == 0.0
              and float(r.get("short_strike") or 0) == 754.0 and float(r.get("long_strike") or 0) == 762.0
              and r.get("option_side") == "call",
              f"live rows {live_rows}, broker path reached {len(posted)}, paper rows {len(rows)}, {dict((k, r.get(k)) for k in ('strategy', 'entry_premium', 'stop_premium', 'short_strike'))}")
    except Exception as exc:                                  # noqa: BLE001
        check("T3 (did not run)", False, f"{type(exc).__name__}: {exc}")
        main = None

    # T4 — the real exit engine
    try:
        import execution.exit_engine as XE
        eng = XE.ExitEngine(paper_trading=True)
        def leg(strategy):
            return make_record(trade_id="x-" + strategy, symbol="QQQ", strategy=strategy, setup_type="orcs_call",
                               direction="neutral", option_side="call", short_strike=754.0, long_strike=762.0,
                               spread_width=8.0, credit_received=0.2, contracts=1, entry_premium=0.2,
                               is_condor_leg=1, paper_trade=1, status="open", underlying_stop=0.0)
        sv = (XE.is_hard_close_time, eng._condor_sibling_open)
        XE.is_hard_close_time = lambda: False
        eng._condor_sibling_open = lambda record, default=False: False
        try:
            held = eng._evaluate_condor_leg(leg("OpeningRangeCreditSpread"), 2.00)
            nick = eng._evaluate_condor_leg(leg("OpeningRangeCreditSpread"), 0.01)
            ctrl = eng._evaluate_condor_leg(leg("IronCondorStrategy"), 2.00)
            XE.is_hard_close_time = lambda: True
            sv2 = XE.eod_close_due
            XE.eod_close_due = lambda *a, **k: True
            try:
                eod = eng._evaluate_condor_leg(leg("OpeningRangeCreditSpread"), 2.00)
            finally:
                XE.eod_close_due = sv2
        finally:
            XE.is_hard_close_time, eng._condor_sibling_open = sv
        check("T4 ORCS at ten times its credit HOLDS (no stop) and at a penny HOLDS (no nickel); the condor control stops; EOD closes it",
              held.should_exit is False and nick.should_exit is False and ctrl.should_exit is True
              and eod.should_exit is True and "hard_close" in str(eod.exit_reason),
              f"orcs {held.should_exit}/{nick.should_exit}, control {ctrl.should_exit} ({ctrl.exit_reason}), eod {eod.should_exit} ({eod.exit_reason})")
    except Exception as exc:                                  # noqa: BLE001
        check("T4 (did not run)", False, f"{type(exc).__name__}: {exc}")

    # T5 — the roll
    try:
        from strategy import condor_roll as CR
        import inspect
        class _PM:
            def __init__(self, strat): self.s = strat
            def get_open_records(self):
                return [{"is_condor_leg": 1, "strategy": self.s, "option_side": "put", "short_strike": 746.0,
                         "long_strike": 738.0, "trade_id": "a"},
                        {"is_condor_leg": 1, "strategy": self.s, "option_side": "call", "short_strike": 754.0,
                         "long_strike": 762.0, "trade_id": "b"}]
        seen = {}
        sv = CR.classify_tested
        CR.classify_tested = lambda legs, *a, **k: (seen.setdefault("n", len(legs)) and None, None)
        try:
            r_orcs = CR.check_and_execute_roll(_PM("OpeningRangeCreditSpread"), object(), 750.0, None)
            n_orcs = seen.pop("n", 0)
            try:
                CR.check_and_execute_roll(_PM("IronCondorStrategy"), object(), 750.0, None)
            except Exception:                                 # noqa: BLE001
                pass
            n_ctrl = seen.pop("n", 0)
        finally:
            CR.classify_tested = sv
        check("T5 two ORCS legs never reach the roll's tested-side read; two condor legs do (the control)",
              r_orcs is False and n_orcs == 0 and n_ctrl == 2, f"orcs legs seen {n_orcs}, control {n_ctrl}")
    except Exception as exc:                                  # noqa: BLE001
        check("T5 (did not run)", False, f"{type(exc).__name__}: {exc}")

    # T6 — retired
    try:
        import config as C
        called = []
        main._set_admission(None)
        for nm in ("SweepCreditSpread", "SweepForLeg2", "TrendCreditSpread"):
            main._safe_strategy(nm, lambda nm=nm: called.append(nm), None)
        off = list(called)
        sv = (C.SWEEP_CS_ENABLED, C.TREND_CREDIT_ACTIVE)
        C.SWEEP_CS_ENABLED = C.TREND_CREDIT_ACTIVE = True
        try:
            for nm in ("SweepCreditSpread", "SweepForLeg2", "TrendCreditSpread"):
                main._safe_strategy(nm, lambda nm=nm: called.append(nm), None)
        finally:
            C.SWEEP_CS_ENABLED, C.TREND_CREDIT_ACTIVE = sv
        main._safe_strategy("RunawayContinuation", lambda: called.append("RunawayContinuation"), None)
        check("T6 the sweep, its leg two and the TCS are not called; each switch restores them; the runaway is untouched",
              off == [] and sv == (False, False)
              and called == ["SweepCreditSpread", "SweepForLeg2", "TrendCreditSpread", "RunawayContinuation"],
              f"off {off}, defaults {sv}, after {called}")
    except Exception as exc:                                  # noqa: BLE001
        check("T6 (did not run)", False, f"{type(exc).__name__}: {exc}")

    # T7 — admission
    try:
        import execution.position_manager as PMM
        rule = PMM.rules().get("OpeningRangeCreditSpread")
        check("T7 ORCS is admitted 09:45-10:30, two of the type, NOT exempt from the daily cap",
              rule is not None and tuple(map(tuple, rule.window)) == ((9, 45), (10, 30))
              and rule.max_open_of_type == 2 and rule.cap_exempt is False and not rule.blocks and not rule.blocked_by,
              str(rule))
    except Exception as exc:                                  # noqa: BLE001
        check("T7 (did not run)", False, f"{type(exc).__name__}: {exc}")

    if FAILED:
        print(f"\nRED — {len(FAILED)} check(s): {FAILED}")
        return 1
    print("\nGREEN — ORCS finds its strikes, fills at the limit or not at all, is held to the close; sweep and TCS retired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
