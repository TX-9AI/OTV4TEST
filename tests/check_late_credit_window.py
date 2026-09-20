#!/usr/bin/env python3
"""tests/check_late_credit_window.py — v1.0
A CREDIT ENTRY ALWAYS HAS LIFE, AND A DEBIT NEVER OPENS INTO ITS OWN FLATTEN.

v1.0  2026-09-20 — OTV4TEST r71. The operator widened the CREDIT entry windows
      to 15:40 and moved the vertical close to 15:50, to catch the late-day
      moves: *"I've seen multiple end of day moves now that I'm convinced smart
      money is intentionally placing those orders to keep zero DTE traders out
      of it. Well, I'll have none of that."*

🔴 THE SESSION THAT PROVED IT — 2026-09-16. QQQ fell 11.66 points, 711.78
(11:47) to 700.12 (15:27). A london support was REJECTED at 14:53 and ACCEPTED
THROUGH at 14:57:45, with three more supports wicked one second later; chain net
GEX crossed zero into TRENDING at 15:00:15 with 5.2 points still to come. **The
sweep — the strategy whose entire job is trading swept levels — was DORMANT from
14:00**, and the box held nothing in the direction of the day's defining move.

  W1  SWEEP and TCS both close at 15:40
  W2  🔑 STRUCTURAL: every DEBIT strategy closes AT OR BEFORE the flatten
      ladder opens, so a debit can never be widened into its own flatten
  W3  🔑 STRUCTURAL: every CREDIT strategy closes STRICTLY BEFORE the vertical
      hold, so a credit entry always has at least a minute of life
  W4  the vertical hold is 15:50, and sits AFTER the ladder opens (which is
      what makes the credit exemption meaningful)
  W5  the vertical hold lands before the final 15:57 reconcile sweep and
      before the 16:00 expiry — assignment requires a FAILED FLATTEN, not a
      held position
  W6  the vertical exit label is DERIVED from the constant, never a literal
  W7  SCOPE PIN: exactly ONE site moved. Five genuine HARD_CLOSE_ET sites
      remain and the constant is still 15:45 — so this change cannot have
      quietly moved the general hard close along with the vertical one.
      ⚠️ NOT a control: it is born red at base (six sites), and calling it one
      would teach the reader that a red here is expected.

⚠️ W2 AND W3 ARE THE POINT. W1 pins today's numbers and will need editing the
next time the operator rules; W2 and W3 encode the RELATIONSHIP and would catch
the mistake at any values — a debit widened into its own ladder holds nothing,
and a credit entered at or after its close is a round trip for the spread.
"""
from __future__ import annotations

import ast
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)
FAILED, RAN = [], []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    RAN.append(name)
    if not ok:
        FAILED.append(name)


def guard(name, fn, detail=lambda: ""):
    try:
        ok = bool(fn())
    except Exception as exc:                                    # noqa: BLE001
        check(name, False, f"raised {type(exc).__name__}: {exc}")
        return False
    try:
        d = detail()
    except Exception:                                           # noqa: BLE001
        d = ""
    check(name, ok, d)
    return ok


try:
    import config
    from execution.position_manager import rules
    ERR = None
except Exception as exc:                                        # noqa: BLE001
    ERR = "%s: %s" % (type(exc).__name__, exc)

if ERR:
    for n in ("W1", "W2", "W3", "W4", "W5", "W6", "W7"):
        check(n + " (not reached)", False, ERR)
    print("\nRED — " + ERR)
    sys.exit(1)

R = rules()
LADDER = tuple(config.FLATTEN_WINDOW_OPEN_ET)
VHOLD = tuple(config.VERTICAL_HOLD_TO_ET)

# Which structures pay a debit. MEASURED on the book 2026-09-20: both
# butterflies carry net_debit (0.26, 0.47) and credit_received 0.0.
DEBIT = {"GEXPinButterfly", "ATPButterfly", "ORBStrategy", "RunawayContinuation",
         "LiquidityHunt", "Breakout"}
CREDIT = {"SweepCreditSpread", "TrendCreditSpread"}


def _close(name):
    r = R.get(name)
    return tuple(r.window[1]) if r else None


guard("W1 SWEEP and TCS both close at 15:40",
      lambda: _close("SweepCreditSpread") == (15, 40)
      and _close("TrendCreditSpread") == (15, 40),
      lambda: "sweep=%s tcs=%s" % (_close("SweepCreditSpread"), _close("TrendCreditSpread")))


def _w2():
    bad = [n for n in R if n in DEBIT and _close(n) > LADDER]
    _w2.bad = bad
    return not bad


guard("W2 no DEBIT strategy opens at or after the flatten ladder",
      _w2, lambda: "ladder=%s bad=%s" % (LADDER, getattr(_w2, "bad", [])))


def _w3():
    bad = [n for n in R if n in CREDIT and _close(n) >= VHOLD]
    _w3.bad = bad
    return not bad


guard("W3 every CREDIT strategy closes strictly before the vertical hold",
      _w3, lambda: "vhold=%s bad=%s" % (VHOLD, getattr(_w3, "bad", [])))

guard("W4 the vertical hold is 15:50 and sits after the ladder opens",
      lambda: VHOLD == (15, 50) and VHOLD > LADDER,
      lambda: "vhold=%s ladder=%s" % (VHOLD, LADDER))

guard("W5 the vertical hold precedes the final 15:57 sweep and the 16:00 expiry",
      lambda: VHOLD < (15, 57) < tuple(config.RTH_CLOSE_ET),
      lambda: "vhold=%s rth_close=%s" % (VHOLD, tuple(config.RTH_CLOSE_ET)))


def _w6():
    """The vertical branch must not assign a LITERAL reason string."""
    src = open(os.path.join(_root, "execution", "exit_engine.py"),
               encoding="utf-8").read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        t = node.test
        if not (isinstance(t, ast.Name) and t.id == "_vert_close"):
            continue
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Assign)
                    and any(isinstance(x, ast.Attribute) and x.attr == "exit_reason"
                            for x in sub.targets)):
                return not isinstance(sub.value, ast.Constant)
    return False


guard("W6 the vertical exit label is derived from the constant, not a literal", _w6)


def _w7():
    src = open(os.path.join(_root, "execution", "exit_engine.py"),
               encoding="utf-8").read()
    n = src.count('exit_reason = "hard_close_15:45_ET"')
    _w7.n = n
    return n == 5 and tuple(config.HARD_CLOSE_ET) == (15, 45)


guard("W7 SCOPE: exactly one site moved — the other five still read 15:45",
      _w7, lambda: "%d site(s), HARD_CLOSE_ET=%s" % (getattr(_w7, "n", -1),
                                                     tuple(config.HARD_CLOSE_ET)))

print()
if FAILED:
    print(f"RED — {len(FAILED)} of {len(RAN)}: " + ", ".join(FAILED))
    sys.exit(1)
print(f"GREEN — {len(RAN)} checks")
sys.exit(0)
