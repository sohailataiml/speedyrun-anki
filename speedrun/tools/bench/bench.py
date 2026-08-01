#!/usr/bin/env python3
"""PRD §10 benchmark: reports p50/p95/worst-case for every row in
ARCHITECTURE.md §10's performance table, against the shared 50k-card
fixture deck (make_fixture.py). "One number you picked yourself does not
count" - every metric below is N repeated real measurements, not a
single cherry-picked run.

What's measured directly vs. by proxy, stated plainly:
  - next_card_after_grading, dashboard_first_load, dashboard_refresh,
    cold_start_backend: measured directly against the real Collection/
    RPC surface (col.sched.*, col.mastery_query, col.readiness_query) -
    the same backend calls the desktop and Android UIs make.
  - button_press_acknowledged: NOT measured here. This is a UI input-to-
    render latency (Qt/AnkiDroid event loop + paint), which a headless
    script can't observe without driving the actual GUI - see the
    "Not measured" note in the results instead of a fabricated number.
  - cold_start (full app): backend collection-open time is measured and
    reported as a floor/lower-bound, not the full desktop/Android
    process-launch-to-interactive time (Qt init, window paint, etc. add
    to this and aren't measured here).
  - sync: NOT run in this script - speedrun/tools/sync-test/ already
    exercises real sync against a live server; see that tool's own
    output for sync timing rather than duplicating server setup here.
  - memory_at_50k: process RSS after loading the full fixture, via
    psutil. A real number, though it reflects this Python harness's
    process, not the Qt or Android app's own memory footprint - the
    dominant cost (the same rslib Collection object) is shared, but Qt/
    JVM overhead on top of it isn't included.
"""

from __future__ import annotations

import json
import shutil
import statistics
import sys
import time
from pathlib import Path

import psutil

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "out" / "pylib"))

from anki.collection import Collection  # noqa: E402

SOURCE_FIXTURE_PATH = Path(__file__).parent / "output" / "fixture_50k.anki2"
# next_card_after_grading permanently advances review state (grading
# consumes due cards), so bench runs against a disposable copy rather
# than mutating the shared fixture - otherwise a second run silently
# exhausts the due queue and next_card_after_grading has nothing to time.
FIXTURE_PATH = Path(__file__).parent / "output" / "fixture_50k_working.anki2"
RESULTS_PATH = Path(__file__).parent / "output" / "bench_results.json"

TARGETS_MS = {
    "next_card_after_grading": 100,
    "dashboard_first_load": 1000,
    "dashboard_refresh": 500,
}
COLD_START_TARGET_MS = 5000


def percentile(values: list[float], p: float) -> float:
    values = sorted(values)
    if not values:
        return 0.0
    k = (len(values) - 1) * p
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


def summarize(name: str, samples_ms: list[float], target_ms: float | None) -> dict:
    p50, p95, worst = (
        percentile(samples_ms, 0.50),
        percentile(samples_ms, 0.95),
        max(samples_ms),
    )
    result = {
        "n": len(samples_ms),
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "worst_ms": round(worst, 2),
        "target_ms": target_ms,
        "meets_p95_target": (p95 <= target_ms) if target_ms is not None else None,
    }
    status = "" if target_ms is None else (
        "PASS" if result["meets_p95_target"] else "FAIL"
    )
    print(
        f"{name}: p50={p50:.1f}ms p95={p95:.1f}ms worst={worst:.1f}ms "
        f"n={len(samples_ms)}"
        + (f"  target(p95)<{target_ms}ms {status}" if target_ms is not None else "")
    )
    return result


def bench_cold_start_backend() -> dict:
    """Time to open the Collection from the 50k-card fixture file - a
    lower bound on real cold start, not the full desktop/Android app
    launch time. Repeated 5x (open/close cycles) rather than once."""
    samples = []
    for _ in range(5):
        start = time.perf_counter()
        col = Collection(str(FIXTURE_PATH))
        col.close()
        samples.append((time.perf_counter() - start) * 1000)
    return summarize("cold_start_backend (lower bound)", samples, COLD_START_TARGET_MS)


