#!/usr/bin/env python3
"""
tests/check_levels_in_play.py  v1.0
v1.0  2026-09-22  OTV4TEST r103 — born RED at 4a7da4f, where `levels_in_play`
      does not exist and P0 NAMES that rather than dying on a traceback.

r103 — THE RAILS MAY NOT TAKE A HELD EXTREME'S SLOT.

🔴 SETTLED THREE TIMES AT THE PRODUCER, NEVER ONCE AT THE CONSUMER. r15 removed
`_tines()` from `_sources()`; r19 stopped any pool flagged `moving` reaching
`level_ledger` at all, after 22 simultaneously-live "1h upper tine" rows
spanning 5.79 points were found in it; r33 gave every level-trading plan ONE
accessor. `board()` has been correct since r19 and says so in its own
docstring: *"THE FORK IS A SECOND PRODUCT, NOT A LEVEL IN THIS LIST ... NEVER
merged into above/below (r19: co-inform, do not conjoin)"*.

🔴 AND r33 WROTE THE CONJUNCTION ITSELF. The same revision titled "THE FORK
BESIDE IT AS AN OR LEVEL" added `levels = levels + tines` ONE LINE ABOVE the
`[:LEVELS_EACH_SIDE]` slice — so a rail nearer to spot claimed a slot and the
furthest-out held extreme fell off the board. Every gate stayed green, because
every gate asserted what `board()` RETURNS and none asserted what a CONSUMER
does with it. §23 — fix every reader, not just the writer.

🔑 THE TWO ARE DIFFERENT KINDS OF THING. Operator 2026-09-22: *"The pitchfork is
a co-informer and does not live in the liquidity level levels ... it's a moving
target it has to be a separate artifact"*, and *"It's not a LIQUIDITY level.
It's just a respected level."* A held extreme is a fixed price with resting
stops beyond it — that pool is what a sweep RAIDS. A rail holds no pool.

⚠️ THE RAILS ARE NOT WITHDRAWN, AND P2 PINS THAT. Asked directly whether they
should leave this plan, the operator ruled: *"The sweep still works with the
pitchfork, because the channel is respected."* PLUS, not competing.

  P0  the machinery exists                      (guard, not a check)
  P1  rails nearer than the held extremes DO NOT displace them
  P2  ...and the rails are still in play        (not a withdrawal)
  P3  held and rail counts stay separable
  P4  fewer than the limit is an answer, never padded
  P5  the cap binds the held extremes, and ONLY them
  P6  the regression line r33 wrote is absent from the plan

Run:  venv/bin/python tests/check_levels_in_play.py
"""
from __future__ import annotations

import glob
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# ⚠️ The lander runs CHECKs under system `python3`; the SDK lives in the venv.
for _sp in glob.glob(os.path.join(ROOT, "venv", "lib", "python*", "site-packages")):
    if _sp not in sys.path:
        sys.path.insert(1, _sp)
_s = tempfile.mkdtemp(prefix="check_levels_in_play.")
os.environ.setdefault("OT_TRADES_DB", os.path.join(_s, "trades.db"))
os.environ.setdefault("OT_DERIVED_DB", os.path.join(_s, "derived_store.db"))

FAIL: list = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAIL.append(name.split()[0])


try:
    import strategy.sweep_plan as SP
    _have = hasattr(SP, "levels_in_play")
except Exception as _e:                                          # noqa: BLE001
    SP, _have = None, False
check("P0 sweep_plan exposes levels_in_play", _have,
      "r103 has not landed in this tree")
if not _have:
    print(f"\nRED — {len(FAIL)} failed: {FAIL}")
    sys.exit(1)

PX = 744.5
# Held extremes, ALL further from spot than the rails — the shape that loses a
# level under the old merge. `d`/`e` below, `a`/`b`/`c` above.
HELD = [{"kind": "resistance", "price": 750.0, "level_id": "a"},
        {"kind": "resistance", "price": 752.0, "level_id": "b"},
        {"kind": "resistance", "price": 755.0, "level_id": "c"},
        {"kind": "support",    "price": 740.0, "level_id": "d"},
        {"kind": "support",    "price": 735.0, "level_id": "e"}]
