#!/usr/bin/env python3
"""tests/check_reentry_gate.py — v1.0
NO RE-ENTRY WITHIN 20 s OF A SAME-SIDE PREMIUM EXIT (RENT.2, OTV4TEST r306).

v1.0  2026-10-19  OTV4TEST r306 — the operator, 2026-10-12 10:34 ET: "A good place to get out cannot be a good place
      to get in and vice versa"; 2026-10-19 20:17 ET: "Yes" to the 20 s gate after PREMIUM exits only (A7 study,
      /var/tmp/a7_study).

THE GATE is driven through the REAL main._execute_entry_signal with a spy on entry_engine.enter - refused means the
order was never reached. The book is a SCRATCH trades.db written here (refused unless it is a temp path); COMMIT.2 and
COMMIT.3 are set off for every fire so a refusal is this gate's. Every refusal case has a control that differs in ONE
fact (age, exit kind, side, mode) and is placed.

  R0  analysis.reentry exists (RED on the base: no module)
  R1  same-side PREMIUM exit 5 s ago, trade + paper -> NOT placed, row BLOCKED with the would-be order (contracts 7)
  R2  the same exit 25 s ago -> placed, row allowed
  R3  a same-side MARKET exit 5 s ago -> placed, row allowed, prev.premium false
  R4  an OPPOSITE-side premium exit 5 s ago -> placed, no row
  R5  mode log -> placed, row would_block
  R6  mode off -> placed, no row
  R7  a LIVE box + trade -> placed, row effective=log
  R8  a premium exit at 15:59:55 ET YESTERDAY, entry at 09:30:05 today (now pinned) -> allowed (the ET day bounds it)
  R9  an unreadable trades.db -> placed, row names why
  R10 no commitment key on ctx (not a tick, e.g. another checker) -> placed, NO row
  R11 a non-directional (GEXPinButterfly) 5 s after a premium exit -> placed, no row
  R12 a BUTTERFLY's premium exit 5 s ago does not gate a directional entry -> placed
  R13 the classifier: the study's premium kinds are premium; structure_stop / exhaustion / handoff / None are not
  S1  config: unset -> trade; log/off kept; a bogus value -> log and named
  B1  the Service mode line names reentry_gate
NOT RUN (exit 2), never FAIL, when the bot's imports cannot load (e.g. a bare python3, no pytz/pandas).
Run:  OT_INSTRUMENT=QQQ python3 tests/check_reentry_gate.py
"""
import datetime as _dt
import json
import os
import sqlite3
import subprocess
import sys
import tempfile

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)
_tmp = tempfile.mkdtemp(prefix="check_reentry_gate_")
os.environ["OT_COUNTERFACTUAL_DIR"] = os.path.join(_tmp, "cf")
os.environ["OT_TRADES_DB"] = os.path.join(_tmp, "trades.db")
os.environ.setdefault("OT_LOG_FILE", os.path.join(_tmp, "bot.log"))
os.environ.setdefault("OT_DERIVED_DB", os.path.join(_tmp, "derived_store.db"))
os.environ.setdefault("OT_RESTING_DB", os.path.join(_tmp, "resting_orders.db"))
os.environ.setdefault("OT_SIGNAL_JOURNAL_DIR", os.path.join(_tmp, "signal_journal"))
FAILED, RAN = [], []


def check(name, ok, detail=""):
    RAN.append(name)
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok or not detail else f"  -- {detail}"))
    if not ok:
        FAILED.append(name.split()[0])


def guard(name, fn, detail=""):
    try:
        ok = bool(fn())
    except Exception as exc:                                     # noqa: BLE001
        check(name, False, f"{type(exc).__name__}: {exc}")
        return
    check(name, ok, detail() if callable(detail) else detail)


try:
    import main                                                 # noqa: E402
    from strategy.base_strategy import OptionsSignal            # noqa: E402
    import config                                               # noqa: E402
except Exception as exc:                                         # noqa: BLE001
    print(f"  NOT RUN — the bot's imports cannot load here: {type(exc).__name__}: {exc}")
    sys.exit(2)

try:
    from analysis import reentry                                # noqa: E402
    check("R0 analysis.reentry exists", True)
except Exception as exc:                                         # noqa: BLE001
    reentry = None
    check("R0 analysis.reentry exists", False, f"{type(exc).__name__}: {exc}")


