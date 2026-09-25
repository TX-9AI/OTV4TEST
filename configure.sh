#!/usr/bin/env bash
# ==========================================================================
# configure.sh  v4.10
# v4.10 2026-09-25  OTV4TEST r138 — DONE STARTS THE BOT. Operator: the bot is "not
#       started by default and then when I set all the variables in configure and
#       exit out of the menu that resets everything and starts it". setup_ec2.sh
#       v4.7 installs optionsbot NOT enabled and NOT started; `finish_session`
#       (the Done path) now ENABLES it (so it survives reboots and wakes) and
#       STARTS it when it is not running, or RESTARTS it when it is running and
#       something changed. Running and unchanged: nothing happens, as before.
# v4.9  2026-09-24  OTV4TEST r136 — ITEM 10 IS DATA CAPTURE: MANAGED OR STANDALONE.
#       Operator: *"a toggle in configure.sh call it 'managed' or 'standalone'
#       data capture"*. `change_data_capture` runs deploy/data_capture.sh - the
#       ONE implementation setup_ec2.sh also calls - and the label is read from
#       the UNITS (data_capture.sh status), never from a flag file. It does not
#       touch the bot unit, so it does not set CHANGED and the bot is not
#       restarted for it. "Done" moves to 11; the prompt names 1-11.
# v4.8  2026-09-24  OTV4TEST r127 — ITEM 7 IS THE PIN-PROXIMITY GATE; THE RELAXED
#       ENTRY TOGGLE IS REMOVED. Operator: *"make it replace the relaxed entry
#       toggle. Since we don't do relaxed entries here."* and, turning r97's gate
#       off pending data: *"I would prefer to interact with it there."*
#       `change_pin_gate` writes OT_PIN_PROXIMITY_ACTIVE (1 on / 0 off) with the
#       same set_env + reload_daemon every item uses. `pin_gate_label` shows what
#       the operator SET, or "not set" plus the default read from config.py — the
#       r91 rule: nothing is displayed that he did not choose, and the default is
#       never hardcoded here, where it would rot the day config.py moves.
#       ⚠️ RELAXED ENTRY IS NOT DELETED FROM THE CODE: strategy/relaxed.py still
#       honours OT_RELAXED_ENTRY if a unit sets it; this box does not (measured
#       2026-09-24: unset), and unset is OFF. Only the menu item is gone.
#       ⚠️ THE GEX PIN BUTTERFLY DOES NOT READ THIS KEY — its PINNING condition is
#       foundational in strategy/gex_pin_butterfly.py. The gate is main.py:4802,
#       long_debit entries only.
#       Also fixes the out-of-range prompt, which said 1-9 on a 10-item menu.
# v4.7  2026-09-22  r91 — A DECLARATION SURFACE PRINTS DECLARATIONS. Operator:
#       *"Configure.sh is where I enter env variables. The only thing it
#       displays is the current variables that the operator has chosen... The
#       per trade differences due to stop width should never be displayed
#       there."* The r201 ORB "spot hint" READ orb_state.json and printed the
#       live price into this script — machine state on a declaration screen —
#       and is DELETED. `fmt_declared` prints what was set or "not set", never
#       another key's value dressed as a default. ORB ramp TOP
#       (OT_ORB_BUDGET_USD) and ORB ramp START (OT_ORB_RISK_USD) are now a
#       settable pair: the START governed the whole ORB sizing ramp from r44
#       and was never once declared or displayed.
# v4.6  2026-09-17  OTV4TEST r34 — MOVED BACK TO THE REPO ROOT (operator's ruling).
#   r14 moved it to deploy/ because it is a .sh, but it installs no unit, touches
#   no systemd and runs on no timer — it is the sixth operator reader and belongs
#   beside status.py and query.py. No behaviour change.
# v4.5  2026-09-11  OTV4TEST r14 — moved from the repo root to deploy/ (root cleanup); no behaviour change.
#
# v4.4  2026-08-31  r203 — THE r201 SPOT HINT WAS BROKEN AND BAKED. It read a
#   `data/` subdirectory that does not exist, and `2>/dev/null` made the
#   failure look like a deliberate blank. Paths now come from config.py;
#   stderr is visible; the land gate RUNS the function and requires output.
#   🔴 r201's gate checked that the function existed and that this file
#   parsed. Presence and a clean parse are not evidence that a display
#   displays.
#
# v4.3  2026-08-31  r201 — menu item 8: ORB BUDGET (OT_ORB_BUDGET_USD), set
#   PER UNDERLYING. Shows SPOT as the reference — live from orb_state.json,
#   or derived from the last trade's underlying_entry, labelled either way.
#   ⚠️ The default fails closed at one trade's risk, so an unconfigured box
#   trades SMALL; r91 — the menu now reads "not set" rather than borrowing
#   another key's value, because a declaration surface prints declarations.
#   ⚠️ Fixed in passing: the prompt said "between 1 and 7" on an 8-item menu.
# Per-box configuration.
#
# v4.2  2026-08-20  change_relaxed now calls reload_daemon after set_env, like
#       every other change_*. set_env edits the UNIT FILE; without the reload
#       systemd restarts from its cached copy, so the bot runs the OLD value
#       while the menu reports the new one. Pinned by check_configure_relaxed
#       C6: any function that calls set_env must also call reload_daemon.
#
# v4.1  2026-08-20  Option 7 (relaxed entry) called an undefined `confirm`,
#       so it always took the else branch: it could never be switched ON, and
#       opening the item wrote OT_RELAXED_ENTRY=0. Now calls ask_yn, the
#       helper the rest of the file uses. Both branches are executed by
#       tests/check_configure_relaxed.py, which also traps
#       command-not-found so a future undefined helper cannot fail quietly.
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
# repo-wide v3.0 bump: Yahoo-Finance purge & data stream
#         mapping optimization (single shared TastyTrade candle feed). No
#         logic change in this file.
#  options_trader v2.0  —  Live Configuration Manager
#  v1.0 — original release
#  replaced SMS/Twilio with Telegram
#  swapped menu order: Telegram now 4, TT credentials now 5
#  fixed menu display lines to match handler order
#  auto restart on exit if changes made, no prompt
#  wipe trades.db on instrument change (paper mode only);
#          ORB range auto-fetched for new instrument via get_orb_range.py
#  add Daily loss cap override menu (OT_DAILY_LOSS_LIMIT)
#  add single-name instruments (directional-only) to the
#          instrument menu for wider paper-trading coverage
#  archive trades.db (+WAL sidecars) on EVERY mode switch,
#          labeled by the outgoing mode (trades_paper_*.db / trades_live_*.db).
#          Paper and live histories never share a file (audit defect Q);
#          companion to trade_logger v3.7 mode-scoped queries.
#  going LIVE now reports that broker reconciliation
#          auto-enables with the mode (config.py v1.8 default follows
#          OT_PAPER_TRADING); show_config gains a "Broker reconcile" status
#          line; warns loudly if OT_BROKER_RECONCILE=False pins it off.
#  instrument picker now types the ticker (validated against
#          config.STRIKE_INCREMENTS) instead of a numbered menu — scales to the
#          full screener universe
#  Run this anytime to view or change bot settings.
#  Changes take effect on the NEXT bot start — the bot is
#  never restarted automatically to avoid mid-session surprises.
#  Usage:
#    ./configure.sh          — interactive menu
#    ./configure.sh --show   — print current config and exit
# ==========================================================================
SERVICE_NAME="optionsbot"
BOT_DIR="$HOME/options-trader"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# ── Colours ──────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

