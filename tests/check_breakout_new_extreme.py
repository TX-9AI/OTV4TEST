#!/usr/bin/env python3
"""
tests/check_breakout_new_extreme.py  v1.1
v1.1  2026-09-25  OTV4TEST r142 — N9: A RE-FIRE ON THE SAME SIGNAL BAR IS REFUSED. Live,
      2026-09-25: a long fired at 09:36:16 on the 09:35 close; at 09:36:51 the
      09:35 bar was still the last closed bar and the re-fire PASSED this gate on
      the same close (-$1,250). N1-N8 never caught it: every re-fire they asked
      was on a LATER bar. ⚠️ THE FIXTURE'S CLOCK IS FIXED WITH IT: `_log` stamped
      entries at the REAL time, which the new "signal bar closed after the last
      entry" rule reads, so a run in the afternoon would refuse every re-fire and
      one at 08:00 would pass them - entries now carry the synthetic minute they
      fired at. N4b moves from minute 30 to 31: at 30 it re-asked the SAME bar the
      short had just fired on, which is now N9c's property; at 31 it still tests
      "not below the session low", and asserts the same 97.50.
A BREAKOUT RE-FIRE ON A SIDE NEEDS A NEW SESSION EXTREME (r131).

v1.0  2026-09-24  OTV4TEST r131 — born red at r130 (b1b6594): the plan has no
      re-fire gate there, so the second long fires on a close that is still
      beyond the edge and nowhere near a new high.

THE OPERATOR'S RULING, 2026-09-24, verbatim: *"A new reclaimed level has to
happen before it can fire again? A new high for a long, a new low for a
short."* The first entry per side per session keeps the break trigger (the
last closed 1m bar's CLOSE beyond the range edge). Every LATER entry on that
side needs that close strictly above the highest HIGH (long) / below the
lowest LOW (short) of every prior RTH bar since 09:30. Closes are acceptance;
no tolerance.

EVERYTHING HERE DRIVES THE REAL PLAN. `BreakoutPlan.prepare` on synthetic
bars written to a scratch feed store, with "already fired" coming from a
scratch trades.db whose rows go in through the repo's own `TradeLogger`.
Only the order-flow READER is stubbed to a passing value (it reads live
prints "as of now"); the research acceptance is pinned open so the informers
cannot decide a tick this file is not about.

  N1  the first break on a side fires exactly as before
  N2  a second long, close beyond the edge but not above the session high,
      is refused under the gate "new_extreme" (and a close EQUAL to the
      session high is refused too — strictly beyond)
  N3  a close above the session high is allowed
  N4  the short side mirrors it, and a long already fired does not block the
      first short
  N5  a restart (a fresh interpreter) still knows the side fired — trades.db
  N6  a 60-bar df_1m that no longer reaches the session high does not shrink it
  N7  breakout.GATES declares NEW_EXTREME FOUNDATIONAL, and it is the name refused
  N8  an unreadable book or tape, or a tape that does not reach 09:30, FAILS
      CLOSED under the same named gate
"""
import os
import sys
import shutil
import sqlite3
import subprocess
import tempfile

import glob as _glob
for _sp in _glob.glob(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "venv", "lib", "python*", "site-packages")):
    if _sp not in sys.path: sys.path.insert(1, _sp)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# the N5 child re-enters this file in a fresh interpreter and must use the
# PARENT's scratch stores — that is the whole point of the restart check
SCRATCH = (os.environ["N5_SCRATCH"] if os.environ.get("N5_RESTART") == "1"
           else tempfile.mkdtemp(prefix="chk_brk_ne_", dir="/var/tmp"))
os.environ["OT_TRADES_DB"] = os.path.join(SCRATCH, "trades.db")
os.environ["OT_DERIVED_DB"] = os.path.join(SCRATCH, "derived.db")
os.environ["OT_RESTING_DB"] = os.path.join(SCRATCH, "resting.db")
os.environ["OT_FEED_DB"] = os.path.join(SCRATCH, "feed.db")
os.environ["OT_BRK_RESEARCH_UNTIL"] = "2099-12-31"      # informers: accept any
FAILED, RAN = [], []
ET = "America/New_York"


def check(name, ok, detail=""):
    RAN.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILED.append(name.split()[0])


