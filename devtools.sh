#!/usr/bin/env bash
# ==========================================================================
# devtools.sh  v2.0  — OTV4TEST box menu, rebuilt (fork-numbered from here)
# v2.0  2026-09-08  OTV4TEST r4 — THE BOX MENU CATCHES UP WITH CONTROL.
#       Operator: this instance is standalone; control's devtools never reaches
#       it, and the box's own menu was the otv1-era break-glass list. The
#       control menu's BOT-SPECIFIC items are ported here to run LOCALLY —
#       SENSORS (the same SQL, over this box's own derived_store.db and
#       feed_store.db, an ET date prompt where control took one), DEBUG / LOGS,
#       and the R SUITE (the fork's own tests/r_ledger.py, stop_sweep.py,
#       exit_replay.py, edge_scan.py via their `--db` escape hatch on
#       trades.db — this box is masked from S3 by construction). Everything
#       about wrangling a fleet is deliberately absent. NEW sensors: PLAN ROWS
#       (the per-tick narrative) and LEVEL EVENTS (WICKED / REJECTED /
#       ACCEPTED, derived/levels v4.1, r3).
#       🔑 THE MENU IS DATA, as on control (dtp v1.32): MENU=(SECTION|… /
#       ITEM|label|function) rendered with numbers assigned at display time,
#       so nothing here cites a number — LAND and BAKE moved; their labels did
#       not. Existing functions are kept verbatim.
#       Version numbering restarts at 2.0 by the operator's request; the
#       v4.x lineage below is the file's history, not a downgrade.
# v4.4  2026-09-08  OTV4TEST r3 — LAND auto-selects a lone archive; BAKE added.
# v4.3  2026-09-08  OTV4TEST r1 — LAND a tarball (the fork lander).
# v4.2  2026-09-08  r322 — the comment markers (this script had done nothing
#       since 2026-08-25: a changelog line written as shell aborted the parse).
# v4.1  2026-08-25  r65 EXORCISM.  v4.0  2026-08-19  ported at the OTV4 split.
# ==========================================================================
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$REPO/venv/bin/python"
export PYTHONPATH="$REPO"
BOT="optionsbot"          # systemd unit (setup_ec2.sh SERVICE_NAME)
FEED="candle-feed"        # systemd unit (single DXFeed producer)
BOTLOG="$REPO/bot.log"    # ExecStartPre touches this in the unit
DERIVED_DB="${OT_DERIVED_DB:-$REPO/data/derived_store.db}"
FEED_DB="$REPO/data/feed_store.db"
TRADES_DB="$REPO/trades.db"
cd "$REPO" 2>/dev/null || { echo "cannot cd to $REPO"; exit 1; }
[ -x "$PY" ] || echo "warn: no venv python at $PY — python items will fail"

pause()   { read -rp $'\n[enter] '; }
confirm() { read -rp "$1 [y/N] " a; case "${a:-}" in y|Y|yes|YES|Yes) return 0 ;; *) return 1 ;; esac; }
svc()     { systemctl is-active "$1" 2>/dev/null || echo "unknown"; }
_sql()    { # $1 db, $2 sql — header+column, like control
  [ -f "$1" ] || { echo "  no store at $1"; return 0; }
  sqlite3 -header -column "$1" "$2" 2>&1
}
_et_bounds() {  # $1 = YYYY-MM-DD -> ET_FROM / ET_TO epoch (ET midnight to midnight)
  local nxt; nxt=$(date -d "$1 +1 day" +%F 2>/dev/null)
  ET_FROM=$(TZ=America/New_York date -d "$1 00:00:00" +%s 2>/dev/null)
  ET_TO=$(TZ=America/New_York date -d "$nxt 00:00:00" +%s 2>/dev/null)
  [ -n "$ET_FROM" ] && [ -n "$ET_TO" ] || { echo "  bad date: $1 (YYYY-MM-DD)"; return 1; }
}
_ask_day() {    # prompts; ENTER = today in ET
  local today; today=$(TZ=America/New_York date +%F)
  read -rp "  Session date (YYYY-MM-DD, ENTER = $today): " d
  _et_bounds "${d:-$today}"
}

