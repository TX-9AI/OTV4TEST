#!/usr/bin/env python3
"""tools/claude_boot.py — v1.1
RAISE AN AGENT SESSION AT BOOT, AND PROVE IT IS ACTUALLY RUNNING.

v1.1  2026-09-20 — OTV4TEST r70 (BOX.12). PURGES STALE tmpfs SCRATCHPADS
      before raising, and appends free-tmpfs to the status so it reaches the
      boot alert. /tmp is RAM (455 MB of 908 MB here) and scratch dirs are
      keyed by session id, so they accumulate until every Bash spawn dies
      silently — which is what happened on control.

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
# 🔴 r70 / AUTH.1 — LAUNCH ON THE SUBSCRIPTION, NEVER ON API CREDITS.
# Operator's instruction. Measured 2026-09-20: no key is set anywhere on this
# box and `~/.claude.json` authenticates through `oauthAccount` — so today it
# is right BY ACCIDENT. One stray export would move every boot session onto
# metered credits with nothing saying so. Stripped at the launch rather than
# trusted. ⚠️ IT UNSETS; IT NEVER READS OR PRINTS A VALUE (§18a).
ENV_STRIP = ("env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN"
             " -u CLAUDE_API_KEY -u ANTHROPIC_BASE_URL")
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


def tmpfs_free_mb(path: str = "/tmp") -> int | None:
    """Free megabytes on the filesystem holding `path`, or None."""
    try:
        st = os.statvfs(path)
        return int(st.f_bavail * st.f_frsize / (1024 * 1024))
    except Exception:                                           # noqa: BLE001
        return None


def purge_scratch(root: str | None = None) -> tuple[int, int | None]:
    """Remove OTHER sessions' scratch directories. -> (removed, free_mb_after).

    🔴 r70 (BOX.12) — /tmp IS tmpfs, WHICH IS RAM. 455 MB here of 908 MB
    physical, and the scratchpad path is keyed by SESSION ID, so every new
    session mints a directory and nothing removes the old ones. This box has
    been protected only by its daily reboot; the control box, which does not
    reboot daily, filled its tmpfs completely and EVERY Bash spawn then died
    instantly with no stdout and no stderr — a temp file is needed for the
    shell snapshot, so it fails before executing. An agent that looks
    brain-dead rather than out of space.
    ⚠️ TRANSCRIPTS ARE ON EXT4 (`~/.claude/projects/...`), a different
    filesystem, so this cannot reach them and `tools/last_session.py` still
    reviews the previous thread afterwards. That is measured, not assumed.
    ⚠️ FAILS CLOSED ON THE PATH. The root is rebuilt from `os.getuid()` and
    must match `/tmp/claude-<digits>` exactly; anything else removes nothing.
    A cleanup that globs wrong is worse than no cleanup.
    ⚠️ AND IT NEVER REMOVES THE LIVE SESSION'S OWN DIRECTORY — `CLAUDE_SCRATCH`
    names it when set, so a purge at boot cannot delete the working directory
    of the session it is about to raise.

    🔴 IT ARCHIVES; IT DOES NOT DELETE. Raised by the mainline control agent
    2026-09-20 from a concrete near-miss on their box: an entire unlanded
    revision — the ported raiser, its unit and its gate — was sitting in the
    scratchpad of a session that had been handed off, and a deleting purge
    would have destroyed it. The transcript described the build without
    containing it. **The harness itself directs every agent to put working
    files in the scratchpad**, so treating that directory as disposable is
    wrong by construction. Bytes move to `~/claude_scratch_archive` on ext4
    (5.9 GB free, no quota) and the retention sweep is the ONLY deleting path.
    Their S3.13 is the same lesson at fleet scale: 492,945 objects deleted on
    a reading that turned out to be wrong.
    """
    import re
    import shutil
    # ⚠️ `root` IS A PARAMETER ONLY SO THE GATE CAN DRIVE THIS WITHOUT TOUCHING
    # THE BOX'S REAL SCRATCH ROOT — production passes nothing. A checker that
    # had to delete from the live path to test itself would be r13's class (a
    # fixture reaching live state) with a very bad blast radius.
    root = root or ("/tmp/claude-%d" % os.getuid())
    if not (re.fullmatch(r"/tmp/claude-\d+", root)
            or re.fullmatch(r"/tmp/[A-Za-z0-9_]*scratchtest[A-Za-z0-9_]*", root)):
        return 0, tmpfs_free_mb()
    if not os.path.isdir(root):
        return 0, tmpfs_free_mb()
    keep = os.environ.get("CLAUDE_SCRATCH", "")
    arch = os.path.join(os.path.expanduser("~"), "claude_scratch_archive")
    # ⚠️ ONE LEVEL UNDER $HOME AND CARRYING NO `.git`, deliberately: `land.sh`
    # resolves its target by scanning `$HOME/*/` for a `.git` plus repo
    # markers, so an archive root that never holds one at its own top level
    # cannot be mistaken for a checkout.
    stamp = time.strftime("%Y%m%d-%H%M%S")
    moved = 0
    for name in os.listdir(root):
        p = os.path.join(root, name)
        if keep and (os.path.abspath(keep) == p
                     or os.path.abspath(keep).startswith(p + os.sep)):
            continue                                  # the live session's own
        try:
            os.makedirs(arch, exist_ok=True)
            shutil.move(p, os.path.join(arch, "%s-%s" % (stamp, name)))
            moved += 1
        except Exception:                                       # noqa: BLE001
            pass
    _sweep_archive(arch)
    return moved, tmpfs_free_mb()


ARCHIVE_DAYS = 14


def _sweep_archive(arch: str, days: int = ARCHIVE_DAYS) -> int:
    """The ONLY path that deletes. Bounded retention so archiving is not an
    unbounded trade of disk for reversibility."""
    import shutil
    if not os.path.isdir(arch):
        return 0
    cutoff = time.time() - days * 86400
    gone = 0
    for name in os.listdir(arch):
        p = os.path.join(arch, name)
        try:
            if os.path.getmtime(p) < cutoff:
                shutil.rmtree(p) if os.path.isdir(p) else os.unlink(p)
                gone += 1
        except Exception:                                       # noqa: BLE001
            pass
    return gone


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
    _raise("%s %s --remote-control %s --continue; exec bash"
           % (ENV_STRIP, binp, RC_NAME))
    if _settle():
        return True, "up (continue)"

    # 2 — the fallback. A --continue with no prior thread, or one that refuses
    # to resume, must not leave the box with no agent at 08:00.
    # ⚠️ The brief is passed as ONE argument. r32 measured the hazard: the file
    # contains double quotes, and expanding it through another shell layer ends
    # the argument at the first one and hands Claude a truncated brief.
    _kill()
    if os.path.exists(BRIEF):
        _raise("%s %s --remote-control %s \"$(cat %s)\"; exec bash"
               % (ENV_STRIP, binp, RC_NAME, _sh_quote(BRIEF)))
    else:
        _raise("%s %s --remote-control %s; exec bash"
               % (ENV_STRIP, binp, RC_NAME))
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
    # 🔴 r70 — ONLY PURGE WHEN WE ARE ACTUALLY GOING TO RAISE. Found by the
    # mainline control agent's review before this shipped: the first cut ran
    # the purge UNCONDITIONALLY and `bring_up()` returns "already running"
    # WITHOUT killing anything when a session is live. Under systemd
    # `CLAUDE_SCRATCH` is unset, so nothing was protected — meaning
    # `systemctl start optbot-claude-boot.service` against a LIVE session would
    # have archived that running agent's working directory out from under it
    # and left it running. The operator ran exactly that command on 2026-09-20.
    # 🔑 GATING ON `agent_alive()` MAKES THE PURGE AND THE RAISE ONE DECISION:
    # we only reclaim when we are replacing, which is the only moment it is safe.
    freed = tmpfs_free_mb()
    if a.dry_run or agent_alive():
        print("claude_boot: a session is live — scratch purge SKIPPED")
    else:
        try:
            n, freed = purge_scratch()
            if n:
                print("claude_boot: archived %d stale scratch dir(s)" % n)
        except Exception as exc:                                # noqa: BLE001
            print("claude_boot: scratch purge skipped (%s)" % type(exc).__name__)

    try:
        ok, text = bring_up(dry=a.dry_run)
    except Exception as exc:                                    # noqa: BLE001
        ok, text = False, "NOT AVAILABLE (raiser error: %s)" % type(exc).__name__
    # 🔑 THE FREE-SPACE FIGURE RIDES THE STATUS STRING, so it reaches the boot
    # Telegram beside the IP with NO change to alert_manager — the operator
    # sees "tmpfs 454M free" every morning instead of discovering a full one
    # when a shell dies three days later.
    if freed is not None:
        text = "%s, tmpfs %dM free" % (text, freed)
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
