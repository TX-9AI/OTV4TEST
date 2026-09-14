#!/usr/bin/env python3
"""tests/check_map_accuracy.py — v1.0
THE GENERATED MAPS ARE CHECKED FOR ACCURACY, NOT ONLY FOR FRESHNESS.

v1.0  2026-09-14 — OTV4TEST r28 (MAP.2, MAP.3). Both `--check` gates ask "does
      the map regenerate identical?", which a map blind to a writer passes every
      time. MAP.1 (r18) sat behind a green `--check` for months. On 2026-09-14
      the write map was current and still credited `warehouse/retention_purge.py`
      with deleting from `candles` ONLY, while it deletes from thirteen more
      tables through `f"DELETE FROM {table}"` loops over its policy dicts. That
      is the path r26 found deleting live rows, and r27 put it on a timer. The
      file map's orphan list named `warehouse/midnight_halt.py` (an installed
      timer) and `tools/check_land_discipline.py` (run by every land).

  W1  every table in the purge's policy dicts is a `retention_purge` DELETE on the map
  W1b ...and no NEVER_PURGE table is (the resolution must stay conservative)
  W1c the rendered WRITE_MAP row for each of those tables names the purge
  E1  every repo script a deploy/ unit launches is a declared ENTRY_POINT
  E1b ...and every one of them EXISTS (r21's defect class: a unit naming no file)
  E2  every repo script tools/land.sh runs is a declared ENTRY_POINT
  L1  every table in the box's four stores is on the write map (MAP.1's class)
  L2  ...in the database the map says it is in
  L3  (report only) map tables not yet on disk, each named

🔑 THE EXPECTATIONS COME FROM THE REPO, NOT FROM THE GENERATOR'S BELIEF (§0.4).
W reads the purge's dicts by IMPORTING `warehouse/retention_purge.py` — runtime
values — while the generator reads source; E reads the unit text in deploy/ and
`tools/land.sh`; L reads `sqlite_master`.

⚠️ L READS THE BOX'S LIVE STORES, READ-ONLY, AND THAT IS ITS WHOLE JOB. Every
connection is `mode=ro`; nothing is written. The stores are found at the layout
the repo's own defaults use (`~/options-trader/data/*.db`, `~/options-trader/
trades.db`: `data/options_chain.py`, `data/derived_store.py`, `config.DB_PATH`,
`execution/resting_orders.py`) — NOT through OT_TRADES_DB/OT_DERIVED_DB, which
the lander points at empty scratch files. OT_MAP_STORE_ROOT overrides the root.
A store that is absent prints NOT RUN by name — never PASS (§38.7).
⚠️ L3 DOES NOT FAIL. A table the code creates on first write (e.g.
`exit_counterfactual` before any flow exit is evaluated) is legitimately absent;
failing on it would be a red that means "not yet", and reds like that get skipped.

Born red at a9f4677 (r27): W1, W1c, E1, E2. L1 is proven against r17's
generator (8dc81a0), which cannot see `derived_engine_status`.
Run:  python3 tests/check_map_accuracy.py
"""
import importlib.util
import os
import re
import sqlite3
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILED, RAN = [], []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    RAN.append(name)
    if not ok:
        FAILED.append(name)


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_root, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _unit_scripts():
    """Repo scripts named by ExecStart/ExecCondition anywhere under deploy/."""
    out = set()
    rx_path = re.compile(r"(?:\$DIR|\$\{DIR\}|__INSTALL_DIR__|/home/ubuntu/options-trader)/([\w/]+\.py)")
    rx_mod = re.compile(r"\s-m\s+([\w.]+)")
    d = os.path.join(_root, "deploy")
    for fn in sorted(os.listdir(d)):
        for ln in open(os.path.join(d, fn), encoding="utf-8", errors="replace"):
            s = ln.strip()
            if not re.match(r"Exec(Start|Condition)=", s):
                continue
            out.update(rx_path.findall(s))
            out.update(m.replace(".", "/") + ".py" for m in rx_mod.findall(s))
    return out


def _land_scripts():
    """Repo scripts outside tests/ that tools/land.sh runs with python3."""
    src = open(os.path.join(_root, "tools", "land.sh"), encoding="utf-8").read()
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    return {p for p in re.findall(r"python3\s+\"?[^\s\"]*?((?:tools|warehouse|deploy)/[\w/]+\.py)", code)}


