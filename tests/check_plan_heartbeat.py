#!/usr/bin/env python3
"""
tests/check_plan_heartbeat.py  v1.0
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

print(f"\n{'PASS' if not FAIL else 'FAIL'}: {len(FAIL)} problem(s) {FAIL}")
sys.exit(1 if FAIL else 0)
