#!/usr/bin/env python3
"""tools/claude_boot.py — v1.0
RAISE AN AGENT SESSION AT BOOT, AND PROVE IT IS ACTUALLY RUNNING.

v1.0  2026-09-20 — OTV4TEST r68 (BOX.11). The operator: *"Can we have a tmux
      session Claude --continue added to the boot sequence on this box so that
      an agent is available from the moment the box auto wakes?"*

🔴 THE CHECK IS THE HARD PART, AND THE TWO OBVIOUS ONES ARE BOTH WRONG.
Measured on the live session 2026-09-20:

    tmux list-panes -t claude -F '#{pane_pid} #{pane_current_command}'
      ->  1727 bash                                  <- says BASH
    ps --ppid 1727
      ->  1731 claude --remote-control qqq-test ...   <- claude is the CHILD

`devtools.sh` launches `"claude ...; exec bash"`, so (1) the pane's foreground
command reads `bash` WHILE CLAUDE IS RUNNING FINE — a check on it would report
"not available" over a working session, and §17 says an alarm that cries wolf
stops being read; and (2) the tmux session OUTLIVES a dead claude, because the
trailing `exec bash` keeps the pane alive — so "the session exists" reports UP
over a crashed agent, which is the laundered green §18 names.
🔑 SO AVAILABILITY IS A LIVE `claude` PROCESS IN THE SESSION'S PROCESS TREE,
verified after a settle delay, and nothing weaker.

⚠️ IT REUSES `devtools.sh`'s SHAPE RATHER THAN INVENTING ONE. Same session
name, same `--remote-control qqq-test` flag (r32: the argument is OPTIONAL, so
a bare flag on the HAND OFF site could swallow the brief as the session name),
same `; exec bash` tail so the operator can attach to a pane that survives.
Two mechanisms for one job is the failure §35 keeps recording.

⚠️ AND AN AVAILABLE SESSION IS NOT A WORKING AGENT. §38.7 — *"the assistant
does not run continuously"* — is untouched by this. A resumed thread sits at a
prompt and does nothing until the operator types. This raises a door, not a
worker.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

from utils.agent_status import record                           # noqa: E402

SESSION = os.environ.get("CLAUDE_TMUX", "claude")

# 🔴 A SYSTEMD UNIT DOES NOT HAVE THE OPERATOR'S PATH, AND THE MENU'S OWN
# RESOLVER WOULD FAIL HERE. `devtools.sh::_claude_bin` is `command -v claude`,
# which works in his login shell because the profile adds `~/.local/bin` —
# measured, that is exactly where the binary is (`/home/ubuntu/.local/bin/
# claude`, 2.1.278). A unit starts with systemd's default PATH and no profile
# is ever read, and tmux runs its command under `/bin/sh`, which reads none
# either. So `claude` would simply not be found AT BOOT, on a box where it is
# plainly installed and works by hand — the §40 shape, where a claim about
# behaviour is a claim about an environment.
_LIKELY = (
    os.path.expanduser("~/.local/bin/claude"),
    "/usr/local/bin/claude",
    "/usr/bin/claude",
)


def claude_bin() -> str:
    """Absolute path to the claude binary, or "" when it is genuinely absent."""
    import shutil
    found = shutil.which("claude")
    if found:
        return found
    for cand in _LIKELY:
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return ""
RC_NAME = "qqq-test"
BRIEF = os.path.join(_root, "docs", "HANDOFF.md")

# The settle budget. `claude` needs a few seconds to be a real process; the
# unit's own TimeoutStartSec sits above this so systemd never waits longer
# than the script's own worst case.
SETTLE_S = float(os.environ.get("OT_CLAUDE_SETTLE_S", "12"))
POLL_S = 0.5


def tmux_bin() -> str:
    """Absolute path to tmux, for the same reason as `claude_bin` — a unit does
    not read a profile and must not assume the operator's PATH."""
    import shutil
    return (shutil.which("tmux") or
            next((c for c in ("/usr/bin/tmux", "/usr/local/bin/tmux")
                  if os.path.isfile(c) and os.access(c, os.X_OK)), ""))


class _Failed:
    """A subprocess result that did not happen. Stands in for a missing binary
    so every caller sees a clean failure rather than an exception."""
    returncode = 127
    stdout = ""
    stderr = "binary not found"


def _tmux(*args, **kw):
    # 🔴 NEVER RAISE. Found by this file's own gate (B7): with tmux off PATH
    # the raiser died with FileNotFoundError, exited NON-ZERO and recorded NO
    # STATUS AT ALL — so the unit would have gone to `failed` and the boot
    # alert would have said "unknown" with nothing anywhere explaining why.
    # A component whose entire job is REPORTING availability must not have a
    # path on which it reports nothing (§0.5).
    b = tmux_bin()
    if not b:
        return _Failed()
    try:
        return subprocess.run([b, *args], capture_output=True, text=True, **kw)
    except OSError:
        return _Failed()