print_banner() {
    echo ""
    echo -e "${BOLD}${CYAN}============================================================${RESET}"
    echo -e "${BOLD}${CYAN}  options_trader  —  Configuration Manager${RESET}"
    echo -e "${BOLD}${CYAN}============================================================${RESET}"
    echo ""
}

print_ok()   { echo -e "  ${GREEN}✓${RESET}   $1"; }
print_warn() { echo -e "  ${YELLOW}⚠${RESET}   $1"; }
print_info() { echo -e "  ${CYAN}→${RESET}  $1"; }
ask()        { read -p "    $1: " "$2"; }
ask_secret() { read -s -p "    $1: " "$2"; echo ""; }
ask_yn()     {
    while true; do
        read -p "    $1 [y/n]: " yn
        case "$yn" in [Yy]) return 0;; [Nn]) return 1;; esac
    done
}

# ── Read a single Environment= value from the unit file ──────
get_env() {
    sudo grep -oP "(?<=Environment=${1}=).*" "$UNIT_FILE" 2>/dev/null | tail -1 || echo ""
}

# ── r91 — WHAT A DECLARATION SURFACE IS ALLOWED TO PRINT ─────
# 🔴 THE OPERATOR'S RULING, 2026-09-22: *"Configure.sh is where I enter env
# variables. The only thing it displays is the current variables that the
# operator has chosen... The per trade differences due to stop width should
# never be displayed there."* And: *"they are STATIC. They never change unless
# I change them."*
# So a value shows as the operator SET it, or it shows as unset. It never
# borrows another key's value and dresses it as a default — that prints a
# number he did not choose on the line where he chooses it, which is how
# `OT_ORB_RISK_USD` governed the whole ORB sizing ramp for four days while
# being invisible here (r91). This also cost a live-state reader: the r201 ORB
# "spot hint" read `orb_state.json` and printed the running price INTO this
# script, which is machine state, not a declaration.
fmt_declared() {
    if [[ -n "$1" ]]; then
        printf '$%s' "$1"
    else
        printf 'not set'
    fi
}

