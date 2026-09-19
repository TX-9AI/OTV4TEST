#!/usr/bin/env python3
"""tests/check_exit_replay.py — v1.0
THE PREMIUM-REPLAY TOOL IS GATED (RPL.1).

v1.0  2026-09-19  OTV4TEST r62 — `tests/exit_replay.py` carried six defects and
      NOTHING RAN IT. It is not a `check_*.py`, so the sweep never touched it,
      and its `--selftest` takes an argument the lander's CHECK directive cannot
      pass. It therefore sat at 0 of 44 replayed, announcing that the TAPE was
      empty, for as long as anyone had been reading its output. This wrapper
      puts it inside the sweep and inside every land.

🔑 IT RUNS THE TOOL'S OWN SELFTEST AND THEN ASSERTS THE THINGS THAT SELFTEST
CANNOT: that the orientation resolver actually imported (not a silent fallback),
and that the closing verdict is GATED so it can never blame the tape while the
tool is naming its own refusals.

⚠️ NOTHING HERE TOUCHES A LIVE STORE. The selftest is `:memory:`; the verdict
case drives `run()` with an empty fetch and an in-memory row.

  X1  the tool's own selftest passes
  X2  the orientation resolver IMPORTED — no silent fallback to the dead flag
  X3  ...and it resolves a credit structure as credit (it is wired, not merely present)
  X4  OCC -> streamer, including a split-adjusted root and a half-strike
  X5  a butterfly is weighted 1/2/1
  X6  the verdict cannot blame the tape when refusals exist
  X7  `option_symbol` resolves a single-leg debit

Run:  python3 tests/check_exit_replay.py
"""
import io
import os
import sys
import contextlib

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)
sys.path.insert(0, os.path.join(_root, "tests"))
FAILED, RAN = [], []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    RAN.append(name)
    if not ok:
        FAILED.append(name)


def guard(name, fn):
    try:
        ok, detail = fn()
    except Exception as exc:                                    # noqa: BLE001
        check(name, False, f"{type(exc).__name__}: {exc}")
        return
    check(name, bool(ok), detail)


import exit_replay as er                                        # noqa: E402

guard("X1 exit_replay's own selftest passes",
      lambda: (er.selftest() == 0, ""))
guard("X2 the orientation resolver imported (no silent fallback)",
      lambda: (bool(er.RESOLVER) and er.RESOLVER_FALLBACKS == 0,
               er.RESOLVER or f"UNAVAILABLE: {er.RESOLVER_ERR}"))
guard("X3 ...and it resolves a credit structure AS credit",
      lambda: (er._is_credit({"strategy": "SweepCreditSpread",
                              "setup_type": "sweep_credit_short"})
               and not er._is_credit({"strategy": "ORBStrategy"}), ""))
guard("X4 OCC -> streamer, adjusted root and half-strike included",
      lambda: (er.streamer_symbol("QQQ   260823C00100000") == ".QQQ260823C100"
               and er.streamer_symbol("CRM   260918C00182500") == ".CRM260918C182.5"
               and er.streamer_symbol("GOOGL1260918C00150000") == ".GOOGL1260918C150"
               and er.streamer_symbol("nonsense") is None, ""))


def _fly():
    legs, why = er.legs_of({"strategy": "GEXPinButterfly",
                            "lower_symbol": "QQQ   260918C00718000",
                            "center_symbol": "QQQ   260918C00720000",
                            "upper_symbol": "QQQ   260918C00722000"})
    return (not why) and sorted(s for _y, s in legs) == [-2, 1, 1], str(legs)


guard("X5 a butterfly is weighted 1/2/1, not 1/1/1", _fly)


def _verdict():
    """A row that refuses must NOT produce the tape-blaming verdict."""
    row = {"strategy": "ORBStrategy", "status": "closed",
           "entry_time": "2026-09-18T13:00:00+00:00",
           "exit_time": "2026-09-18T13:10:00+00:00",
           "option_symbol": "QQQ   260918C00718000",
           "pnl_usd": 0.0, "contracts": 1, "entry_premium": 1.0}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        er.run([row], lambda sym, lo, hi: [])       # no quotes at all
    out = buf.getvalue()
    blamed = "needs its first live" in out or "s3_push" in out
    named = "REFUSED" in out
    return (named and not blamed), ("blamed the tape" if blamed else "refusal named only")


guard("X6 the verdict cannot blame the tape while naming refusals", _verdict)
guard("X7 option_symbol resolves a single-leg debit",
      lambda: (er.legs_of({"strategy": "ORBStrategy",
                           "option_symbol": "QQQ   260823C00100000"})[0]
               == [(".QQQ260823C100", +1)], ""))

print()
if FAILED:
    print(f"  RED — {len(FAILED)} of {len(RAN)} failed: " + ", ".join(FAILED))
    sys.exit(1)
print(f"  GREEN — {len(RAN)} checks")