def guard(name, fn):
    try:
        ok, det = fn()
    except Exception as exc:                                    # noqa: BLE001
        ok, det = False, f"{type(exc).__name__}: {exc}"
    check(name, bool(ok), det)


# ── the synthetic session. Range 100.00-101.00 (long) on TST; TSS mirrors it
#    about 200 (range 99.00-100.00, short). One bar per minute from 09:30.
def _long_session():
    bars = {}
    for m in range(0, 5):                                  # 09:30-09:34 the range
        bars[m] = (100.5, 101.00, 100.00, 100.5)
    for m in range(5, 101):                                # 09:35-11:10 filler
        bars[m] = (101.5, 101.80, 101.30, 101.6)
    bars[5] = (100.6, 101.40, 100.55, 101.30)              # 09:35 FIRST BREAK close
    bars[10] = (101.6, 102.50, 101.50, 101.9)              # 09:40 SESSION HIGH 102.50
    bars[15] = (102.0, 102.50, 101.90, 102.50)             # 09:45 close EQUAL to it
    bars[29] = (101.5, 101.85, 101.40, 101.60)             # 09:59 beyond edge, no new high
    bars[79] = (101.7, 102.05, 101.60, 102.00)             # 10:49 above the 60-bar frame, not the session
    bars[90] = (102.0, 102.80, 101.95, 102.70)             # 11:00 NEW HIGH close
    return bars


def _mirror(bars):
    return {m: (200 - o, 200 - l, 200 - h, 200 - c) for m, (o, h, l, c) in bars.items()}


def _write_feed(day):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    c = sqlite3.connect(os.environ["OT_FEED_DB"])
    c.execute("CREATE TABLE IF NOT EXISTS candles (symbol TEXT NOT NULL, interval TEXT NOT NULL, "
              "ts_epoch_ms INTEGER NOT NULL, open REAL, high REAL, low REAL, close REAL, "
              "volume REAL, PRIMARY KEY (symbol, interval, ts_epoch_ms))")
    o = int(datetime(day.year, day.month, day.day, 9, 30, tzinfo=ZoneInfo(ET)).timestamp() * 1000)
    gap = {m: b for m, b in _long_session().items() if m != 0}     # no 09:30 bar
    for sym, bars in (("TST", _long_session()), ("TSS", _mirror(_long_session())),
                      ("TSG", gap)):
        for m, (op, h, l, cl) in bars.items():
            c.execute("INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?)",
                      (sym, "1m", o + m * 60_000, op, h, l, cl, 1000.0))
    c.commit()
    c.close()


def _frame(sym, day, minute, keep=60):
    """The frame main.py hands over: bars up to and INCLUDING the forming one
    (at `minute`), the last `keep` of them, tz-aware ET like fetch_candles."""
    import pandas as pd
    from datetime import datetime
    from zoneinfo import ZoneInfo
    o = int(datetime(day.year, day.month, day.day, 9, 30, tzinfo=ZoneInfo(ET)).timestamp() * 1000)
    c = sqlite3.connect(f"file:{os.environ['OT_FEED_DB']}?mode=ro", uri=True)
    rows = c.execute("SELECT ts_epoch_ms, open, high, low, close, volume FROM candles "
                     "WHERE symbol=? AND interval='1m' AND ts_epoch_ms <= ? ORDER BY ts_epoch_ms",
                     (sym, o + minute * 60_000)).fetchall()
    c.close()
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.pop("ts"), unit="ms", utc=True).dt.tz_convert(ET)
    return df.iloc[-keep:]


class _ORB:
    def __init__(self, hi, lo):
        self.orb_high, self.orb_low = hi, lo


class _C:
    def __init__(self, k):
        self.strike, self.mark, self.delta, self.gamma, self.expiry, self.ask = k, 1.0, 0.5, 0.05, "", 1.05


class _Chain:
    def __init__(self, px):
        ks = [round(px) + i for i in range(-6, 7)]
        self.calls, self.puts = [_C(k) for k in ks], [_C(k) for k in ks]


def _hm(minute):
    return f"{9 + (30 + minute) // 60:02d}:{(30 + minute) % 60:02d}"