def has_session(name: str = SESSION) -> bool:
    return _tmux("has-session", "-t", name).returncode == 0


def agent_alive(name: str = SESSION) -> bool:
    """A live `claude` process inside this session's panes. See the header —
    neither the session's existence nor the pane's command answers this."""
    if not has_session(name):
        return False
    r = _tmux("list-panes", "-t", name, "-F", "#{pane_pid}")
    if r.returncode != 0:
        return False
    for pid in [x.strip() for x in r.stdout.split() if x.strip().isdigit()]:
        # the pane process itself, and its children — claude is normally a child
        try:
            ps = subprocess.run(["ps", "-o", "pid=,comm=", "--ppid", pid],
                                capture_output=True, text=True)
            own = subprocess.run(["ps", "-o", "comm=", "-p", pid],
                                 capture_output=True, text=True)
        except OSError:
            continue
        names = [ln.split()[-1] for ln in ps.stdout.splitlines() if ln.strip()]
        names += [ln.strip() for ln in own.stdout.splitlines() if ln.strip()]
        if any(n == "claude" for n in names):
            return True
    return False


def _kill(name: str = SESSION) -> None:
    _tmux("kill-session", "-t", name)


def _raise(cmd: str, name: str = SESSION) -> None:
    _tmux("new-session", "-d", "-s", name, "-c", _root, cmd)


def _settle(budget: float = SETTLE_S) -> bool:
    """Poll rather than sleep a flat interval: a fast box reports sooner and a
    slow one still gets its full budget."""
    deadline = time.time() + budget
    while time.time() < deadline:
        if agent_alive():
            return True
        time.sleep(POLL_S)
    return agent_alive()


def bring_up(dry: bool = False) -> tuple[bool, str]:
    """-> (ok, status text). Tries --continue, then falls back to a FRESH
    thread bootstrapped from the brief, and reports WHICH ONE came up.

    The operator's ruling, 2026-09-20: *"--continue, with fallback"*, and the
    reason the mode is named in the status is that "Claude up" must never be a
    guess about which thread he is attaching to.
    """
    if dry:
        return True, "up (dry-run, nothing raised)"

    if not tmux_bin():
        return False, "NOT AVAILABLE (tmux not found)"

    if agent_alive():
        return True, "up (already running)"

    binp = claude_bin()
    if not binp:
        return False, "NOT AVAILABLE (claude binary not found)"

    # 1 — the operator's first choice: continue the last thread.
    _kill()
    _raise("%s --remote-control %s --continue; exec bash" % (binp, RC_NAME))
    if _settle():
        return True, "up (continue)"

    # 2 — the fallback. A --continue with no prior thread, or one that refuses
    # to resume, must not leave the box with no agent at 08:00.
    # ⚠️ The brief is passed as ONE argument. r32 measured the hazard: the file
    # contains double quotes, and expanding it through another shell layer ends
    # the argument at the first one and hands Claude a truncated brief.
    _kill()
    if os.path.exists(BRIEF):
        _raise("%s --remote-control %s \"$(cat %s)\"; exec bash"
               % (binp, RC_NAME, _sh_quote(BRIEF)))
    else:
        _raise("%s --remote-control %s; exec bash" % (binp, RC_NAME))
    if _settle():
        return True, ("up (fresh brief)" if os.path.exists(BRIEF)
                      else "up (fresh, NO BRIEF FOUND)")

    # 3 — named absence, never silence (§0.5).
    why = "session exists but no claude process" if has_session() else "tmux session did not start"
    return False, "NOT AVAILABLE (%s)" % why


def _sh_quote(p: str) -> str:
    return "'" + p.replace("'", "'\\''") + "'"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would happen; raise nothing")
    ap.add_argument("--status-only", action="store_true",
                    help="report current availability without raising anything")
    a = ap.parse_args(argv)

    if a.status_only:
        ok = agent_alive()
        print("agent_alive=%s session=%s bin=%s"
              % (ok, has_session(), claude_bin() or "(not found)"))
        return 0 if ok else 1

    # ⚠️ ANY escape still leaves a STATUS and still exits 0. The unit is ordered
    # before the bot; a traceback here must never become a failed unit with no
    # explanation on the alert. B7 drives exactly this path.
    try:
        ok, text = bring_up(dry=a.dry_run)
    except Exception as exc:                                    # noqa: BLE001
        ok, text = False, "NOT AVAILABLE (raiser error: %s)" % type(exc).__name__
    record(text)
    print("claude_boot: %s" % text)
    # ⚠️ EXIT 0 EVEN ON FAILURE, DELIBERATELY. This unit is ordered BEFORE the
    # bot; a non-zero exit would mark it failed and, with the wrong dependency
    # later added, could hold up trading. §29 — nothing on this box may be
    # load-bearing for the bot. THE STATUS FILE IS THE REPORT, not the exit
    # code, and the operator reads it on the boot alert.
    return 0


if __name__ == "__main__":
    sys.exit(main())