def _book(rows):
    """rows: (direction, exit_reason, exit_epoch, is_butterfly)."""
    p = config.DB_PATH
    if not os.path.realpath(p).startswith((os.path.realpath(tempfile.gettempdir()) + os.sep, "/tmp/")):
        raise RuntimeError(f"refusing to write a fixture trades.db at {p} (not a temp path)")
    if os.path.isdir(p):
        os.rmdir(p)
    if os.path.exists(p):
        os.remove(p)
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE trades (trade_id TEXT PRIMARY KEY, strategy TEXT, status TEXT, direction TEXT, "
              "is_butterfly INTEGER, is_condor_leg INTEGER, relaxed_entry INTEGER, entry_time TEXT, exit_time TEXT, "
              "exit_reason TEXT, pnl_usd REAL)")
    for i, (d, why, x, fly) in enumerate(rows):
        c.execute("INSERT INTO trades VALUES (?,?,?,?,?,0,0,?,?,?,?)",
                  (f"x{i}", "GEXPinButterfly" if fly else "Breakout", "closed", d, fly,
                   _dt.datetime.fromtimestamp(x - 120, _dt.timezone.utc).isoformat(),
                   _dt.datetime.fromtimestamp(x, _dt.timezone.utc).isoformat(), why, 50.0))
    c.commit()
    c.close()


class _Sizing:
    allowed = True
    contracts = 7
    total_cost = 700.0
    reject_reason = None


class _Risk:
    def size_for(self, *a, **kw):
        return _Sizing()


class _Spy:
    def __init__(self):
        self.entered = []

    def enter(self, signal=None, sizing=None, **kw):
        self.entered.append((getattr(signal, "strategy_name", "?"), getattr(sizing, "contracts", None)))
        return None


class _Macro:
    butterfly_half_size = False


class _State:
    paper_trading = True


def _sig(name="Breakout", direction="short"):
    return OptionsSignal(strategy_name=name, setup_type="fixture", direction=direction,
                         option_side="call" if direction == "long" else "put",
                         underlying_entry=100.0, underlying_stop=(101.0 if direction == "short" else 99.0),
                         strike=100.0, entry_premium=1.25)


def _rows():
    p = os.path.join(_tmp, "cf", "reentry_gate.jsonl")
    if not os.path.exists(p):
        return []
    with open(p) as fh:
        return [json.loads(x) for x in fh if x.strip()]


def _fire(signal, *, mode="trade", paper=True, has_key=True):
    spy = _Spy()
    saved = (main.get_risk_manager, main.get_entry_engine, main.COMMIT_GATE_MODE, main.CAUTION_SIZE_MODE,
             main.REENTRY_GATE_MODE, main.PAPER_TRADING)
    main.get_risk_manager = lambda *a, **kw: _Risk()
    main.get_entry_engine = lambda *a, **kw: spy
    main.COMMIT_GATE_MODE, main.CAUTION_SIZE_MODE = "off", "off"
    main.REENTRY_GATE_MODE, main.PAPER_TRADING = mode, paper
    ctx = {"price": 100.0, "macro": _Macro()}
    if has_key:
        ctx["commitment"] = {"bar_ts": 1, "long": {"state": "NEUTRAL"}, "short": {"state": "NEUTRAL"}}
    try:
        main._execute_entry_signal(signal, ctx, None, _State(), None, additive=True)
    finally:
        (main.get_risk_manager, main.get_entry_engine, main.COMMIT_GATE_MODE, main.CAUTION_SIZE_MODE,
         main.REENTRY_GATE_MODE, main.PAPER_TRADING) = saved
    return spy.entered


def _case(book, signal=None, **kw):
    import time as _t
    now = _t.time()
    _book([(d, why, now - age, fly) for d, why, age, fly in book])
    n0 = len(_rows())
    placed = _fire(signal or _sig(), **kw)
    return placed, _rows()[n0:]


TRAIL = "trail_stop_hit pnl=10.4%"


def r1():
    placed, rows = _case([("short", TRAIL, 5, 0)])
    return (not placed and len(rows) == 1 and rows[0]["decision"] == "BLOCKED"
            and rows[0]["order"]["contracts"] == 7 and rows[0]["prev"]["premium"] is True)


guard("R1 same-side PREMIUM exit 5 s ago -> NOT placed, row BLOCKED with contracts", r1, lambda: json.dumps(_rows()[-1:]))
guard("R2 the same exit 25 s ago -> placed, row allowed",
      lambda: (lambda p, r: bool(p) and len(r) == 1 and r[0]["decision"] == "allowed")(*_case([("short", TRAIL, 25, 0)])))
guard("R3 same-side MARKET exit 5 s ago -> placed, row allowed, premium false",
      lambda: (lambda p, r: bool(p) and len(r) == 1 and r[0]["decision"] == "allowed"
               and r[0]["prev"]["premium"] is False)(*_case([("short", "structure_stop: 1m close 745.38 through", 5, 0)])))
guard("R4 OPPOSITE-side premium exit 5 s ago -> placed, no row",
      lambda: (lambda p, r: bool(p) and not r)(*_case([("long", TRAIL, 5, 0)])))