# ── Update or add an Environment= line in the unit file ──────
set_env() {
    local key="$1" val="$2"
    if sudo grep -q "Environment=${key}=" "$UNIT_FILE" 2>/dev/null; then
        sudo sed -i "s|Environment=${key}=.*|Environment=${key}=${val}|" "$UNIT_FILE"
    else
        sudo sed -i "/ExecStartPre=/i Environment=${key}=${val}" "$UNIT_FILE"
    fi
}

reload_daemon() {
    sudo systemctl daemon-reload
}

# v2.0 (audit defect Q): archive the trade DB on EVERY mode switch so paper and
# live histories never share a file. mv on the same filesystem keeps the inode,
# so a still-running bot finishes its session writing into the archive; the
# restarted bot creates a fresh trades.db in the new mode. WAL sidecars move
# with the DB so no unflushed rows are lost.
archive_trades_db() {
    local from_mode="$1"   # outgoing mode: "paper" or "live"
    local db="$BOT_DIR/trades.db"
    if [[ ! -f "$db" ]]; then
        print_info "No trades.db to archive — starting the new mode fresh."
        return
    fi
    local stamp dest
    stamp=$(date +%Y%m%d_%H%M%S)
    dest="$BOT_DIR/trades_${from_mode}_${stamp}.db"
    mv "$db" "$dest"
    [[ -f "${db}-wal" ]] && mv "${db}-wal" "${dest}-wal"
    [[ -f "${db}-shm" ]] && mv "${db}-shm" "${dest}-shm"
    print_ok "Archived ${from_mode} trade history → $(basename "$dest")"
    print_info "A fresh trades.db is created on next start — ${from_mode} P&L can never leak into the new mode."
}

bot_is_running() {
    systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null
}

# ──────────────────────────────────────────────────────────────
# SHOW CURRENT CONFIG
# ──────────────────────────────────────────────────────────────
show_config() {
    local instrument risk paper account

    if [[ ! -f "$UNIT_FILE" ]]; then
        echo -e "  ${RED}Service unit not found.${RESET}"
        echo -e "  Run setup_ec2.sh first to install the bot."
        return 1
    fi

    instrument=$(get_env "OT_INSTRUMENT")
    risk=$(get_env "OT_RISK_USD")
    paper=$(get_env "OT_PAPER_TRADING")
    account=$(get_env "TT_ACCOUNT_NUMBER")
    telegram_token=$(get_env "TELEGRAM_TOKEN")
    telegram_chat=$(get_env "TELEGRAM_CHAT_ID")

    local mode_label
    if [[ "$paper" == "False" ]]; then
        mode_label="${RED}${BOLD}🔴 LIVE — real money${RESET}"
    else
        mode_label="${GREEN}📄 PAPER — simulated fills${RESET}"
    fi

    local status_label
    if bot_is_running; then
        status_label="${GREEN}● running${RESET}"
    else
        status_label="${YELLOW}○ stopped${RESET}"
    fi

    echo -e "  ${BOLD}Current Configuration${RESET}"
    echo -e "  ─────────────────────────────────────────"
    echo -e "  Bot status:     $(echo -e $status_label)"
    echo -e "  Instrument:     ${BOLD}${instrument:-not set}${RESET}"
    echo -e "  Risk per trade: ${BOLD}\$${risk:-not set}${RESET}"
    local dll=$(get_env "OT_DAILY_LOSS_LIMIT")
    echo -e "  Daily loss cap: ${BOLD}$(fmt_declared "$dll")${RESET}"
    echo -e "  Pin gate:       ${BOLD}$(pin_gate_label)${RESET}"
    echo -e "  Data capture:   ${BOLD}$(data_capture_label)${RESET}"
    echo -e "  Trading mode:   $(echo -e $mode_label)"
    local rec_pin rec_label
    rec_pin=$(get_env "OT_BROKER_RECONCILE")
    if [[ "$rec_pin" == "True" ]]; then rec_label="on (pinned)"
    elif [[ "$rec_pin" == "False" ]]; then rec_label="OFF (pinned)"
    elif [[ "$paper" == "False" ]]; then rec_label="on (auto, follows LIVE)"
    else rec_label="off (auto, follows PAPER)"; fi
    echo -e "  Broker reconcile: ${BOLD}${rec_label}${RESET}"
    echo -e "  TT Account:     ${BOLD}${account:-not set}${RESET}"
    local tg_status
    if [[ -n "$telegram_token" ]]; then
        tg_status="✓ enabled (chat ${telegram_chat})"
    else
        tg_status="— disabled"
    fi
    echo -e "  Telegram:       ${BOLD}${tg_status}${RESET}"
    echo -e "  ─────────────────────────────────────────"
    echo ""

    if bot_is_running; then
        print_warn "Bot is currently running. Changes take effect on next start."
    else
        print_warn "Bot is NOT running - it starts (and is enabled at boot) when you choose Done."
    fi
}

