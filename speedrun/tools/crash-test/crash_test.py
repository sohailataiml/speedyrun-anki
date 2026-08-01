#!/usr/bin/env python3
"""PRD §10 crash test: kill the app mid-review 20x, assert zero
corrupted collections.

Each iteration: fresh copy of a 1000-card all-due template -> launch
worker.py against it -> sleep a short RANDOM duration (so kills land at
unpredictable points relative to the worker's write operations, not a
fixed timing that could accidentally always land between transactions)
-> hard-kill the process (Windows TerminateProcess via psutil, the
closest equivalent to SIGKILL - no cleanup, no chance for the process to
flush/close gracefully) -> reopen the collection and run fix_integrity(),
Anki's own database consistency checker.

"Zero corrupted collections" is the pass bar - not zero data loss. A
kill mid-write can legitimately lose the one in-flight review (that
review not being recorded is expected and fine); what must never happen
is the sqlite file itself becoming unopenable or inconsistent.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

import psutil

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "out" / "pylib"))

from anki.collection import Collection  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"
TEMPLATE_PATH = OUTPUT_DIR / "template.anki2"
TEST_COL_PATH = OUTPUT_DIR / "test_collection.anki2"
RESULTS_PATH = OUTPUT_DIR / "crash_test_results.json"
WORKER_PATH = Path(__file__).parent / "worker.py"
PYTHON_EXE = REPO_ROOT / "out" / "pyenv" / "Scripts" / "python.exe"

ITERATIONS = 20
MIN_SLEEP_S = 0.05
MAX_SLEEP_S = 0.6


def cleanup_col_files(base: Path) -> None:
    for suffix in ("", "-wal", "-shm", ".media"):
        p = Path(str(base) + suffix)
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p, ignore_errors=True)


def run_one_iteration(i: int, rng: random.Random) -> dict:
    cleanup_col_files(TEST_COL_PATH)
    shutil.copy(TEMPLATE_PATH, TEST_COL_PATH)

    proc = subprocess.Popen(
        [str(PYTHON_EXE), str(WORKER_PATH), str(TEST_COL_PATH)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    sleep_s = rng.uniform(MIN_SLEEP_S, MAX_SLEEP_S)
    time.sleep(sleep_s)

    killed_cleanly = True
    try:
        p = psutil.Process(proc.pid)
        p.kill()  # Windows: TerminateProcess. No cleanup, no flush.
        p.wait(timeout=5)
    except psutil.NoSuchProcess:
        # Worker had already exited (ran through all 1000 cards and
        # returned) before the kill landed - not a failure, just means
        # this iteration's sleep window was longer than the work took.
        killed_cleanly = False
    proc.wait(timeout=5)

    # Give the OS a moment to release file handles before reopening.
    time.sleep(0.2)

    error = ""
    ok = False
    try:
        col = Collection(str(TEST_COL_PATH))
        error, ok = col.fix_integrity()
        card_count = col.card_count()
        col.close()
    except Exception as e:  # noqa: BLE001 - crash-test must capture ANY failure mode
        error = f"exception opening/checking collection: {e!r}"
        card_count = None

    result = {
        "iteration": i,
        "sleep_s": round(sleep_s, 3),
        "worker_already_exited": not killed_cleanly,
        "integrity_ok": ok,
        "integrity_error": error,
        "card_count_after": card_count,
    }
    status = "OK" if ok else "CORRUPTED"
    print(f"[{i + 1}/{ITERATIONS}] slept {sleep_s:.3f}s, killed, integrity={status}")
    if not ok:
        print(f"    error: {error}")
    return result


def main() -> None:
    if not TEMPLATE_PATH.exists():
        raise SystemExit(f"Template not found at {TEMPLATE_PATH} - run make_fixture.py first.")

    rng = random.Random(1234)
    results = [run_one_iteration(i, rng) for i in range(ITERATIONS)]

    corrupted = [r for r in results if not r["integrity_ok"]]
    print(
        f"\n{ITERATIONS - len(corrupted)}/{ITERATIONS} passed integrity check "
        f"after a hard kill mid-review."
    )
    if corrupted:
        print(f"FAILURES: {len(corrupted)} corrupted collection(s) - see {RESULTS_PATH}")
    else:
        print("PASS: zero corrupted collections.")

    OUTPUT_DIR.mkdir(exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "iterations": ITERATIONS,
                "corrupted_count": len(corrupted),
                "pass": len(corrupted) == 0,
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"-> {RESULTS_PATH}")


if __name__ == "__main__":
    main()
