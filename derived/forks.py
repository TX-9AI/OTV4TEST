"""
derived/forks.py  v4.3
v4.3  2026-09-23  OTV4TEST r115 — THE BUILDER DECIDES A FORK'S DEATH. Operator: "I wanna
      make sure that the invalidation of the fork comes from the fork builder's
      engine, not from a strategy-plan" / "it's gone when the engine says it's
      gone, not when a strategy says it's gone". r114 put the breach judgement in
      the LEVEL engine, which kept a private dead-set while this engine kept
      serving the fork to every other reader. Now `_judge_rails` runs here on
      every closed 1m bar: a rail BREACHED (level_rules: 1m close beyond, next
      open beyond) adds the identity to `_dead`, clears `last_forks[tf]` so NO
      consumer receives it, and writes an `INVALIDATED:` row to fork_series;
      the builder's rebuild of that same identity is refused every run after
      (reason INVALIDATED_IDENTITY), and a restart restores the dead set from
      those rows (§22). `fork_identity()` is the ONE identity definition — the
      anchor prices, never `idx`.
v4.2  2026-09-12  OTV4TEST r15 — a failed build clears `last_forks[tf]`/`last_idx[tf]`
      (ported from mainline r364): the level map dies with the fork.
v4.1  2026-09-08  OTV4TEST r5 — the engine KEEPS the last built fork per frame
      (`last_forks[tf]`) and the frame's current bar index (`last_idx[tf]`) so
      derived/levels can ask where a tine IS at the bar — the tines are moving
      levels (time + slope) and the level engine must not recompute the fork.
Owns `fork_series`. Tier 2 — regressive, and dies on restart today.

v4.0  2026-08-22  See docs/DERIVED_STORES.md.

The pitchfork reaches back 60-80 bars to find its anchors and currently lives
in a **process-resident cache** (`pitchfork_observer._cache`). Three costs, all
of which the r59 investigation ran straight into:

  · It dies on every deploy. The 10:39 restart on 2026-08-21 is the same class
    of loss that wiped confirmed ORB setups on four boxes.
  · Nobody can see what it decided. When the condor said "rails=absent" all day
    there was no way to ask what fork it had at 10:15 — the diagnosis had to be
    reconstructed synthetically in a sandbox, which is why it was WRONG TWICE.
  · Rejections are computed and thrown away.

🔴 THE REJECTION REASONS ARE THE POINT. `pitchfork.py` names six —
FRAME_TOO_SHORT, NOT_ANCHOR_TF, NO_ATR, NO_CONTAINED_WINDOW, RECENCY,
SEPARATION — and **not one reaches storage or a log.** "No usable daily
pitchfork (rails=absent)" was a single undifferentiated message covering six
different problems, printed on every box on every tick of a zero-trade session.

⚠️ A REJECTION IS A ROW, NOT A SKIPPED WRITE. `built=0` with the reason and the
scan depth. A table that only records successes cannot answer "why not", which
is the question actually being asked when the condor stands down.

⚠️ CONDOR ANCHOR IS 1h — operator ruling 2026-08-22. The daily fork demands an
excursion between anchors that a single session rarely meets, so gating on it
produces a permanent no-trade rather than a guardrail. Both frames are recorded
here regardless; the ruling decides what the CONDOR reads, not what we keep.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from derived.base import DerivedEngine

logger = logging.getLogger(__name__)

# Both anchor frames are recorded. Keeping the one the condor does not read
# costs almost nothing and means a later ruling change has history behind it.
FRAMES = ("1h", "1d")


def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def fork_identity(fork) -> Optional[tuple]:
    """THE ONE DEFINITION OF A FORK'S IDENTITY — its three anchor PRICES.
    Never the anchors' `idx`: that is a position in the rolling frame and shifts
    by one every bar (one fork, 09-09..09-14, wore 17 idx-keys). The level engine
    and derived/fork_projection call this; nobody keeps a private copy."""
    try:
        return tuple(round(float(getattr(fork, a).price), 4) for a in ("p0", "p1", "p2"))
    except Exception:                                           # noqa: BLE001
        return None


# minutes per frame bar — the rail's slope is per BAR, so a rail is walked back
# along it by (minutes / TF_MINUTES) of a bar to find where it stood at a minute
TF_MINUTES = {"15m": 15, "1h": 60, "1d": 390}
INVALIDATION_RESTORE_S = 7 * 86400     # how far back a restart reads its own invalidations


class ForkEngine(DerivedEngine):
    name = "forks"
    table = "fork_series"
    # The scan is the expensive part of this file; 60s is far finer than the
    # rate at which a 1h fork's geometry can meaningfully change.
    min_interval_s = 60.0

    def __init__(self, store=None, symbol: str = ""):
        super().__init__(store)
        self.symbol = symbol
        self.last_forks: dict = {}      # tf -> Pitchfork (v4.1)
        self.last_idx: dict = {}        # tf -> current bar index in that frame
        # v4.3 — THE BUILDER DECIDES A FORK'S DEATH (operator, 2026-09-23: "it's
        # gone when the engine says it's gone, not when a strategy says it's gone")
        self._dead: dict = {}           # tf -> {identity} a rail BREACH invalidated
        self._dead_loaded = False       # restored from this table's own INVALIDATED rows (§22)
        self._judged_to: dict = {}      # tf -> last 1m bar (epoch ms) judged against the rails
        self._eps: dict = {}            # (tf, identity, rail, role) -> level_rules.Episode

    def derive(self, ctx: dict) -> int:
        store = self._store
        if store is None:
            return 0
        sym = self.symbol or ctx.get("symbol") or ""
        data = ctx.get("data") or {}
        if not sym or not data:
            return 0

        from analysis import pitchfork as pf

        now = time.time()
        rows = []
        self._restore_dead(store, sym, now)
        for tf in FRAMES:
            df = data.get(tf)
            if df is None or getattr(df, "empty", True):
                # ⚠️ RECORDED, NOT SKIPPED. "the frame was not there" is a
                # DIFFERENT failure from "the geometry did not qualify", and
                # on 2026-08-21 the 1d frame was absent from the warehouse
                # entirely — a fact that took hours to establish because
                # nothing wrote it down.
                rows.append((sym, tf, now, 0, "NO_FRAME", 0, None,
                             None, None, None, None, None, None, None, None,
                             None, None, None, None, None, None))
                continue
            try:
                atr = float((df["high"] - df["low"]).tail(20).mean())
            except Exception:                                   # noqa: BLE001
                atr = 0.0
            fork = None
            try:
                fork = pf.build_fork_contained(sym, df, tf, atr)
            except Exception as exc:                            # noqa: BLE001
                logger.debug("fork build raised for %s %s: %s", sym, tf, exc)
            # r15 (mainline r364's rule): a failed build CLEARS the held fork, so a
            # dead structure cannot be served one tick later — "if the fork stops
            # emitting, then the map has to go with it… out of sight, out of mind."
            reason = None
            try:
                reason = pf.last_reject_reason()
                depth = pf.last_scan_depth()
            except Exception:                                   # noqa: BLE001
                depth = 0
            # 🔴 v4.3 — AN INVALIDATED IDENTITY IS NEVER SERVED AGAIN. The builder
            # rebuilds from the frame every run, so the fork a rail breach killed
            # comes straight back next minute unless the engine refuses it here.
            if fork is not None and fork_identity(fork) in self._dead.get(tf, set()):
                fork, reason = None, "INVALIDATED_IDENTITY"
            if fork is not None:
                self.last_forks[tf] = fork
                self.last_idx[tf] = len(df) - 1
                # judge the rails on every CLOSED 1m bar since the last run; a
                # BREACH kills the fork here, in its builder, and nowhere else
                killed = self._judge_rails(tf, fork, len(df) - 1, ctx.get("df_1m"), now, sym)
                if killed is not None:
                    rows.append(killed)
                    self.last_forks.pop(tf, None)
                    self.last_idx.pop(tf, None)
                    continue
            else:
                self.last_forks.pop(tf, None)
                self.last_idx.pop(tf, None)

            if fork is None:
                rows.append((sym, tf, now, 0, reason or "UNKNOWN", depth,
                             None, None, None, None, None, None, None,
                             None, None, None, None, None, None, None, None))
                continue

            # Built. Record the anchors so the fork can be REDRAWN later from
            # the row alone — a fork you cannot reconstruct is a number, not a
            # measurement.
            # ⚠️ FIELD NAMES READ FROM THE DATACLASS, NOT ASSUMED. Fork carries
            # p0/p1/p2 as named Pivots (idx, price, kind, k, timeframe) and has
            # NO containment/span/upper/median/lower attributes — the first
            # draft of this file invented all five. Containment and span live
            # inside `filters_passed` as tags like ("CONTAINMENT_0.96",
            # "SPAN_71"), so they are parsed out rather than read.
            def pv(pt, attr):
                try:
                    return _f(getattr(pt, attr))
                except Exception:                               # noqa: BLE001
                    return None
            contain, span = None, None
            for tag in (getattr(fork, "filters_passed", None) or ()):
                t = str(tag)
                if t.startswith("CONTAINMENT_"):
                    contain = _f(t.split("_", 1)[1])
                elif t.startswith("SPAN_"):
                    try:
                        span = int(t.split("_", 1)[1])
                    except (TypeError, ValueError):
                        span = None
            rows.append((
                sym, tf, now, 1, None, depth,
                getattr(fork, "direction", None),
                pv(getattr(fork, "p0", None), "idx"),
                pv(getattr(fork, "p0", None), "price"),
                pv(getattr(fork, "p1", None), "idx"),
                pv(getattr(fork, "p1", None), "price"),
                pv(getattr(fork, "p2", None), "idx"),
                pv(getattr(fork, "p2", None), "price"),
                _f(getattr(fork, "origin_idx", None)),
                _f(getattr(fork, "origin_price", None)),
                _f(getattr(fork, "slope", None)),
                contain, span,
                # The rails themselves are a projection at a given bar index,
                # not stored state — left NULL here and computed on read from
                # origin + slope, which the row fully determines.
                None, None, None,
            ))
        return store.append_forks(rows)

    # ══ v4.3 — THE FORK'S DEATH, DECIDED BY THE THING THAT BUILDS IT ══════
    def _restore_dead(self, store, sym: str, now: float) -> None:
        """§22 — in-memory state dies on every bake. The invalidations this
        engine wrote to its own table are read back once, so a restart can
        never resurrect a fork the market already broke."""
        if self._dead_loaded:
            return
        self._dead_loaded = True
        try:
            for tf, a, b, c in store.conn.execute(
                    "SELECT interval, p0_price, p1_price, p2_price FROM fork_series"
                    " WHERE symbol=? AND reject_reason LIKE 'INVALIDATED:%' AND ts_epoch >= ?",
                    (sym, now - INVALIDATION_RESTORE_S)):
                if None not in (a, b, c):
                    self._dead.setdefault(tf, set()).add(
                        (round(float(a), 4), round(float(b), 4), round(float(c), 4)))
        except Exception as exc:                                # noqa: BLE001
            logger.warning("[forks] could not restore invalidated forks: %s", exc)
        # 🔑 THE r114 -> r115 HANDOVER. r114 judged breaches in the LEVEL engine
        # and recorded them in level_event (event INVALIDATED, identity repr in
        # `depth` as ((price, kind), ...)). Without reading those once, the fork
        # r114 killed would be served again until this engine re-judged it.
        # r114's rows only ever named the 1h fork.
        try:
            import ast
            for (k,) in store.conn.execute(
                    "SELECT depth FROM level_event WHERE symbol=? AND event='INVALIDATED' AND ts_epoch >= ?",
                    (sym, now - INVALIDATION_RESTORE_S)):
                try:
                    key = ast.literal_eval(k)
                    self._dead.setdefault("1h", set()).add(
                        tuple(round(float(x[0] if isinstance(x, (tuple, list)) else x), 4) for x in key))
                except Exception:                               # noqa: BLE001
                    continue
        except Exception as exc:                                # noqa: BLE001
            logger.debug("[forks] no r114 invalidations to carry: %s", exc)

    def _judge_rails(self, tf: str, fork, idx_now: float, df_1m, now: float, sym: str):
        """Every closed 1m bar since the last judgement, against each rail at
        that minute, by derived/level_rules (the same BREACHED as a level: a
        1m close beyond, then the next 1m open beyond). Operator, 2026-09-23:
        "A breech is an event that invalidates the fork" — and "any
        interaction that doesn't cause the fork object to destruct is a touch",
        so a HELD changes nothing here. Returns the INVALIDATED row, or None."""
        from derived import level_rules as R
        from derived import fork_projection as FP
        ident = fork_identity(fork)
        if ident is None or df_1m is None or len(df_1m) < 2:
            return None
        try:
            closed = df_1m.iloc[:-1]                           # the last row is still forming
            stamps = [int(x.timestamp() * 1000) for x in closed.index]
        except Exception:                                       # noqa: BLE001
            return None
        last = self._judged_to.get(tf)
        todo = [i for i, t in enumerate(stamps) if last is None or t > last]
        if last is None:
            todo = todo[-1:]                                    # first sight: judge from now, not history
        self._eps = {k: v for k, v in self._eps.items() if not (k[0] == tf and k[1] != ident)}
        per = float(TF_MINUTES.get(tf, 60))
        for i in todo:
            ts = stamps[i]
            row = closed.iloc[i]
            bar = (ts, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))
            self._judged_to[tf] = ts
            mins_back = max(0.0, (now * 1000 - ts) / 60000.0 - 1.0)
            for rail in FP.RAILS:
                try:
                    px = float(FP.rail_at(fork, rail, idx_now - mins_back / per))
                except Exception:                               # noqa: BLE001
                    continue
                role = FP.role(rail, px, bar[4])
                key = (tf, ident, rail, role)
                ep = self._eps.get(key)
                if ep is None:
                    ep = self._eps[key] = R.Episode(role)
                if R.BREACHED in ep.step(bar, (px, px)):
                    self._dead.setdefault(tf, set()).add(ident)
                    self._eps = {k: v for k, v in self._eps.items() if k[1] != ident}
                    logger.warning("[forks] %s %s fork %s: the %s rail (%.2f) was BREACHED on the "
                                   "%s bar — the fork is INVALIDATED by its builder (operator "
                                   "2026-09-23); it is not served again", sym, tf, ident, rail, px,
                                   time.strftime("%H:%M", time.localtime(ts / 1000)))
                    return (sym, tf, now + 0.001, 0, f"INVALIDATED: {rail} rail breached at {ts}", 0,
                            getattr(fork, "direction", None),
                            None, ident[0], None, ident[1], None, ident[2],
                            None, None, _f(getattr(fork, "slope", None)), None, None,
                            None, None, None)
        return None