# ── STATUS ─────────────────────────────────────────────────────────────────
run_status()    { "$PY" status.py; pause; }
run_query()     { "$PY" query.py; pause; }
run_decisions() { "$PY" query.py --decisions; pause; }
run_debug()     { "$PY" debug_status.py; pause; }
run_eod()       { "$PY" eod_summary.py; pause; }

# ── SENSORS (this box's derived stores; read-only) ─────────────────────────
s_manifold() { echo; echo "  Per-stream bulbs from tools/manifold_health.py."; "$PY" tools/manifold_health.py; pause; }
s_notes() {
  echo; echo "  Source: derived_store.db -> strategy_note (what each engine SAW)"; _ask_day || { pause; return; }
  _sql "$DERIVED_DB" "SELECT strategy, SUM(fired) AS signalled, COUNT(*)-SUM(fired) AS quiet, COUNT(*) AS looks FROM strategy_note WHERE ts_epoch >= $ET_FROM AND ts_epoch < $ET_TO GROUP BY strategy ORDER BY looks DESC;"; pause; }
s_plan_board() {
  echo; echo "  Source: derived_store.db -> plan_tick + plan_check"; _ask_day || { pause; return; }
  _sql "$DERIVED_DB" "SELECT strategy, verdict, COUNT(*) n, ROUND(MIN(r_now),2) r_lo, ROUND(MAX(r_now),2) r_hi, ROUND(AVG(underlying),2) px FROM plan_tick WHERE ts_epoch >= $ET_FROM AND ts_epoch < $ET_TO GROUP BY strategy, verdict ORDER BY strategy, verdict;"
  echo; echo "  WHICH CHECK FAILED, AND HOW OFTEN:"
  _sql "$DERIVED_DB" "SELECT strategy, check_name, verdict, COUNT(*) n, ROUND(MIN(value),2) lo, ROUND(MAX(value),2) hi FROM plan_check WHERE ts_epoch >= $ET_FROM AND ts_epoch < $ET_TO GROUP BY strategy, check_name, verdict ORDER BY strategy, check_name, verdict;"; pause; }
s_plan_rows() {
  echo; echo "  Source: derived_store.db -> plan_tick, the ROWS (newest last) — the per-tick narrative"; _ask_day || { pause; return; }
  read -rp "  Strategy (ENTER = all): " S; local W=""; [ -n "$S" ] && W=" AND strategy='$S'"
  read -rp "  How many rows [40]: " N; N="${N:-40}"
  _sql "$DERIVED_DB" "SELECT * FROM (SELECT datetime(ts_epoch,'unixepoch','-4 hours') AS et, strategy, verdict, substr(reason,1,150) AS reason FROM plan_tick WHERE ts_epoch >= $ET_FROM AND ts_epoch < $ET_TO$W ORDER BY ts_epoch DESC LIMIT $N) ORDER BY et;"; pause; }
s_plan_ledger() {
  echo; echo "  Source: derived_store.db -> plan_ledger (intent + terminal reason)"; _ask_day || { pause; return; }
  _sql "$DERIVED_DB" "SELECT strategy, state, COALESCE(terminal_reason,'(live)') AS reason, COUNT(*) AS n FROM plan_ledger WHERE created_ts >= $ET_FROM AND created_ts < $ET_TO GROUP BY strategy, state, reason ORDER BY n DESC;"; pause; }
s_exit_cf() {
  echo; echo "  Source: derived_store.db -> exit_counterfactual (flow vs the stop)"
  _sql "$DERIVED_DB" "SELECT trade_id, strategy, reason, COUNT(*) AS evals, MAX(threat) AS peak_threat, MAX(would_fire) AS would_have FROM exit_counterfactual GROUP BY trade_id, strategy, reason ORDER BY peak_threat DESC LIMIT 25;"; pause; }