# Rails INSIDE all of them.
RAILS = [{"kind": "resistance", "price": 746.0, "level_id": "t1"},
         {"kind": "support",    "price": 743.0, "level_id": "t2"}]

above, below, held_up, held_dn = SP.levels_in_play(HELD, RAILS, PX)
_ids_a = [x["level_id"] for x in above]
_ids_b = [x["level_id"] for x in below]

# ── P1 — THE DEFECT ───────────────────────────────────────────────────────
check("P1 a nearer rail does NOT evict a held extreme",
      {"a", "b", "c"} <= set(_ids_a) and {"d", "e"} <= set(_ids_b),
      f"above={_ids_a} below={_ids_b}")

# ── P2 — AND THE RAILS ARE STILL THERE ────────────────────────────────────
# ⚠️ A fix that quietly dropped the rails would satisfy P1 and BREAK the plan.
check("P2 the rails remain in play (not withdrawn)",
      "t1" in _ids_a and "t2" in _ids_b,
      "operator: 'The sweep still works with the pitchfork'")

# ── P3 — THE COUNTS STAY SEPARABLE ────────────────────────────────────────
# 🔴 One combined count makes a board of three rails read identically to three
# held extremes — the conflation r19 exists to prevent.
check("P3 held counts exclude the rails", held_up == 3 and held_dn == 2,
      f"held_up={held_up} held_dn={held_dn}")
check("P3b and the plan declares them as distinct checks",
      {"held_above", "held_below", "rails_in_play"} <= set(SP.SweepPlan.PLAN_CHECKS))

# ── P4 — FEWER THAN THE LIMIT IS AN ANSWER ────────────────────────────────
# ⚠️ Operator: "Three would be ideal ... if there's less we can accept that
# too." Never padded, never an error.
_a4, _b4, _h4u, _h4d = SP.levels_in_play(
    [{"kind": "resistance", "price": 750.0, "level_id": "only"}], [], PX)
check("P4 fewer than the limit is an answer, never padded",
      _h4u == 1 and _h4d == 0 and len(_a4) == 1 and not _b4,
      f"above={len(_a4)} below={len(_b4)}")

# ── P5 — THE CAP BINDS THE HELD EXTREMES, AND ONLY THEM ───────────────────
_many_held = [{"kind": "resistance", "price": 750.0 + i, "level_id": f"h{i}"}
              for i in range(8)]
_many_rail = [{"kind": "resistance", "price": 745.0 + i * 0.1, "level_id": f"r{i}"}
              for i in range(4)]
_a5, _b5, _h5u, _h5d = SP.levels_in_play(_many_held, _many_rail, PX, limit=3)
check("P5 the limit caps held extremes at 3", _h5u == 3, f"held_up={_h5u}")
check("P5b and does NOT cap the rails", len(_a5) - _h5u == 4,
      f"{len(_a5) - _h5u} rails survived")
# ⚠️ AND THE THREE KEPT ARE THE NEAREST — r29's walk is newest-first and each
# older rung further out, so nearest IS newest. Keeping an arbitrary three
# would make the board random, which is the operator's stated reason for the
# ordering existing at all.
check("P5c the three kept are the NEAREST held extremes",
      [x["level_id"] for x in _a5[:3]] == ["h0", "h1", "h2"],
      str([x["level_id"] for x in _a5[:3]]))

# ── P6 — THE REGRESSION IS GONE STRUCTURALLY, NOT TEXTUALLY ───────────────
# 🔴 THE FIRST CUT OF THIS CHECK GREPPED FOR THE LITERAL `levels = levels +
# tines` AND WENT RED ON ITS OWN DOCSTRING — the paragraph above that explains
# the removal necessarily names the line. That is §20 precisely, the trap
# check_age_gate_gone A6 already records: assert on the STRUCTURE, never on
# source text a changelog must also contain.
# 🔑 So this walks the AST for a real assignment whose value adds a `tines`-ish
# name into a `levels`-ish one. Strings and comments are invisible to it.
import ast as _ast
_tree = _ast.parse(open(os.path.join(ROOT, "strategy", "sweep_plan.py"),
                        encoding="utf-8").read())
