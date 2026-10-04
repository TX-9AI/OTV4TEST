"""
analysis/volatility_measures.py  v4.1
v4.1  2026-10-03  OTV4TEST r223 (EM.1) — every expected-move formula lives here: expected_move_session (the butterflies' / TCS / Hunt), straddle_nearest_marked (condor), straddle_nearest (readiness), straddle_same_strike + quote_mark (ORCS), each MOVED VERBATIM. No number changes.
Realised volatility, implied volatility and EXPECTED MOVE.

v4.0  2026-08-22  Built with the manifold. See docs/DERIVED_STORES.md.

Three things this file makes possible that were not before:

  1. **REALISED vol** from the candles — close-to-close, Parkinson, Garman-
     Klass. Nothing ever blocked this; nobody built it.
  2. **IMPLIED vol as a SERIES.** `Greeks.volatility` was on the wire all along
     and was being DISCARDED by chain_marks' last-write-wins. Kept, it gives
     the smile AND its trajectory.
  3. **EXPECTED MOVE that decays through the session.** This is the one that
     matters for 0DTE: at 09:35 with 6.5 hours left the expected move is a
     different number from 14:00 with two hours left. A single `atm_iv` scalar
     CANNOT express that. The series can.

⚠️ THREE WAYS TO GET EXPECTED MOVE AND THEY DISAGREE — that disagreement is
information, so all three are returned rather than one being picked:
  · STRADDLE  — ATM call + ATM put premium. The market's own number, no model.
  · IV-DERIVED — S x sigma x sqrt(T). Model-flavoured; very sensitive to how T
    is counted, which for 0DTE is HOURS not days.
  · REALISED  — what the tape actually delivered over a comparable window.
When straddle >> realised, options are expensive: that is a credit signal. The
VARIANCE RISK PREMIUM (implied minus realised) is exactly the condor's and the
butterfly's edge question, and nothing in this repo could compute it.

⚠️ CONTRIBUTOR, NEVER A GATE. Every function returns None when the inputs will
not support an honest answer. **None means "not measurable", never 0.0.** A
realised vol of zero means the tape did not move — a real reading. A realised
vol that could not be computed is the absence of one.

⚠️ ANNUALISATION IS STATED, NOT ASSUMED. Every sigma returned by this module is
ANNUALISED (x sqrt(periods_per_year)) unless the name says otherwise, so callers
never have to guess which convention a number is in. That guessing is how a
"volatility" gets compared against another "volatility" measured differently.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, time as dtime
from typing import Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

MIN_BARS = 20                    # below this, a sigma is noise
RTH_MINUTES = 390.0              # 09:30 -> 16:00
TRADING_DAYS = 252.0

# Bars per year, per interval — the annualisation factor's denominator.
_BARS_PER_YEAR = {
    "1m":  TRADING_DAYS * RTH_MINUTES,
    "5m":  TRADING_DAYS * RTH_MINUTES / 5.0,
    "15m": TRADING_DAYS * RTH_MINUTES / 15.0,
    "1h":  TRADING_DAYS * 6.5,
    "1d":  TRADING_DAYS,
}


def _closes(bars) -> list:
    out = []
    for b in bars:
        c = b.get("close") if isinstance(b, dict) else getattr(b, "close", None)
        if c is not None and c > 0:
            out.append(float(c))
    return out


def realised_vol_cc(bars, interval: str) -> Optional[float]:
    """Close-to-close annualised sigma. None if the sample is too thin."""
    c = _closes(bars)
    if len(c) < MIN_BARS + 1:
        return None
    rets = [math.log(c[i] / c[i - 1]) for i in range(1, len(c)) if c[i - 1] > 0]
    if len(rets) < MIN_BARS:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    bpy = _BARS_PER_YEAR.get(interval)
    if not bpy or var < 0:
        return None
    return math.sqrt(var) * math.sqrt(bpy)


def realised_vol_parkinson(bars, interval: str) -> Optional[float]:
    """Parkinson high/low estimator, annualised.

    ⚠️ USES THE RANGE, NOT THE CLOSE — so it sees intrabar movement that
    close-to-close is blind to. A session that whipsawed and closed flat has a
    LOW close-to-close sigma and a HIGH Parkinson sigma, and the difference
    between them is a real statement about the character of the tape.
    """
    vals = []
    for b in bars:
        h = b.get("high") if isinstance(b, dict) else getattr(b, "high", None)
        l = b.get("low") if isinstance(b, dict) else getattr(b, "low", None)
        if h and l and h > 0 and l > 0 and h >= l:
            vals.append(math.log(h / l) ** 2)
    if len(vals) < MIN_BARS:
        return None
    bpy = _BARS_PER_YEAR.get(interval)
    if not bpy:
        return None
    var = sum(vals) / (4.0 * math.log(2.0) * len(vals))
    return math.sqrt(var) * math.sqrt(bpy)


def session_fraction_remaining(now: Optional[datetime] = None) -> Optional[float]:
    """Fraction of the RTH session still ahead, in [0, 1].

    🔴 THIS IS THE 0DTE TERM. Expected move scales with sqrt(time remaining),
    and for a same-day expiry that term is HOURS. Counting it in days — or
    worse, holding it constant — makes the expected move at 14:00 look like the
    expected move at 09:35, which is the error that makes an afternoon entry
    look identically sized to a morning one.
    """
    # 🔴 r125 — IN ET. The 09:30/16:00 boundaries below are EXCHANGE hours, so
    # the clock compared against them must be the exchange's. `datetime.now()`
    # was the BOX's clock and the boxes run UTC: at 14:12 ET it computed from
    # 18:12 and returned 0.036 session remaining when the true answer is ~0.42.
    # ⚠️ THIS IS THE 0DTE TERM AND IT FEEDS STRIKE DISTANCE. Expected move
    # scales with sqrt(remaining), so a 12x understated fraction shrank EM by
    # ~3.5x — all day, on every box, silently. It was visible in CVX's payload
    # as session_fraction_remaining=0.036 at 11:45 and read as "some other
    # cutoff" until the manifold board surfaced the same clock bug.
    from utils.time_utils import ET
    now = now or datetime.now(ET)
    t = now.time()
    if t >= dtime(16, 0):
        return 0.0
    if t <= dtime(9, 30):
        return 1.0
    mins = (now.hour * 60 + now.minute) - (9 * 60 + 30)
    return max(0.0, min(1.0, (RTH_MINUTES - mins) / RTH_MINUTES))


def expected_move_iv(spot: float, atm_iv: float,
                     frac_remaining: Optional[float] = None) -> Optional[float]:
    """S x sigma x sqrt(T), where T is the SESSION FRACTION for 0DTE.

    Returns the one-sigma move in price terms, or None.
    """
    if not spot or not atm_iv or spot <= 0 or atm_iv <= 0:
        return None
    f = session_fraction_remaining() if frac_remaining is None else frac_remaining
    if f is None or f <= 0:
        return 0.0 if f == 0.0 else None     # at the bell the move IS zero
    return spot * atm_iv * math.sqrt(f / TRADING_DAYS)


def expected_move_straddle(call_mid: Optional[float],
                           put_mid: Optional[float]) -> Optional[float]:
    """ATM straddle price — THE MARKET'S OWN NUMBER, no model, no term guess.

    ⚠️ PREFER THIS WHEN AVAILABLE. It embeds the market's real view of time
    remaining, skew and event risk, none of which the IV formula knows about.
    """
    if call_mid is None or put_mid is None:
        return None
    if call_mid < 0 or put_mid < 0:
        return None
    return float(call_mid) + float(put_mid)


def variance_risk_premium(atm_iv: Optional[float],
                          realised: Optional[float]) -> Optional[float]:
    """Implied minus realised, annualised. None if either side is missing.

    🔴 POSITIVE = options are expensive relative to what the tape delivered:
    a CREDIT signal. Negative = the tape is moving more than options price:
    a DEBIT signal. This is the condor's and the butterfly's core edge
    question, and nothing in this repo could compute it before the greeks
    series existed.

    ⚠️ NEVER RETURNS 0.0 FOR A MISSING SIDE. A VRP of zero says implied and
    realised agree — a strong claim. Absence says we do not know.
    """
    if atm_iv is None or realised is None:
        return None
    return float(atm_iv) - float(realised)


def summarise(bars, interval: str, spot: Optional[float] = None,
              atm_iv: Optional[float] = None,
              call_mid: Optional[float] = None,
              put_mid: Optional[float] = None) -> dict:
    """Everything this module can say right now. Missing values are None.

    ⚠️ RETURNS A DICT WITH EVERY KEY PRESENT, values None where unmeasurable —
    never omits a key. A caller can then tell "not measured" from "not
    offered", which an absent key cannot express.
    """
    rv_cc = realised_vol_cc(bars, interval)
    rv_pk = realised_vol_parkinson(bars, interval)
    frac = session_fraction_remaining()
    return {
        "realised_vol_cc": rv_cc,
        "realised_vol_parkinson": rv_pk,
        "atm_iv": atm_iv,
        "variance_risk_premium": variance_risk_premium(atm_iv, rv_cc),
        "session_fraction_remaining": frac,
        "expected_move_iv": (expected_move_iv(spot, atm_iv, frac)
                             if spot and atm_iv else None),
        "expected_move_straddle": expected_move_straddle(call_mid, put_mid),
    }


# ══ r223 (EM.1) — EVERY EXPECTED-MOVE FORMULA IN THE TREE LIVES HERE ══════════
# The 10-03 audit (C8) counted five; ORCS added a sixth the same day. They are
# NOT the same number and none is changed by this move - each keeps its own
# arithmetic and its own return convention, so no trade sees a different value:
#   expected_move_iv(spot, iv, frac)      S x sigma x sqrt(session fraction / 252); 0.0 at the bell
#   expected_move_session(S, iv, now)     the same idea in hours to 16:00, FLOORED at 15 minutes,
#                                         3.0 h when the clock cannot be read (the butterflies, TCS, Hunt)
#   expected_move_straddle(call, put)     the two mids, handed in
#   straddle_nearest_marked(chain, S)     nearest strike WITH A MARK on each side (the sides may differ); 0.0
#   straddle_nearest(chain, S)            nearest strike on each side, marked or not; 0.0
#   straddle_same_strike(chain, S)        ONE strike quoted on both sides, two-sided mid; (None, None)
# Which of these a trade SHOULD use - and whether the 15-minute floor stays - is
# the operator's ruling, not this file's.

def expected_move_session(underlying, atm_iv, now=None) -> Optional[float]:
    """1x expected move for the REMAINING session, from the chain's ATM IV.

    MOVED VERBATIM from strategy/gex_pin_butterfly.expected_move (r223): hours to
    16:00 ET, never under 0.25 h (the 15-minute floor), 3.0 h if the clock cannot
    be read; S x iv x sqrt(hours / 6.5) / sqrt(252). None when S or iv is unusable."""
    from utils.math_utils import safe_float
    underlying = safe_float(underlying)
    atm_iv = safe_float(atm_iv)
    if not underlying or not atm_iv or atm_iv <= 0 or underlying <= 0:
        return None
    try:
        from utils.time_utils import ET
        now = now or datetime.now(ET)
        close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        hours = max((close - now).total_seconds() / 3600.0, 0.25)
    except Exception:                                          # noqa: BLE001
        hours = 3.0
    return underlying * atm_iv * math.sqrt(hours / 6.5) / math.sqrt(252)


def straddle_nearest_marked(chain, underlying: float) -> float:
    """ATM call mark + ATM put mark, each the nearest strike WITH mark > 0. 0.0 if unavailable.
    MOVED VERBATIM from IronCondorStrategy._expected_move_from_straddle (r223)."""
    try:
        atm_call = min([c for c in chain.calls if c.mark > 0],
                       key=lambda c: abs(c.strike - underlying))
        atm_put = min([c for c in chain.puts if c.mark > 0],
                      key=lambda c: abs(c.strike - underlying))
        if atm_call.mark > 0 and atm_put.mark > 0:
            return atm_call.mark + atm_put.mark
    except Exception:                                          # noqa: BLE001
        pass
    return 0.0


def straddle_nearest(chain, price: float) -> float:
    """Nearest-strike call mark + put mark, marked or not. 0.0 if unavailable.
    MOVED VERBATIM from analysis/trade_readiness._expected_move_now's body (r223)."""
    try:
        if chain is None or price <= 0:
            return 0.0
        calls = getattr(chain, "calls", None) or []
        puts = getattr(chain, "puts", None) or []
        if not calls or not puts:
            return 0.0
        atm_c = min(calls, key=lambda c: abs(getattr(c, "strike", 0.0) - price))
        atm_p = min(puts, key=lambda c: abs(getattr(c, "strike", 0.0) - price))
        em = float(getattr(atm_c, "mark", 0.0) or 0.0) + float(getattr(atm_p, "mark", 0.0) or 0.0)
        return em if em > 0 else 0.0
    except Exception:                                          # noqa: BLE001
        return 0.0