s_fire_snapshot() {
  echo; echo "  Source: derived_store.db -> fire_snapshot (everything derived at the INSTANT a trade fired)"
  _sql "$DERIVED_DB" "SELECT trade_id, datetime(fired_ts,'unixepoch','-4 hours') AS fired_et, substr(payload,1,160) AS payload FROM fire_snapshot ORDER BY fired_ts DESC LIMIT 10;"; pause; }
s_surface() {
  echo; echo "  Source: derived_store.db -> surface_series (last 24h)"
  _sql "$DERIVED_DB" "SELECT strike, ROUND(AVG(charm),4) AS charm, ROUND(AVG(vanna),4) AS vanna, ROUND(MAX(gex)/1e6,2) AS gex_m, COUNT(*) AS n FROM surface_series WHERE ts_epoch > strftime('%s','now','-1 day') GROUP BY strike ORDER BY n DESC LIMIT 20;"; pause; }
s_indicators() {
  echo; echo "  Source: derived_store.db -> indicator_series (last 24h)"
  _sql "$DERIVED_DB" "SELECT interval, COUNT(*) AS n, ROUND(MIN(adx),1) AS adx_lo, ROUND(MAX(adx),1) AS adx_hi, ROUND(AVG(adx),1) AS adx_avg, ROUND(AVG(vwap),2) AS vwap FROM indicator_series WHERE ts_epoch > strftime('%s','now','-1 day') GROUP BY interval;"; pause; }
s_forks() {
  echo; echo "  Source: derived_store.db -> fork_series (built vs reject reason, last 24h)"
  _sql "$DERIVED_DB" "SELECT interval, CASE built WHEN 1 THEN 'BUILT' ELSE COALESCE(reject_reason,'?') END AS outcome, COUNT(*) AS n, ROUND(AVG(containment),3) AS contain FROM fork_series WHERE ts_epoch > strftime('%s','now','-1 day') GROUP BY interval, outcome ORDER BY n DESC;"; pause; }
s_levels() {
  echo; echo "  Source: derived_store.db -> level_ledger (touches + retirements)"
  _sql "$DERIVED_DB" "SELECT provenance, kind, COUNT(*) AS levels, SUM(touch_count) AS touches, SUM(CASE WHEN retired_ts IS NULL THEN 0 ELSE 1 END) AS retired FROM level_ledger GROUP BY provenance, kind ORDER BY touches DESC;"; pause; }
s_level_events() {
  echo; echo "  Source: derived_store.db -> level_event (WICKED / REJECTED / ACCEPTED — the rejection fact, r3)"; _ask_day || { pause; return; }
  _sql "$DERIVED_DB" "SELECT event, depth, COUNT(*) AS n FROM level_event WHERE ts_epoch >= $ET_FROM AND ts_epoch < $ET_TO GROUP BY event, depth ORDER BY event, depth;"
  echo; echo "  THE EVENTS, IN ORDER:"
  _sql "$DERIVED_DB" "SELECT bar_ts, event, kind, price, provenance, ROUND(pierce_pct*100,3) AS pierce_pct, depth, closes_back, bar_close FROM level_event WHERE ts_epoch >= $ET_FROM AND ts_epoch < $ET_TO ORDER BY ts_epoch, bar_ts LIMIT 60;"; pause; }
s_order_flow() {
  echo; echo "  Source: feed_store.db -> prints + quote_series (last 24h)"
  _sql "$FEED_DB" "SELECT COALESCE(aggressor_side,'(untagged)') AS side, COUNT(*) AS prints, ROUND(SUM(size)) AS volume FROM prints WHERE ts_epoch > strftime('%s','now','-1 day') GROUP BY side;"
  _sql "$FEED_DB" "SELECT COUNT(*) AS quote_rows, ROUND(AVG(bid_size)) AS avg_bid_sz, ROUND(AVG(ask_size)) AS avg_ask_sz FROM quote_series WHERE ts_epoch > strftime('%s','now','-1 day');"; pause; }

