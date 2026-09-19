"""
strategy/breakout.py  v1.1
THE SPECIFICATION. The plan searches; this declares what it must find.

v1.1  2026-09-19  OTV4TEST r53 — `flow_commit` STOPS BEING A PRIOR. Measured
      over 255 fleet breaks with prints: signed imbalance >= +0.10 lifts the 1R
      rate from 52.5% to 65.1% (1.24x, keeps 33%). The prior was 0.15, which
      measured 61.3% — right neighbourhood, slightly too strict.
      🔴 AND `tagged_frac` NEVER BINDS: median 1.00, p10 1.00 over the same
      sample. Kept as insurance against a degraded feed, labelled as insurance
      rather than evidence.
v1.0  2026-09-18  OTV4TEST r51 (BRK.1) — the operator's 5-minute opening range
      breakout, taken WITHOUT a retest.

WHY IT EXISTS, IN HIS WORDS. The ORB *"is typically a loser… which is crazy
because we're waiting for the level to prove itself before entering."* **The
retest IS that wait.** This trade pays for immediacy with EVIDENCE gathered at
the moment of the break instead of with time.

🔑 THIS FILE IS A DECLARATION, NOT A SEARCH (PLAN_SPEC §10). Operator,
2026-09-18: *"The strategy file is the specification. It lists the bars that
must be cleared to execute the trade. The plan file is what searches the feed
every tick for the nearest qualifying setup that satisfies the strategy… If it
can't satisfy every single hurdle then it doesn't put forward a plan. The plan
exists for the sole purpose of forming the trigger the strategy executes on.
Literally A, B, C was satisfied at X strike, execute if/when it reaches."*
So: this holds NO chain, picks NO strike, and reads NO feed. It states the
bars; `breakout_plan.py` clears them and hands back a trigger.

⚠️ EVERY CONSTANT BELOW IS A DECLARED PRIOR, AND TWO ARE MEASURED FACTS THAT
CONTRADICT AN EARLIER PRIOR. They are named here, in one place, so a study can
move them without hunting through the plan.
  🔴 VOLUME EXPANSION IS NOT A CONDITION. Measured 2026-09-18 over 736 fleet
     breaks (every warehouse `ohlc` object back to 2026-07-08): the break bar's
     volume multiple does NOT separate a break that reached +1R from one that
     was stopped — medians 0.62 vs 0.59 on the ORB baseline, and the best
     threshold on any of four baselines lifted the hit rate from 50.9% to
     55.3% (1.08x, n=266). **The operator predicted this before the study
     ran:** *"one of the characteristics of a fakeout is taking out stops and
     then turning the other way."* Stops are market orders, so a harvest
     MANUFACTURES the volume spike — it describes that a break happened, never
     whether it holds. It is recorded as context, never gated on.
  🔑 ROOM TO RUN IS THE ONE GATE WITH EVIDENCE, AND IT IS A BINARY. Same study,
     n=327 with a liquidity ledger: breaking into OPEN AIR reached 1R 63.0% of
     the time against 49.5% with a named pool ahead (base 51.4%). ⚠️ n=46 on
     the open-air arm, a standard error near 7 points — suggestive, not
     established. The DISTANCE bands did not behave monotonically (0–0.5R beat
     0.5–1.0R), most likely because a pool that close IS the level that formed
     the range, so no distance threshold is declared.
"""
from __future__ import annotations

import logging

import config

logger = logging.getLogger(__name__)

# ── WA §36 — EVERY GATE CONSTANT, NAMED AND CATEGORISED ─────────────────────
# SELECTION   the operator toggles it as data arrives
# FOUNDATIONAL it changes what the trade IS — his ruling, not a tuning knob
# FEASIBILITY  can the trade physically be done at all
# 🔑 THE THREE FOUNDATIONAL ONES ARE FOUNDATIONAL FOR ONE REASON: they decide
# whether this is a BREAKOUT at all. Take the window away and it is a different
# trade; take the close-beyond away and it is the wick-triggered entry r5 ruled
# out; take room_to_run away and it is a trade INTO a resting pool, which is the
# hunt's setup, not this one.
GATES = {
    "EARLIEST_ET":          "FOUNDATIONAL",
    "LATEST_ET":            "FOUNDATIONAL",
    "RANGE_MIN_PCT":        "FEASIBILITY",   # a 3-cent range cannot be traded
    "RANGE_MAX_PCT":        "FEASIBILITY",   # a gap-day range cannot be stopped
    "ROOM_MIN_R":           "FOUNDATIONAL",  # measured: open air 63.0% vs 49.5%
    "FLOW_IMBALANCE_MIN":   "SELECTION",     # MEASURED n=255, lift 1.24x
    "FLOW_TAGGED_MIN":      "SELECTION",     # measured: NEVER BINDS (tagged=1.00)
    "REGIME_MAX":           "SELECTION",     # PRIOR — unmeasured
    "DEPTH_DEPLETION_MIN":  "SELECTION",     # PRIOR — unmeasured
    "R_FLOOR":              "SELECTION",
}

