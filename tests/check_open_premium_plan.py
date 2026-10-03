#!/usr/bin/env python3
"""
tests/check_open_premium_plan.py  v1.0
v1.0  2026-10-03  OTV4TEST r203 (PREM.1) — THE OPENING PREMIUM SPREAD PLAN FINDS ITS STRIKES AND PLACES NOTHING.

  The operator, 2026-10-03: "build the plan that searches the chain for our
  trigger components' location on the chain", and "we get better than mark or
  we don't trade it."

  Drives the REAL OpenPremiumPlan with a REAL OptionsChain of OptionContracts
  and the REAL Plan / write_row on a scratch store. The expected strikes are
  worked by hand from the fixture; the expected credits are read off the
  fixture's own bid and ask.
  O1  LOCATION: each side's short is the nearest OTM strike with delta <= 0.15
      (put 746, call 754 at spot 750.20); the long is ~1% of spot further
  O2  THE IMPLIED-MOVE FLOOR BINDS: with a dear straddle the delta-qualified
      strike inside 1.25 implied moves is skipped for the next one out
  O3  PRICED AT THE MARK: credit = mid - mid; bid/ask credit recorded beside it;
      the offer rests one cent better than the mark and is written to the rows
  O4  DAY GATES: not 0DTE, a gap over the limit, an UNMEASURED gap, and a tick
      before 09:45 each leave no offer (and the gap never passes by default)
  O5  THE OFFER IS FROZEN AND WATCHED: spot moves, the offer's strikes do not;
      the mark reaching the limit records filled; ten minutes unfilled expires
  O6  A RESTART CONTINUES THE OFFER: a new plan on the same store restores the
      strikes and limit from its own rows instead of re-freezing
  O7  RECORD-ONLY (a source check, stated as one): the module imports nothing
      from execution/, and main asks it through one wrapped call
  O8  the preliminary dials are config's, at the values the studies chose

Run:  python3 tests/check_open_premium_plan.py   (exit 0 green, 1 red)
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
_S = tempfile.mkdtemp(prefix="check_open_premium_plan_")
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
        "SELECT check_name, value, verdict FROM plan_check WHERE strategy='OpenPremiumSpread' AND ts_epoch>=? "
        "ORDER BY ts_epoch", (since,))}


def _verdict(st):
    r = st.conn.execute("SELECT verdict, reason FROM plan_tick WHERE strategy='OpenPremiumSpread' "
                        "ORDER BY ts_epoch DESC LIMIT 1").fetchone()
    return (r["verdict"], r["reason"]) if r else (None, None)


def main():
    try:
        from strategy import plan as P
        from strategy import open_premium_plan as M
    except Exception as exc:                                  # noqa: BLE001
        for n in ("O1", "O2", "O3", "O4", "O5", "O6", "O7", "O8"):
            check(f"{n} (did not run)", False, f"{type(exc).__name__}: {exc}")
        print(f"\nRED — {len(FAILED)} check(s): {FAILED}")
        return 1

    GAP = {"gap_pct": 0.30, "gap_abs_pct": 0.30}
    t0 = _et(9, 45).timestamp()

    def fresh(tag):
        st = _Store(os.path.join(_S, f"{tag}.db"))
        P.bind_store(st)
        P._DORMANT.pop("OpenPremiumSpread", None)
        return st, M.OpenPremiumPlan()

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
        P._DORMANT.pop("OpenPremiumSpread", None)
        plan_b = M.OpenPremiumPlan()
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
                ("f", {"chain": _chain(750.2, 1.0), "gap": GAP}, (9, 44), "DORMANT", "entry_window")):
            st, plan = fresh(tag)
            ts = _et(*when).timestamp()
            P.begin_tick(ts)
            prep = plan.prepare(price_now=750.2, now_et=_et(*when), today=DAY, now_epoch=ts, **kw)
            v, why = _verdict(st)
            out.append((tag, v, (why or "").split(":")[0], bool(plan._offers), bool(prep.ready)))
        ok = all(v == wv and g == wg and not off and not rdy
                 for (_t, v, g, off, rdy), (wv, wg) in zip(out, (("DECLINE", "zero_dte"), ("DECLINE", "gap_abs_pct"),
                                                                ("DECLINE", "gap_abs_pct"), ("DORMANT", "entry_window"))))
        check("O4 not 0DTE, a 1.25% gap, an unmeasured gap and 09:44 each leave no offer and nothing ready",
              ok, str(out))
    except Exception as exc:                                  # noqa: BLE001
        check("O4 (did not run)", False, f"{type(exc).__name__}: {exc}")
    finally:
        P.bind_store(None)

    # ── O7 — record-only, a source check ────────────────────────────────────
    try:
        src = open(os.path.join(_root, "strategy", "open_premium_plan.py")).read()
        mods = set()
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.ImportFrom):
                mods.add(n.module or "")
            elif isinstance(n, ast.Import):
                mods.update(a.name for a in n.names)
        bad = sorted(m for m in mods if m.split(".")[0] in ("execution", "risk", "database", "main"))
        msrc = open(os.path.join(_root, "main.py")).read()
        tree = ast.parse(msrc)
        fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_ask_open_premium"), None)
        wrapped = fn is not None and any(isinstance(b, ast.Try) for b in fn.body)
        calls = sum(1 for n in ast.walk(tree) if isinstance(n, ast.Call)
                    and getattr(n.func, "id", "") == "_ask_open_premium")
        check("O7 the plan imports nothing that can trade, and main asks it through one wrapped call",
              not bad and wrapped and calls == 1 and "take(" not in src,
              f"imports {bad}, wrapped {wrapped}, call sites {calls}")
    except Exception as exc:                                  # noqa: BLE001
        check("O7 (did not run)", False, f"{type(exc).__name__}: {exc}")

    # ── O8 — the dials ──────────────────────────────────────────────────────
    try:
        import config as C
        got = (tuple(C.OPS_START_ET), tuple(C.OPS_END_ET), C.OPS_SHORT_DELTA_MAX, C.OPS_MIN_IM_MULT, C.OPS_WING_PCT,
               C.OPS_MIN_CREDIT, C.OPS_MAX_GAP_PCT, C.OPS_LIMIT_IMPROVE, C.OPS_REST_MIN)
        want = ((9, 45), (10, 30), 0.15, 1.25, 0.01, 0.10, 0.90, 0.01, 10.0)
        check("O8 config carries the nine preliminary dials and the plan reads the same values",
              got == want and (M.OPS_START_ET, M.OPS_SHORT_DELTA_MAX, M.OPS_REST_MIN) == ((9, 45), 0.15, 10.0)
              and "OpenPremiumSpread" not in C.ENTRY_WINDOWS, f"{got}")
    except Exception as exc:                                  # noqa: BLE001
        check("O8 (did not run)", False, f"{type(exc).__name__}: {exc}")

    if FAILED:
        print(f"\nRED — {len(FAILED)} check(s): {FAILED}")
        return 1
    print("\nGREEN — the plan finds its strikes, prices them at the mark, freezes and watches the offer, places nothing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