# ── TESTS ──────────────────────────────────────────────────────────────────
PYTEST_SUITE=(
  tests/test_entry_fill_confirmation.py
  tests/test_mode_isolation.py
  tests/test_phantom_pnl_recovery.py
  tests/test_roll_is_real.py
  tests/test_runner_refinements.py
)
run_suite() {
  if ! "$PY" -c "import pytest" 2>/dev/null; then
    echo "pytest not in this venv. Install with:"; echo "  $PY -m pip install pytest"; pause; return 1
  fi
  echo "── full regression suite (go-live gate) ─────────────────────────────"
  "$PY" -m pytest "${PYTEST_SUITE[@]}" -v; pause
}
run_standing() {
  # the lander's standing set, run by hand between landings
  echo "── standing checks (the lander runs these on every land) ─────────────"
  local rc=0
  for t in check_imports check_gates check_attr_fidelity check_plan_wiring check_orb_plan check_runaway_plan check_level_rejection check_land_tooling; do
    [ -f "tests/$t.py" ] || continue
    if "$PY" "tests/$t.py" >/tmp/dt_$t.log 2>&1; then echo "  PASS  $t"; else echo "  FAIL  $t  (see /tmp/dt_$t.log)"; rc=1; fi
  done
  [ "$rc" = 0 ] && echo "  ALL PASS" || echo "  RED — read the log before landing anything"
  pause
}
run_contract() { "$PY" -m tests.test_market_data_contract; pause; }
run_orb()      { "$PY" tests/test_orb_retest_v33.py; pause; }
run_feed_verify() {
  echo "verify_feed_v3.sh must run ON-BOX during RTH with $FEED + $BOT live (paper)."
  confirm "run it now?" || { echo "skipped"; pause; return; }
  bash tests/verify_feed_v3.sh; echo "exit=$?"; pause
}

# ── DEBUG / LOGS (this box) ────────────────────────────────────────────────
svc_status() {
  echo "── this box ─────────────────────────────────────────────────────────"
  echo "  $BOT  : $(svc "$BOT")"
  echo "  $FEED : $(svc "$FEED")"
  systemctl --no-pager -l status "$BOT" "$FEED" 2>/dev/null | grep -E "Active:|Main PID:|Loaded:" | sed 's/^/  /'; pause
}
log_journal_n() { read -rp "  How many journal lines [50]: " N; N="${N:-50}"; journalctl -u "$BOT" -n "$N" --no-pager; pause; }
log_journal()   { echo "following journal for $BOT — Ctrl-C to stop"; journalctl -u "$BOT" -n 100 -f; }
log_botfile() {
  [ -f "$BOTLOG" ] && { echo "tailing $BOTLOG — Ctrl-C to stop"; tail -n 100 -f "$BOTLOG"; } \
                   || { echo "no bot.log at $BOTLOG (is this a bot box?)"; pause; }
}
log_bot_tail() { [ -f "$BOTLOG" ] && tail -n 40 "$BOTLOG" || echo "no bot.log at $BOTLOG"; pause; }
feed_health() {
  local age; age=$(( $(date +%s) - $(stat -c %Y "${FEED_DB}-wal" 2>/dev/null || stat -c %Y "$FEED_DB" 2>/dev/null || echo 0) ))
  echo "  $FEED=$(svc "$FEED")  store_write_age_s=$age  ($FEED_DB)"
  _sql "$FEED_DB" "SELECT symbol, interval, COUNT(*) AS bars, datetime(MAX(ts_epoch_ms)/1000,'unixepoch','-4 hours') AS last_bar_et FROM candles GROUP BY symbol, interval ORDER BY interval;" 2>/dev/null | head -20; pause
}