_merges = []
for _n in _ast.walk(_tree):
    if not isinstance(_n, (_ast.Assign, _ast.AugAssign)):
        continue
    _val = _n.value
    _names = {x.id for x in _ast.walk(_val) if isinstance(x, _ast.Name)}
    if isinstance(_val, _ast.BinOp) and isinstance(_val.op, _ast.Add) \
            and "tines" in _names and "levels" in _names:
        _merges.append(_n.lineno)
    if isinstance(_n, _ast.AugAssign) and isinstance(_n.op, _ast.Add) \
            and isinstance(_n.target, _ast.Name) and _n.target.id == "levels" \
            and "tines" in _names:
        _merges.append(_n.lineno)
check("P6 no statement merges tines into the level list", not _merges,
      f"lines {_merges}" if _merges else "AST-checked, not grepped")


# ══ R — THE RAILS: A DEAD READER, AND A SLOPE NOBODY WALKED FORWARD ═══════
import ast as _a2
import types as _ty

# ── R1 — THE DEAD READER (r103) ───────────────────────────────────────────
# 🔴 `anchors.nearest_tine` queried `level_ledger` for `fork1h/%` — the table
# r19's clause (1) GUARANTEES is empty, because `_sources()` skips any pool
# flagged `moving`. It returned None on every row ever written: MEASURED
# 2026-09-22, SweepCreditSpread.anchor_tine_to_level banked 639 rows, all None.
# ⚠️ A GATE SAT BESIDE IT AGREEING — check_level_rejection F1 asserts the ledger
# holds ZERO rail rows, correctly, while this reader queried it expecting rows.
# Both passed. §23: fix every reader, not just the writer.
_asrc = open(os.path.join(ROOT, "derived", "anchors.py"), encoding="utf-8").read()
_atree = _a2.parse(_asrc)
_fn = next((n for n in _a2.walk(_atree)
            if isinstance(n, _a2.FunctionDef) and n.name == "nearest_tine"), None)
check("R1 nearest_tine exists", _fn is not None)
_body = _a2.unparse(_fn) if _fn else ""
check("R1b and it no longer reads level_ledger",
      "level_ledger" not in _body.split('"""')[-1],
      "r19 guarantees that table holds no rails")

# ── R2 — AND IT RETURNS A NUMBER WHEN A FORK IS LIVE ──────────────────────
# ⚠️ ABSENCE OF THE OLD QUERY IS NOT PRESENCE OF AN ANSWER. R1b would pass
# against a function that returned None unconditionally.
from derived.levels import LevelEngine as _LE                    # noqa: E402
import derived.registry as _REG                                  # noqa: E402


class _Fork:
    slope = 0.6
    def upper_at(self, i):  return 748.0
    def median_at(self, i): return 742.0
    def lower_at(self, i):  return 736.0


