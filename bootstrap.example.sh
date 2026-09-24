#!/bin/bash
# v4.0 — 2026-09-24 — OTV4TEST r132. REWRITTEN FOR THIS FORK, AND TRACKED AGAIN.
#         The v3 template it replaces downloaded options_trader_v3's install.sh,
#         so a box built from it ran v3; and a sorted .gitignore had silently
#         dropped the template from the repo. Adds the r132 toggles (Claude at
#         boot, swap, git push, git ref) and the Claude login (CLAUDE_LOGIN_B64).
# v3.0 — 2026-07-10 — options_trader_v3 (predecessor).
# =============================================================================
# bootstrap.sh — one-shot unattended deploy of OTV4TEST onto a fresh EC2 box.
#
# This is a TEMPLATE (placeholders only) — safe to commit, and the repo is
# PUBLIC. Put real secrets ONLY in a copy named bootstrap.sh, which is
# gitignored (every bootstrap*.sh except this .example is ignored).
#
# HOW TO USE:
#   1. cp bootstrap.example.sh bootstrap.sh   # your copy — gitignored
#   2. Fill in the REPLACE_ME values in bootstrap.sh (Claude login: see below).
#   3. scp bootstrap.sh ubuntu@IP:~
#   4. On the instance:  chmod +x bootstrap.sh && ./bootstrap.sh
#      It re-launches itself in tmux; if SSH drops, reconnect and run
#      `tmux attach -t deploy` to watch it finish.
#   Preview without changing anything: after step 3, on the instance,
#      OT_PLAN_ONLY=1 ./bootstrap.sh     (prints PLAN lines, installs nothing)
#
# Recommended instance: t3.medium, Ubuntu 26.04 LTS (the reference box's
# release; the pinned packages were frozen on its Python 3.14).
#
# It exports every value setup_ec2.sh would otherwise prompt for, then runs the
# web installer hands-free. setup_ec2.sh SHREDS bootstrap.sh during cleanup, once
# the credentials are in the systemd units. On a failed install it remains so you
# can re-run — delete it by hand if you abandon the deploy.
# =============================================================================

# ── Run inside tmux ───────────────────────────────────────────────────────────
# A dropped SSH connection can't kill a multi-minute install (or leave secrets
# un-shredded). Reconnect with:  tmux attach -t deploy
if [ -z "$TMUX" ] && [ -z "$OT_PLAN_ONLY" ]; then
    command -v tmux >/dev/null 2>&1 || { sudo apt-get update -qq; sudo apt-get install -y -qq tmux; }
    if command -v tmux >/dev/null 2>&1; then
        exec tmux new-session -A -s deploy "bash '$(readlink -f "$0")'"
    else
        echo "  (tmux unavailable — running directly; keep this session connected)"
    fi
fi

# ── Instrument and sizing (optional; these are the defaults) ──────────────────
# Installs are ALWAYS paper. Switch to live later, deliberately, via configure.sh.
export OT_INSTRUMENT="QQQ"
export OT_RISK_USD="200"
# export OT_ORB_RISK_USD="200"          # defaults to OT_RISK_USD
# export OT_ORB_BUDGET_USD="200"        # defaults to OT_RISK_USD
# export OT_DAILY_LOSS_LIMIT="200"      # defaults to OT_RISK_USD
export OT_PIN_PROXIMITY_ACTIVE="0"      # PIN.1: off pending data (2026-09-24)

# ── Box ───────────────────────────────────────────────────────────────────────
export OT_ROLE="control"        # full checkout: tests/ (the sweep) and docs/ (the agent's brief)
export OT_SWAP_GB="2"           # /swapfile when the box has no swap; 0 = none
export OT_GIT_REF="main"        # branch, tag or commit to install
export OT_GIT_PUSH="0"          # 1 = this box may push (stores GITHUB_TOKEN); 0 = pull only

# ── TastyTrade OAuth ──────────────────────────────────────────────────────────
export TT_CLIENT_SECRET="REPLACE_ME"
export TT_REFRESH_TOKEN="REPLACE_ME"
export TT_ACCOUNT_NUMBER="REPLACE_ME"   # e.g. 5WT12345

# ── Telegram alerts ───────────────────────────────────────────────────────────
export TELEGRAM_TOKEN="REPLACE_ME"
export TELEGRAM_CHAT_ID="REPLACE_ME"

# ── GitHub ────────────────────────────────────────────────────────────────────
# The repo is public, so cloning needs no token. The token is for push.sh and,
# with OT_GIT_PUSH=1, for git push.
export GITHUB_REPO="TX-9AI/OTV4TEST"
export GITHUB_TOKEN="REPLACE_ME"

# ── Claude Code ───────────────────────────────────────────────────────────────
# Installed on every box, pinned (deploy/install_claude.sh). Whether it comes up
# in a Remote Control session at boot is this toggle:
export OT_CLAUDE_AT_BOOT="0"            # 1 = raise it at first boot and every boot
# export OT_RC_NAME="qqq-test"          # Remote Control session name
#
# THE LOGIN (optional; without it, ssh in once and run `claude auth login`).
# Make a DEDICATED login for this box — never copy an existing box's, or the two
# can log each other out. On a machine where you are already working:
#     CLAUDE_CONFIG_DIR=~/newbox-claude claude auth login
#       (open the link, approve, paste the code back if it asks)
#     CLAUDE_CONFIG_DIR=~/newbox-claude claude auth status     # must say logged in
#     tar -C ~/newbox-claude -czf - .credentials.json .claude.json | base64 -w0
#     rm -rf ~/newbox-claude
# and paste the one long line here:
export CLAUDE_LOGIN_B64=""

# ── Run the installer (inherits every export above) ───────────────────────────
curl -fsSL "https://raw.githubusercontent.com/${GITHUB_REPO}/${OT_GIT_REF}/deploy/install.sh" -o install.sh \
    && bash install.sh