# ── SERVICES ───────────────────────────────────────────────────────────────
restart_bot()  { confirm "restart $BOT on THIS box?"  && sudo systemctl restart "$BOT"  && echo "restarted → $(svc "$BOT")"; pause; }
restart_feed() { confirm "restart $FEED on THIS box?" && sudo systemctl restart "$FEED" && echo "restarted → $(svc "$FEED")"; pause; }
stop_bot()     { confirm "STOP $BOT (this box stops trading)?" && sudo systemctl stop "$BOT" && echo "stopped → $(svc "$BOT")"; pause; }
start_bot()    { confirm "start $BOT on THIS box?" && sudo systemctl start "$BOT" && echo "started → $(svc "$BOT")"; pause; }

# ── R SUITE (this box's own trades.db — no S3 here, by construction) ───────
_r_tool() {  # $1 = tests/<tool>.py ; the --db escape hatch is the whole point on a masked box
  local TOOL="$REPO/tests/$1"
  [ -f "$TOOL" ] || { echo "  🔴 $TOOL missing"; pause; return; }
  [ -f "$TRADES_DB" ] || { echo "  no trades.db at $TRADES_DB"; pause; return; }
  echo "    ENTER  = the engine epoch onward · a date = single session or START of a range · all = everything"
  read -rp "  Date (YYYY-MM-DD, ENTER, or 'all'): " d; local d2=""
  if [ -n "$d" ] && [ "$d" != "all" ] && [ "$d" != "ALL" ]; then read -rp "  END of range (ENTER = single day): " d2; fi
  local ARGS=(--db "$TRADES_DB")
  if [ "$d" = "all" ] || [ "$d" = "ALL" ]; then ARGS+=(--all-history)
  elif [ -n "$d" ] && [ -n "$d2" ]; then ARGS+=(--from "$d" --to "$d2")
  elif [ -n "$d" ]; then ARGS+=(--date "$d"); fi
  "$PY" "$TOOL" "${ARGS[@]}"; pause
}
r_ledger()      { echo; echo "  R, expectancy, capture + giveback per strategy/side/exit; selection vs extension."; _r_tool r_ledger.py; }
r_stop_sweep()  { echo; echo "  Bounds, not points: a cell matters only when its PESSIMISTIC net beats the book."; _r_tool stop_sweep.py; }
r_exit_replay() { echo; echo "  Trail fit on real premium paths."; _r_tool exit_replay.py; }
r_edge_scan()   { echo; echo "  Edge scan over the recorded book."; _r_tool edge_scan.py; }
trades_taken()  { echo; _sql "$TRADES_DB" "SELECT substr(entry_time,1,16) AS entered_utc, strategy, direction, strike, contracts AS n, ROUND(entry_premium,2) AS in_prem, ROUND(exit_premium,2) AS out_prem, ROUND(pnl_usd,0) AS pnl, status, substr(exit_reason,1,44) AS exit_reason FROM trades ORDER BY rowid DESC LIMIT 30;"; pause; }

# ── GIT & LAND (this box) ──────────────────────────────────────────────────
git_pull()  { echo "[pull] git pull --ff-only"; git pull --ff-only; pause; }
git_state() { git -C "$REPO" log -3 --oneline | cut -c1-110; echo; git -C "$REPO" status -s; echo; tail -1 docs/GENESIS-TEST.md | cut -c1-120; pause; }
mi_land()   { land_tarball; pause; }
mi_bake()   { bake; pause; }