def _tick(plan, spec, sym, day, minute, keep=60):
    """Ask the plan at the START of `minute`: the last closed bar is minute-1."""
    df = _frame(sym, day, minute, keep)
    px = float(df.iloc[-1]["open"])
    hi, lo = (100.00, 99.00) if sym == "TSS" else (101.00, 100.00)
    prep = plan.prepare(spec=spec, orb=_ORB(hi, lo), price_now=px, now_et=_hm(minute),
                        chain=_Chain(px), df_1m=df, flow_conn=None, symbol=sym)
    return prep, df


def _refused_at_gate(prep):
    t = prep.tick
    return (not prep.ready and t.verdict == "DECLINE"
            and t.plan.last()[2].startswith("new_extreme:")
            and (t.checks.get("new_extreme") or (None, None))[1] is False)


def _why(prep):
    t = prep.tick
    return (f"ready={prep.ready} verdict={t.verdict or prep.verdict} "
            f"why={(t.plan.last()[2] if t.closed else '-')[:90]!r} "
            f"sess={(t.checks.get('session_extreme') or (None,))[0]}")


def _log(side, minute, day):
    """An entry filled 16s into `minute` (09:30 + minute) of `day` — on the
    fixture's clock, because the r142 rule reads the entry TIME."""
    import uuid
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from database.trade_logger import get_trade_logger, make_record
    tid = str(uuid.uuid4())
    tl = get_trade_logger()
    tl.log_entry(make_record(
        trade_id=tid, symbol="TST", strategy="Breakout",
        setup_type=f"breakout_{'long' if side == 'call' else 'short'}",
        direction=("long" if side == "call" else "short"), option_side=side,
        orb_range_high=101.0, orb_range_low=100.0, paper_trade=1))
    at = (datetime(day.year, day.month, day.day, 9, 30, tzinfo=ZoneInfo(ET))
          + timedelta(minutes=minute, seconds=16)).astimezone(ZoneInfo("UTC")).isoformat()
    conn = tl._connect()
    try:
        conn.execute("UPDATE trades SET entry_time=? WHERE trade_id=?", (at, tid))
        conn.commit()
    finally:
        conn.close()




