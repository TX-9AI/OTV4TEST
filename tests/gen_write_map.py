#!/usr/bin/env python3
"""
tests/gen_write_map.py  v4.3
Generates docs/WRITE_MAP.md — what every box writes, and who writes it.

v4.3  2026-09-14  OTV4TEST r28 (MAP.3) — THE PURGE'S DELETES WERE INVISIBLE,
      ON THE ONE PATH THAT HAD JUST DELETED LIVE ROWS. `warehouse/retention_purge.py`
      deletes through `f"DELETE FROM {table} ..."` inside loops over its own
      policy dicts (`ARTIFACT_DAYS`, `DERIVED_ARTIFACT_DAYS`, `DERIVED_CDC_DAYS`),
      so the map credited it with `candles` only while it deletes from thirteen
      more tables. `--check` was green: the map was current and wrong (MAP.2).
      r18's constant resolution could not help — the placeholder is a LOOP
      VARIABLE, not a constant. `_loop_sql()` now reads the AST: a `for` whose
      target (or first unpacked name) is the placeholder, over an iterable built
      ONLY from this module's own literal dict/list/tuple/set constants of
      strings (plus `list`/`sorted`/`tuple`/`set` and `.items()`/`.keys()`), has
      each f-string SQL in its body matched once per member. ⚠️ CONSERVATIVE AS
      r18's: any other name in the iterable skips the loop, so an imported
      constant or a runtime value stays invisible (the old behaviour), and only
      tables some module CREATEs are attributed. `tests/check_map_accuracy.py`
      W1b pins that no NEVER_PURGE table picks up a delete.

v4.2  2026-09-13  OTV4TEST r18 — A TABLE NAMED THROUGH A CONSTANT WAS INVISIBLE,
      AND FOUR MORE WERE "(unattributed)" ONLY BECAUSE NOBODY ADDED THE LINE.
      `derived/base.py` writes `CREATE TABLE IF NOT EXISTS {STATUS_TABLE}`, so
      `derived_engine_status` — written by every derived engine every tick, read
      by `tools/manifold_health.py` — appeared NOWHERE, while the flag list
      reported "No writer (0): none" and the header reported 29 tables. The map
      that exists to make a table with no writer visible was itself blind to a
      writer with no literal. Module constants are now resolved into their own
      placeholders; the substitution is conservative and an unresolvable name
      simply stays invisible, which is the old behaviour rather than a wrong one.
      Plus `gate_disposition`/`plan_check`/`plan_tick` -> derived_store.db and
      `resting_orders` -> resting_orders.db, all four verified against the live
      files on the box — the last of which is a FOURTH database the map had
      never named.
v4.1  2026-08-26  r146 — THE MAP WAS ORDER-DEPENDENT AND FAILED THE GATE ON
      CONTROL WHILE PASSING IN THE SANDBOX. `scan()` recorded a READ only if
      the table's creator/writer had ALREADY been scanned, and `_files()`
      walked directories in FILESYSTEM order (os.walk, unsorted). So a reader
      that sat in a directory walked before its writer's directory was
      silently dropped — and which directory walks first differs between two
      machines. It surfaced the moment r146 moved plan_tick's creator from
      derived/ to strategy/. Fixed: directories are walked sorted, and reads
      are collected in a SECOND pass after every writer is known. The output
      is now a function of the tree alone.

v4.0  2026-08-25  Operator's ask: "a document that answers what does every box
write and who writes it — like a file map, but for journal writers."

WHY IT IS SEPARATE FROM FILE_MAP.md. That map answers "what calls what" from
the import graph. This answers a different question the import graph cannot:
**which module OWNS which table.** By r70 this repo had 22 tables across three
databases and NO SINGLE INDEX of who writes them — the ownership lived only in
scattered docstrings, which is the same shape as the sensor problem: a thing
that exists with no way to see it whole.

⚠️ GENERATED, NEVER HAND-MAINTAINED. A hand-kept write map drifts exactly the
way the version headers drifted across day_trader_pro — the changelogs advanced
while the title lines went stale for weeks. This is regenerated in the gate.

⚠️ IT REPORTS WHAT THE SOURCE SAYS, NOT WHAT A SCHEMA DUMP SAYS. A live
database shows tables that exist; this shows tables the CODE creates and
writes. The difference is the interesting part — a table in the db with no
writer in the tree is an orphan, and a writer whose table nobody reads is dead
weight. Both are visible here and in neither place alone.

Run:  python3 tests/gen_write_map.py           # regenerate
      python3 tests/gen_write_map.py --check   # fail if stale
"""

