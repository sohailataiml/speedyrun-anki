"""Imports accepted jitter variants into a collection.

Deliberately a separate step from generation. `run_jitter.py` only writes
JSONL, so every variant is reviewable before anything lands in a deck a
student will actually study.

Each variant becomes an ordinary card in a `Speedrun::Jitter` deck,
tagged:

    jitter::src::<source note id>   provenance, and what Rust filters on
    topic::<name>                   inherited, so it scores under the
                                    same topic as the card it came from

That shape is the whole design: because a jitter card is just a card,
"accuracy on jitter cards" is the existing revlog math with a tag filter.
No new table, no new sync path, no new failure mode.

Usage:
    python import_jitter.py <collection.anki2> [--jsonl path]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "out" / "pylib"))

from anki.collection import Collection  # noqa: E402

DEFAULT_JSONL = Path(__file__).parent / "output" / "jitter_cards.jsonl"
DECK_NAME = "Speedrun::Jitter"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("collection")
    parser.add_argument("--jsonl", default=str(DEFAULT_JSONL))
    args = parser.parse_args()

    records = [
        json.loads(line)
        for line in Path(args.jsonl).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not records:
        raise SystemExit(f"no variants in {args.jsonl}")

    col = Collection(args.collection)
    deck_id = col.decks.id(DECK_NAME)
    basic = col.models.by_name("Basic")

    existing = {
        t for t in col.tags.all() if t.startswith("jitter::src::")
    }
    added = skipped = 0
    for rec in records:
        tag = f"jitter::src::{rec['source_nid']}"
        # Re-running the generator must not duplicate cards in the deck.
        if tag in existing:
            skipped += 1
            continue
        note = col.new_note(basic)
        note["Front"] = rec["front"]
        note["Back"] = rec["back"]
        note.tags = [tag]
        if rec.get("topic"):
            note.tags.append(rec["topic"])
        col.add_note(note, deck_id)
        existing.add(tag)
        added += 1

    col.save()
    print(f"added {added} jitter cards to {DECK_NAME}, skipped {skipped} already present")
    print(f"jitter cards now in collection: {len(col.find_cards('tag:jitter::*'))}")
    col.close()


if __name__ == "__main__":
    main()
