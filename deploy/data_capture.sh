#!/usr/bin/env bash
# deploy/data_capture.sh  v1.0
#
# v1.0  2026-09-24  OTV4TEST r136 — ONE SWITCH: "managed" OR "standalone" DATA
#       CAPTURE. The operator, 2026-09-24, on bringing up OTV4TEST boxes under
#       the day_trader_pro conductor: "Make the s3 push compatible with the
#       conductor through a toggle in configure.sh call it 'managed' or
#       'standalone' data capture", "Have the same toggle switch off the cleanup
#       for 'managed'", "Have the same toggle switch off the VIX logging".
#
#   managed     the conductor owns this box's data. Enables what it drives, by
#               the EXACT names its quiesce/rearm and close use (1-REPORTER,
#               dtp 3003ac4: eod_conductor_v2.py:215/:227/:251):
#                 s3-push.timer (unmasked, installed, OT_INSTRUMENT given to the
#                 unit so the box pushes under its OWN symbol from minute one -
#                 own_symbol() otherwise falls back to sym=UNKNOWN until the
#                 first OHLC file, and the conductor's sweep culls unknown
#                 symbols), candle-logger.timer, optbot-self-close.timer (the
#                 16:45 backstop for a night control never arrives).
#               DISABLES optbot-retention-purge.timer - the conductor runs the
#               same purge at 16:05 on every box (eod_conductor_v2.py:493); two
#               schedulers for one job is r256's founding shape. The shared flock
#               (data/retention_purge.lock) would serialize them anyway.
#               Needs /usr/bin/python3 + boto3: s3-push and the conductor's
#               `--verify` run under the SYSTEM interpreter, not the venv.
#   standalone  this box pushes nothing: s3-push disabled and MASKED (the
#               reference QQQ box must never write into sym=QQQ, §38.3),
#               candle-logger and self-close off, our own 16:05 purge on.
#   status      which mode the UNITS are in - read from systemd, never from a
#               flag file, so the answer cannot drift from what actually runs.
#
# VIX: no OTV4TEST box uploads the VIX family in EITHER mode (s3_push.py v4.8,
# mainline r350's root match); the feed still collects VIX for local decisions.
#
# Usage:  bash deploy/data_capture.sh managed|standalone|status
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-status}"
UNIT_FILE="/etc/systemd/system/optionsbot.service"

_state() {
    # is-enabled PRINTS "not-found" AND exits non-zero for a missing unit, so the
    # output is the answer and the exit code is ignored; empty means absent.
    local s; s="$(systemctl is-enabled "$1" 2>/dev/null)"; echo "${s:-absent}"
}

status() {
    local s3 cl sc rp mode
    s3="$(_state s3-push.timer)"; cl="$(_state candle-logger.timer)"
    sc="$(_state optbot-self-close.timer)"; rp="$(_state optbot-retention-purge.timer)"
    if [ "$s3" = "enabled" ] && [ "$cl" = "enabled" ] && [ "$sc" = "enabled" ] && [ "$rp" != "enabled" ]; then
        mode="managed"
    elif [ "$s3" != "enabled" ] && [ "$cl" != "enabled" ] && [ "$sc" != "enabled" ] && [ "$rp" = "enabled" ]; then
        mode="standalone"
    else
        mode="MIXED"
    fi
    echo "data capture: $mode"
    echo "  s3-push.timer=$s3  candle-logger.timer=$cl  optbot-self-close.timer=$sc  optbot-retention-purge.timer=$rp"
    [ "$mode" = "MIXED" ] && echo "  ⚠️ neither mode is fully in effect - run: bash deploy/data_capture.sh managed|standalone"
    return 0
}

_instrument() {
    # the bot unit's own OT_INSTRUMENT, the same read configure.sh's get_env does;
    # an explicit OT_INSTRUMENT (setup_ec2.sh, before the unit exists) wins.
    if [ -n "${OT_INSTRUMENT:-}" ]; then echo "$OT_INSTRUMENT"; return; fi
    sudo grep -oP '(?<=^Environment=OT_INSTRUMENT=).*' "$UNIT_FILE" 2>/dev/null | tail -1
}

managed() {
    local sym rc=0
    sym="$(_instrument)"
    if [ -z "$sym" ]; then
        echo "🔴 no OT_INSTRUMENT (not in the environment, not in $UNIT_FILE) - refusing:"
        echo "   a managed box must push under its own symbol."; return 1
    fi
    if ! /usr/bin/python3 -c "import boto3" 2>/dev/null; then
        echo "  installing python3-boto3 (s3-push and the conductor's --verify run under /usr/bin/python3)"
        sudo apt-get install -y -qq python3-boto3 >/dev/null || { echo "🔴 python3-boto3 install failed"; return 1; }
    fi
    sudo systemctl unmask s3-push.service s3-push.timer >/dev/null 2>&1 || true
    sudo mkdir -p /etc/systemd/system/s3-push.service.d
    printf '[Service]\nEnvironment=OT_INSTRUMENT=%s\n' "$sym" \
        | sudo tee /etc/systemd/system/s3-push.service.d/instrument.conf >/dev/null
    bash "$DIR/deploy/install_s3_push_timer.sh"       || { echo "🔴 s3-push install failed"; rc=1; }
    bash "$DIR/deploy/install_candle_logger_timer.sh" || { echo "🔴 candle-logger install failed"; rc=1; }
    bash "$DIR/deploy/install_self_close.sh"          || { echo "🔴 self-close install failed"; rc=1; }
    sudo systemctl disable --now optbot-retention-purge.timer >/dev/null 2>&1 || true
    sudo systemctl daemon-reload
    echo "managed: pushing as sym=$sym; the conductor owns the 16:05 purge."
    return $rc
}

standalone() {
    sudo systemctl disable --now s3-push.timer >/dev/null 2>&1 || true
    sudo systemctl mask s3-push.service s3-push.timer >/dev/null 2>&1 || true
    sudo systemctl disable --now candle-logger.timer optbot-self-close.timer >/dev/null 2>&1 || true
    if [ -f /etc/systemd/system/optbot-retention-purge.timer ]; then
        sudo systemctl enable --now optbot-retention-purge.timer >/dev/null 2>&1 || true
    else
        bash "$DIR/deploy/install_retention_purge_timer.sh" || { echo "🔴 retention-purge install failed"; return 1; }
    fi
    sudo systemctl daemon-reload
    echo "standalone: nothing is pushed; this box's own 16:05 purge is on."
}

case "$MODE" in
    managed)    managed;    rc=$?; status; exit $rc ;;
    standalone) standalone; rc=$?; status; exit $rc ;;
    status)     status ;;
    *) echo "usage: bash deploy/data_capture.sh managed|standalone|status"; exit 2 ;;
esac