def main():
    wm = _load("tests/gen_write_map.py", "_wm_under_check")
    fm = _load("tests/gen_file_map.py", "_fm_under_check")
    rp = _load("warehouse/retention_purge.py", "_rp_under_check")
    creates, writes, reads, dbs = wm.scan()
    rendered = wm.render()

    # ── W: the purge's dynamic deletes ────────────────────────────────────
    purged = set(rp.ARTIFACT_DAYS) | set(rp.DERIVED_ARTIFACT_DAYS) | set(rp.DERIVED_CDC_DAYS)
    purged -= set(rp.NEVER_PURGE)
    miss = sorted(t for t in purged
                  if "delete" not in writes.get(t, {}).get("warehouse/retention_purge.py", set()))
    check("W1 every purge-policy table is a retention_purge DELETE on the map",
          not miss, "missing: " + ", ".join(miss) if miss else f"{len(purged)} tables")
    wrong = sorted(t for t in rp.NEVER_PURGE
                   if "warehouse/retention_purge.py" in writes.get(t, {}))
    check("W1b no NEVER_PURGE table is attributed to the purge", not wrong, ", ".join(wrong))
    rows = {ln.split("|")[1].strip().strip("`"): ln for ln in rendered.splitlines()
            if ln.startswith("| `")}
    bad = sorted(t for t in purged
                 if "`warehouse/retention_purge.py` (delete" not in rows.get(t, ""))
    check("W1c the rendered row of each purged table names the purge",
          not bad, "missing: " + ", ".join(bad) if bad else "")

    # ── E: entry points the import graph cannot see ───────────────────────
    units = _unit_scripts()
    missing_ep = sorted(p for p in units if p not in fm.ENTRY_POINTS)
    check("E1 every script a deploy/ unit launches is a declared entry point",
          not missing_ep, "not declared: " + ", ".join(missing_ep) if missing_ep else f"{len(units)} scripts")
    absent = sorted(p for p in units if not os.path.isfile(os.path.join(_root, p)))
    check("E1b every script a deploy/ unit launches exists", not absent, ", ".join(absent))
    land = _land_scripts()
    missing_l = sorted(p for p in land if p not in fm.ENTRY_POINTS)
    check("E2 every script tools/land.sh runs is a declared entry point",
          bool(land) and not missing_l,
          "not declared: " + ", ".join(missing_l) if missing_l else ", ".join(sorted(land)) or "none found")

    # ── L: the map against the box's stores (MAP.2) ───────────────────────
    store_root = os.environ.get("OT_MAP_STORE_ROOT") or os.path.expanduser("~/options-trader")
    tables = set(creates) | set(writes)
    map_db = {t: dbs.get(t, "(unattributed)") for t in tables}
    disk = {}
    for db in sorted(set(map_db.values()) - {"(unattributed)"}):
        path = next((p for p in (os.path.join(store_root, "data", db), os.path.join(store_root, db))
                     if os.path.isfile(p)), None)
        if path is None:
            print(f"  NOT RUN  L  {db}: no store at {store_root}/data/{db} or {store_root}/{db}")
            continue
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
        try:
            disk[db] = {r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        finally:
            c.close()
        print(f"  read   {path} (read-only): {len(disk[db])} tables")
    if not disk:
        print("  NOT RUN  L1/L2 — no store found; this is not a pass")
    else:
        unmapped = sorted(f"{db}:{t}" for db, ts in disk.items() for t in ts if t not in tables)
        check("L1 every table on disk is on the write map", not unmapped, ", ".join(unmapped))
        misplaced = sorted(f"{t} (map {map_db[t]}, disk {db})" for db, ts in disk.items()
                           for t in ts if t in tables and map_db[t] != db)
        check("L2 each is in the database the map names", not misplaced, ", ".join(misplaced))
        notyet = sorted(f"{map_db[t]}:{t}" for t in tables
                        if map_db[t] in disk and t not in disk[map_db[t]])
        print("  info  L3 on the map, not yet on disk: " + (", ".join(notyet) or "none"))

    print()
    if FAILED:
        print(f"RED — {len(FAILED)} of {len(RAN)} failed: {', '.join(FAILED)}")
        return 1
    print(f"GREEN — {len(RAN)} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