def main():
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime
        day = datetime.now(ZoneInfo(ET)).date()
        _write_feed(day)
        from database.trade_logger import get_trade_logger
        get_trade_logger()                                   # the repo's schema
        from strategy.breakout import Breakout
        import strategy.breakout as B
        from strategy.breakout_plan import BreakoutPlan
        BreakoutPlan._flow = staticmethod(lambda conn, symbol: (0.2, 1.0))
        spec = Breakout()
        plan = spec._plan_()
    except Exception as exc:                                    # noqa: BLE001
        for n in ("N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8", "N9"):
            check(f"{n} setup", False, f"{type(exc).__name__}: {exc}")
        return _tail()

    # ── N1 — the FIRST long: nothing in the book, the break close decides ──
    p1, _ = _tick(plan, spec, "TST", day, 6)                 # signal 09:35 close 101.30
    guard("N1 the first break on a side fires exactly as before (no book row, close beyond the edge)",
          lambda: (p1.ready and p1.direction == "long"
                   and "session_extreme" not in p1.tick.checks, _why(p1)))

    # ── N9 — the long filled at 09:36:16; the 09:35 bar is STILL the last closed
    # bar for the rest of that minute (2026-09-25, 09:36:51, -$1,250) ────────────
    _log("call", 6, day)
    p9, _ = _tick(plan, spec, "TST", day, 6)                 # signal 09:35 AGAIN
    guard("N9 a re-fire on the SAME signal bar that fired the last entry is refused",
          lambda: (_refused_at_gate(p9) and "no bar has closed since" in p9.tick.plan.last()[2],
                   _why(p9)))
    p9b, _ = _tick(plan, spec, "TST", day, 7)                # signal 09:36: close 101.60 > 09:35's 101.40
    guard("N9b the NEXT bar re-fires when it really makes a new high — the side is not locked",
          lambda: (p9b.ready and p9b.direction == "long"
                   and abs(float(p9b.tick.checks["session_extreme"][0]) - 101.40) < 1e-9, _why(p9b)))

    # ── N2 — one long in the book; a close beyond the edge, no new high ─────
    p2, _ = _tick(plan, spec, "TST", day, 30)                # signal 09:59 close 101.60 < 102.50
    guard("N2 a second long beyond the edge but NOT above the session high is refused at 'new_extreme'",
          lambda: (_refused_at_gate(p2)
                   and abs(float(p2.tick.checks["session_extreme"][0]) - 102.50) < 1e-9, _why(p2)))
    p2b, _ = _tick(plan, spec, "TST", day, 16)               # signal 09:45 close == 102.50
    guard("N2b a close EQUAL to the session high is refused — strictly above, no tolerance",
          lambda: (_refused_at_gate(p2b), _why(p2b)))

    # ── N3 — a close above the session high is allowed ───────────────────
    p3, _ = _tick(plan, spec, "TST", day, 91)                # signal 11:00 close 102.70 > 102.50
    guard("N3 a close ABOVE the session high re-fires",
          lambda: (p3.ready and p3.direction == "long"
                   and (p3.tick.checks.get("new_extreme") or (None, None))[1] is True, _why(p3)))

    # ── N4 — the short side mirrors it ────────────────────────────────────
    # the first short is taken at 09:59 — below the edge, NOT below the 09:40
    # session low — so only a per-SIDE count lets it through: a long in the
    # book must not make the first short need a new extreme.
    p4a, _ = _tick(plan, spec, "TSS", day, 30)               # 98.40, session low 97.50
    guard("N4a the first SHORT fires on the break close although a long already fired — the latch is per side",
          lambda: (p4a.ready and p4a.direction == "short"
                   and "session_extreme" not in p4a.tick.checks, _why(p4a)))
    _log("put", 30, day)
    p9c, _ = _tick(plan, spec, "TSS", day, 30)               # the SAME 09:59 bar the short fired on
    guard("N9c the short side: the same signal bar cannot re-fire either",
          lambda: (_refused_at_gate(p9c) and "no bar has closed since" in p9c.tick.plan.last()[2],
                   _why(p9c)))
    p4b, _ = _tick(plan, spec, "TSS", day, 31)               # 10:00 bar: 98.40 not below 97.50
    guard("N4b a second short below the edge but NOT below the session low is refused",
          lambda: (_refused_at_gate(p4b)
                   and abs(float(p4b.tick.checks["session_extreme"][0]) - 97.50) < 1e-9, _why(p4b)))
    p4c, _ = _tick(plan, spec, "TSS", day, 91)               # 97.30 below 97.50
    guard("N4c a close BELOW the session low re-fires the short",
          lambda: (p4c.ready and p4c.direction == "short", _why(p4c)))

    # ── N5 — a restart: a FRESH interpreter, a fresh plan, the same book ───
    def restart():
        env = dict(os.environ, N5_RESTART="1", N5_SCRATCH=SCRATCH)
        out = subprocess.run([sys.executable, os.path.abspath(__file__)], env=env, capture_output=True,
                             text=True, timeout=120)
        line = [l for l in out.stdout.splitlines() if l.startswith("N5RESULT")]
        return (bool(line) and line[-1].split()[1] == "REFUSED",
                (line[-1] if line else (out.stderr.strip().splitlines() or ["no output"])[-1])[:160])
    guard("N5 a restart still knows the long fired — read from trades.db, not memory", restart)

    # ── N6 — the 60-bar frame lost the 09:40 high; the session did not ────
    p6, df6 = _tick(plan, spec, "TST", day, 80, keep=60)     # signal 10:49 close 102.00
    frame_hi = float(df6.iloc[:-2]["high"].max())
    guard("N6 a truncated df_1m does not shrink the session high (09:40's 102.50 still binds)",
          lambda: (frame_hi < 102.00 and df6.index[0].strftime("%H:%M") > "09:40"
                   and _refused_at_gate(p6),
                   f"frame {df6.index[0].strftime('%H:%M')}-{df6.index[-1].strftime('%H:%M')} "
                   f"high {frame_hi:.2f}; " + _why(p6)))

    # ── N7 — declared FOUNDATIONAL, and it is the name refused under ──────
    guard("N7 breakout.GATES declares NEW_EXTREME FOUNDATIONAL and the plan refuses under that name",
          lambda: (B.GATES.get("NEW_EXTREME") == "FOUNDATIONAL"
                   and getattr(B, "NEW_EXTREME", None) == "new_extreme"
                   and "new_extreme" in Breakout.PLAN_CHECKS,
                   f"GATES={B.GATES.get('NEW_EXTREME')} NEW_EXTREME={getattr(B, 'NEW_EXTREME', None)}"))

    # ── N8 — fail closed: an unreadable tape, then an unreadable book ─────
    feed = os.environ["OT_FEED_DB"]
    os.environ["OT_FEED_DB"] = os.path.join(SCRATCH, "absent", "feed.db")
    try:
        p8 = plan.prepare(spec=spec, orb=_ORB(101.0, 100.0), price_now=102.0, now_et="11:01",
                          chain=_Chain(102.0), df_1m=_frame_from(feed, "TST", day, 91),
                          flow_conn=None, symbol="TST")
    finally:
        os.environ["OT_FEED_DB"] = feed
    guard("N8a an unreadable feed store refuses a re-fire at 'new_extreme', never passes it",
          lambda: (_refused_at_gate(p8) or (not p8.ready and p8.tick.verdict == "DECLINE"
                                            and p8.tick.plan.last()[2].startswith("new_extreme:")),
                   _why(p8)))
    p8c, _ = _tick(plan, spec, "TSG", day, 91)               # would pass on a whole tape
    guard("N8c a session tape that does not reach 09:30 refuses a re-fire — the high may be missing",
          lambda: (_refused_at_gate(p8c) and "09:30" in p8c.tick.plan.last()[2], _why(p8c)))
    import database.trade_logger as TL
    saved = TL._trade_logger
    class _Broken:
        _mode_flag = 1
        def _connect(self):
            raise sqlite3.OperationalError("disk I/O error")
    TL._trade_logger = _Broken()
    try:
        p8b, _ = _tick(plan, spec, "TST", day, 6)
    finally:
        TL._trade_logger = saved
    guard("N8b an unreadable trades.db refuses at 'new_extreme' — it cannot know the side is fresh",
          lambda: (not p8b.ready and p8b.tick.verdict == "DECLINE"
                   and p8b.tick.plan.last()[2].startswith("new_extreme:"), _why(p8b)))
    # (last on purpose: its second long entry would change what every later
    # minute-91 re-ask is testing)
    # N9d — freshness is judged against the LATEST entry, not the first: a second
    # long fills at 11:01:16 on the 11:00 new-high close; asked again on that same
    # bar it must refuse, although the 09:36 entry is long gone.
    _log("call", 91, day)
    p9d, _ = _tick(plan, spec, "TST", day, 91)
    guard("N9d the LATEST same-side entry sets the fresh-bar bound, not the first",
          lambda: (_refused_at_gate(p9d) and "no bar has closed since" in p9d.tick.plan.last()[2]
                   and "11:01:16" in p9d.tick.plan.last()[2], _why(p9d)))
    return _tail()


