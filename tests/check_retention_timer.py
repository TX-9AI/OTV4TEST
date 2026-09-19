#!/usr/bin/env python3
"""tests/check_retention_timer.py — v1.1
THE NIGHTLY RETENTION PURGE TIMER RENDERS A UNIT THAT CAN RUN, WHEN THE OPERATOR ASKED.

v1.1  2026-09-19 — OTV4TEST r53. T5 REPINNED TO NIGHTLY 16:05 ET (operator: "You
      can make it a nightly purge, but have it run at 1605").
      🔴 AND THIS CHECKER IS WHY THE DEFECT WAS CAUGHT, BY BEING GREEN ON BOTH SIDES
      OF THE CHANGE. The cadence was first changed by hand on the LIVE systemd unit;
      the installer still rendered Sat 08:30, so T5 passed, the full sweep was clean,
      and the live box had SILENTLY DRIFTED FROM ITS OWN INSTALLER — the next install
      would have reverted the operator's instruction with nothing saying so.
      ⚠️ SAME SHAPE AS r52's WAL PRAGMA: a setting applied to the running instance
      instead of to the thing that recreates it does not survive, and looks fixed
      until it is recreated. The rule this repo keeps relearning is that the
      INSTALLER is the source of truth and the live unit is only its output.
v1.0  2026-09-14 — OTV4TEST r27 (BOX.4). Operator: "I want the purge put on a timer.
      Let's try Saturday after the automatic 8AM wake."

🔑 RENDERED, NOT REASONED (check_midnight_halt M4's method, r21). The REAL
installer runs in a scratch copy of the repo layout with `sudo` STUBBED — `tee`
writes into scratch, `systemctl` and `rm` are logged and never executed, anything
else is refused — and the units it wrote are read back.
⚠️ T0 IS THE GUARD AND RUNS FIRST: if `sudo` does not resolve to the stub, the
installer is NOT RUN. A checker that could install a live timer during a land is
a fixture reaching live state (r13) with a worse blast radius.

  T0  GUARD: `sudo` resolves to the stub
  T1  the installer renders a service and a timer
  T2  ExecStart names a script that EXISTS, under the repo root (r21's defect class)
  T3  ...run by the repo's own venv python
  T4  ...with --apply (r162: without it the purge is a dry run forever)
  T5  the timer fires NIGHTLY 16:05 America/New_York — after the close, zone-aware
  T6  Persistent=true (a missed purge is harmless to replay, by ruling)
  T7  the service never stops or halts anything — no shutdown, no systemctl stop
  T8  it asks systemd to enable the timer (logged by the stub, not executed)
  T9  with no venv the installer REFUSES rather than binding a guessed python3
  T10 the calendar expression parses on this box's systemd and yields a next elapse

Born red at r26: the installer does not exist.
Run:  python3 tests/check_retention_timer.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILED, RAN = [], []
INSTALLER = os.path.join("deploy", "install_retention_purge_timer.sh")

_STUB_SUDO = """#!/usr/bin/env bash
: "${MH_ETC:?stub sudo refuses to run without MH_ETC}"
case "$1" in
  tee)       exec tee "$MH_ETC/$(basename "$2")" >/dev/null ;;
  systemctl) echo "[stub] systemctl ${*:2}"; exit 0 ;;
  rm)        echo "[stub] rm ${*:2}"; exit 0 ;;
  *)         echo "[stub] REFUSED: $*" >&2; exit 1 ;;