from __future__ import annotations

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "WRITE_MAP.md")

SKIP_DIRS = {".git", "__pycache__", "venv", "docs", "node_modules"}

RE_CREATE = re.compile(r"CREATE TABLE IF NOT EXISTS\s+([a-z_]+)", re.I)
RE_INSERT = re.compile(r"INSERT\s+(?:OR\s+\w+\s+)?INTO\s+([a-z_]+)", re.I)
RE_UPDATE = re.compile(r"UPDATE\s+([a-z_]+)\s+SET", re.I)
RE_DELETE = re.compile(r"DELETE\s+FROM\s+([a-z_]+)", re.I)
RE_SELECT = re.compile(r"FROM\s+([a-z_]+)", re.I)
RE_DBFILE = re.compile(r"([a-z_]+)\.db")

# r18 — A TABLE NAMED THROUGH A CONSTANT WAS INVISIBLE, AND THE MAP SAID SO
# NOWHERE. Every pattern above requires a LITERAL table name, so
# `CREATE TABLE IF NOT EXISTS {STATUS_TABLE}` in `derived/base.py` matched
# nothing: `derived_engine_status` — written by every derived engine on every
# tick and read by `tools/manifold_health.py` — was absent from a document
# whose flag list reported "No writer (0): none".
# 🔑 THE FAILURE RENDERED AS A SMALLER, PLAUSIBLE COUNT rather than an error,
# which is this repo's most-repeated defect shape (WORKING_AGREEMENT §35).
# So module-level `NAME = "table_name"` constants are resolved and substituted
# into their own `{NAME}` placeholders before anything is matched.
# ⚠️ DELIBERATELY CONSERVATIVE: only a bare uppercase assignment to a single
# lowercase identifier, only inside a `{...}` placeholder, only in the file
# that declares it. An unresolvable name substitutes nothing and the table goes
# back to being invisible — which is the old behaviour, never a wrong answer.
RE_CONST = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*[\"']([a-z_][a-z0-9_]*)[\"']\s*$", re.M)


def _resolve_consts(src: str) -> str:
    """Substitute this module's own `NAME = "table"` constants into `{NAME}`."""
    consts = dict(RE_CONST.findall(src))
    if not consts:
        return src
    for name, val in consts.items():
        src = src.replace("{" + name + "}", val)
    return src


# r28 (MAP.3) — the iterable may be dressed in these and nothing else.
_ITER_WRAPPERS = {"list", "sorted", "tuple", "set"}
_ITER_METHODS = {"items", "keys"}


def _string_members(node):
    """A literal dict's keys or a list/tuple/set's elements, if all are strings."""
    if isinstance(node, ast.Dict):
        elts = node.keys
    elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        elts = node.elts
    else:
        return None
    vals = [e.value for e in elts if isinstance(e, ast.Constant)]
    if len(vals) != len(elts) or not all(isinstance(v, str) for v in vals):
        return None
    return vals


def _iter_members(node, consts):
    """Members of a `for` iterable built only from this module's literal constants.
    -> list of strings, or None when anything in it is not resolvable."""
    names = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            names.add(sub.id)
        elif isinstance(sub, ast.Attribute) and sub.attr not in _ITER_METHODS:
            return None
        elif not isinstance(sub, (ast.Name, ast.Attribute, ast.Call, ast.BinOp,
                                  ast.Add, ast.Load)):
            return None
    out = []
    for n in sorted(names):
        if n in _ITER_WRAPPERS:
            continue
        if n not in consts:
            return None
        out.extend(consts[n])
    return out or None


