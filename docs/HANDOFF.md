Lone retail algo options trader "Vertigo Capital" attempting to build an institutional grade day trading modular suite current iteration (otv4) with high fidelity customization and expansive reporting and control functions to serve a functioning semi-autonomous day trading platform that recognizes price action signals and patterns on the near, medium and higher timeframe reference points to identify opportune trade setups with some degree of certainty and scales entries appropriately based on the quality of the setup conditions. We are using some derived artifacts calculated from the feed (information layer) to co-inform our trading "plans" (decision layer) that feed the strategies (execution layer). You exist on QQQ-TEST, a fork of the predecessor (OTV4). The goal is to have this fork supersede OTV4 in-place on the fleet and become vOTV5.

You should be familiar with public repo- https://github.com/TX-9AI/options_trader_v4 (primary) and https://github.com/TX-9AI/day_trader_pro (control). Those are the predecessors. We are not working there or changing anything there unless you discover a significant flaw it's carrying identified by your work here.

You have direct ownership of https://github.com/TX-9AI/OTV4TEST

## SATURDAY EARLY WAKE — THE RESEARCH RUN (do this BEFORE the catch-up below)

If you were raised on a SATURDAY between 02:00 and 06:00 ET, you were woken for this. Do it first; the catch-up below waits until the operator arrives (~08:00). The operator, 2026-09-27: *"I don't wanna come up with the ideas myself ... I want you to look at the data critically and try different variables and if you find one that presents an interesting sample that's when you would expand it to try it on other symbols ... creatively approach it because my creativity has limits."*

ASSIGNED ITEMS FIRST. Before your own ideas, do every row in docs/BACKLOG.md tagged **SAT-RUN** whose state is still OPEN (`grep -n "SAT-RUN" docs/BACKLOG.md`). They are the operator's (2026-09-28: *"Make sure this is part of the SATURDAY TIMER's work, so it's ready in time for the Saturday Brief"*). Each goes at the top of the study file with its result; the rules below govern them too. Report each row's result so the next delivery can mark it. Then spend the time left on your own hypotheses. No SAT-RUN row open means the whole run is yours.

YOUR JOB: find better exits, stops and dials than the ones we run. Nobody hands you the ideas. Read the week critically - this box's trades.db (QQQ), the bucket's SOFI/AAL trades, the losers, the giveback - form your OWN hypotheses and test them on history. When one looks interesting, EXPAND it: the other symbols, the newest week.

THE RULES THAT KEEP IT HONEST:
- Discovery first (QQQ + the older weeks). Before expanding an idea to other symbols or the newest week, WRITE ITS TERMS DOWN (what counts as a pass), then test. Two sessions agreeing is not evidence; unseen data is.
- Keep a lab notebook: every idea tried, including the dead ones, with numbers.
- Score the operator's way: losing days first, trend days kept, against today's settings AND hold-to-close; dollars and percent.
- The harness: /var/tmp/breakout_exit_wargame (simulate, candidates, hist, fetch_stream, run_history2.sh, the cache of 266+ symbol-days; PREREG_EXIT_COMPROMISE.md for what was already tried and failed). Add the new week to the cache first.
- BIG JOBS STREAM. The warehouse is large (QQQ quote_series ~1.3 GB a day in 12 MB objects). Never load a whole object: stream it in chunks, match rows on the raw bytes, decode only the rows you keep (fetch_stream.py is the pattern, proven identical to a full load). Cache what you keep to disk under /var/tmp and simulate from the cache. Measure a job's memory on one day before a big run.
- Every process under guarded.sh (memory cap, and it volunteers as the first OOM victim - the bot's oom_score was once HIGHER than a study's). One heavy job at a time; the 03:00 boot also runs the full checker sweep (~9 min) - wait for it.
- READ AND STUDY ONLY: no code/config/service changes, no commits, no pushes, no warehouse writes, no deletes outside your own scratch.
- Stop by 07:30 ET. Write /var/tmp/saturday_study_<date>.md, every line 76 characters or fewer: the 3-5 findings worth his time, how many ideas were tried per finding kept, and whether each held on symbols it was not found on. Then do the catch-up below.

FIRST, CATCH UP ON WHERE WE LEFT OFF — run `python3 tools/last_session.py`. It prints my messages from the previous conversation in order, with the revisions that landed in that window and how the thread ended. That is 2-7k tokens, not the transcript; the transcripts are 50MB and live in ~/.claude/projects/-home-ubuntu-options-trader/ if you ever need to search them for something specific (`--list` shows every session, `--session <id>` reads a particular one). READ IT BEFORE YOU START THE WORK BELOW — a ruling I already gave you is not a question to ask me again.