bake() {
  # v4.4 (OTV4TEST r3) — LANDED ≠ BAKED. A landed revision is live only after
  # the service restarts on this box. Pull, prove the tree imports, restart.
  confirm "BAKE: git pull --ff-only, check_imports, restart $BOT on THIS box?" || { echo "cancelled"; return; }
  ( cd "$REPO" && git pull --ff-only ) || { echo "  pull FAILED — not restarting"; return 0; }
  ( cd "$REPO" && "$PY" tests/check_imports.py ) || { echo "  check_imports FAILED — NOT restarting; the tree does not start"; return 0; }
  sudo systemctl restart "$BOT" && echo "baked → $(svc "$BOT")  $(git -C "$REPO" log -1 --oneline)"
}
land_tarball() {
  # OTV4TEST r1 — the fork lands its own archives, because it is segregated
  # from control and no fleet deploy reaches it. Same lander as day_trader_pro,
  # driven the same way: the archive carries land.sh at its root, so the
  # BOOTSTRAP case (a fresh box with no lander yet) works identically to the
  # steady state and there is no second procedure to remember.
  # ⚠️ THE ARCHIVE'S OWN land.sh IS THE ONE THAT RUNS, never the repo's copy —
  # a delivery that changes the lander must be landed BY the lander it ships,
  # or a lander fix could never be applied.
  local arc n=0 pick
  mapfile -t arcs < <(ls -1t "$HOME"/*.tar.gz 2>/dev/null)
  if [ "${#arcs[@]}" = "0" ]; then
    echo "  no .tar.gz in $HOME — download one first."; return 0
  fi
  echo
  if [ "${#arcs[@]}" = "1" ]; then
    # v4.4 — one archive, no picker; the name is still shown so the operator
    # sees what is about to land.
    arc="${arcs[0]}"
    echo "  one archive in ~: $(basename "$arc")"
  else
    for arc in "${arcs[@]}"; do n=$((n+1)); printf '  %d) %s\n' "$n" "$(basename "$arc")"; done
    read -rp $'\nwhich archive (blank = cancel): ' pick
    [ -n "$pick" ] || return 0
    case "$pick" in (*[!0-9]*|"") echo "  not a number"; return 0 ;; esac
    [ "$pick" -ge 1 ] && [ "$pick" -le "${#arcs[@]}" ] || { echo "  out of range"; return 0; }
    arc="${arcs[$((pick-1))]}"
  fi
  rm -rf /tmp/fork_land && mkdir -p /tmp/fork_land
  tar xf "$arc" -C /tmp/fork_land || { echo "  extract FAILED — check the filename"; return 0; }
  [ -f /tmp/fork_land/land.sh ] || { echo "  archive carries no land.sh at its root — refusing."; return 0; }
  local halves
  halves="$(cd /tmp/fork_land && find . -maxdepth 2 -name land.spec -printf '%h\n' | sed 's|^\./||')"
  [ -n "$halves" ] || { echo "  archive carries no land.spec — refusing."; return 0; }
  echo "  halves: $halves"
  LAND_ARCHIVE="$arc" bash /tmp/fork_land/land.sh $halves
}

# ── THE MENU IS DATA — numbers are assigned at render time ─────────────────
MENU=(
  "SECTION|STATUS (this box)"
  "ITEM|status.py              live bot status snapshot|run_status"
  "ITEM|query.py               performance dashboard|run_query"
  "ITEM|DECISIONS NOW          (enter on / exit on, live snapshot)|run_decisions"
  "ITEM|debug_status.py        raw debug dump|run_debug"
  "ITEM|eod_summary.py         end-of-day summary|run_eod"

  "SECTION|SENSORS (this box's derived stores; read-only)"
  "ITEM|Manifold health board|s_manifold"
  "ITEM|Strategy notes        (what each engine SAW - signals, not trades)|s_notes"
  "ITEM|PLAN BOARD            (every plan, every check, per tick)|s_plan_board"
  "ITEM|PLAN ROWS             (the per-tick narrative, one strategy or all)|s_plan_rows"
  "ITEM|Plan ledger           (intent + terminal reason)|s_plan_ledger"
  "ITEM|Exit counterfactual   (flow vs the stop)|s_exit_cf"
  "ITEM|Fire snapshot         (derived vector at entry)|s_fire_snapshot"
  "ITEM|Surface               (charm / vanna / GEX)|s_surface"
  "ITEM|Indicators            (ADX / ATR / VWAP series)|s_indicators"
  "ITEM|Forks                 (built vs reject reason)|s_forks"
  "ITEM|Levels                (touches + retirements)|s_levels"
  "ITEM|LEVEL EVENTS          (WICKED / REJECTED / ACCEPTED - the rejection fact)|s_level_events"
  "ITEM|Order flow            (aggression + depth)|s_order_flow"

  "SECTION|TESTS"
  "ITEM|STANDING CHECKS       (what the lander runs; by hand between landings)|run_standing"
  "ITEM|full pytest suite     the 5 audit-defect tests|run_suite"
  "ITEM|market-data contract  standalone|run_contract"
  "ITEM|ORB retest v3.3       standalone|run_orb"
  "ITEM|verify_feed_v3.sh     ON-BOX, needs live services in RTH|run_feed_verify"

  "SECTION|DEBUG / LOGS (this box)"
  "ITEM|Service status        (bot + feed)|svc_status"
  "ITEM|Journal tail (last N)|log_journal_n"
  "ITEM|Journal follow        (Ctrl-C to stop)|log_journal"
  "ITEM|Feed health           (store freshness + last bar per interval)|feed_health"
  "ITEM|Bot log tail (last 40)|log_bot_tail"
  "ITEM|Bot log follow        (Ctrl-C to stop)|log_botfile"

  "SECTION|SERVICES (this box)"
  "ITEM|restart optionsbot|restart_bot"
  "ITEM|restart candle-feed|restart_feed"
  "ITEM|stop optionsbot|stop_bot"
  "ITEM|start optionsbot|start_bot"

  "SECTION|R SUITE (this box's trades.db)"
  "ITEM|TRADES TAKEN          (one line per trade, phone width)|trades_taken"
  "ITEM|R LEDGER              (R, expectancy, capture + selection vs extension)|r_ledger"
  "ITEM|Stop / TP sweep       (R surface over excursions)|r_stop_sweep"
  "ITEM|Exit replay           (trail fit on real premium paths)|r_exit_replay"
  "ITEM|Edge scan|r_edge_scan"

  "SECTION|GIT & LAND (this box - OTV4TEST only)"
  "ITEM|show commit / status / last ledger row|git_state"
  "ITEM|git pull --ff-only|git_pull"
  "ITEM|LAND a tarball from ~   (verify -> commit -> push; appends docs/GENESIS-TEST.md)|mi_land"
  "ITEM|BAKE                    (pull --ff-only, check_imports, restart the bot)|mi_bake"
)

menu_render() {
  local n=0 e kind rest label
  echo
  echo "═══ OTV4TEST devtools v2.0 — options-trader @ $(hostname) ═══════════════════"
  echo "  bot=$(svc "$BOT")  feed=$(svc "$FEED")  $(git -C "$REPO" log -1 --oneline 2>/dev/null | cut -c1-40)"
  for e in "${MENU[@]}"; do
    kind="${e%%|*}"; rest="${e#*|}"
    if [ "$kind" = "SECTION" ]; then echo; echo "  $rest"
    else n=$((n+1)); label="${rest%%|*}"; printf '  %2d) %s\n' "$n" "$label"; fi
  done
  echo; echo "   0) quit"
}
menu_dispatch() {  # $1 = number -> runs the function at that position
  local n=0 e kind rest fn
  for e in "${MENU[@]}"; do
    kind="${e%%|*}"; rest="${e#*|}"
    [ "$kind" = "ITEM" ] || continue
    n=$((n+1))
    if [ "$n" = "$1" ]; then fn="${rest##*|}"; "$fn"; return 0; fi
  done
  echo "unknown option: $1"
}

while true; do
  menu_render
  read -rp "select: " choice
  case "${choice:-}" in
    0) exit 0 ;;
    *[!0-9]*|"") echo "not a number" ;;
    *) menu_dispatch "$choice" ;;
  esac
done
