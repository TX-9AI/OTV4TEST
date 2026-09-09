#!/usr/bin/env bash
# ==========================================================================
# devtools.sh  v4.4
# v4.4  2026-09-08  OTV4TEST r3 — item 40 auto-selects when exactly ONE archive
#       sits in ~ (the name is still printed; the picker appears only for two
#       or more), and item 41 BAKE: git pull --ff-only, check_imports, then
#       restart the bot — the step that makes a landed revision live.
# v4.3  2026-09-08  OTV4TEST r1 — item 40, LAND a tarball. This fork is
#       segregated from control (no EC2 Name tag, no fleet fan-out reaches it),
#       so it lands its own archives with its own lander, appending
#       docs/GENESIS-TEST.md rather than the inherited docs/GENESIS.md.
#       ⚠️ THE ARCHIVE'S land.sh RUNS, NOT THE REPO'S — so a delivery that
#       fixes the lander is landed by the lander it ships, and a fresh box
#       bootstraps by the same path it uses forever after.
# v4.2  2026-09-08  r322 — 🔴 THE COMMENT MARKERS. r65 wrote its changelog
#       entry into this header WITHOUT them, so lines 4-6 were SHELL, not
#       prose: `v4.1: command not found`, then a syntax error on the
#       parenthesis in "(delivery)" — and a syntax error aborts the parse, so
#       this script has done NOTHING since 2026-08-25. Four files, one commit,
#       identical three lines.
# v4.1  2026-08-25  r65 EXORCISM: every mention of the retired classification
#       system removed - identifiers, comments, docstrings, schema. The word
#       does not appear in this tree. Full accounting: REMOVAL_LOG (delivery).

# Control-side service menu.
#
# v4.0  2026-08-19  Ported from options_trader_v3 at the OTV4 split.
#
# INHERITED DOCTRINE
# MEASUREMENTS AND CONSTRAINTS CARRIED FROM v3 - NOT A CHANGELOG.
# Dated release framing and trivia are stripped; what remains is the
# reasoning behind the thresholds, the design guarantees, and the
# defects that recur when forgotten. WORKING_AGREEMENT 32 requires
# this block be read before the file is edited.
#
#!/usr/bin/env bash
# devtools.sh v1.0 — PER-BOX operator menu for a single options_trader box.
# Vertigo Capital / options_trader_v3.
# This is the break-glass companion to the two existing menus:
#   day_trader_pro/devtools.sh  — FLEET-WIDE control-server ops (the primary tool)
#   shadow_devtools.sh          — the shadow (QQQ-TEST) subsystem
# Use THIS when you're SSH'd into one bot box (e.g. over Termius) and, on the
# rare occasion you can't drive it from control, need to see what this box is
# doing, run the suite, or bounce a service locally.
# Thin dispatcher by design: every item shells out to the real script/unit —
# no logic lives here. Run from the repo root:  ./devtools.sh
# ==========================================================================
set -uo pipefail

# --- self-locate: correct whether this checkout is ~/options-trader (a bot box)
#     or ~/options-trader-v3 (the control replay checkout). Never hardcoded. ----
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$REPO/venv/bin/python"
export PYTHONPATH="$REPO"

BOT="optionsbot"          # systemd unit (setup_ec2.sh SERVICE_NAME)
FEED="candle-feed"        # systemd unit (single DXFeed producer)
BOTLOG="$REPO/bot.log"    # ExecStartPre touches this in the unit

cd "$REPO" 2>/dev/null || { echo "cannot cd to $REPO"; exit 1; }
[ -x "$PY" ] || echo "warn: no venv python at $PY — python items will fail"

pause() { read -rp $'\n[enter] '; }
confirm() { read -rp "$1 [y/N] " a; [ "$a" = "y" ] || [ "$a" = "Y" ]; }
svc() { systemctl is-active "$1" 2>/dev/null || echo "unknown"; }

# ---- status / dashboards (reads this box's live DB + log) -------------------
run_status()  { "$PY" status.py; }
run_query()   { "$PY" query.py; }
run_debug()   { "$PY" debug_status.py; }
run_eod()     { "$PY" eod_summary.py; }

