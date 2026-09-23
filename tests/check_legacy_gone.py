#!/usr/bin/env python3
"""
tests/check_legacy_gone.py  v1.0
LVL.15 STEP 5 — THE OLD LEVEL CODE LEAVES, ONE MODULE AT A TIME, AND NOTHING
STILL IMPORTS WHAT LEFT.

v1.0  2026-09-23  OTV4TEST r121 — analysis/pitchfork_lifecycle.py, the first.

The operator approved step 5 on 2026-09-23 ("Yes, for sure"): delete the code
the rebuilt levels replaced. Each delivery appends its module to LEGACY below.

⚠️ WHAT THIS CAN AND CANNOT ASSERT. The lander applies `DEL` AFTER it runs the
CHECKs (r302's lesson, tools/land.sh), so a gate that asserted "the file is
absent" would fail the very delivery that removes it. What is true BEFORE the
delete, and what makes the delete safe, is that NO OTHER FILE IMPORTS IT —
statically, lazily inside a function, or through importlib/__import__ with a
literal name. That is asserted here. The absence itself is verified after the
land, by hand, and recorded in the ledger.

  G0 CONTROL — the scanner FINDS a live import (execution/exit_engine.py
     imports derived.level_rules), so an empty result below means something
  G1 nothing in the tree imports any module in LEGACY
"""
from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# module -> the revision that deleted it
LEGACY = {
    "analysis.pitchfork_lifecycle": "r121",
}

FAILED, RAN = [], []


def check(name, ok, detail=""):
    RAN.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILED.append(name.split()[0])


def _files():
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in ("venv", ".git", "__pycache__", "node_modules")]
        for fn in fns:
            if fn.endswith(".py"):
                yield os.path.join(dp, fn)


def imports_of(path):
    """Every module name this file imports: `import a.b`, `from a import b`
    (yields a and a.b), and importlib.import_module / __import__ with a literal."""
    try:
        tree = ast.parse(open(path, encoding="utf-8").read(), path)
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return set()
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            out.add(n.module)
            out.update(f"{n.module}.{a.name}" for a in n.names)
        elif isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant) \
                and isinstance(n.args[0].value, str):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name in ("import_module", "__import__"):
                out.add(n.args[0].value)
    return out


def main():
    found = {}
    for p in _files():
        rel = os.path.relpath(p, ROOT)
        for m in imports_of(p):
            found.setdefault(m, set()).add(rel)
    ctl = found.get("derived.level_rules", set())
    check("G0 control: the scanner finds exit_engine importing derived.level_rules",
          "execution/exit_engine.py" in ctl, f"{len(ctl)} importer(s)")
    bad = []
    for mod in LEGACY:
        own = mod.replace(".", "/") + ".py"
        users = sorted(u for u in found.get(mod, set()) if u != own)
        bad += [f"{u} -> {mod}" for u in users]
    check("G1 nothing imports a deleted legacy module", not bad,
          "; ".join(bad) if bad else f"{len(LEGACY)} module(s): {', '.join(LEGACY)}")
    print()
    if FAILED:
        print(f"RED — {len(FAILED)} of {len(RAN)} failed: {', '.join(FAILED)}")
        return 1
    print(f"GREEN — {len(RAN)} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