guard("R5 mode log -> placed, row would_block",
      lambda: (lambda p, r: bool(p) and len(r) == 1 and r[0]["decision"] == "would_block")(
          *_case([("short", TRAIL, 5, 0)], mode="log")))
guard("R6 mode off -> placed, no row",
      lambda: (lambda p, r: bool(p) and not r)(*_case([("short", TRAIL, 5, 0)], mode="off")))
guard("R7 LIVE box + trade -> placed, row effective=log",
      lambda: (lambda p, r: bool(p) and len(r) == 1 and r[0]["effective"] == "log"
               and r[0]["decision"] == "would_block")(*_case([("short", TRAIL, 5, 0)], paper=False)))


def r8():
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    x = _dt.datetime(2026, 10, 15, 15, 59, 55, tzinfo=et).timestamp()
    now = _dt.datetime(2026, 10, 16, 9, 30, 5, tzinfo=et).timestamp()
    _book([("short", TRAIL, x, 0)])
    hit = reentry.last_same_side_exit(config.DB_PATH, "short", now)
    ctrl = reentry.last_same_side_exit(config.DB_PATH, "short", x + 5)
    return (hit is None and ctrl is not None and abs(ctrl["age_s"] - 5) < 0.01
            and not reentry.gate(_sig(), {"commitment": {}}, mode="trade", paper=True, now=now))


guard("R8 yesterday's 15:59:55 premium exit does not gate today's 09:30:05 entry (control: 5 s later same day)", r8)


def r9():
    p = config.DB_PATH
    if os.path.exists(p):
        os.remove(p)
    os.makedirs(p)                      # a directory where the book should be: unreadable
    try:
        n0 = len(_rows())
        placed = _fire(_sig())
        rows = _rows()[n0:]
    finally:
        os.rmdir(p)
    return bool(placed) and len(rows) == 1 and rows[0]["decision"] == "allowed" and rows[0].get("why_unread")


guard("R9 unreadable trades.db -> placed, row names why", r9, lambda: json.dumps(_rows()[-1:]))
guard("R10 no commitment key (not a tick) -> placed, NO row",
      lambda: (lambda p, r: bool(p) and not r)(*_case([("short", TRAIL, 5, 0)], has_key=False)))
guard("R11 non-directional GEXPinButterfly 5 s after a premium exit -> placed, no row",
      lambda: (lambda p, r: bool(p) and not r)(*_case([("short", TRAIL, 5, 0)], signal=_sig(name="GEXPinButterfly"))))
guard("R12 a butterfly's premium exit 5 s ago does not gate -> placed",
      lambda: (lambda p, r: bool(p) and not any(x["decision"] == "BLOCKED" for x in r))(
          *_case([("short", TRAIL, 5, 1)])))
guard("R13 classifier: premium kinds yes; structure_stop / exhaustion / handoff / None no",
      lambda: (all(reentry.is_premium_exit(x) for x in (
          "trail_stop_hit pnl=1%", "orb_trail_stop pnl=2%", "hard_stop_20% pnl=-20%", "stop_40%",
          "premium_stop_15%", "volt_premium_floor: 0.86 <= 0.90", "post_target_trail pnl=111%"))
          and not any(reentry.is_premium_exit(x) for x in (
              "structure_stop: 1m close", "exhaustion: new short extreme", "handoff: pool 716.87", None, ""))))


def _cfg(env):
    e = {k: v for k, v in os.environ.items() if not k.startswith("OT_REENTRY_GATE")}
    e.update(env)
    out = subprocess.run([sys.executable, "-c", "import config as c; print(c.REENTRY_GATE_MODE, "
                          "repr(c.REENTRY_GATE_ENV_REFUSED))"],
                         cwd=_root, env=e, capture_output=True, text=True, timeout=60)
    return out.stdout.strip().splitlines()[-1] if out.stdout.strip() else out.stderr[-200:]


guard("S1 OT_REENTRY_GATE: unset -> trade; log kept; off kept; bogus -> log, named",
      lambda: (_cfg({}).split()[0] == "trade" and _cfg({"OT_REENTRY_GATE": "log"}).split()[0] == "log"
               and _cfg({"OT_REENTRY_GATE": "off"}).split()[0] == "off"
               and _cfg({"OT_REENTRY_GATE": "bogus"}).split() == ["log", "'bogus'"]),
      lambda: _cfg({"OT_REENTRY_GATE": "bogus"}))
guard("B1 the Service mode line names reentry_gate", lambda: " · reentry_gate=" in main._banner_dials())

print()
if FAILED:
    print(f"  RED — {len(FAILED)} of {len(RAN)} failed: " + ", ".join(FAILED))
    sys.exit(1)
print(f"  GREEN — {len(RAN)} checks")