# ---- tests -----------------------------------------------------------------
PYTEST_SUITE=(
  tests/test_entry_fill_confirmation.py
  tests/test_mode_isolation.py
  tests/test_phantom_pnl_recovery.py
  tests/test_roll_is_real.py
  tests/test_runner_refinements.py
)
run_suite() {
  if ! "$PY" -c "import pytest" 2>/dev/null; then
    echo "pytest not in this venv. Install with:"
    echo "  $PY -m pip install pytest"
    return 1
  fi
  echo "── full regression suite (go-live gate) ─────────────────────────────"
  "$PY" -m pytest "${PYTEST_SUITE[@]}" -v
}
run_contract() { "$PY" -m tests.test_market_data_contract; }
run_orb()      { "$PY" tests/test_orb_retest_v33.py; }
run_feed_verify() {
  echo "verify_feed_v3.sh must run ON-BOX during RTH with $FEED + $BOT live (paper)."
  confirm "run it now?" || { echo "skipped"; return; }
  bash tests/verify_feed_v3.sh; echo "exit=$?"
}

# ---- per-box service management --------------------------------------------
svc_status() {
  echo "── this box ─────────────────────────────────────────────────────────"
  echo "  $BOT  : $(svc "$BOT")"
  echo "  $FEED : $(svc "$FEED")"
  systemctl --no-pager -l status "$BOT" "$FEED" 2>/dev/null | grep -E "Active:|Main PID:|Loaded:" | sed 's/^/  /'
}
log_journal() { echo "following journal for $BOT — Ctrl-C to stop"; journalctl -u "$BOT" -n 100 -f; }
log_botfile() {
  [ -f "$BOTLOG" ] && { echo "tailing $BOTLOG — Ctrl-C to stop"; tail -n 100 -f "$BOTLOG"; } \
                   || echo "no bot.log at $BOTLOG (is this a bot box?)"
}
restart_bot()  { confirm "restart $BOT on THIS box?"  && sudo systemctl restart "$BOT"  && echo "restarted → $(svc "$BOT")"; }
restart_feed() { confirm "restart $FEED on THIS box?" && sudo systemctl restart "$FEED" && echo "restarted → $(svc "$FEED")"; }
stop_bot()     { confirm "STOP $BOT (this box stops trading)?" && sudo systemctl stop "$BOT" && echo "stopped → $(svc "$BOT")"; }
start_bot()    { sudo systemctl start "$BOT" && echo "started → $(svc "$BOT")"; }

# ---- git (this box) --------------------------------------------------------
git_pull()   { echo "[pull] git pull --ff-only"; git pull --ff-only; }
git_pull_restart() {
  # the July-16 recovery move, single-box: pull the fix, bounce the bot so the
  # box re-adopts its open positions cleanly on restart.
  confirm "pull --ff-only AND restart $BOT on this box?" || { echo "cancelled"; return; }
  git pull --ff-only && sudo systemctl restart "$BOT" && echo "restarted → $(svc "$BOT")"
}
git_state()  { git -C "$REPO" log -1 --oneline; echo; git -C "$REPO" status -s; }

menu() {
  cat <<MENU

═══ options_trader devtools — $(basename "$REPO") @ $(hostname) ══════════════
  bot=$(svc "$BOT")  feed=$(svc "$FEED")

  STATUS (this box)
    1) status.py            live bot status snapshot
    2) query.py             performance dashboard
    3) debug_status.py      raw debug dump
    4) eod_summary.py       end-of-day summary

  TESTS
   10) full pytest suite    the 5 audit-defect tests  ← go-live gate
   11) market-data contract standalone
   12) ORB retest v3.3      standalone
   14) verify_feed_v3.sh    ON-BOX, needs live services in RTH

  SERVICES (this box)
   20) service status       $BOT + $FEED
   21) journal -f           follow $BOT log
   22) tail bot.log
   23) restart $BOT
   24) restart $FEED
   25) stop $BOT
   26) start $BOT

  DEPLOY (this box — OTV4TEST only)
   40) LAND a tarball from ~   the fork lander; appends docs/GENESIS-TEST.md
   41) BAKE                    pull --ff-only, check_imports, restart the bot

  GIT (this box)
   30) git pull --ff-only
   31) pull + restart $BOT  (single-box recovery)
   32) show commit / status

    0) quit
MENU
  read -rp $'\nselect: ' choice
  case "$choice" in
    1) run_status ;;   2) run_query ;;   3) run_debug ;;   4) run_eod ;;
    10) run_suite ;;  11) run_contract ;; 12) run_orb ;;   13) run_gate ;; 14) run_feed_verify ;;
    20) svc_status ;; 21) log_journal ;; 22) log_botfile ;;
    23) restart_bot ;; 24) restart_feed ;; 25) stop_bot ;; 26) start_bot ;;
    30) git_pull ;;   31) git_pull_restart ;; 32) git_state ;;
    40) land_tarball ;;
    41) bake ;;
    0) exit 0 ;;
    *) echo "unknown option: $choice" ;;
  esac
  pause
}

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

while true; do menu; done
