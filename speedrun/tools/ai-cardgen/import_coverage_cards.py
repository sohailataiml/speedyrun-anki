#!/usr/bin/env python3
"""Imports the generated coverage cards into an Anki collection, tagged
with the `topic::` tag for their AAMC content category and a
`source::<chunk>` tag carrying provenance.

**Deliberately does not simulate review history.** An earlier draft had a
`--review N` flag that would mark the imported cards as already studied,
which would have pushed the headline coverage number up immediately. That
would have been fabricating study that nobody did - the same inflation
this project's own Brainlift attacks competitors for. Importing real
cards is genuine work; claiming they were reviewed is not.

The consequence is visible and correct: after this import the collection
has *content* for nine content categories but *studied* material for
three. The coverage map reports both numbers separately for exactly that
reason - see speedrun/docs/coverage-map.md.

The app must be closed - Anki holds an exclusive lock on the collection.

Usage:
  python import_coverage_cards.py <collection.anki2> [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CARDS_PATH = Path(__file__).parent / "output" / "coverage_cards.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("collection")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(REPO_ROOT / "out" / "pylib"))
    from anki.collection import Collection  # noqa: E402

    payload = json.loads(CARDS_PATH.read_text(encoding="utf-8"))
    cards = payload["cards"]
    print(f"{len(cards)} cards to import, by category: {payload['by_category']}")
    if args.dry_run:
        return

    col = Collection(args.collection)
    try:
        notetype = col.models.by_name("Basic")
        deck_id = col.decks.id("Default")
        existing = set(col.find_notes('"tag:source::*"'))
        if existing:
            print(f"note: {len(existing)} previously-imported notes already present")

        added = 0
        for card in cards:
            note = col.new_note(notetype)
            note["Front"] = card["front"]
            note["Back"] = card["back"]
            # Provenance travels with the note, not just the JSON: the
            # source chunk is what makes "traces to a named source"
            # checkable from inside the collection itself.
            note.tags = [card["topic_tag"], f"source::{card['source_chunk']}"]
            col.add_note(note, deck_id)
            added += 1
        print(f"added {added} notes (all new, unreviewed - nothing faked)")
    finally:
        col.close()
    print("done")


if __name__ == "__main__":
    main()
