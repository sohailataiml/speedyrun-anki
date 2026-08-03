"""Builds a SYNTHETIC collection that exhibits the spacebar reflex, so the
v3 give-up rule's rote-pattern detection can be demonstrated firing.

Why this exists, and what it is *not*
-------------------------------------
The rote-pattern rule cannot be demonstrated on the real dev collection,
because the real collection contains genuine study: volatility there runs
0.60-1.06, three to five times the 0.2 threshold (see
speedrun/docs/latency-volatility.md). That is the correct null result, but
it means the positive case was only covered by unit tests.

This script writes a **throwaway collection in a temp path**. It does not
touch the user's collection, and the review history it writes is openly
fabricated — its whole purpose is to fabricate the *bad* behaviour so the
detector can be seen catching it.

That is a different act from the review-simulation that was cut from the
coverage-map importer. There, fabricated reviews would have inflated a
readiness number the student had not earned. Here, fabricated reviews make
the app refuse to score. A fixture that can only ever make the product
look worse is not a way of cheating the product's own honesty rule.

Usage:
    python make_rote_collection.py <output.anki2>
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "out" / "pylib"))

from anki.collection import Collection  # noqa: E402

# Uniform to within a few ms: what pressing space without reading looks
# like. CV lands far below the 0.2 rote threshold.
ROTE_LATENCIES_MS = [1000, 1005, 995, 1010, 1000, 1002, 998, 1006]
# Real study: some cards instant, some genuinely considered.
REAL_LATENCIES_MS = [800, 4500, 1500, 11000, 2200, 7000, 1100, 9500]

ROTE_TOPICS = ["krebs_cycle", "glycolysis", "central_dogma", "amino_acids"]
REAL_TOPICS = ["gas_laws", "water_solutions"]

REVIEWS_PER_CARD = 40


def build(path: Path) -> None:
    if path.exists():
        path.unlink()
    col = Collection(str(path))
    deck_id = col.decks.id("Rote Demo")
    basic = col.models.by_name("Basic")

    def add_topic(topic: str, latencies: list[int]) -> None:
        note = col.new_note(basic)
        note["Front"] = f"{topic} demo card"
        note["Back"] = f"{topic} demo answer"
        note.tags = [f"topic::{topic}"]
        col.add_note(note, deck_id)
        cid = col.card_ids_of_note(note.id)[0]

        now_ms = int(time.time() * 1000)
        for i in range(REVIEWS_PER_CARD):
            taken = latencies[i % len(latencies)]
            col.db.execute(
                "insert into revlog (id, cid, usn, ease, ivl, lastIvl, factor, time, type)"
                " values (?, ?, -1, 3, 1, 1, 2500, ?, 1)",
                now_ms + i * 1000,
                cid,
                taken,
            )

    for t in ROTE_TOPICS:
        add_topic(t, ROTE_LATENCIES_MS)
    for t in REAL_TOPICS:
        add_topic(t, REAL_LATENCIES_MS)

    col.save()
    col.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    out = Path(sys.argv[1])
    build(out)
    print(f"wrote synthetic rote collection: {out}")
    print(f"  {len(ROTE_TOPICS)} rote topics, {len(REAL_TOPICS)} genuinely-studied topics")
    print(f"  {REVIEWS_PER_CARD} reviews each")
