#!/usr/bin/env python3
"""
tests/check_plan_heartbeat.py  v1.1
v1.1  2026-09-21  OTV4TEST r84 — H6/H7/H8. Born red 3 of 9 at
      674c8d5, H6 naming all 13 ungated call sites.
v1.0  2026-09-21  OTV4TEST r83 — born RED at 0e4c8f1.

🔴 THE PLANS PANEL WAS MEASURING PUNCTUATION. It asked "is this plan stale?"
by comparing the newest `plan_tick` row against a 300-second cut. r41 made
those rows EDGE-TRIGGERED by the operator's own ruling, so a plan behaving
perfectly writes nothing and turns "stale" five minutes later. MEASURED
2026-09-21 14:44: **16 of 18 rows flagged ⚠️ STALE and all 16 were correct**;
the only two that read "fresh" were the two whose reason text embeds live
prices, so every tick produced a new string.

Operator: *"I wanna see on that page if my strategies are actively evaluating
the feed. If they're not then say that, and if they are tell me what they're
looking at."* And: *"I don't think stale needs to be the same thing as window
closed. Report stale if it really is stale and report window closed if that's
the reason."*

  H1  UPSERT, NOT APPEND — the table cannot grow (r41's ruling is untouched)
  H2  a plan that RAN reads EVALUATING
  H3  CLASS: the gate is CARRIED from BOTH mechanisms, never parsed from prose
  H4  a window-closed plan reads WINDOW CLOSED and NOT stale
  H5  a plan in the admission table that never heartbeat is surfaced

Run:  python3 tests/check_plan_heartbeat.py
"""
from __future__ import annotations
import io as _io, os, sys, tempfile, time, contextlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_s = tempfile.mkdtemp(prefix="check_plan_heartbeat.")
os.environ.setdefault("OT_TRADES_DB", os.path.join(_s, "trades.db"))
os.environ.setdefault("OT_DERIVED_DB", os.path.join(_s, "derived_store.db"))

FAIL: list = []
def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAIL.append(name.split()[0])

import strategy.plan as P

# ⚠️ H0 IS A GUARD, NOT A CHECK (the r72/V0 pattern). At a base without r83
# this file would otherwise die on an AttributeError traceback — "born red" in
# the sense that it exits non-zero, but naming nothing. A gate that cannot say
# WHAT is missing teaches the reader to skim the red (§36).
_missing = [n for n in ("_write_heartbeats", "ensure_tables", "_SKIP_GATE", "REGISTRY")
            if not hasattr(P, n)]
check("H0 strategy.plan exposes the heartbeat machinery",
      not _missing, f"missing={_missing} — r83 has not landed in this tree")
if _missing:
    print(f"\n{'PASS' if not FAIL else 'FAIL'}: {len(FAIL)} problem(s) {FAIL}")
    sys.exit(1)


class _FakePlan:
    def __init__(self, verdict, why, wrote, gate=""):
        self._v, self._w, self._wrote = verdict, why, wrote
        if gate:
            self._last_gate = gate
    def last(self):
        return (1, self._v, self._w)
    def wrote_this_tick(self):
        return self._wrote

from data.derived_store import get_derived_store
store = get_derived_store()
# the same helper the bot uses — never a hand-rolled CREATE, or the fixture
# could pass against a schema production does not have (§0.4)
P.ensure_tables(store)

P.REGISTRY.clear()
P.REGISTRY["Alpha"] = _FakePlan("HOLD", "reading the tape", True)
P.REGISTRY["Beta"]  = _FakePlan("INACTIVE", "inactive — window: Beta is outside 09:35-11:30 ET", False)
P._SKIP_GATE.clear(); P._SKIP_GATE["Beta"] = "window"
P._ASKED.clear()

P._write_heartbeats(store, "QQQ", 7, time.time())
P._write_heartbeats(store, "QQQ", 8, time.time())      # twice: UPSERT, not append

rows = list(store.conn.execute(
    "SELECT plan, state, gate, verdict FROM plan_heartbeat WHERE symbol='QQQ' ORDER BY plan"))
n_alpha = list(store.conn.execute(
    "SELECT COUNT(*) FROM plan_heartbeat WHERE symbol='QQQ' AND plan='Alpha'"))[0][0]

check("H1 UPSERT, not append — two ticks leave ONE row per plan",
      n_alpha == 1, f"Alpha rows={n_alpha} — r41's ruling governs the LEDGER; "
                    f"this is current state and must not grow")

_by = {r[0]: r for r in rows}
check("H2 a plan that RAN reads EVALUATING",
      _by.get("Alpha", (None, None))[1] == "EVALUATING",
      f"Alpha={_by.get('Alpha')}")

