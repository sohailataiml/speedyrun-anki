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
# All comfortably above a ~2.9s minimum reading time: this is what
# studying looks like when every prompt was actually read.
REAL_LATENCIES_MS = [4200, 4500, 6000, 11000, 5500, 7000, 4300, 9500]

ROTE_TOPICS = ["krebs_cycle", "glycolysis", "central_dogma", "amino_acids"]
REAL_TOPICS = ["gas_laws", "water_solutions"]

# A third pattern, for demonstrating the Readiness spacebar-reflex
# discount rather than the give-up refusal. Latencies vary enough that
# volatility stays healthy (so the rote rule does NOT fire and the app
# still scores), but a third of them are far too fast for a long card to
# have been read. That is the case the discount exists for: a student who
# mostly thinks, and sometimes taps through.
#
# Needed because on the fully-rote deck the give-up rule fires first and
# the discount never gets a chance - a refusal is strictly stronger than
# a markdown, so the two can never both be visible on one deck.
# Half below the minimum reading time, half genuinely considered.
MIXED_LATENCIES_MS = [400, 5200, 600, 12000, 500, 8000, 450, 9500]
MIXED_TOPICS = ["neuromuscular", "cell_division"]

REVIEWS_PER_CARD = 60


def build(path: Path, mixed: bool = False) -> None:
    if path.exists():
        path.unlink()
    col = Collection(str(path))
    deck_id = col.decks.id("Rote Demo")
    basic = col.models.by_name("Basic")

    def add_topic(topic: str, latencies: list[int]) -> None:
        note = col.new_note(basic)
        # Deliberately wordy: minimum reading time is derived from card
        # length, so a two-word card could never register a spacebar
        # reflex no matter how fast it was answered.
        # ~12 words total -> a minimum reading time near 2.9s. Long
        # enough that a 500ms answer is provably too fast to have read
        # the card, short enough that ordinary considered answers clear
        # it comfortably. A two-word card could never register a reflex
        # at all, and an essay-length one would flag every review.
        note["Front"] = f"{topic}: which mechanism explains the observed result here"
        note["Back"] = f"{topic} answer with brief supporting explanation"
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

    # --mixed deliberately omits the rote topics. With them present the
    # give-up rule refuses outright and the Readiness discount never runs,
    # so a deck cannot demonstrate both at once.
    if mixed:
        for t in MIXED_TOPICS:
            add_topic(t, MIXED_LATENCIES_MS)
        for t in REAL_TOPICS:
            add_topic(t, REAL_LATENCIES_MS)
    else:
        for t in ROTE_TOPICS:
            add_topic(t, ROTE_LATENCIES_MS)
        for t in REAL_TOPICS:
            add_topic(t, REAL_LATENCIES_MS)

    col.save()
    col.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    out = Path(sys.argv[1])
    mixed = "--mixed" in sys.argv
    build(out, mixed=mixed)
    print(f"wrote synthetic rote collection: {out}")
    if mixed:
        print(f"  {len(MIXED_TOPICS)} mixed topics (healthy volatility, some reviews "
              f"too fast to be read), {len(REAL_TOPICS)} genuinely-studied topics")
    else:
        print(f"  {len(ROTE_TOPICS)} rote topics, {len(REAL_TOPICS)} genuinely-studied topics")
    print(f"  {REVIEWS_PER_CARD} reviews each")