# ── the window (admission also carries it; this is the strategy's own claim) ──
EARLIEST_ET = str(getattr(config, "BREAKOUT_EARLIEST_ET", "09:35"))
LATEST_ET = str(getattr(config, "BREAKOUT_LATEST_ET", "11:30"))

# ── the bars, as priors ──────────────────────────────────────────────────────
# ⚠️ UNMEASURED. The study that gives these numbers separates breaks that RAN
# from breaks that REVERTED on the three inputs a stop run cannot manufacture.
# Until it runs these are declared guesses and are labelled as such in the
# CONDITIONS text, so a plan row never implies more confidence than exists.
# 🔑 MEASURED 2026-09-18, n=255 fleet breaks with prints (08-24 → 09-18), streamed
# from the warehouse. Signed imbalance over the 3 minutes from the break bar,
# against the same +1R-before-−1R outcome the volume study used:
#     reached 1R   p25 −0.023   med +0.074   p75 +0.165
#     stopped      p25 −0.073   med +0.013   p75 +0.099
#     base rate 52.5%  ·  >= +0.10 -> 65.1% (lift 1.24x, keeps 33%, n=83)
# The medians sit 6x apart. This is the ONE entry gate with real separation —
# volume had none (n=736, lift 1.08x) and room_to_run is suggestive on n=46.
# ⚠️ WAS 0.15 AS A PRIOR, AND THE DATA MOVED IT DOWN: 0.15 measured 61.3% against
# 0.10's 65.1%, so the guess was in the right place and slightly too strict. The
# dip at 0.15 is almost certainly noise at this sample size; 0.10 is taken
# because it is the best-supported point, not because the curve is smooth.
FLOW_IMBALANCE_MIN = float(getattr(config, "BRK_FLOW_IMBALANCE_MIN", 0.10))
# 🔴 THIS FLOOR HAS NEVER ONCE BOUND, AND THAT IS RECORDED RATHER THAN QUIETLY
# KEPT. Measured over the same 255 breaks: `tagged_frac` median 1.00, p10 1.00 —
# every print on this feed carries an aggressor side, so a 0.60 floor can never
# fire. The REASONING is still sound (untagged volume stays in the denominator,
# so a thin tape would otherwise fabricate conviction) and it is kept as cheap
# insurance against a degraded feed. But it is insurance, not evidence, and a
# gate that has never gated must say so.
FLOW_TAGGED_MIN = float(getattr(config, "BRK_FLOW_TAGGED_MIN", 0.60))
REGIME_MAX = float(getattr(config, "BRK_REGIME_MAX", 0.0))
DEPTH_DEPLETION_MIN = float(getattr(config, "BRK_DEPTH_DEPLETION_MIN", 0.0))
ROOM_MIN_R = float(getattr(config, "BRK_ROOM_MIN_R", 1.0))
R_FLOOR = float(getattr(config, "BRK_R_FLOOR", 1.0))
RANGE_MIN_PCT = float(getattr(config, "BRK_RANGE_MIN_PCT", 0.0005))
RANGE_MAX_PCT = float(getattr(config, "BRK_RANGE_MAX_PCT", 0.0125))

