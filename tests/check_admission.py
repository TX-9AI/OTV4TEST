#!/usr/bin/env python3
"""
tests/check_admission.py  v1.3
THE ADMISSION TABLE, DRIVEN EXHAUSTIVELY (OTV4TEST r35).

v1.3  2026-09-21  OTV4TEST r72 — A's restated SPEC gains VOLT at 09:35-11:30,
      from the operator's request rather than from `rules()`. 🔑 THIS CHECK
      WENT RED ON r72 AND THAT IS IT WORKING: it restates the table INSIDE the
      checker by design (r35, §0.4) so a fixture cannot agree with the belief
      under test, which means a NEW STRATEGY MUST make it red. Re-pointed at
      the new contract, never loosened (r33/r43/r64).
v1.2  2026-09-20  OTV4TEST r71 — A's restated SPEC moves SWEEP and TCS to
      15:40, from the operator's 2026-09-20 ruling rather than from `rules()`.
      🔑 THIS CHECK WENT RED ON r71 AND THAT IS IT WORKING. It restates the
      window table INSIDE the checker by design (r35, §0.4) so a fixture cannot
      agree with the belief under test — so a superseded ruling MUST turn it
      red. RE-POINTED AT THE NEW CONTRACT, NOT LOOSENED (r33/r43/r64).
v1.1  2026-09-18  OTV4TEST r51 — A0's restated SPEC gains Breakout, from the
      operator's 2026-09-18 ruling rather than from `rules()`.
v1.0  2026-09-17  OTV4TEST r35 — born red at r34 (5ef833e): `risk/admission.py`
      does not exist there, and neither does any single place that can be asked
      "may this plan hand trigger params to this strategy?". Admission was seven
      mechanisms in four files and nothing enumerated them.

WHAT IS PINNED, and it is the OPERATOR'S TABLE, not a paraphrase of it:
  A1-A7    every strategy's window, at BOTH edges, to the minute
  B1-B7    every strategy's concurrency cap, at cap-1, at cap, and above it
  C1-C2    tries-per-session on the two butterflies; unlimited on the rest
  D1-D6    the INTENT: conflicting theses run together, deliberately
  E1-E4    the universals, each refusing on its own name
  F1-F4    the blocking matrix, BOTH directions, via a config override
  G1-G3    the override path itself — partial overrides cannot blank a rule
  H1-H3    purity: same facts, same verdict; inputs never mutated
  X1-X3    the negatives — no VIX gate, unknown strategies fail CLOSED, and
           EVERY gate in gates() is reachable (a gate nothing can trigger is a
           gate nobody knows works — §17, §20's corollary for canaries)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILED = []
RAN = []


def check(name, ok, detail=""):
    RAN.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILED.append(name.split()[0])


def main():
    from execution.position_manager import decide, Facts, rules, gates, AdmissionRule
    from execution.position_manager import ORB, RUNAWAY, HUNT, BREAKOUT, SWEEP, TCS, GEXFLY, ATPFLY, VOLT

    T = rules()
    ALL = [ORB, RUNAWAY, HUNT, SWEEP, TCS, GEXFLY, ATPFLY, VOLT]

    def ok(strategy, hhmm, **kw):
        return decide(Facts(strategy=strategy, now_et=hhmm, orb_established=True, **kw))

    # ── the operator's table, restated HERE so the checker is not reading the
    #    same dict the code reads. §0.4: a fixture built from the belief under
    #    test cannot fail. These numbers come from his message, not from rules().
    SPEC = {
        ORB:     (((9, 35), (11, 30)), 1, None),
        RUNAWAY: (((9, 35), (11, 30)), 1, None),
        HUNT:    (((9, 35), (11, 30)), 1, None),
        # r51 (BRK.1) — the operator's 2026-09-18 ruling, restated from his own
        # words: *"I want the orb, hunt, breakout & sweep all able to fire &
        # non-competing"*, same opening range, nothing blocking anything.
        BREAKOUT: (((9, 35), (11, 30)), 1, None),
        # r71 (LATE.1) — the operator's 2026-09-20 ruling, restated from his own
        # words: *"let's just widen the credit trade window to 1540 for entries
        # & make the credit window flatten at 1550"*, because the late
        # institutional moves he is after are placed AFTER the hour at which
        # 0DTE day traders stop opening. These two are the CREDIT strategies and
        # they are the only ones that move; the debit windows below still close
        # at 15:00 because a debit is flattened by the 15:40 ladder and an entry
        # inside its own flatten window is an entry with no hold time at all.
        # r72 — VOLT, THE CONTROL ARM. Restated from the operator's request
        # (2026-09-20: *"construct 1 more trade strategy & plan… as a control
        # group… a window of 0935 to 1130"*), NOT read from rules().
        # ⚠️ ITS WINDOW MUST EQUAL THE ORB'S — a control measured over a
        # different period measures the period. check_volt_plan V1b pins that
        # equality from the other side.
        VOLT:    (((9, 35), (11, 30)), 1, None),
        SWEEP:   (((9, 35), (15, 40)), 2, None),
        TCS:     (((11, 30), (15, 40)), 1, None),
        GEXFLY:  (((12, 0), (15, 0)), 1, 1),
        ATPFLY:  (((11, 30), (15, 0)), 1, 1),
    }
    check("A0 the table holds exactly the strategies the box runs",
          set(T) == set(SPEC), f"symmetric difference: {sorted(set(T) ^ set(SPEC))}")

    # ── A — windows, at BOTH edges, to the minute ───────────────────────────
    def minus(hhmm):
        t = hhmm[0] * 60 + hhmm[1] - 1
        return (t // 60, t % 60)

    for s in ALL:
        (start, end), _cap, _tries = SPEC[s]
        before, at_start, before_end, at_end = minus(start), start, minus(end), end
        good = (not ok(s, before) and ok(s, at_start)
                and ok(s, before_end) and not ok(s, at_end))
        check(f"A {s} window {start[0]:02d}:{start[1]:02d}-{end[0]:02d}:{end[1]:02d}, "
              f"half-open at both edges",
              good,
              f"{before}={bool(ok(s,before))} {at_start}={bool(ok(s,at_start))} "
              f"{before_end}={bool(ok(s,before_end))} {at_end}={bool(ok(s,at_end))}")

    check("A8 11:30 is the handover: the morning three are OUT and the TCS is IN, same minute",
          not ok(ORB, (11, 30)) and not ok(RUNAWAY, (11, 30)) and not ok(HUNT, (11, 30))
          and bool(ok(TCS, (11, 30))) and bool(ok(ATPFLY, (11, 30))),
          "no overlap, no gap")

    check("A9 the GEX fly runs to 15:00 (its 14:00 cutoff was raised by ruling)",
          bool(ok(GEXFLY, (14, 30))) and bool(ok(GEXFLY, (14, 59))) and not ok(GEXFLY, (15, 0)),
          "14:30 and 14:59 in, 15:00 out")

    # ── B — concurrency caps, at cap-1, at cap, above cap ───────────────────
    for s in ALL:
        (win, cap, _t) = SPEC[s]
        mid = (win[0][0], win[0][1] + 1)
        below = ok(s, mid, open_by_strategy={s: cap - 1}) if cap > 0 else None
        at = ok(s, mid, open_by_strategy={s: cap})
        over = ok(s, mid, open_by_strategy={s: cap + 3})
        check(f"B {s} cap={cap}: admits at {cap-1} open, refuses at {cap} and beyond",
              bool(below) and not at and not over
              and at.gate == "max_open_of_type" == over.gate,
              f"{cap-1}->{bool(below)} {cap}->{at.gate} {cap+3}->{over.gate}")

    check("B8 the SWEEP is the one permitted two — it forms a condor",
          SPEC[SWEEP][1] == 2 and all(SPEC[s][1] == 1 for s in ALL if s != SWEEP),
          "sweep 2, every other type 1")

    check("B9 TCS+TCS is impossible, which is the condor rule with no special case",
          ok(TCS, (13, 0), open_by_strategy={TCS: 1}).gate == "max_open_of_type"
          and bool(ok(TCS, (13, 0), open_by_strategy={SWEEP: 1})),
          "TCS+TCS refused, TCS+SWEEP admitted")

    # ── C — tries per session ───────────────────────────────────────────────
    for s in (GEXFLY, ATPFLY):
        mid = (13, 0)
        check(f"C {s} one attempt per session: 0 used admits, 1 used refuses",
              bool(ok(s, mid, tries_used=0))
              and ok(s, mid, tries_used=1).gate == "tries_per_session",
              f"{ok(s, mid, tries_used=1).gate}")
    check("C3 every other strategy is UNLIMITED attempts (r2: ORB uncapped; r3: runaway per break)",
          all(T[s].max_tries_per_session is None for s in (ORB, RUNAWAY, HUNT, SWEEP, TCS))
          and bool(ok(ORB, (10, 0), tries_used=99)),
          "99 attempts still admits")

    # ── D — THE INTENT: conflicting theses run together ─────────────────────
    intent = [
        ("D1 sweep admits with a runaway open", SWEEP, (10, 0), {RUNAWAY: 1}),
        ("D2 ATP admits with a GEX fly open", ATPFLY, (13, 0), {GEXFLY: 1}),
        ("D3 TCS admits with a sweep open", TCS, (13, 0), {SWEEP: 1}),
        ("D4 hunt admits with an ORB open (the paired comparison)", HUNT, (10, 0), {ORB: 1}),
        ("D5 runaway admits with an ORB and a hunt open", RUNAWAY, (10, 0), {ORB: 1, HUNT: 1}),
    ]
    for name, s, hhmm, openmap in intent:
        check(name, bool(ok(s, hhmm, open_by_strategy=openmap)), str(openmap))

    check("D6 NOTHING caps the TOTAL number of open positions",
          bool(ok(SWEEP, (13, 0),
                  open_by_strategy={ORB: 1, RUNAWAY: 1, HUNT: 1, TCS: 1,
                                    GEXFLY: 1, ATPFLY: 1, SWEEP: 1})),
          "seven open, an eighth still admits")

    # ── E — the universals, each refusing on its own name ───────────────────
    check("E1 not a trading day", decide(Facts(ORB, (10, 0), trading_day=False)).gate == "trading_day")
    check("E2 opening range not established",
          decide(Facts(ORB, (10, 0), orb_established=False)).gate == "orb_range")
    check("E3 catastrophic cap",
          decide(Facts(ORB, (10, 0), orb_established=True, cap_intact=False)).gate == "catastrophic_cap")
    check("E4 past the hard close",
          decide(Facts(ORB, (10, 0), orb_established=True, past_hard_close=True)).gate == "hard_close")
    check("E5 the universals are asked of EVERY strategy, not just some",
          all(decide(Facts(s, (13, 0), orb_established=False)).gate == "orb_range" for s in ALL),
          "all seven refuse on orb_range")

    # ── F — the blocking matrix, BOTH directions, through an override ───────
    blocked = dict(T)
    blocked[SWEEP] = AdmissionRule(T[SWEEP].window, T[SWEEP].max_open_of_type,
                          T[SWEEP].max_tries_per_session,
                          blocks=frozenset(), blocked_by=frozenset({RUNAWAY}))
    check("F1 blocked_by: a named strategy being open refuses this one",
          decide(Facts(SWEEP, (10, 0), orb_established=True,
                       open_by_strategy={RUNAWAY: 1}), blocked).gate == "blocked_by")
    check("F2 ...and only the NAMED one — an unnamed open strategy does not block",
          bool(decide(Facts(SWEEP, (10, 0), orb_established=True,
                            open_by_strategy={ORB: 1}), blocked)),
          "ORB open, sweep still admits")

    blocks = dict(T)
    blocks[RUNAWAY] = AdmissionRule(T[RUNAWAY].window, T[RUNAWAY].max_open_of_type,
                           T[RUNAWAY].max_tries_per_session,
                           blocks=frozenset({SWEEP}), blocked_by=frozenset())
    check("F3 blocks: expressed from the OTHER end, it refuses just the same",
          decide(Facts(SWEEP, (10, 0), orb_established=True,
                       open_by_strategy={RUNAWAY: 1}), blocks).gate == "blocks",
          "a half-configured matrix cannot silently do nothing")
    check("F4 the shipped table blocks NOTHING — that is the ruling, not an oversight",
          all(not T[s].blocks and not T[s].blocked_by for s in ALL),
          "every blocks/blocked_by empty")

    # ── G — the override path ───────────────────────────────────────────────
    import config as _cfg
    _had = hasattr(_cfg, "ADMISSION_RULES")
    _old = getattr(_cfg, "ADMISSION_RULES", None)
    try:
        _cfg.ADMISSION_RULES = {GEXFLY: {"max_open_of_type": 3}}
        T2 = rules()
        check("G1 an override changes the named field",
              T2[GEXFLY].max_open_of_type == 3, f"{T2[GEXFLY].max_open_of_type}")
        check("G2 ...and leaves every UNNAMED field of that rule intact",
              T2[GEXFLY].window == T[GEXFLY].window
              and T2[GEXFLY].max_tries_per_session == T[GEXFLY].max_tries_per_session,
              "a partial override cannot blank a rule by omission")
        check("G3 ...and does not touch any other strategy",
              all(T2[s] == T[s] for s in ALL if s != GEXFLY))
    finally:
        if _had:
            _cfg.ADMISSION_RULES = _old
        else:
            delattr(_cfg, "ADMISSION_RULES")

    # ── H — purity ──────────────────────────────────────────────────────────
    f = Facts(SWEEP, (10, 0), orb_established=True, open_by_strategy={RUNAWAY: 1})
    v1, v2 = decide(f), decide(f)
    check("H1 same facts, same verdict — no hidden state", v1 == v2, f"{v1} / {v2}")
    check("H2 the caller's facts are not mutated",
          f.open_by_strategy == {RUNAWAY: 1} and f.strategy == SWEEP)
    # ── H3 — decide() REACHES NOTHING OUTSIDE THE ADMISSION BLOCK ──────────
    # ⚠️ TWO EARLIER CUTS OF THIS CHECK ARE RECORDED RATHER THAN REPLACED.
    # (1) The first read `for m in {}.get(...) and []` — iterating an EMPTY LIST,
    #     so `not any(...)` was true whatever the module imported. §21's failure
    #     inside a checker written to enforce §21.
    # (2) The second imported the module in a clean interpreter and asserted that
    #     NOTHING from strategy/ or execution/ was loaded. That was true while
    #     admission lived in its own file and is FALSE now that it lives in its
    #     right home: `position_manager` has imported `strategy.structure` and
    #     `execution.exit_engine` since long before this (a pre-existing
    #     execution -> strategy edge, position_manager.py:137). Purity-by-module
    #     did not survive the move, and deleting the check to hide that would be
    #     worse than losing it.
    # WHAT STILL MATTERS AND IS STILL TRUE: `decide()` calls nothing outside the
    # admission block. That is what keeps it testable without a tick loop or a
    # store, and what stops the position manager DRIVING the plans — it answers.
    import ast as _ast
    _src = open(os.path.join(ROOT, "execution", "position_manager.py"), encoding="utf-8").read()
    _tree = _ast.parse(_src)
    _decide = next(n for n in _tree.body
                   if isinstance(n, _ast.FunctionDef) and n.name == "decide")
    _allowed = {"rules", "Facts", "Verdict", "_within", "int", "set", "sorted",
                "dict", "frozenset", "len", "str", "float", "bool", "tuple", "getattr"}
    _called = {n.func.id for n in _ast.walk(_decide)
               if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)}
    _attrs = {n.func.attr for n in _ast.walk(_decide)
              if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute)}
    check("H3 decide() calls nothing outside the admission block — it answers, it never drives",
          not (_called - _allowed) and not (_attrs - {"get", "items", "keys"}),
          f"calls={sorted(_called - _allowed)} attrs={sorted(_attrs - {'get','items','keys'})}")

    check("H4 eligible_now() exists and never reaches into strategy/ (the one-way flow)",
          "def eligible_now" in _src
          and "import strategy" not in _src.split("def eligible_now")[1].split("def why_not")[0],
          "position manager feeds the plans; it does not call them")

    # ── X — the negatives ───────────────────────────────────────────────────
    src = open(os.path.join(ROOT, "execution", "position_manager.py"), encoding="utf-8").read()
    check("X1 the VIX crisis gate is GONE — a ruling, not an omission",
          "vix" not in [g.lower() for g in gates()]
          and "vix_entries_allowed" not in src.split('"""')[-1],
          f"gates={list(gates())}")
    check("X2 an unknown strategy fails CLOSED — a new trade joins the table or it does not trade",
          decide(Facts("SomethingNew", (10, 0), orb_established=True)).gate == "unknown_strategy")

    # every gate reachable: a gate nothing can trigger is one nobody knows works
    seen = set()
    for s in ALL:
        for kw in ({"trading_day": False}, {"orb_established": False},
                   {"orb_established": True, "cap_intact": False},
                   {"orb_established": True, "past_hard_close": True},
                   {"orb_established": True},
                   {"orb_established": True, "open_by_strategy": {s: 9}},
                   {"orb_established": True, "tries_used": 99}):
            for hhmm in ((3, 0), (10, 0), (13, 0)):
                seen.add(decide(Facts(s, hhmm, **kw)).gate)
    seen |= {decide(Facts("Nope", (10, 0), orb_established=True)).gate}
    seen |= {decide(Facts(SWEEP, (10, 0), orb_established=True,
                          open_by_strategy={RUNAWAY: 1}), blocked).gate,
             decide(Facts(SWEEP, (10, 0), orb_established=True,
                          open_by_strategy={RUNAWAY: 1}), blocks).gate}
    missing = set(gates()) - seen
    check("X3 EVERY gate in gates() is reachable — none is decorative",
          not missing, f"unreached: {sorted(missing)}" if missing else f"{len(gates())} gates")

    print()
    if FAILED:
        print(f"RED — {len(FAILED)} of {len(RAN)} failed: {', '.join(FAILED)}")
        return 1
    print(f"GREEN — {len(RAN)} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