def bench_next_card_after_grading(col: Collection, n: int = 300) -> dict:
    """Times col.sched.answerCard() - the real write cost the app pays
    when a grade button is pressed. Cards are pulled from a raw is:due
    search rather than the scheduler's own getCard()/queue mechanism:
    getCard() is gated by the deck's reviews-per-day limit (default 200),
    and this fixture's daily quota gets consumed by repeated bench runs
    against the same collection; answerCard() itself doesn't check queue
    membership or daily limits (see v3.py - it operates directly on the
    given Card and its id), so driving it from a plain search measures
    the same write cost without inheriting that unrelated bookkeeping."""
    card_ids = col.find_cards("is:due")[:n]
    samples = []
    for cid in card_ids:
        card = col.get_card(cid)
        card.start_timer()  # normally set by getCard() when it "presents" the card
        start = time.perf_counter()
        col.sched.answerCard(card, 3)  # Good
        samples.append((time.perf_counter() - start) * 1000)
    return summarize("next_card_after_grading", samples, TARGETS_MS["next_card_after_grading"])


def bench_dashboard_first_load(n: int = 30) -> dict:
    """A fresh Collection handle each iteration - the honest analogue of
    "first load" (no warmed caches from a prior call). Self-contained:
    opens and closes its own handle each time, so it must not run while
    any other handle to the same file is open (sqlite allows only one
    writer/backend handle per collection file at a time)."""
    samples = []
    for _ in range(n):
        fresh = Collection(str(FIXTURE_PATH))
        topics = sorted(
            {t[len("topic::") :] for t in fresh.tags.all() if t.startswith("topic::")}
        )
        start = time.perf_counter()
        list(fresh.mastery_query(topics))
        fresh.readiness_query(topics, average_difficulty=0.5, average_timing_seconds=70.0)
        samples.append((time.perf_counter() - start) * 1000)
        fresh.close()
    return summarize("dashboard_first_load", samples, TARGETS_MS["dashboard_first_load"])


def bench_dashboard_refresh(col: Collection, n: int = 30) -> dict:
    """Repeated queries against one already-open handle - the "user is
    already in the app, hits refresh" case, as opposed to first_load's
    cold-open case."""
    topics = sorted(
        {t[len("topic::") :] for t in col.tags.all() if t.startswith("topic::")}
    )
    samples = []
    for _ in range(n):
        start = time.perf_counter()
        list(col.mastery_query(topics))
        col.readiness_query(topics, average_difficulty=0.5, average_timing_seconds=70.0)
        samples.append((time.perf_counter() - start) * 1000)
    return summarize("dashboard_refresh", samples, TARGETS_MS["dashboard_refresh"])


def bench_memory() -> dict:
    process = psutil.Process()
    rss_before = process.memory_info().rss
    col = Collection(str(FIXTURE_PATH))
    # Touch the review queue so the memory cost of building it (not just
    # opening the sqlite file) is included.
    col.sched.getCard()
    rss_after = process.memory_info().rss
    col.close()
    delta_mb = (rss_after - rss_before) / (1024 * 1024)
    print(f"memory_at_50k_cards: {delta_mb:.1f} MB RSS delta (this process, not Qt/Android)")
    return {"rss_delta_mb": round(delta_mb, 1), "note": "Python harness process RSS, not Qt/Android app RSS"}


def main() -> None:
    if not SOURCE_FIXTURE_PATH.exists():
        raise SystemExit(f"Fixture not found at {SOURCE_FIXTURE_PATH} - run make_fixture.py first.")
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(FIXTURE_PATH) + suffix)
        if p.exists():
            p.unlink()
    shutil.copy(SOURCE_FIXTURE_PATH, FIXTURE_PATH)

    results = {"button_press_acknowledged": "NOT MEASURED - requires driving the real GUI, see module docstring"}
    results["cold_start_backend"] = bench_cold_start_backend()

    # Each of these opens/closes its own handle(s) - never overlapping,
    # since sqlite/rslib allow only one open handle per collection file.
    col = Collection(str(FIXTURE_PATH))
    print(f"\nFixture loaded: {col.card_count()} cards")
    results["next_card_after_grading"] = bench_next_card_after_grading(col)
    results["dashboard_refresh"] = bench_dashboard_refresh(col)
    col.close()

    results["dashboard_first_load"] = bench_dashboard_first_load()
    results["memory_at_50k_cards"] = bench_memory()
    results["sync"] = "NOT RUN HERE - see speedrun/tools/sync-test/ for real sync timing"

    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n-> {RESULTS_PATH}")


if __name__ == "__main__":
    main()