class Breakout:
    """The specification. `breakout_plan.BreakoutPlan` satisfies it or stays silent."""

    name = "Breakout"

    # ── WHAT MUST BE TRUE. name -> what "true" means ─────────────────────────
    CONDITIONS = {
        "entry_window":  f"{EARLIEST_ET}-{LATEST_ET} ET",
        "orb_range":     (f"a 5-minute opening range is established and its width is "
                          f"{RANGE_MIN_PCT:.2%}-{RANGE_MAX_PCT:.2%} of spot — neither a "
                          f"three-cent range nor a gap-day monster"),
        "range_clean":   ("no live level sits inside the range — r39 retires them TRAVERSED, "
                          "so a level still inside means the board has not caught up"),
        "break_close":   ("a CLOSED 1m bar's CLOSE beyond the range edge — r5's rule, bodies "
                          "decide and wicks test. This is the anti-fakeout gate that costs "
                          "nothing in TIME, which is the whole point of skipping the retest"),
        "flow_commit":   (f"aggressor imbalance >= {FLOW_IMBALANCE_MIN:+.2f} in the break "
                          f"direction with tagged_frac >= {FLOW_TAGGED_MIN:.0%} "
                          f"(MEASURED n=255: >= +0.10 lifts the 1R rate 52.5% -> 65.1%. "
                          f"The tagged floor has never bound — every print carries a side — "
                          f"and is kept as insurance against a degraded feed)"),
        "gamma_regime":  (f"regime <= {REGIME_MAX:+.2f} — NOT pinning. A break into a pinning "
                          f"regime is one dealers fade; into a trending regime, one they "
                          f"amplify. (PRIOR, unmeasured)"),
        "depth_thin":    (f"resting depth ahead of price DEPLETING, not refilling "
                          f"(>= {DEPTH_DEPLETION_MIN:+.2f}) — the book's answer to the same "
                          f"question flow_commit asks of the tape, and independent of it. "
                          f"(PRIOR, unmeasured)"),
        "room_to_run":   (f"OPEN AIR ahead, or the nearest named pool at least "
                          f"{ROOM_MIN_R:.1f}R away. MEASURED: open air reached 1R 63.0% vs "
                          f"49.5% with a pool ahead (n=327, base 51.4%) — but n=46 on the "
                          f"open-air arm, so it is a BINARY and no distance threshold is "
                          f"claimed"),
    }

    # 🔑 WHICH BARS MUST STILL BE TRUE WHEN PRICE ARRIVES (PLAN_SPEC §10:
    # *"on t+1 the strategy checks the declared conditions against the tick and,
    # if all are true, executes THAT trade"*).
    # Operator, 2026-09-18: *"some of those other trigger components may be
    # conditions that need to remain in a particular state, such as pinning, or
    # rising ATR, or above VWAP. So the plan will say if all of those conditions
    # are still true and price reaches X, then everything is satisfied."*
    # ⚠️ THE TRIGGER IS COMPOUND, AND THE SPLIT IS THE POINT. A SETTLED bar is
    # a fact that cannot decay between the plan and the fill — the range was
    # this wide, the bar closed beyond, this strike is listed. A PERSISTENT bar
    # is LIVE STATE: the regime can flip, the tape can stop paying up, the book
    # can refill. Re-checking a settled fact wastes a tick; NOT re-checking live
    # state fires a trade on evidence that has already expired.
    # ⚠️ ADDING ONE IS A ONE-LINE CHANGE — "above VWAP" or "rising ATR" join
    # CONDITIONS and then this tuple. They are deliberately NOT here yet: no
    # study has shown either separates a break that ran from one that reverted,
    # and r51's own volume result is what that costs when it is assumed.
    PERSISTENT = ("flow_commit", "gamma_regime", "depth_thin")

    # the structural bars — selectable facts, not market conditions
    STRUCTURAL = ("contract", "premium", "stop_survivable", "r", "target")

    # everything recorded per tick, whether it gates or not
    PLAN_CHECKS = tuple(CONDITIONS) + STRUCTURAL + (
        "range_width_pct", "break_dir", "break_close_px", "vol_multiple",
        "flow_imbalance", "flow_tagged", "regime", "depth_ratio",
        "pool_price", "pool_name", "pool_dist_r", "reach_measured", "reach_pool",
        "verdict", "defer_to", "persist_ok",
    )

    # ⚠️ RECORDED, NEVER GATED. `vol_multiple` is here so the study that
    # rehabilitates or buries it has the value on every row — the same reason
    # `derived/snapshot.py` exists (r240/r243/r244: a field computed, used for a
    # DECISION, and never recorded).
    CONTEXT_ONLY = ("vol_multiple",)

    def __init__(self):
        self._plan = None

    def _plan_(self):
        if self._plan is None:
            from strategy.breakout_plan import BreakoutPlan     # lazy: it imports this
            self._plan = BreakoutPlan()
        return self._plan

    def prepare(self, **kw):
        """The plan runs. This file never searches."""
        return self._plan_().prepare(spec=self, **kw)

    def generate_signal(self, **kw):
        """CONFIRM the plan's trigger, then execute it. Picks nothing.

        🔑 THE STRATEGY DETERMINES WHETHER THE TRIGGER COMPONENTS ARE IN PLACE.
        Operator, 2026-09-18: *"the strategy must determine if all the trigger
        components provided by the plan are in place to fire."* The plan's job
        ended when it handed over a trigger — a strike, a stop, an R, and the
        named conditions that must still hold. This re-reads those components
        against THIS tick and fires only if every one is in place.
        ⚠️ IT DOES NOT RE-DERIVE THEM. Re-searching here would make this a
        second plan, which is exactly the duplication PLAN_SPEC §10 removes; it
        reads what `prepare()` recorded and judges it.
        ⚠️ AND THE CHECK IS NOT REDUNDANT WITH `ready`. `ready` is the PLAN's
        verdict that a qualifying setup exists. This is the STRATEGY's verdict
        that it is still true now, and the two are different questions the same
        way a signed contract and a settled trade are different events.
        """
        prep = self.prepare(**kw)
        if prep is None:
            return None
        if not getattr(prep, "ready", False):
            return prep.tick.already()

        # every PERSISTENT bar must still read true on this tick
        stale = [c for c in self.PERSISTENT
                 if not (prep.conditions.get(c) or (None, "", False))[2]]
        if stale:
            prep.tick.check("persist_ok", None, False,
                            note="decayed since the plan: " + ", ".join(stale))
            return prep.tick.hold(f"trigger incomplete — {', '.join(stale)} no longer true")

        # and the trigger itself: price still beyond the edge the break cleared
        px, edge = prep.price_now, prep.trigger
        if px is None or edge is None:
            return prep.tick.hold("trigger unreadable — price or edge absent")
        held = px > edge if prep.direction == "long" else px < edge
        if not held:
            return prep.tick.hold(
                f"trigger not in place — price {px:.2f} back inside {edge:.2f}")

        return prep.emit(self.name)