def quote_mark(c):
    """A contract's mark: the midpoint of a two-sided quote, else its own mark field, else None.
    A zero bid with a live ask is a real quote (half the ask); no ask is no quote.
    MOVED VERBATIM from strategy/orcs_plan.mark_of (r223)."""
    from utils.math_utils import safe_float
    b, a = safe_float(getattr(c, "bid", None)), safe_float(getattr(c, "ask", None))
    if a is not None and a > 0 and b is not None and b >= 0:
        return (a + b) / 2.0
    m = safe_float(getattr(c, "mark", None))
    return m if m is not None and m > 0 else None


def straddle_same_strike(chain, spot: float):
    """(straddle mark, strike): the strike nearest spot listed on BOTH sides, both quoted. (None, None).
    MOVED VERBATIM from strategy/orcs_plan.implied_move (r223)."""
    try:
        calls = {float(c.strike): c for c in (chain.calls or [])}
        puts = {float(p.strike): p for p in (chain.puts or [])}
        both = sorted(set(calls) & set(puts), key=lambda k: abs(k - spot))
        for k in both[:3]:
            mc, mp = quote_mark(calls[k]), quote_mark(puts[k])
            if mc is not None and mp is not None:
                return round(mc + mp, 4), k
    except Exception as exc:                                    # noqa: BLE001
        logger.debug("[em] same-strike straddle unavailable: %s", exc)
    return None, None