# ──────────────────────────────────────────────────────────────
# MENU ACTIONS
# ──────────────────────────────────────────────────────────────

change_instrument() {
    local current allowed full choice
    current=$(get_env "OT_INSTRUMENT")
    # Pull the tradeable universe straight from config.py — single source of truth.
    allowed=$(cd "$BOT_DIR" && python3 -c "import config; print(' '.join(sorted(config.STRIKE_INCREMENTS)))" 2>/dev/null)
    full=$(cd "$BOT_DIR" && python3 -c "import config; print(' '.join(sorted(config.FULL_STRATEGY_INSTRUMENTS)))" 2>/dev/null)
    if [ -z "$allowed" ]; then
        print_warn "Could not read the symbol list from config.py."
        return
    fi
    echo ""
    echo -e "  Current instrument: ${BOLD}${current}${RESET}"
    echo ""
    echo -e "  ${BOLD}Full strategy${RESET} (condor/butterfly):  ${full}"
    echo -e "  ${BOLD}Directional only${RESET} (ORB + sweep):    everything else"
    echo ""
    echo -e "  Tradeable symbols:"
    echo "    ${allowed}"
    echo ""
    while true; do
        read -p "    Enter ticker [ENTER to keep ${current}]: " choice
        choice=$(echo "${choice:-$current}" | tr '[:lower:]' '[:upper:]')
        if [[ "$choice" == "$current" ]]; then
            print_info "Unchanged: ${current}"; return
        fi
        if echo "$allowed" | tr ' ' '\n' | grep -qxF "$choice"; then
            NEW_INST="$choice"; break
        fi
        print_warn "Unknown ticker '${choice}'. Pick one from the list above."
    done
    set_env "OT_INSTRUMENT"  "$NEW_INST"
    set_env "OT_BOT_NAME"    "OptionsTrader-${NEW_INST}"
    reload_daemon
    print_ok "Instrument updated to ${BOLD}${NEW_INST}${RESET}."
    # Wipe trades.db in paper mode — old trades from a different instrument
    # are meaningless and pollute the P&L dashboard
    local paper
    paper=$(get_env "OT_PAPER_TRADING")
    if [[ "$paper" != "False" ]]; then
        rm -f "$BOT_DIR/trades.db"
        print_ok "Paper trade history cleared (instrument changed)."
    fi
}

change_risk() {
    local current
    current=$(get_env "OT_RISK_USD")
    echo ""
    echo -e "  Current risk per trade: ${BOLD}\$${current}${RESET}"
    echo ""
    while true; do
        read -p "    New risk per trade in \$ [ENTER to keep \$${current}]: " input
        if [[ -z "$input" ]]; then
            print_info "Unchanged: \$${current}"
            return
        fi
        if [[ "$input" =~ ^[0-9]+(\.[0-9]+)?$ ]] && (( $(echo "$input > 0" | bc -l) )); then
            set_env "OT_RISK_USD" "$input"
            reload_daemon
            print_ok "Risk per trade updated to ${BOLD}\$$input${RESET}."
            return
        fi
        print_warn "Please enter a positive number (e.g. 200 or 150.50)."
    done
}