THEN READ THE OVERNIGHT SWEEP — `python3 tools/boot_sweep.py --show`. The FULL checker set runs once at the 08:00 boot, ordered after the bot and the feed, so a delivery never has to pay for it. It reports NEW and FIXED against the previous run, not a bare count — this tree carried 11 standing reds once; since r128 (2026-09-24) it carries NONE outside a worktree, so ANY red is the signal. If it reports a NEW failure, BRIEF IT TO ME with the proposed fix and why the fix works before you start the work below; if it reports SKIPPED or CRASHED, say so rather than treating silence as green. The sweep DETECTS and RECORDS; you DIAGNOSE — it cannot produce a rationale and is not trying to.


THEN START THE ALERT WATCH (r171, AGT.1/AGT.2) — arm a Monitor on `python3 tools/agent_watch.py --follow` (timeout at the 30-minute maximum; RE-ARM it every time it expires, for as long as the session runs — its state resumes exactly where it stopped). The first pass also prints what fired while no session was watching; read those first. My ruling, 2026-09-29: *"start building and deploy the ALERT Notification to have you intervene when you get alerted"*, with NO routine alerts (fills, exits, summaries, started/stopped are recorded, never printed). What wakes you:
- **URGENT** (every page that is not routine — blind, dispatch failed, disk, cap hit, hard close failed, broker mismatches, the watchdog): diagnose it at once and FIX WHAT IS ALREADY YOURS TO FIX under WA 38.2 (e.g. restarting a stalled candle-feed, as on 09-29), then tell me what happened and what you did. Anything that closes a position, changes a gate or touches trading stays MINE: bring it to me.
- **UNUSUAL** (an entry during or just after a blind episode, a loss beyond 1.25x its planned risk, a same-direction loss cluster, a strategy with no exit route): tell me, with what the tape shows.
- **LOSS**: read the tape (the 1m/5m bars around the loss, the levels, the trade), then within a couple of minutes record ONE verdict — `python3 tools/agent_verdict.py --trade <id> --event <id> --forbid long|short|both|none --until "<what resolves it>" --note "<your read>"`. My words: *"wire it as observe and comment only ... just put down whether you would forbid long entries, short entries, or both. That way we can timestamp your decision with whatever followed on the tape to see if it would've helped."* The bot never reads it. Record a verdict even when the answer is `none` — the misses count as much as the hits.
- **WATCH-ERROR**: the watcher itself is failing — say so; silence from it is not green.

🔴 **THE PROBE BELOW RUNS ONLY ON A TRADING DAY, BETWEEN 15:30 AND 16:00 ET, WITH NO OPEN
POSITIONS** (the operator's ruling, 2026-09-25: *"Don't run it unless we have no open positions
on a Trading day between 1530 and 1600."* — it opens its own streamer, and on 2026-09-22 he ruled
*"I don't want that probe interfering with trading behavior."*). ⚠️ OTV4TEST r100 already answered
most of it from the server's own FEED_CONFIG replies (BACKLOG FEED.3): the probe CONFIRMS, it is
not the first measurement. Inside that window: RUN `venv/bin/python tools/probe_aux_streams.py`
AND TELL ME THE ANSWER.
I need to know whether the dxFeed `Underlying` event is CARRIED ON OUR PLAN for QQQ.
`underlying_series` has **0 rows** and it is the one stream that publishes
`front_volatility`, `back_volatility` and `put_call_ratio` — term structure and flow
skew straight from the vendor, which is what an expected-move model for strike
selection should be built on. r113 already narrowed it to two candidates and the probe
decides between them: **(a)** wrong symbol space — the aux events subscribe to the
plain ticker while Greeks/Quote subscribe to the CHAIN's streamer symbols, and a
subscription to a symbol with no publisher is accepted and then silent forever; **(b)**
not carried — Trade/TimeAndSale/Summary are exchange prints and populate, while
Underlying/TheoPrice are dxFeed-COMPUTED analytics a plan may not include. ⚠️ **THEY
MAY HAVE DIFFERENT ANSWERS AND r113 LUMPED THEM:** (a) is a strong explanation for
TheoPrice, which is a PER-CONTRACT analytic pointed at a ticker — but it cannot explain
`Underlying`, whose correct symbol space IS the plain ticker. Report them separately.
⚠️ The probe writes no tables, touches no service and holds no locks — but r118 reverted
a subscription change that cost SPX its per-contract feed, so **PROBE ONLY; change no
subscription without telling me first.** This is blocking STRK.1 and the late-day work.

Then start with the WORKING AGREEMENT, then review the past week's changes to GENESIS, then VERIFY if the WRITE MAP is current/accurate. Next VERIFY if the FILE MAP is current/accurate. Our task is to make radical changes to the OTV4 that are not possible to do on an active fleet of 15 trading servers to optimize our strategies and P&L by identifying and employing edge, and using data analysis to propose novel predictive adaptations to capture market moves.

Remember, the working agreement is mandatory—but if it contains obsolete references or requirements, we should correct it. But that is not the purpose of THIS thread. Although we may discuss your findings afterwards, I want you to shelve those for a minute to discuss the task at hand. Conclude by telling me specifically what you understand you are supposed to do and what you are ALLOWED to do without asking me — name the permissions, don't just say you read them. Then let me know when you're caught up!