def _loop_sql(src: str):
    """-> [(sql text with the loop variable substituted), ...] for every f-string
    inside a `for` over this module's own literal constants (see v4.3)."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    consts = {}
    for st in tree.body:
        if (isinstance(st, ast.Assign) and len(st.targets) == 1
                and isinstance(st.targets[0], ast.Name)):
            m = _string_members(st.value)
            if m is not None:
                consts[st.targets[0].id] = m
    if not consts:
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        tgt = node.target
        if isinstance(tgt, ast.Tuple) and tgt.elts:
            tgt = tgt.elts[0]
        if not isinstance(tgt, ast.Name):
            continue
        members = _iter_members(node.iter, consts)
        if not members:
            continue
        for sub in (n for st in node.body for n in ast.walk(st)):
            if not isinstance(sub, ast.JoinedStr):
                continue
            parts, uses = [], False
            for v in sub.values:
                if isinstance(v, ast.Constant):
                    parts.append(str(v.value))
                elif isinstance(v.value, ast.Name) and v.value.id == tgt.id:
                    parts.append("\0")
                    uses = True
                else:
                    parts.append("?")
            if uses:
                tmpl = "".join(parts)
                out.extend(tmpl.replace("\0", m) for m in members)
    return out

# Which database each table lives in. Derived from the module that CREATEs it,
# so a table moving file moves here automatically.
DB_OF_DIR = {
    "data/candle_feed.py": "feed_store.db",
    "data/derived_store.py": "derived_store.db",
    "database/trade_logger.py": "trades.db",
}

# ⚠️ MODULES THAT CREATE THEIR OWN TABLE INSIDE ANOTHER STORE'S FILE.
# `derived/` engines call `self._store.conn.execute("CREATE TABLE ...")` so the
# table lives in derived_store.db while the DDL lives in the engine. That is
# deliberate — one engine per store, each owning its own schema — but it means
# the file that CREATEs is not the file that names the database, and the first
# run of this generator listed four tables as "(unattributed)". Reporting them
# as homeless would be wrong; guessing silently would be worse. This is the
# explicit mapping, and it is the ONE hand-maintained thing here.
# r18 — THE FOUR "(unattributed)" TABLES WERE ALL RESOLVABLE, AND ONE OF THEM
# NAMED A FOURTH DATABASE THE MAP NEVER MENTIONED. Verified by reading the live
# files on the box, not inferred: `gate_disposition`, `plan_check` and
# `plan_tick` are in `derived_store.db`; `resting_orders` is in its own
# `data/resting_orders.db`. An "(unattributed)" heading reads as "nobody knows",
# when in fact nobody had added the line.
DB_OF_PREFIX = {
    "derived/": "derived_store.db",
    "analysis/tenor_publish.py": "feed_store.db",
    "analysis/gate_report.py": "derived_store.db",
    "strategy/plan.py": "derived_store.db",
    "execution/resting_orders.py": "resting_orders.db",
}


def _files():
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = sorted(d for d in dn if d not in SKIP_DIRS)   # v4.1: deterministic
        for f in sorted(fn):
            if f.endswith(".py"):
                yield os.path.relpath(os.path.join(dp, f), ROOT)


def scan():
    creates, writes, reads, dbs = {}, {}, {}, {}
    sources = {}
    looped = {}                         # r28: rel -> loop-resolved SQL texts
    for rel in _files():
        try:
            raw = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        except Exception:                                       # noqa: BLE001
            continue
        sources[rel] = _resolve_consts(raw)
        looped[rel] = _loop_sql(raw)
    for rel, src in sources.items():
        for t in RE_CREATE.findall(src):
            creates.setdefault(t, set()).add(rel)
            if rel in DB_OF_DIR:
                dbs[t] = DB_OF_DIR[rel]
            else:
                for pref, db in DB_OF_PREFIX.items():
                    if rel.startswith(pref):
                        dbs[t] = db
                        break
        for rx, kind in ((RE_INSERT, "insert"), (RE_UPDATE, "update"),
                         (RE_DELETE, "delete")):
            for t in rx.findall(src):
                writes.setdefault(t, {}).setdefault(rel, set()).add(kind)
    # r28 (MAP.3) — loop-resolved SQL, attributed only to tables the tree
    # CREATEs, so a policy key that is not a table can never invent one.
    for rel, texts in looped.items():
        for text in texts:
            for rx, kind in ((RE_INSERT, "insert"), (RE_UPDATE, "update"),
                             (RE_DELETE, "delete")):
                for t in rx.findall(text):
                    if t in creates:
                        writes.setdefault(t, {}).setdefault(rel, set()).add(kind)
            for t in RE_SELECT.findall(text):
                if t in creates:
                    reads.setdefault(t, set()).add(rel)
    # v4.1 — SECOND PASS, after every writer is known. A read is only a read
    # of a table this tree writes; deciding that mid-walk made the answer
    # depend on directory order.
    for rel, src in sources.items():
        for t in RE_SELECT.findall(src):
            # a module that only writes also names the table in its INSERT;
            # reads are recorded separately so "who consumes this" is answerable
            if t in creates or t in writes:
                reads.setdefault(t, set()).add(rel)
    return creates, writes, reads, dbs


def render() -> str:
    creates, writes, reads, dbs = scan()
    tables = sorted(set(creates) | set(writes))
    L = []
    L.append("# WRITE_MAP.md — what every box writes, and who writes it")
    L.append("")
    L.append("**GENERATED by `tests/gen_write_map.py` — do not edit by hand.**")
    L.append("Regenerated in the land gate; a stale map fails `--check`.")
    L.append("")
    L.append("`FILE_MAP.md` answers *what calls what*. This answers *who owns "
             "which table* — a question the import graph cannot.")
    L.append("")
    L.append("⚠️ **A table with no writer is an orphan. A table nobody reads "
             "is dead weight.** Both are visible here and in neither the "
             "schema nor the call graph alone.")
    L.append("")
    L.append(f"**{len(tables)} tables.**")
    L.append("")

    by_db = {}
    for t in tables:
        by_db.setdefault(dbs.get(t, "(unattributed)"), []).append(t)

    for db in sorted(by_db):
        L.append(f"## {db}")
        L.append("")
        L.append("| table | created by | written by | read by |")
        L.append("|---|---|---|---|")
        for t in sorted(by_db[db]):
            c = ", ".join(f"`{x}`" for x in sorted(creates.get(t, []))) or "—"
            w = writes.get(t, {})
            wparts = []
            for mod in sorted(w):
                kinds = "/".join(sorted(w[mod]))
                wparts.append(f"`{mod}` ({kinds})")
            wtxt = ", ".join(wparts) or "**— NO WRITER**"
            r = sorted(x for x in reads.get(t, set())
                       if x not in w and x not in creates.get(t, set()))
            rtxt = ", ".join(f"`{x}`" for x in r) or "—"
            L.append(f"| `{t}` | {c} | {wtxt} | {rtxt} |")
        L.append("")

    orphan_w = [t for t in tables if not writes.get(t)]
    orphan_r = [t for t in tables
                if not [x for x in reads.get(t, set())
                        if x not in writes.get(t, {})]]
    L.append("## Flags")
    L.append("")
    L.append(f"- **No writer** ({len(orphan_w)}): "
             + (", ".join(f"`{t}`" for t in orphan_w) or "none"))
    L.append(f"- **No external reader** ({len(orphan_r)}): "
             + (", ".join(f"`{t}`" for t in orphan_r) or "none"))
    L.append("")
    L.append("⚠️ *No external reader* is not automatically a defect — a table "
             "written today for a study run in a month is exactly the point of "
             "the derived layer. It IS a defect when nobody ever intends to "
             "read it, and this list is where that question gets asked.")
    L.append("")
    return "\n".join(L)


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        try:
            cur = open(OUT, encoding="utf-8").read()
        except FileNotFoundError:
            print("  WRITE_MAP.md missing — run gen_write_map.py")
            return 1
        if cur.strip() != text.strip():
            print("  WRITE_MAP.md is STALE — regenerate it")
            return 1
        print("  write map is current")
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