# ── r127 — THE PIN-PROXIMITY GATE (r97), ON OR OFF ─────────────────────────
# r97 refuses a DIRECTIONAL DEBIT (ORB, Breakout, Runaway, VOLT, the hunt) when
# GEX reads PINNING and price sits within 0.32 of an expected move of the pin.
# Operator, 2026-09-24, after it replayed to -$739 net across every fire and cut
# 18 of 24 trades on 09-21's trend day: *"Turn it off. We need to collect more
# data before ruling on it."* The data keeps collecting with the gate OFF:
# every fire_snapshot records pin_em_fraction, pin_strike and gex_environment.
pin_gate_label() {
    local v dflt
    v=$(get_env "OT_PIN_PROXIMITY_ACTIVE")
    if [[ "$v" == "1" ]]; then printf 'ON'; return; fi
    if [[ "$v" == "0" ]]; then printf 'OFF'; return; fi
    if [[ -n "$v" ]]; then printf 'OFF (set to %s; only 1 is on)' "$v"; return; fi
    # Unset: say so, and name the default from config.py rather than from memory.
    # The key is removed from THIS shell's env first so the answer is the code's.
    dflt=$(cd "$BOT_DIR" && env -u OT_PIN_PROXIMITY_ACTIVE python3 -c \
        "import config; print('ON' if config.PIN_PROXIMITY_ACTIVE else 'OFF')")
    printf 'not set (code default: %s)' "${dflt:-UNREADABLE - config.py did not import}"
}

# ── r136 — DATA CAPTURE: managed (the conductor owns this box's data) or
# standalone (nothing is pushed). One implementation: deploy/data_capture.sh.
data_capture_label() {
    bash "$BOT_DIR/deploy/data_capture.sh" status 2>/dev/null | head -1 | sed 's/^data capture: //'
}

change_data_capture() {
    echo ""
    echo "  Data capture: $(data_capture_label)"
    echo ""
    echo "  MANAGED    - the day_trader_pro conductor owns this box's data: S3 push,"
    echo "               candle-logger and the 16:45 self-close ON; this box's own"
    echo "               16:05 purge OFF (the conductor runs it). Pushes as its own"
    echo "               symbol; never the VIX family."
    echo "  STANDALONE - nothing is pushed (s3-push masked); this box purges itself"
    echo "               at 16:05. The reference QQQ box is standalone."
    echo ""
    if ask_yn "Make this box MANAGED?"; then
        bash "$BOT_DIR/deploy/data_capture.sh" managed
    else
        bash "$BOT_DIR/deploy/data_capture.sh" standalone
    fi
}

change_pin_gate() {
    echo ""
    echo "  Pin-proximity gate: $(pin_gate_label)"
    echo ""
    echo "  ON  - a directional debit (ORB, Breakout, Runaway, VOLT, hunt) is"
    echo "        REFUSED when GEX is PINNING and price is within 0.32 EM of"
    echo "        the pin. (r97)"
    echo "  OFF - no refusal. Pin distance is still recorded on every fire."
    echo "  The GEX pin butterfly is NOT affected either way."
    echo ""
    if ask_yn "Turn the pin-proximity gate ON?"; then
        set_env "OT_PIN_PROXIMITY_ACTIVE" "1"
        reload_daemon
        echo "  Pin-proximity gate ON."
    else
        set_env "OT_PIN_PROXIMITY_ACTIVE" "0"
        reload_daemon
        echo "  Pin-proximity gate OFF."
    fi
}



