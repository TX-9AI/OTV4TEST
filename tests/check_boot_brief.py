#!/usr/bin/env python3
"""
tests/check_boot_brief.py  v1.1
v1.1  2026-10-03  OTV4TEST r232 — ONE AGNOSTIC BRIEF: HANDOFF_SPX.md is retired. B2 uses docs/FIRST_BOOT.md as the
      override target (the switch stays); B6 now pins HANDOFF.md as symbol agnostic.
v1.0  2026-10-03  OTV4TEST r231 (BOOT.7) — A BOX CAN BOOT FROM ITS OWN BRIEF.

  SPX-TEST's first session believed it was QQQ-TEST: every box read docs/HANDOFF.md.
  B1  OT_BRIEF unset -> docs/HANDOFF.md (QQQ-TEST unchanged)
  B2  OT_BRIEF=<a .md under docs/> -> that file (docs/FIRST_BOOT.md as the fixture)
  B3  a missing file, a file outside docs/, a non-.md -> HANDOFF.md, said on stderr
  B4  the first-boot marker still wins over OT_BRIEF
  B5  the installer writes OT_BRIEF into the unit only when it is set
  B6  docs/HANDOFF.md is SYMBOL AGNOSTIC: no "You exist on QQQ-TEST"; it has BOX IDENTITY, the no-push rule, the boot order
Fresh interpreter per case. Run: python3 tests/check_boot_brief.py
"""
import json, os, subprocess, sys, tempfile
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILED = []
def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  — {detail}"))
    if not ok:
        FAILED.append(name.split()[0])
_P = r'''
import json, os, sys
sys.path.insert(0, sys.argv[1])
import tools.claude_boot as cb
b, first = cb.choose_brief()
print("@@" + json.dumps([os.path.relpath(cb.BRIEF, sys.argv[1]), os.path.relpath(b, sys.argv[1]), first]))
'''
def run(brief=None, marker=False):
    env = {k: v for k, v in os.environ.items() if k not in ("OT_BRIEF", "OT_FIRST_BOOT_MARKER")}
    d = tempfile.mkdtemp(prefix="check_boot_brief_")
    m = os.path.join(d, "first_boot")
    if marker:
        open(m, "w").close()
    env["OT_FIRST_BOOT_MARKER"] = m
    if brief is not None:
        env["OT_BRIEF"] = brief
    r = subprocess.run([sys.executable, "-c", _P, _root], env=env, capture_output=True, text=True, timeout=60)
    line = [x for x in r.stdout.splitlines() if x.startswith("@@")]
    return (json.loads(line[0][2:]) if line else None), r.stderr
def main():
    try:
        got, _ = run()
        check("B1 unset -> docs/HANDOFF.md", got == ["docs/HANDOFF.md", "docs/HANDOFF.md", False], str(got))
        got, _ = run("docs/FIRST_BOOT.md")
        check("B2 OT_BRIEF=<a .md under docs/> is the brief", got == ["docs/FIRST_BOOT.md", "docs/FIRST_BOOT.md", False], str(got))
        bad = []
        for v in ("docs/NO_SUCH.md", "README.md", "tools/claude_boot.py", "docs/../README.md"):
            g, err = run(v)
            if g is None or g[1] != "docs/HANDOFF.md" or "OT_BRIEF" not in err:
                bad.append((v, g, err[-80:]))
        check("B3 missing / outside docs / not .md fall back to HANDOFF.md, named on stderr", not bad, str(bad))
        got, _ = run("docs/WORKING_AGREEMENT.md", marker=True)
        check("B4 the first-boot marker still wins", got is not None and got[1] == "docs/FIRST_BOOT.md" and got[2] is True, str(got))
        src = open(os.path.join(_root, "deploy", "install_claude_boot.sh")).read()
        check("B5 the installer carries OT_BRIEF only when set", "${OT_BRIEF:+Environment=OT_BRIEF=$OT_BRIEF}" in src)
        h = open(os.path.join(_root, "docs", "HANDOFF.md")).read()
        check("B6 HANDOFF.md is symbol agnostic: identity read at boot, no-push rule, his boot order",
              "You exist on QQQ-TEST" not in h and "## BOX IDENTITY" in h and "NO TEST BOX PUSHES" in h
              and "OT_S3_PUSH=0" in h and "tell me it's mandate, then notify you that it's awake" in h)
    except Exception as exc:  # noqa: BLE001
        check("B0 (did not run)", False, f"{type(exc).__name__}: {exc}")
    if FAILED:
        print(f"\nRED — {sorted(set(FAILED))}"); return 1
    print("\nGREEN — one symbol-agnostic brief; the OT_BRIEF override still works"); return 0
if __name__ == "__main__":
    sys.exit(main())