def _frame_from(feed, sym, day, minute):
    saved = os.environ["OT_FEED_DB"]
    os.environ["OT_FEED_DB"] = feed
    try:
        return _frame(sym, day, minute)
    finally:
        os.environ["OT_FEED_DB"] = saved


def _tail():
    print()
    if FAILED:
        print(f"RED — {len(FAILED)} of {len(RAN)} failed: {', '.join(FAILED)}")
        return 1
    print(f"GREEN — {len(RAN)} checks: a Breakout re-fire on a side needs a new session extreme")
    return 0


def _n5_child():
    """Run inside a FRESH interpreter against the parent's scratch stores."""
    from zoneinfo import ZoneInfo
    from datetime import datetime
    day = datetime.now(ZoneInfo(ET)).date()
    from strategy.breakout import Breakout
    from strategy.breakout_plan import BreakoutPlan
    BreakoutPlan._flow = staticmethod(lambda conn, symbol: (0.2, 1.0))
    spec = Breakout()
    p, _ = _tick(spec._plan_(), spec, "TST", day, 30)
    print("N5RESULT", "REFUSED" if _refused_at_gate(p) else "ALLOWED", _why(p))


if __name__ == "__main__":
    if os.environ.get("N5_RESTART") == "1":
        _n5_child()
    else:
        try:
            rc = main()
        finally:
            shutil.rmtree(SCRATCH, ignore_errors=True)
        sys.exit(rc)