_eng = _LE.__new__(_LE)
_eng._forks = _ty.SimpleNamespace(last_forks={"1h": _Fork()}, last_idx={"1h": 10})
_eng.symbol = "QQQ"; _eng._store = object(); _eng._fork_key = lambda: "k"
_keep_le = getattr(_REG, "level_engine", None)
_REG.level_engine = lambda: _eng
try:
    from derived import anchors as _A2
    _nt = _A2.nearest_tine(744.0)
    check("R2 nearest_tine returns a real distance under a live fork",
          isinstance(_nt, float) and abs(_nt) > 0, f"{_nt}")

    # ── R3 — EVERY ANCHOR FIELD SURVIVES float() ──────────────────────────
    # 🔴 r99's DEFECT IN A NEW COSTUME. `stamp()` does `float(v)` and swallows
    # the failure, and `plan_check` has no text column — so a categorical like
    # "built" or "fork1h/upper" would store None on EVERY row. WHICH rail is
    # encoded as a documented code (+1 upper / 0 median / -1 lower) instead.
    # ⚠️ GUARDED: at a base without r103 `rail_context` does not exist, and a
    # checker that dies on AttributeError never delivers the verdict it was
    # written for — the failure this whole revision is about.
    _ctx = getattr(_A2, "rail_context", lambda _p: None)(744.0)
    check("R3pre anchors exposes rail_context", isinstance(_ctx, dict),
          "r103 has not landed" if _ctx is None else "")
    _ctx = _ctx or {}
    _bad = [k for k, v in _ctx.items() if v is not None and not isinstance(v, (int, float))]
    check("R3 every rail anchor is numeric and survives stamp()", not _bad,
          f"non-numeric: {_bad or 'none'}")
    check("R3b and it names WHICH rail as a code, not a string",
          _ctx.get("rail_above_which") == 1.0, f"{_ctx.get('rail_above_which')}")

    # ── R4 — THE PROJECTION WALKS FORWARD ─────────────────────────────────
    # 🔑 The operator, repeatedly: "the rails belong in a projection map so that
    # you can go outward in time because you already know the slope". r19 built
    # `minutes_back`; nothing ever passed it a NEGATIVE value.
    _rp = getattr(_eng, "rail_projection", None)
    check("R4pre the engine exposes rail_projection", _rp is not None,
          "r103 has not landed" if _rp is None else "")
    if _rp is None:
        print(f"\nRED — {len(FAIL)} failed: {FAIL}")
        sys.exit(1)
    _pr = _eng.rail_projection(744.0)
    _h = _pr["horizons"]
    _u0, _u60 = _h[0]["fork1h/upper"], _h[60]["fork1h/upper"]
    check("R4 the projection moves the rail along its own slope",
          _u60 > _u0 and abs((_u60 - _u0) - 0.6) < 1e-6,
          f"t0={_u0} t+60={_u60} slope={_pr['slope_per_bar']}")
    check("R4b and it carries the convergence, not just the position",
          _pr["below"]["bars_to_contact"] is not None,
          f"bars_to_contact={_pr['below']['bars_to_contact']}")

    # ── R5 — THE TINE RULE SURVIVES THE PROJECTION ────────────────────────
    # 🔴 Operator: "a top rail has to be resistance, and a bottom rail has to be
    # support and never the inverse." Price ABOVE the top rail must not acquire
    # a floor at it.
    _above_top = _eng.rail_projection(750.0)
    check("R5 price above the top rail does NOT get it as support",
          _above_top["above"] is None
          and (_above_top["below"] or {}).get("provenance") != "fork1h/upper",
          f"above={_above_top['above']} below={(_above_top['below'] or {}).get('provenance')}")

    # ── R6 — A DEAD FORK IS AN EXPLICIT ABSENCE ───────────────────────────
    _eng._forks = _ty.SimpleNamespace(last_forks={}, last_idx={})
    _dead = _eng.rail_projection(744.0)
    check("R6 a dead fork yields an explicit absence, never a stale rail",
          _dead["fork"] == "absent" and _dead["above"] is None
          and _dead["below"] is None and not _dead["horizons"],
          "r19: the projection dies with the fork that graphed it")
finally:
    if _keep_le is not None:
        _REG.level_engine = _keep_le


# ══ E — END TO END: THE ANCHORS REACH THE ROW ═════════════════════════════
# 🔴 THIS IS THE ONE THAT WOULD HAVE CAUGHT THE ORIGINAL DEFECT. Every check
# above can pass while the values never reach a plan row — which is exactly
# what happened: `anchor_tine_to_level` banked 639 rows of None while the
# board, the tine rule and the separation were all correct. So this drives the
# REAL strategy through a REAL store and reads what actually landed (§21).
import time as _t2
import tempfile as _tf2