# ── r203 — SPOT, FOR SIZING THE ORB BUDGET AGAINST ────────────────────────
# 🔴 THIS FUNCTION SHIPPED BROKEN IN r201 AND THE FLEET BAKED IT. It read
# `<install>/data/orb_state.json` and `<install>/data/trades.db`. Neither
# exists: both files sit at the install root, and both paths were already in
# config.py — DB_PATH at 1604, LOG_FILE at 1613 — with orb_state.json written
# beside the log (main.py ~1358). I invented a subdirectory instead of reading
# two lines I had edited an hour earlier.
# 🔴 AND `2>/dev/null` TURNED THE FAILURE INTO A BLANK LINE. That was a
# deliberate choice, made to keep this screen tidy, on a feature whose entire
# job is to display a number. Silence over noise is the failure class this
# project exists to hunt, committed inside a display.
# 🔴 THE TEST COULD NOT FAIL. I built a fixture directory matching my own guess
# and verified against it. It passed, and it proved only that the guess was
# consistent with itself. The r201 land gate asserted the function EXISTED and
# that configure.sh PARSED — neither asks whether it produces output.
# 🔑 THE FIX, AND WHY IT IS SHAPED THIS WAY:
#   · paths are IMPORTED from config, never spelled here, so a future move of
#     either file cannot silently blank this display;
#   · stderr is NOT suppressed — every failure names itself and its path;
#   · the r203 land gate RUNS this body against a planted repo and REQUIRES a
#     Spot line back, and refuses both a literal `data/` path and any
#     re-suppression of stderr on this call.
change_orb_risk() {
    local current
    current=$(get_env "OT_ORB_RISK_USD")
    echo ""
    echo -e "  ${BOLD}ORB ramp START${RESET}  (OT_ORB_RISK_USD)"
    echo ""
    echo -e "  Current: ${BOLD}$(fmt_declared "$current")${RESET}"
    echo ""
    while true; do
        read -p "    New ORB ramp start in \$, ENTER to keep: " input
        if [[ -z "$input" ]]; then
            print_info "Unchanged."
            return
        fi
        if [[ "$input" =~ ^[0-9]+(\.[0-9]+)?$ ]] && (( $(echo "$input > 0" | bc -l) )); then
            set_env "OT_ORB_RISK_USD" "$input"
            reload_daemon
            print_ok "ORB ramp start updated to ${BOLD}\$$input${RESET}."
            return
        fi
        print_warn "Enter a positive number, or ENTER to keep."
    done
}

change_orb_budget() {
    local current risk
    current=$(get_env "OT_ORB_BUDGET_USD")
    risk=$(get_env "OT_RISK_USD")
    echo ""
    echo -e "  ${BOLD}ORB ramp TOP${RESET}  (OT_ORB_BUDGET_USD)"
    echo ""
    echo -e "  Current: ${BOLD}$(fmt_declared "$current")${RESET}"
    echo ""
    while true; do
        read -p "    New ORB budget in \$, 'r' to reset to default, ENTER to keep: " input
        if [[ -z "$input" ]]; then
            print_info "Unchanged."
            return
        fi
        if [[ "$input" == "r" ]]; then
            set_env "OT_ORB_BUDGET_USD" "$risk"
            reload_daemon
            print_ok "ORB budget reset to the per-trade risk default (\$${risk})."
            return
        fi
        if [[ "$input" =~ ^[0-9]+(\.[0-9]+)?$ ]] && (( $(echo "$input > 0" | bc -l) )); then
            set_env "OT_ORB_BUDGET_USD" "$input"
            reload_daemon
            print_ok "ORB budget updated to ${BOLD}\$$input${RESET}."
            return
        fi
        print_warn "Enter a positive number, 'r' to reset, or ENTER to keep."
    done
}

change_daily_loss() {
    local current risk
    current=$(get_env "OT_DAILY_LOSS_LIMIT")
    risk=$(get_env "OT_RISK_USD")
    echo ""
    echo -e "  ${BOLD}Daily loss cap${RESET} — halts NEW entries once the day's NET"
    echo -e "  P&L is down by this amount. Open trades still exit normally."
    echo -e "  Current: ${BOLD}$(fmt_declared "$current")${RESET}"
    echo ""
    while true; do
        read -p "    New cap in \$, 'r' to reset to risk default, ENTER to keep: " input
        if [[ -z "$input" ]]; then
            print_info "Unchanged."
            return
        fi
        if [[ "$input" == "r" ]]; then
            set_env "OT_DAILY_LOSS_LIMIT" "$risk"
            reload_daemon
            print_ok "Daily loss cap reset to per-trade risk (\$${risk})."
            return
        fi
        if [[ "$input" =~ ^[0-9]+(\.[0-9]+)?$ ]] && (( $(echo "$input > 0" | bc -l) )); then
            set_env "OT_DAILY_LOSS_LIMIT" "$input"
            reload_daemon
            print_ok "Daily loss cap updated to ${BOLD}\$$input${RESET}."
            return
        fi
        print_warn "Enter a positive number, 'r' to reset, or ENTER to keep."
    done
}

