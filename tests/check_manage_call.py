#!/usr/bin/env python3
"""
tests/check_manage_call.py  v1.1

v1.1  2026-09-20  OTV4TEST r71 (LATE.1) — M3c RE-POINTED, M3d ADDED, BOTH
      MINUTES DERIVED. Until r71 the hard close and the vertical hold were THE
      SAME MINUTE, so an assertion written against 15:45 could not say which of
      the two it was pinning — and M3c ("both flattened") went red the moment
      the operator separated them. RE-POINTED AT THE NEW CONTRACT, NOT LOOSENED
      (r33/r43/r64): M3c now pins THE GAP — at `HARD_CLOSE_ET` the debit goes
      and the credit STAYS — and M3d pins the hold itself.
      🔑 BOTH READ FROM `config`, PLUS AN ASSERT THAT THE HOLD IS AFTER THE
      CLOSE, so one literal can never again stand for two different facts.
      ⚠️ THE EVIDENCE IT WAS ALWAYS MEANT TO BE DERIVED WAS IN THE FILE: this
      module has carried `import config` UNUSED since v1.0.
v1.0  2026-08-24  OTV4 r99 (ea6d773, MAINLINE — inherited at the fork) —
      born RED at df44518 (r98) on M1, M3, M4. That commit is the one that
      introduced "verticals hold to 15:45"; r71 is what supersedes it.

r99 — THE MANAGE BRANCH MUST BE CALLABLE, AND THE FLATTEN MUST HOLD VERTICALS.

Born RED at df44518 (r98) on M1, M3, M4. Plain script (WA 36).

  M1  every `pos_mgr.<method>(kw=...)` call in main.py passes ONLY keywords the
      PositionManager method actually accepts (the `ms=None` TypeError class —
      r65 renamed the retired label kwarg at the call and deleted it from the signature; every
      tick with an open position raised into the loop catch-all)
  M2  the call is exercised for real: a stub PositionManager receives the
      exact kwargs main passes and does not raise
  M3  flatten_all HOLDS a credit vertical before VERTICAL_HOLD_TO_ET and
      FLATTENS it after (executed against a patched clock). r71 — the hard
      close and the hold are no longer the same minute, so M3c pins the gap
      (debit out, credit held) and M3d pins the hold itself.
  M4  main.py's hard-close branch runs a manage pass while verticals are held

Run:  python3 tests/check_manage_call.py
"""
from __future__ import annotations
import ast, os, sys, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILURES: list = []

def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)

import execution.position_manager as pm
src = open(os.path.join(ROOT, "main.py")).read()
tree = ast.parse(src)

# M1 — kwargs at every pos_mgr.<method>() call vs the real signature
bad = []; seen = 0
for node in ast.walk(tree):
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "pos_mgr"):
        meth = getattr(pm.PositionManager, node.func.attr, None)
        if meth is None:
            bad.append(f"{node.func.attr}: no such method"); continue
        params = inspect.signature(meth).parameters
        accepts_kw = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
        seen += 1
        for kw in node.keywords:
            if kw.arg is not None and kw.arg not in params and not accepts_kw:
                bad.append(f"line {node.lineno} {node.func.attr}({kw.arg}=...)")
check("M1 every pos_mgr.* call in main.py matches its signature", not bad, "; ".join(bad) or f"{seen} calls")

# M2 — replay main's manage kwargs against the real method on a stub instance
calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
         and n.func.attr == "manage_open_position"]
ok = bool(calls)
for n in calls:
    kws = {k.arg: None for k in n.keywords}
    try:
        inspect.signature(pm.PositionManager.manage_open_position).bind(object(), **kws)
    except TypeError as e:
        ok = False; print("     ", e)
check("M2 manage_open_position kwargs bind against the real signature", ok, f"{len(calls)} call(s)")

# M3 — flatten_all holds a credit vertical before 15:45, flattens after
import config
from datetime import datetime
from utils.time_utils import ET
booked = []
class _TL:
    def get_open_trades(self): return []