try:
    import strategy.sweep_credit_spread as _SW
    import strategy.sweep_plan as _SWP
    from data.derived_store import DerivedStore as _DS
    from strategy import plan as _PL

    _ds = _DS(path=os.path.join(_tf2.mkdtemp(), "derived.db"))
    _SWP._symbol_of = lambda: "TST"
    _SW._symbol_of = lambda: "TST"
    # ⚠️ `bind_store` CREATES plan_check. Without it the harness dies on "no
    # such table" — which the E0 guard reported rather than passing green.
    if hasattr(_PL, "bind_store"):
        _PL.bind_store(_ds)
    _S = _SW.SweepCreditSpreadStrategy()
    _S.plan._store = _ds
    _S.planner.symbol = "TST"
    _now2 = _t2.time()

    for _p, _k, _pv in ((96.0, "support", "ny"), (95.0, "support", "london"),
                        (94.0, "support", "asia"), (101.0, "resistance", "prev_day")):
        _ds.upsert_level((f"TST:{_pv}:{_p:.2f}", "TST", _p, _k, _pv, "session",
                          _now2 - 3600, 0, None, 0, None, None, 1))
    _ds.insert_level_event(("TST", "TST:ny:96.00", "2026-09-09 10:31:00", _now2 - 30,
                            "REJECTED", 96.0, "support", "ny", 0.0018, "shallow", 1, 96.1))

    class _Ct:
        def __init__(self, k, bid, ask):
            self.strike, self.bid, self.ask = float(k), float(bid), float(ask)
            self.mark = (bid + ask) / 2
            self.delta, self.gamma, self.theta = 0.2, 0.01, -0.03
            self.expiry, self.open_interest, self.symbol = "x", 100, f"P{k}"

    class _Chn:
        def __init__(self, puts): self.puts, self.calls = list(puts), []

    # rails INSIDE the held extremes — the eviction shape
    _eng2 = _LE.__new__(_LE)

    class _F2:
        slope = 0.6
        def upper_at(self, i):  return 99.0
        def median_at(self, i): return 96.4
        def lower_at(self, i):  return 95.8

    _eng2._forks = _ty.SimpleNamespace(last_forks={"1h": _F2()}, last_idx={"1h": 10})
    _eng2.symbol = "TST"; _eng2._store = _ds; _eng2._fork_key = lambda: "k1"
    _keep2 = getattr(_REG, "level_engine", None)
    _REG.level_engine = lambda: _eng2
    try:
        _PL.begin_tick(101.0)
        _S.generate_signal(chain=_Chn([_Ct(97.5, 2.40, 2.50), _Ct(95, 1.40, 1.44),
                                       _Ct(92.5, 0.08, 0.10), _Ct(90, 0.03, 0.05),
                                       _Ct(87.5, 0.02, 0.03)]),
                           price_now=96.6, now_et="10:32", atr_pct=0.08,
                           orb_high=99.5, orb_low=97.5)
        _banked = dict(_ds.conn.execute(
            "SELECT check_name, value FROM plan_check "
            "WHERE strategy='SweepCreditSpread' AND check_name LIKE 'anchor_rail%'"))
        check("E1 the rail anchors reach the plan row", len(_banked) >= 8,
              f"{len(_banked)} banked")
        # ⚠️ PRESENCE IS NOT A VALUE. 639 rows of None were "present" too.
        _real = {k: v for k, v in _banked.items() if v is not None}
        check("E2 and they carry REAL numbers, not None",
              len(_real) >= 4, str(sorted(_real.items())[:4]))
        check("E2b including the DISTANCE to the correctly-oriented rail",
              _banked.get("anchor_rail_above_dist_pts") is not None
              and _banked.get("anchor_rail_below_dist_pts") is not None,
              f"above={_banked.get('anchor_rail_above_dist_pts')} "
              f"below={_banked.get('anchor_rail_below_dist_pts')}")
        _counts = dict(_ds.conn.execute(
            "SELECT check_name, value FROM plan_check WHERE strategy='SweepCreditSpread' "
            "AND check_name IN ('held_below','rails_in_play')"))
        check("E3 held and rail counts are banked SEPARABLY",
              _counts.get("held_below") == 3 and (_counts.get("rails_in_play") or 0) >= 1,
              str(_counts))
    finally:
        if _keep2 is not None:
            _REG.level_engine = _keep2
except Exception as _ee:                                         # noqa: BLE001
    # ⚠️ A harness failure must be REPORTED, never swallowed into a green run.
    check("E0 the end-to-end harness ran", False, f"{type(_ee).__name__}: {_ee}")

if FAIL:
    print(f"\nRED — {len(FAIL)} failed: {', '.join(FAIL)}")
    sys.exit(1)
print("\nGREEN — held extremes claim their slots; the rails join beside them")
sys.exit(0)