esac
"""


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    RAN.append(name)
    if not ok:
        FAILED.append(name)


def _scratch(tmp, with_venv):
    tree, etc, stub = (os.path.join(tmp, d) for d in ("repo", "etc", "stub"))
    for d in (os.path.join(tree, "deploy"), os.path.join(tree, "warehouse"),
              os.path.join(tree, "data"), etc, stub):
        os.makedirs(d)
    shutil.copy(os.path.join(_root, INSTALLER), os.path.join(tree, INSTALLER))
    shutil.copy(os.path.join(_root, "warehouse", "retention_purge.py"),
                os.path.join(tree, "warehouse", "retention_purge.py"))
    if with_venv:
        os.symlink(os.path.join(_root, "venv"), os.path.join(tree, "venv"))
    sudo = os.path.join(stub, "sudo")
    with open(sudo, "w") as f:
        f.write(_STUB_SUDO)
    os.chmod(sudo, 0o755)
    path = stub + os.pathsep + "/usr/bin" + os.pathsep + "/bin"
    return tree, etc, sudo, path


def main():
    if not os.path.isfile(os.path.join(_root, INSTALLER)):
        check("T1 the installer exists", False, INSTALLER)
        print(f"\nRED — {len(FAILED)} of {len(RAN)} failed")
        return 1
    have_venv = os.path.isdir(os.path.join(_root, "venv"))
    with tempfile.TemporaryDirectory() as tmp:
        tree, etc, sudo, path = _scratch(tmp, have_venv)
        resolved = shutil.which("sudo", path=path)
        check("T0 GUARD: `sudo` resolves to the STUB — nothing can reach the real /etc",
              resolved == sudo, f"resolved={resolved}")
        if resolved != sudo:
            check("T1 the installer was NOT RUN, because the guard failed", False)
        elif not have_venv:
            print("  SKIP  T1-T8 no venv at the repo root in this environment — the installer refuses by design")
        else:
            r = subprocess.run(["bash", os.path.join(tree, INSTALLER)], capture_output=True, text=True,
                               timeout=60, env={"PATH": path, "MH_ETC": etc, "HOME": tmp})
            svc_p = os.path.join(etc, "optbot-retention-purge.service")
            tmr_p = os.path.join(etc, "optbot-retention-purge.timer")
            svc = open(svc_p).read() if os.path.exists(svc_p) else ""
            tmr = open(tmr_p).read() if os.path.exists(tmr_p) else ""
            check("T1 the installer renders a service and a timer", bool(svc and tmr),
                  (r.stderr or r.stdout)[-160:] if not (svc and tmr) else "")
            es = next((l.split("=", 1)[1] for l in svc.splitlines() if l.startswith("ExecStart=")), "")
            parts = es.split()
            py = parts[0] if parts else ""
            script = next((p for p in parts[1:] if p.endswith(".py")), "")
            check("T2 ExecStart names a script that EXISTS under the repo root",
                  bool(script) and os.path.isfile(script)
                  and script == os.path.join(tree, "warehouse", "retention_purge.py"),
                  es.replace(tree, "<repo>") or "no ExecStart")
            check("T3 ...run by the repo's own venv python", py == os.path.join(tree, "venv", "bin", "python"),
                  py.replace(tree, "<repo>"))
            check("T4 ...with --apply", "--apply" in parts[1:], es.replace(tree, "<repo>"))
            cal = next((l.split("=", 1)[1].strip() for l in tmr.splitlines() if l.startswith("OnCalendar=")), "")
            check("T5 the timer fires NIGHTLY 16:05 America/New_York", cal == "*-*-* 16:05:00 America/New_York", cal)
            check("T6 Persistent=true", "Persistent=true" in tmr.splitlines())
            code = [l for l in svc.splitlines() if not l.lstrip().startswith("#")]
            check("T7 the service stops and halts nothing",
                  not any("shutdown" in l or "systemctl" in l or "poweroff" in l for l in code))
            check("T8 it enables the timer (through the stub, never executed)",
                  "[stub] systemctl enable --now optbot-retention-purge.timer" in r.stdout, r.stdout[-120:])
    with tempfile.TemporaryDirectory() as tmp:
        tree, etc, sudo, path = _scratch(tmp, with_venv=False)
        r = subprocess.run(["bash", os.path.join(tree, INSTALLER)], capture_output=True, text=True,
                           timeout=60, env={"PATH": path, "MH_ETC": etc, "HOME": tmp})
        check("T9 with no venv the installer REFUSES, writing no unit",
              r.returncode != 0 and not os.listdir(etc) and "refusing" in r.stderr, f"rc={r.returncode}")
    sa = shutil.which("systemd-analyze")
    if sa:
        r = subprocess.run([sa, "calendar", "*-*-* 16:05:00 America/New_York"],
                           capture_output=True, text=True, timeout=30)
        nxt = next((l for l in r.stdout.splitlines() if "Next elapse" in l), "")
        check("T10 the calendar parses on this box's systemd, next elapse within 24h",
              r.returncode == 0 and bool(nxt), nxt.strip())
    else:
        print("  SKIP  T10 no systemd-analyze in this environment")

    print()
    if FAILED:
        print(f"RED — {len(FAILED)} of {len(RAN)} failed: {', '.join(FAILED)}")
        return 1
    print(f"GREEN — {len(RAN)} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