class _PM(pm.PositionManager):
    def __init__(self):
        self.paper_trading = True; self._trade_logger = _TL(); self._open_records = []
    def _fetch_current_premium(self, record, chain=None): return 0.10
    def _execute_exit(self, record, decision, premium):
        booked.append(record["trade_id"]); return True
vert = {"trade_id": "VERT0001", "strategy": "SweepCreditSpread", "setup_type": "sweep_credit_call",
        "is_condor_leg": 1, "entry_premium": 0.30, "contracts": 1}
deb  = {"trade_id": "DEBT0001", "strategy": "ORBStrategy", "setup_type": "orb", "entry_premium": 0.50, "contracts": 1}
real_now = pm.now_et if hasattr(pm, "now_et") else None
import utils.time_utils as tu
_orig = tu.now_et
try:
    tu.now_et = lambda: datetime(2026, 8, 24, 15, 41, tzinfo=ET)
    p = _PM(); p._open_records = [dict(vert), dict(deb)]; booked.clear()
    failed = p.flatten_all("hard_close_15:45_ET")
    check("M3a 15:41 — debit flattened, vertical HELD", booked == ["DEBT0001"] and not failed, f"booked={booked} failed={failed}")
    check("M3b 15:41 — held vertical stays in open records", any(r["trade_id"] == "VERT0001" for r in p._open_records))
    # 🔴 r71 (LATE.1) — M3c USED TO READ "15:45 — both flattened", AND IT WENT
    # RED ON THE CREDIT-WINDOW DELIVERY. That is the gate working: until r71 the
    # hard close and the vertical hold were THE SAME MINUTE, so a check written
    # against 15:45 could not tell which of the two it was actually pinning.
    # The operator's 2026-09-20 ruling separates them — credits hold to 15:50 —
    # so the check is RE-POINTED AT THE NEW CONTRACT rather than loosened
    # (r33/r43/r64): 15:45 now asserts the debit goes and the credit STAYS, and
    # a new M3d asserts the credit goes at the hold time. Both minutes are
    # DERIVED from config so the same ambiguity cannot come back.
    hold_h, hold_m = config.VERTICAL_HOLD_TO_ET
    hard_h, hard_m = config.HARD_CLOSE_ET
    assert (hard_h, hard_m) < (hold_h, hold_m), "the hold must be AFTER the hard close"
    tu.now_et = lambda: datetime(2026, 8, 24, hard_h, hard_m, tzinfo=ET)
    p = _PM(); p._open_records = [dict(vert), dict(deb)]; booked.clear()
    p.flatten_all("hard_close_15:45_ET")
    check(f"M3c {hard_h:02d}:{hard_m:02d} hard close — debit flattened, credit STILL HELD",
          booked == ["DEBT0001"] and any(r["trade_id"] == "VERT0001" for r in p._open_records),
          f"booked={booked}")
    tu.now_et = lambda: datetime(2026, 8, 24, hold_h, hold_m, tzinfo=ET)
    p = _PM(); p._open_records = [dict(vert), dict(deb)]; booked.clear()
    p.flatten_all("hard_close_15:45_ET")
    check(f"M3d {hold_h:02d}:{hold_m:02d} vertical hold — both flattened",
          sorted(booked) == ["DEBT0001", "VERT0001"], f"booked={booked}")
finally:
    tu.now_et = _orig

# M4 — the hard-close branch in main_loop runs a manage pass for held verticals
loop = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main_loop")
hc = None
for n in ast.walk(loop):
    if isinstance(n, ast.If) and "is_hard_close_time" in ast.unparse(n.test):
        hc = ast.unparse(n); break
check("M4 hard-close branch manages held verticals before 15:45",
      hc is not None and "manage_open_position" in hc and "_vertical_close_due" in hc)

print(f"\n{'PASS' if not FAILURES else 'FAIL'}: {len(FAILURES)} problem(s) {FAILURES}")
sys.exit(1 if FAILURES else 0)
