"""
shadow/trading_day.py  v4.1
v4.1  2026-09-07  r304 / DEP.9 - the holiday list moved to utils/market_calendar and is imported, not copied. Semantics and the 0/1 ExecCondition exit are unchanged.
Session-boundary helper for the observer.

v4.0  2026-08-19  Ported from options_trader_v3 at the OTV4 split.

INHERITED DOCTRINE
MEASUREMENTS AND CONSTRAINTS CARRIED FROM v3 - NOT A CHANGELOG.
Dated release framing and trivia are stripped; what remains is the
reasoning behind the thresholds, the design guarantees, and the
defects that recur when forgotten. WORKING_AGREEMENT 32 requires
this block be read before the file is edited.

shadow/trading_day.py v1.0 — standalone US-market trading-day check.
Self-contained (stdlib only, no shadow/* imports) so it can run as a plain
script from a systemd ExecCondition. Exits 0 on a trading day, 1 on a
weekend or US market holiday — the start service uses that to SKIP (not fail)
on holidays. Evaluates the date in ET regardless of the box's system timezone.
⚠ Holiday list is hardcoded and must be refreshed annually (2026–2027 below).
Fail-safe: a wrong 'holiday' just means shadow doesn't observe that day (no harm);
a missed holiday means it observes an empty tape (harmless noise), never a trade.
"""
import datetime
import sys
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# NYSE full-day closes (observed dates). Refresh each year.
# 🔴 r304 / DEP.9 — THE LIST MOVED TO utils/market_calendar.py AND IS NOT
# COPIED BACK. It lived here first and was the only holiday awareness in otv4;
# the trading clock now needs it too, and two lists meaning one thing is the
# drift this repo keeps finding. This module keeps its OWN semantics (it is the
# shadow-start ExecCondition and exits 0/1) and only the DATES are shared.
from utils.market_calendar import US_MARKET_HOLIDAYS, is_trading_day  # noqa: F401


# is_trading_day is imported above — one implementation, one list.


if __name__ == "__main__":
    sys.exit(0 if is_trading_day() else 1)
