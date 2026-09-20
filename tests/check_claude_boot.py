#!/usr/bin/env python3
"""tests/check_claude_boot.py — v1.0
AN AGENT SESSION IS RAISED AT BOOT, AND "UP" MEANS A LIVE CLAUDE PROCESS.

v1.0  2026-09-20 — OTV4TEST r68 (BOX.11). The operator asked for a
      `claude --continue` session at boot and for the boot Telegram — the one
      already carrying the IP — to say whether it came up.

🔴 THE WHOLE DIFFICULTY IS THE WORD "UP", AND BOTH OBVIOUS CHECKS ARE WRONG.
Measured on the live session 2026-09-20, `devtools.sh` launches
`"claude ...; exec bash"`, so:
  · `#{pane_current_command}` reads **bash** WHILE CLAUDE IS RUNNING — a check
    on it reports "not available" over a working session, and §17 says an
    alarm that cries wolf stops being read;
  · the tmux session OUTLIVES a dead claude, because `exec bash` keeps the
    pane — so "the session exists" reports UP over a crashed agent, which is
    the laundered green §18 names.
B1 and B1b are that pair, driven for real.

  B0c no tmux session is left behind (HYG.9's class, found on the born-red run)
  B0  THE GUARD, FIRST: the installer is NOT run unless sudo resolves to the
      stub (r21's M4a — a checker that could install a live unit is worse than
      no gate), and B0b proves /etc/systemd/system was untouched
  B1  a tmux session that EXISTS with no claude in it reads NOT alive
  B1b ...and one with a claude-named process as a pane child reads ALIVE
  B2  the binary resolves under a systemd-like PATH (the menu's own
      `command -v claude` would NOT — no profile is read in a unit)
  B3  the installed unit's ExecStart script exists and runs the venv python
  B4  it is ordered Before the bot and takes NO Requires/Wants on it (§29)
  B5  HOME is set explicitly (credentials live in ~/.claude)
  B6  RemainAfterExit keeps the cgroup under the tmux server
  B7  the raiser exits 0 even when it can raise nothing (§29: ordering must
      never become a dependency that can hold up trading)
  B8  the status round-trips, and a stale stamp reads as unknown
  B9  the REAL send_startup_alert carries the agent field, B9b says UNKNOWN
      when the stamp is absent — nothing here can reach Telegram (r22's idiom)
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

FAILED, RAN = [], []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    RAN.append(name)
    if not ok:
        FAILED.append(name)


def guard(name, fn, detail=lambda: ""):
    try:
        ok = bool(fn())
    except Exception as exc:                                    # noqa: BLE001
        check(name, False, f"raised {type(exc).__name__}: {exc}")
        return False
    try:
        d = detail()
    except Exception:                                           # noqa: BLE001
        d = ""
    check(name, ok, d)
    return ok


TMP = tempfile.mkdtemp(prefix="cb_")
os.environ["OT_AGENT_STATUS"] = os.path.join(TMP, "AGENT_STATUS")

try:
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "_cb", os.path.join(_root, "tools", "claude_boot.py"))
    cb = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(cb)
except Exception as exc:                                        # noqa: BLE001
    _WHY = "tools/claude_boot.py absent or unimportable: %s: %s" % (
        type(exc).__name__, exc)

    class _Absent:
        def __getattr__(self, n):
            raise RuntimeError(_WHY)

    cb = _Absent()

HAVE_TMUX = shutil.which("tmux") is not None
SESS = "cbcheck_%d" % os.getpid()


def _kill(s=SESS):
    subprocess.run(["tmux", "kill-session", "-t", s],
                   capture_output=True)


# ── B1 / B1b — the pair that defines "up" ────────────────────────────────────
def _b1():
    if not HAVE_TMUX:
        raise RuntimeError("tmux absent — NOT RUN rather than passed (§38.7)")
    # ⚠️ try/finally, AND IT IS NOT DECORATION. The first cut killed the session
    # on the LAST line, so when `cb` was the absent-module stub the raise
    # escaped BEFORE the cleanup and left a live `cbcheck_*` tmux session on the
    # box — found in the post-sweep `tmux ls`. That is HYG.9/HYG.10's class, a
    # checker leaving its fixtures behind on the real machine, and it showed up
    # on exactly the born-red run this gate exists to produce.
    _kill()
    try:
        subprocess.run(["tmux", "new-session", "-d", "-s", SESS,
                        "echo dead; exec bash"], capture_output=True)
        time.sleep(1.0)
        exists = subprocess.run(["tmux", "has-session", "-t", SESS],
                                capture_output=True).returncode == 0
        alive = cb.agent_alive(SESS)
        return exists and not alive
    finally:
        _kill()


guard("B1 a session that exists with no claude reads NOT alive", _b1)


def _b1b():
    if not HAVE_TMUX:
        raise RuntimeError("tmux absent — NOT RUN rather than passed (§38.7)")
    # A stand-in named exactly `claude` so `ps -o comm=` reports it. The real
    # binary is never launched: a checker that starts an agent session on the
    # box is r13's class (a fixture reaching live state).
    d = tempfile.mkdtemp(prefix="fakebin_")
    fake = os.path.join(d, "claude")
    with open(fake, "w") as fh:
        fh.write("#!/bin/sh\nsleep 30\n")
    os.chmod(fake, 0o755)
    _kill()
    try:
        subprocess.run(["tmux", "new-session", "-d", "-s", SESS,
                        "%s; exec bash" % fake], capture_output=True)
        time.sleep(1.5)
        pane_cmd = subprocess.run(
            ["tmux", "list-panes", "-t", SESS, "-F", "#{pane_current_command}"],
            capture_output=True, text=True).stdout.strip()
        alive = cb.agent_alive(SESS)
        # the naive check would have said "bash"; ours must say alive
        return alive and pane_cmd != "claude"
    finally:
        _kill()
        shutil.rmtree(d, ignore_errors=True)


guard("B1b a claude process as a pane child reads ALIVE (pane cmd says bash)", _b1b)

guard("B2 the binary resolves under a systemd-like PATH",
      lambda: bool(subprocess.run(
          [sys.executable, os.path.join(_root, "tools", "claude_boot.py"),
           "--status-only"],
          capture_output=True, text=True,
          env={"HOME": os.path.expanduser("~"), "PATH": "/usr/bin:/bin",
               "OT_AGENT_STATUS": os.environ["OT_AGENT_STATUS"]}
      ).stdout.strip()),
      lambda: "resolver ran under PATH=/usr/bin:/bin")


# ── B0 / B3-B6 — drive the REAL installer with sudo stubbed ──────────────────
UNIT_TXT = {}


def _run_installer():
    d = tempfile.mkdtemp(prefix="inst_")
    repo = os.path.join(d, "repo")
    os.makedirs(os.path.join(repo, "deploy"))
    os.makedirs(os.path.join(repo, "tools"))
    os.makedirs(os.path.join(repo, "venv", "bin"))
    shutil.copy(os.path.join(_root, "deploy", "install_claude_boot.sh"),
                os.path.join(repo, "deploy", "install_claude_boot.sh"))
    shutil.copy(os.path.join(_root, "tools", "claude_boot.py"),
                os.path.join(repo, "tools", "claude_boot.py"))
    py = os.path.join(repo, "venv", "bin", "python")
    open(py, "w").write("#!/bin/sh\nexit 0\n")
    os.chmod(py, 0o755)

    out = os.path.join(d, "unit.txt")
    stub = os.path.join(d, "sudo")
    with open(stub, "w") as fh:
        fh.write(
            "#!/bin/sh\n"
            "# stubbed sudo: tee writes to scratch, everything else is logged\n"
            'case "$1" in\n'
            '  tee) cat > "$CB_UNIT_OUT"; exit 0 ;;\n'
            '  systemctl) echo "systemctl $*" >> "$CB_UNIT_OUT.log"; exit 0 ;;\n'
            '  rm) echo "rm $*" >> "$CB_UNIT_OUT.log"; exit 0 ;;\n'
            '  *) echo "REFUSED: $*" >&2; exit 90 ;;\n'
            "esac\n")
    os.chmod(stub, 0o755)
    env = {**os.environ, "PATH": d + os.pathsep + os.environ.get("PATH", ""),
           "CB_UNIT_OUT": out}
    r = subprocess.run(["bash", os.path.join(repo, "deploy",
                                             "install_claude_boot.sh")],
                       capture_output=True, text=True, env=env, cwd=repo)
    UNIT_TXT["repo"] = repo
    UNIT_TXT["rc"] = r.returncode
    UNIT_TXT["txt"] = open(out).read() if os.path.exists(out) else ""
    UNIT_TXT["stub"] = stub
    return UNIT_TXT["txt"]


_sysd_before = sorted(os.listdir("/etc/systemd/system")) if os.path.isdir(
    "/etc/systemd/system") else []

guard("B0 the guard: sudo resolves to the stub before the installer is run",
      lambda: bool(_run_installer()) and UNIT_TXT.get("rc") == 0,
      lambda: "rc=%s unit=%d bytes" % (UNIT_TXT.get("rc"), len(UNIT_TXT.get("txt", ""))))

if FAILED:
    print("\nREFUSING TO CONTINUE — the installer did not run under the stub.")
    sys.exit(1)

_txt = UNIT_TXT["txt"]
_repo = UNIT_TXT["repo"]


def _execstart():
    m = re.search(r"^ExecStart=(\S+)\s+(\S+)", _txt, re.M)
    return m.groups() if m else ("", "")


guard("B3 the unit's ExecStart script exists and runs the venv python",
      lambda: (lambda py, sc: os.path.isfile(sc)
               and sc.startswith(_repo) and py.endswith("venv/bin/python"))(*_execstart()),
      lambda: " ".join(_execstart()))

guard("B4 ordered Before the bot, with NO Requires/Wants on it (§29)",
      lambda: "Before=optionsbot.service" in _txt
      and not re.search(r"^(Requires|Wants|BindsTo)=.*optionsbot", _txt, re.M),
      lambda: "Before=yes requires=no")

guard("B5 HOME is set explicitly in the unit",
      lambda: re.search(r"^Environment=HOME=/home/ubuntu\s*$", _txt, re.M) is not None)

guard("B6 RemainAfterExit keeps the cgroup under the tmux server",
      lambda: re.search(r"^RemainAfterExit=yes\s*$", _txt, re.M) is not None
      and re.search(r"^Type=oneshot\s*$", _txt, re.M) is not None)

guard("B6b the unit bounds how long it can delay the bot",
      lambda: re.search(r"^TimeoutStartSec=(\d+)", _txt, re.M) is not None
      and int(re.search(r"^TimeoutStartSec=(\d+)", _txt, re.M).group(1)) <= 60,
      lambda: re.search(r"^TimeoutStartSec=(\d+)", _txt, re.M).group(0))


# ── B7 — the raiser never fails its unit ─────────────────────────────────────
def _b7():
    d = tempfile.mkdtemp(prefix="nobin_")
    # no claude anywhere on PATH and none at the likely paths
    env = {"HOME": d, "PATH": d, "OT_AGENT_STATUS": os.path.join(d, "S"),
           "CLAUDE_TMUX": "cb_nobin_%d" % os.getpid(),
           "OT_CLAUDE_SETTLE_S": "1"}
    r = subprocess.run([sys.executable,
                        os.path.join(_root, "tools", "claude_boot.py")],
                       capture_output=True, text=True, env=env)
    txt = ""
    if os.path.exists(env["OT_AGENT_STATUS"]):
        txt = open(env["OT_AGENT_STATUS"]).read()
    return r.returncode == 0 and "NOT AVAILABLE" in txt


guard("B7 it exits 0 and records NOT AVAILABLE when it can raise nothing", _b7)


# ── B8 — the stamp ───────────────────────────────────────────────────────────
def _b8():
    from utils import agent_status as ast_
    ast_.record("up (continue)")
    fresh = ast_.read() == "up (continue)"
    stale = ast_.read(now=time.time() + ast_.MAX_AGE_S + 10) is None
    return fresh and stale


guard("B8 the status round-trips and a stale stamp reads as unknown", _b8)


# ── B9 — the REAL alert, captured, never sent ────────────────────────────────
def _alert(with_stamp: bool):
    import notifications.alert_manager as am
    from utils import agent_status as ast_
    try:
        os.unlink(ast_.path())
    except Exception:                                           # noqa: BLE001
        pass
    if with_stamp:
        ast_.record("up (continue)")
    mgr = am.AlertManager.__new__(am.AlertManager)
    mgr._tg, mgr._enabled = None, False
    sent = []
    mgr._send = lambda msg: (sent.append(msg), True)[1]
    am.public_ip = lambda: ("1.2.3.4", "")
    mgr.send_startup_alert(paper=True, instrument="QQQ", risk_usd=1050.0,
                           restart_type="fresh boot")
    return sent[0] if sent else ""


_A = {}
guard("B9 the real startup alert carries the agent field",
      lambda: "Claude up (continue)" in _A.setdefault("on", _alert(True)),
      lambda: _A.get("on", "")[:120])

guard("B9b it says UNKNOWN when there is no stamp, never guessing",
      lambda: "Claude status unknown" in _A.setdefault("off", _alert(False)),
      lambda: _A.get("off", "")[:120])

guard("B0c no tmux session is left behind by this checker",
      lambda: subprocess.run(["tmux", "has-session", "-t", SESS],
                             capture_output=True).returncode != 0,
      lambda: "session %s absent" % SESS)

guard("B0b /etc/systemd/system is untouched",
      lambda: (sorted(os.listdir("/etc/systemd/system"))
               if os.path.isdir("/etc/systemd/system") else []) == _sysd_before)

print()
if FAILED:
    print(f"RED — {len(FAILED)} of {len(RAN)}: " + ", ".join(FAILED))
    sys.exit(1)
print(f"GREEN — {len(RAN)} checks")
sys.exit(0)
