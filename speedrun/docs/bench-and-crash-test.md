# Bench and crash-test (PRD §10)

Results and methodology for the two remaining PRD §10 requirements:
performance targets against a shared 50k-card deck, and a 20x
kill-mid-review crash test. Both tools live in `speedrun/tools/` and are
independently rerunnable.

## crash-test — PASS, 20/20

`speedrun/tools/crash-test/`: hard-kills (`psutil` `.kill()`, Windows
`TerminateProcess` — no cleanup, no flush) a worker process actively
answering cards against a real collection, at a random point (0.05–0.6s
into its run, so kills land unpredictably relative to its write
operations rather than at a fixed, potentially-lucky timing), then
reopens the collection and runs `fix_integrity()` — Anki's own database
consistency checker.

```
20/20 passed integrity check after a hard kill mid-review.
PASS: zero corrupted collections.
```

All 20 kills landed on a still-running worker (`worker_already_exited:
false` in every result), confirming they genuinely interrupted live
write activity rather than racing an already-finished process. Full
per-iteration results: `speedrun/tools/crash-test/output/crash_test_results.json`.

**What this validates:** SQLite/rslib's write durability under this
fork's usage pattern — a legitimate thing to verify even though the
storage layer itself is inherited from upstream Anki, since the PRD's
bar is "zero corrupted collections," not "zero corrupted collections in
code we personally wrote." **What "pass" means here:** the sqlite file
itself never became unopenable or inconsistent. It does *not* mean zero
data loss — the one review in flight at kill time not being recorded is
expected and correct, not a failure.

**Scope:** desktop only. Android crash-testing would need the same
kill-mid-write idea driven against a live `adb`-controlled app process,
but this session's emulator was too resource-constrained to run 20
reliable iterations (see the emulator stability notes in
[rust-change-note.md](rust-change-note.md) and [demo.md](demo.md)) —
stated as a gap, not silently skipped.

Rerun: `python speedrun/tools/crash-test/make_fixture.py && python speedrun/tools/crash-test/crash_test.py`
(needs `out/pylib` built — see below).

## bench — partial pass, with a real bug found and fixed along the way

`speedrun/tools/bench/`: builds a 50k-card fixture (50 topics × 1000
cards, 60% with realistic review history) and times every PRD §10 row
against it, p50/p95/worst-case over real repeated measurements — never
a single cherry-picked number.

### A real scaling bug, found by this benchmark and fixed

The first run: `dashboard_first_load`/`dashboard_refresh` took
**13–28 seconds**. Root cause: `mastery_query` searched `"tag:topic::x"`
once per requested topic. `notes.tags` has no index, so every tag search
is a full notes-table scan — with 50 topics, that's 50 full scans of the
whole collection instead of one, i.e. O(topics × collection_size) rather
than O(collection_size). This scaled invisibly at the small (1-30 card)
collections used everywhere else this project, and only showed up once a
benchmark actually ran at the PRD's required 50k-card scale — exactly
what "you must benchmark on the shared 50k-card deck, not a number you
picked yourself" is supposed to catch.

**Fix:** `rslib/src/stats/mastery.rs` now does one combined
`tag:topic::*` search across all topic-tagged cards, then groups by each
note's topic tag in memory, instead of one search per topic. Full
before/after and the Rust-level detail are in
[rust-change-note.md](rust-change-note.md). All existing
`mastery_query`/`give_up_gate`/`readiness_query` tests pass unchanged
(555 total, plus this file's own 4 — see rust-change-note.md) — this was
a performance fix, not a behavior change.

**Result of the fix:** dashboard load time dropped from 13–28s to
**1.7–2.6s — roughly a 10x improvement.**

### Full results (after the fix)

| Metric | Target (p95) | p50 | p95 | worst | Result |
|---|---|---|---|---|---|
| `cold_start_backend` (lower bound) | < 5000ms | 8ms | 9ms | 9ms | PASS |
| `next_card_after_grading` | < 100ms | 4ms | 6ms | 33ms | PASS |
| `dashboard_first_load` | < 1000ms | 1759ms | 2147ms | 2990ms | **FAIL** |
| `dashboard_refresh` | < 500ms | 1885ms | 2583ms | 5913ms | **FAIL** |
| `memory_at_50k_cards` | (limit not stated in PRD) | — | — | — | 6.5MB RSS delta (this harness process, not Qt/Android) |

Full JSON: `speedrun/tools/bench/output/bench_results.json`.

**Why the two dashboard metrics still fail, honestly:** the remaining
~1-2s is dominated by fetching real review-log rows for every
topic-tagged card (up to ~600k revlog rows across 30k reviewed cards at
this fixture's scale) across the Rust/Python FFI boundary, not by the
tag-search bug the fix already closed — isolated timing showed the
single combined search itself is fast; the cost is in the volume of
revlog data pulled and serialized per call. Closing the remaining gap
would need the scores to be computed from incrementally-maintained
per-topic aggregates instead of a full revlog scan on every dashboard
load — a real architectural change, out of scope for the time available
this session. Stated as a known limitation, not hidden behind a
narrower benchmark that would have passed.

### What's measured directly vs. by proxy

- `next_card_after_grading`, `dashboard_first_load`, `dashboard_refresh`,
  `cold_start_backend`: real timings against the actual `Collection`/RPC
  surface (`col.sched.answerCard`, `col.mastery_query`,
  `col.readiness_query`) — the same backend calls the desktop and
  Android UIs make.
- `button_press_acknowledged`: **not measured.** This is UI input-to-paint
  latency (Qt/AnkiDroid event loop), which a headless script can't
  observe without driving the real GUI.
- `cold_start` (full app): `cold_start_backend` is a lower bound
  (collection-open time only) — real desktop/Android cold start adds Qt
  init, window paint, JVM startup, etc. on top of this.
- `sync`: not run here — `speedrun/tools/sync-test/` already exercises
  real sync against a live server; see that tool's own output rather
  than duplicating server setup in bench.py.
- `crash test`: its own tool, see above — the row appears in both the
  PRD's bench table and as a dedicated `speedrun/tools/crash-test/`.

### A second real bug found while building this: the legacy deck-config write API silently no-ops

`col.decks.config_dict_for_deck_id()` / `col.decks.save(conf)` — the
dict-based legacy config read/write pair — reads fine but **writes
silently do nothing** in this Anki version. Found by `bench.py`'s
`next_card_after_grading` mysteriously returning 0 samples on a second
run: the fixture's daily review-limit (default 200/day) was never
actually being raised as the fixture-build script intended, so a few
runs against the same collection exhausted the day's quota. Fixed two
ways: `make_fixture.py` now uses the real write path
(`get_deck_configs_for_update` / `update_deck_configs`, the proto-based
API), and `bench.py`'s `next_card_after_grading` drives `answerCard()`
directly from a raw `is:due` search rather than through the
scheduler's daily-limited queue — `answerCard()` itself doesn't check
queue membership or limits (confirmed by reading `scheduler/v3.py`), so
this measures the same real write cost without inheriting unrelated
queue bookkeeping. Neither fix changes anything about the real app's
behavior; both are fixes to this benchmark's own harness code.

## Reproducing this

```bash
# Requires this fork's built Python backend - from core/:
tools\ninja.bat pylib

cd speedrun/tools/bench
python make_fixture.py   # ~10 min, builds the 50k-card fixture
python bench.py          # ~1 min

cd ../crash-test
python make_fixture.py   # seconds, builds the 1000-card template
python crash_test.py     # ~15s (20 iterations)
```
