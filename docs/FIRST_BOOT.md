FIRST BOOT — you are the Claude agent on a FRESHLY PROVISIONED OTV4TEST box. (docs/FIRST_BOOT.md v1.0 — 2026-09-24, OTV4TEST r132: first release)

This box was built minutes ago by `bootstrap.sh` → `deploy/install.sh` → `setup_ec2.sh`. It has no history, no memories and no prior conversations — do NOT run `tools/last_session.py`; there is nothing to catch up on. The operator's own words for this session: *"Look over the services and the feed and the plans and just make sure that everything is comfortable writing to the new location and that there are no complaints."*

This box is a PROVING GROUND for the unattended install. The question you answer is: **did the automation produce a box that works, with nothing done by hand?**

## Rules for this session
- **READ-ONLY.** Pull only. No commit, no push, no landing, no `git reset`, no edits to tracked files. The operator: *"That box won't be pushing anything."*
- No systemd changes (install, enable, disable, mask, edit). No subscription changes on the feed. No writes to trades.db, data/derived_store.db or data/resting_orders.db.
- Never print a credential: no `systemctl cat`, no unfiltered `systemctl show -p Environment`, no `env`/`printenv`, no `/proc/*/environ`. Report a setting's NAME and whether it is present, never its value.
- It trades PAPER. If anything says LIVE, that is the first finding — stop and report it.
- Times to the operator are US Eastern. Stores are UTC.

## What to check, in this order
1. **What was installed.** `git -C ~/options-trader log -1 --format='%h %s'` against `git ls-remote https://github.com/TX-9AI/OTV4TEST.git main`. Python: `venv/bin/pip freeze` against `requirements.lock` (every pin should match). Claude: `claude --version` against the pinned version in `deploy/install_claude.sh`. Swap: `swapon --show`.
2. **Every unit.** `systemctl is-active candle-feed optionsbot` (both active) and `systemctl is-enabled` for candle-feed, optionsbot, optbot-boot-sweep, optbot-claude-boot, optbot-midnight-halt.timer, optbot-retention-purge.timer, optbot-open-scan-ready.timer, optbot-open-scan-live.timer; `systemctl is-enabled s3-push.service` must read **masked**. `systemctl list-timers 'optbot-*' --all`.
3. **The feed.** `journalctl -u candle-feed --since '-30min' --no-pager | tail -50` — connected, subscribed, writing. `data/feed_store.db` exists under ~/options-trader and its newest 1m bar is recent (during RTH, within 2 minutes).
4. **The bot and the plans.** `journalctl -u optionsbot --since '-30min' --no-pager` — STARTED, no tracebacks. `python status.py`. During RTH: `venv/bin/python tools/open_scan.py --phase ready` and, from 09:45 ET, `--phase live` — every plan should see its inputs; a plan seeing 0 levels is a finding.
5. **Everything writes to the new location.** Each store and log the services write — trades.db, data/feed_store.db, data/derived_store.db, data/resting_orders.db, bot.log, logs/ — exists under `/home/ubuntu/options-trader`, is owned by `ubuntu`, and its modification time moves while the services run. (Files under `logs/` are created by systemd's `append:` and are root-owned — expected, not a finding.) Anything written somewhere else, or failing on permissions, is a finding.
6. **Complaints.** Every WARNING / ERROR / Traceback in both journals since boot, grouped by message. Name each one, and say whether it is expected on an empty box (no trade history, no level book yet, no prior session) or a defect of the install.
7. **The full checker sweep.** `venv/bin/python tools/boot_sweep.py` (it skips itself when memory is short — report that if it happens), then `--show`.

## Report
One message to the operator: a table of what you checked, PASS / FINDING for each, the installed commit, and every finding with the evidence line. Separate **install defects** (the automation got something wrong) from **empty-box effects** (expected on a new box). Then stop and wait.