# 🔑 H3 IS THE CLASS CHECK AND IT FAILED TWICE IN DEVELOPMENT. The gate reaches
# the board by TWO different mechanisms — `_report_block` for a plan that ran
# and refused itself, `_SKIP_GATE` for one that was never asked — and the first
# two cuts read only one, so every window-closed plan came out a bare HELD.
check("H3 CLASS: the gate is CARRIED from the not-asked path, not parsed",
      _by.get("Beta", (None, None, None))[2] == "window",
      f"Beta gate={_by.get('Beta', (None,None,''))[2]!r} — parsing it back out "
      f"of 'inactive — window: ...' is what broke twice")

# H4/H5 drive the REAL panel and read what the operator would read.
import query
buf = _io.StringIO()
with contextlib.redirect_stdout(buf):
    try:
        query.show_decisions(store.conn)
    except Exception as e:                                      # noqa: BLE001
        print(f"panel raised: {e}")
out = buf.getvalue()
check("H4 a window-closed plan reads WINDOW CLOSED and never STALE",
      ("WINDOW CLOSED" in out) and ("STALE" not in out),
      f"window_closed={'WINDOW CLOSED' in out} stale_present={'STALE' in out}")

check("H5 a plan in the admission table that never heartbeat is SURFACED",
      "NOT RUNNING" in out,
      "a plan that is never constructed cannot heartbeat; asking the heartbeat "
      "who exists would hide exactly the failure this panel is for")

# ── H6 — THE CLASS: EVERY SKIP SITE PASSES A GATE (r84) ───────────────────
# 🔴 MEASURED 2026-09-21: 15 of 16 `_plan_skip`/`_plan_skip_all` calls in
# main.py passed NO gate, so every refusal that was not the clock reached the
# board unlabelled and rendered as a bare "HELD" — including the butterflies'
# one-per-session quota, which the operator asked to see named: *"shouldn't
# the plan say something about that? Something like quota hit."*
# ⚠️ `_plan_skip`'s OWN DOCSTRING ALREADY WARNED ABOUT THIS — "recovering a
# gate by parsing the reason sentence is how that rule would quietly stop
# working the first time someone reworded a message" — and 15 call sites
# ignored it anyway. A rule stated in prose and unenforced decays; this is the
# enforcement.
import ast as _ast
_src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "main.py"), encoding="utf-8").read()
_ungated = []
for node in _ast.walk(_ast.parse(_src)):
    if (isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name)
            and node.func.id in ("_plan_skip", "_plan_skip_all")):
        if not any(k.arg == "gate" for k in node.keywords):
            _ungated.append(node.lineno)
check("H6 CLASS: every _plan_skip call site passes a gate",
      not _ungated,
      f"ungated at main.py lines {_ungated} — an unlabelled refusal renders "
      f"as a bare HELD and the board cannot name why")

# ── H7 — THE PLAN IS BUILT ON CONSTRUCTION, NOT ON FIRST USE (r84) ────────
# 🔴 Breakout built its plan lazily in `_plan_()`, so outside 09:35-11:30
# nothing called `prepare()`, `BreakoutPlan()` was never constructed, and it
# entered NO registry at all: no heartbeat, absent from the board, and nothing
# could tell "not yet constructed" from "crashed". THIS IS r77 IN A DIFFERENT
# COSTUME — there a lazy IMPORT let check_imports pass green on a strategy
# raising every tick; here a lazy CONSTRUCTION hides the plan from every
# registry-based check.
_cases = [("Breakout", "strategy.breakout", "Breakout"),
          ("VOLT", "strategy.volt_strategy", "VoltStrategy")]
_lazy = []
for want, mod, cls in _cases:
    P.REGISTRY.clear()
    try:
        m = __import__(mod, fromlist=[cls])
        getattr(m, cls)()
        if want not in P.REGISTRY:
            _lazy.append(f"{cls} -> {sorted(P.REGISTRY)}")
    except Exception as e:                                      # noqa: BLE001
        _lazy.append(f"{cls} raised {type(e).__name__}: {e}")
check("H7 CLASS: constructing a strategy registers its plan immediately",
      not _lazy,
      f"lazy={_lazy} — a plan that registers only on first use is invisible "
      f"to every board and every checker until its window opens")

# ── H8 — the gate vocabulary reaches the reader ──────────────────────────
import inspect as _insp
_qsrc = _insp.getsource(query.show_decisions)
check("H8 the board names the session quota rather than a bare HELD",
      '"tries_per_session": "QUOTA HIT"' in _qsrc,
      "expected a tries_per_session -> QUOTA HIT mapping in the panel")

print(f"\n{'PASS' if not FAIL else 'FAIL'}: {len(FAIL)} problem(s) {FAIL}")
sys.exit(1 if FAIL else 0)
