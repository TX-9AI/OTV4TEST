"""
shadow/trading_day.py  v4.2
v4.2  2026-09-08  r319 / SHD.3 — 🔴 THIS FILE STOPPED RUNNING AS A SCRIPT ON
      2026-09-07, AND IT TOOK THE WHOLE SHADOW CORPUS WITH IT. r304 replaced
      the local holiday list with `from utils.market_calendar import ...` — an
      ABSOLUTE PACKAGE IMPORT in the one module whose entire contract is to be
      runnable as a plain script from a systemd `ExecCondition`. Python puts
      the SCRIPT'S OWN DIRECTORY on `sys.path`, never the working directory,
      so `/usr/bin/python3 <install>/shadow/trading_day.py` raises
      ModuleNotFoundError and exits 1 — and `WorkingDirectory=` does not save
      it. Reproduced both ways before the fix.
      🔴 **A NON-ZERO ExecCondition IS A SKIP, NOT A FAILURE.** `shadow-start`
      quietly did nothing, `shadow-observer` was never started, and no unit
      entered a failed state — so nothing on the box was wrong to look at.
      Fifteen boxes wrote ZERO rows on the first session after it landed, and
      the only thing that noticed was dtp's `shadow_watch` guard at 09:40.
      **THE REPO ROOT IS NOW PUT ON `sys.path` BEFORE THE IMPORT**, the same
      self-locating idiom `shadow/observer.py` already uses for `OUT_DIR`. One
      list is still the rule; only the path resolution changed.
      ⚠️ AND THE GATE THAT WAS SUPPOSED TO COVER THIS READ SOURCE TEXT.
      `check_holiday_aware` H5 asserted the string `from utils.market_calendar
      import` APPEARS in this file — which is exactly what broke it — and it
      passed on every run while the script could not execute. WORKING_AGREEMENT
      §21, one layer up: H5c now RUNS the ExecCondition line from outside the
      repo and reads its exit code.
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
Runnable as a plain script from a systemd ExecCondition. ⚠️ SINCE r304 IT IS
NO LONGER STDLIB-ONLY — it imports the shared holiday list from
`utils.market_calendar`, and r319 is what makes that import work under script
invocation. Anything added here must survive
`/usr/bin/python3 <install>/shadow/trading_day.py` run from ANY directory. Exits 0 on a trading day, 1 on a
weekend or US market holiday — the start service uses that to SKIP (not fail)
on holidays. Evaluates the date in ET regardless of the box's system timezone.
⚠ Holiday list is hardcoded and must be refreshed annually (2026–2027 below).
Fail-safe: a wrong 'holiday' just means shadow doesn't observe that day (no harm);
a missed holiday means it observes an empty tape (harmless noise), never a trade.
"""
import datetime
import os
import sys
from zoneinfo import ZoneInfo

# 🔴 r319 — THE REPO ROOT, BEFORE THE IMPORT BELOW. `python3 <path>/shadow/
# trading_day.py` puts THIS FILE'S directory on `sys.path` and never the
# working directory, so the absolute import r304 added could not resolve and
# the ExecCondition exited 1 — which systemd reads as SKIP, silently. Computed
# from __file__ rather than assumed, the same idiom `shadow/observer.py` uses
# for `OUT_DIR`; harmless under `python -m shadow.trading_day`, where the root
# is already there.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

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