change_mode() {
    local current
    current=$(get_env "OT_PAPER_TRADING")
    echo ""
    if [[ "$current" == "False" ]]; then
        echo -e "  Current mode: ${RED}${BOLD}🔴 LIVE${RESET}"
        echo ""
        if ask_yn "Switch to PAPER mode?"; then
            set_env "OT_PAPER_TRADING" "True"
            reload_daemon
            archive_trades_db "live"
            print_ok "Switched to ${BOLD}📄 PAPER mode${RESET}."
        else
            print_info "Unchanged: LIVE."
        fi
    else
        echo -e "  Current mode: ${GREEN}📄 PAPER${RESET}"
        echo ""
        print_warn "You are about to enable LIVE TRADING."
        print_warn "Real orders will be placed with real money."
        echo ""
        read -p "    Type  LIVE  to confirm: " confirm
        if [[ "$confirm" == "LIVE" ]]; then
            set_env "OT_PAPER_TRADING" "False"
            reload_daemon
            archive_trades_db "paper"
            print_ok "Switched to ${RED}${BOLD}🔴 LIVE mode${RESET}."
            # v1.9: broker reconciliation follows the mode (config.py default) —
            # LIVE turns it on automatically unless OT_BROKER_RECONCILE pins it.
            local rec_pin
            rec_pin=$(get_env "OT_BROKER_RECONCILE")
            if [[ "$rec_pin" == "False" ]]; then
                print_warn "Broker reconciliation is PINNED OFF (OT_BROKER_RECONCILE=False in the unit file) — phantoms and manual closes will NOT be reconciled."
            else
                print_ok "Broker reconciliation: auto-enabled with LIVE mode."
            fi
        else
            print_info "Confirmation not received — mode unchanged."
        fi
    fi
}

change_tt_credentials() {
    echo ""
    echo -e "  Update your TastyTrade OAuth credentials."
    echo -e "  ${CYAN}Leave blank and press ENTER to keep the current value.${RESET}"
    echo ""

    local current_secret current_token current_account
    current_secret=$(get_env "TT_CLIENT_SECRET")
    current_token=$(get_env "TT_REFRESH_TOKEN")
    current_account=$(get_env "TT_ACCOUNT_NUMBER")

    read -s -p "    New Client Secret  [ENTER to keep current]: " new_secret; echo ""
    read -s -p "    New Refresh Token  [ENTER to keep current]: " new_token;  echo ""
    read -p    "    Account Number     [ENTER to keep ${current_account}]: " new_account

    local changed=false
    if [[ -n "$new_secret" ]]; then
        set_env "TT_CLIENT_SECRET"  "$new_secret";  changed=true; fi
    if [[ -n "$new_token" ]]; then
        set_env "TT_REFRESH_TOKEN"  "$new_token";   changed=true; fi
    if [[ -n "$new_account" ]]; then
        set_env "TT_ACCOUNT_NUMBER" "$new_account"; changed=true; fi

    if [[ "$changed" == "true" ]]; then
        reload_daemon
        print_ok "TastyTrade credentials updated."
    else
        print_info "No credentials changed."
    fi
}

change_telegram() {
    local current_token current_chat
    current_token=$(get_env "TELEGRAM_TOKEN")
    current_chat=$(get_env "TELEGRAM_CHAT_ID")
    echo ""

    if [[ -n "$current_token" ]]; then
        echo -e "  Telegram alerts are currently ${GREEN}enabled${RESET}."
        echo -e "  Chat ID: ${BOLD}${current_chat}${RESET}"
    else
        echo -e "  Telegram alerts are currently ${YELLOW}disabled${RESET}."
    fi

    echo ""
    echo -e "  ${CYAN}Press ENTER on any field to keep the current value.${RESET}"
    echo ""

    read -p "    Bot Token [ENTER = no change]: " new_token
    read -p "    Chat ID   [ENTER = no change, current: ${current_chat}]: " new_chat

    local changed=false
    if [[ -n "$new_token" ]]; then
        set_env "TELEGRAM_TOKEN" "$new_token"
        changed=true
    fi
    if [[ -n "$new_chat" ]]; then
        set_env "TELEGRAM_CHAT_ID" "$new_chat"
        changed=true
    fi

    if [[ "$changed" == "true" ]]; then
        reload_daemon
        print_ok "Telegram settings updated."
    else
        print_info "No changes made."
    fi
}

# ── r138 — THE DONE PATH: enable + start a stopped bot, restart a changed one ─
finish_session() {
    if ! bot_is_running; then
        echo ""
        echo "  Starting the bot (and enabling it at boot)..."
        sudo systemctl enable "$SERVICE_NAME" >/dev/null 2>&1
        sudo systemctl start "$SERVICE_NAME"
        sleep 4
        if bot_is_running; then
            print_ok "Bot started with these settings."
        else
            print_warn "Bot failed to start — check: journalctl -u ${SERVICE_NAME} -n 20"
        fi
    elif [[ "$CHANGED" == "true" ]]; then
        echo ""
        show_config
        sudo systemctl enable "$SERVICE_NAME" >/dev/null 2>&1
        auto_restart
    fi
}

auto_restart() {
    echo ""
    echo "  Applying changes and restarting bot..."
    sudo systemctl restart "$SERVICE_NAME"
    sleep 4
    if bot_is_running; then
        print_ok "Bot restarted successfully with new settings."
    else
        print_warn "Bot failed to start — check: journalctl -u ${SERVICE_NAME} -n 20"
    fi
}

# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────

if [[ "${1:-}" == "--show" ]]; then
    print_banner
    show_config
    exit 0
fi

if [[ ! -f "$UNIT_FILE" ]]; then
    print_banner
    echo -e "  ${RED}No service unit found at ${UNIT_FILE}${RESET}"
    echo -e "  Run setup_ec2.sh first to install and configure the bot."
    echo ""
    exit 1
fi

print_banner
show_config

CHANGED=false
while true; do
    echo -e "  ${BOLD}What would you like to change?${RESET}"
    echo ""
    echo -e "  ${BOLD}1.${RESET}  Instrument          (currently: $(get_env OT_INSTRUMENT))"
    echo -e "  ${BOLD}2.${RESET}  Risk per trade      (currently: \$$(get_env OT_RISK_USD))"
    echo -e "  ${BOLD}3.${RESET}  Paper / Live mode   (currently: $([ "$(get_env OT_PAPER_TRADING)" = "False" ] && echo "🔴 LIVE" || echo "📄 PAPER"))"
    echo -e "  ${BOLD}4.${RESET}  Telegram alerts     (chat: $(get_env TELEGRAM_CHAT_ID))"
    echo -e "  ${BOLD}5.${RESET}  TastyTrade credentials"
    echo -e "  ${BOLD}6.${RESET}  Daily loss cap      (currently: \$$(dll=$(get_env OT_DAILY_LOSS_LIMIT); echo ${dll:-$(get_env OT_RISK_USD)}))"
    echo -e "  ${BOLD}7.${RESET}  Pin-proximity gate  (currently: $(pin_gate_label))"
    echo -e "  ${BOLD}8.${RESET}  ORB ramp TOP        (currently: $(fmt_declared "$(get_env OT_ORB_BUDGET_USD)"))"
    echo -e "  ${BOLD}9.${RESET}  ORB ramp START      (currently: $(fmt_declared "$(get_env OT_ORB_RISK_USD)"))"
    echo -e "  ${BOLD}10.${RESET} Data capture        (currently: $(data_capture_label))"
    echo -e "  ${BOLD}11.${RESET} Done"
    echo ""
    read -p "    Select [1-11]: " menu_choice

    case "$menu_choice" in
        1) change_instrument; CHANGED=true ;;
        2) change_risk;       CHANGED=true ;;
        3) change_mode;       CHANGED=true ;;
        4) change_telegram;       CHANGED=true ;;
        5) change_tt_credentials; CHANGED=true ;;
        6) change_daily_loss;     CHANGED=true ;;
        7) change_pin_gate;       CHANGED=true ;;
        8) change_orb_budget;     CHANGED=true ;;
        9) change_orb_risk;       CHANGED=true ;;
        10) change_data_capture ;;
        11) break ;;
        *) print_warn "Please enter a number between 1 and 11." ;;
    esac
    echo ""
done

finish_session

echo ""
