#!/usr/bin/env python3
"""A small (1000-card, all due) fixture for crash-test - deliberately not
the 50k bench deck. crash-test recopies this file fresh before every one
of its 20 iterations; recopying 50k cards 20x would be slow disk I/O for
no benefit, since what's under test is write-durability during a review,
not queue-build performance at scale (that's bench's job).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "out" / "pylib"))

from anki import deck_config_pb2  # noqa: E402
from anki.collection import Collection  # noqa: E402
from anki.consts import CARD_TYPE_REV, QUEUE_TYPE_REV  # noqa: E402

TEMPLATE_PATH = Path(__file__).parent / "output" / "template.anki2"
CARD_COUNT = 1000


def build() -> None:
    TEMPLATE_PATH.parent.mkdir(exist_ok=True)
    if TEMPLATE_PATH.exists():
        TEMPLATE_PATH.unlink()

    col = Collection(str(TEMPLATE_PATH))
    # config_dict_for_deck_id()/decks.save() silently no-ops on writes in
    # this Anki version - see bench/make_fixture.py's comment for how
    # this was found. update_deck_configs() is the write path that
    # actually persists.
    info = col.decks.get_deck_configs_for_update(1)
    deck_config = info.all_config[0].config
    deck_config.config.new_per_day = CARD_COUNT
    deck_config.config.reviews_per_day = CARD_COUNT
    col.decks.update_deck_configs(
        deck_config_pb2.UpdateDeckConfigsRequest(
            target_deck_id=1, configs=[deck_config], removed_config_ids=[]
        )
    )

    notetype = col.models.by_name("Basic")
    deck_id = col.decks.current()["id"]
    card_ids = []
    for i in range(CARD_COUNT):
        note = col.new_note(notetype)
        note["Front"] = f"Crash-test question {i}"
        note["Back"] = f"Crash-test answer {i}"
        col.add_note(note, deck_id)
        card_ids.extend(c.id for c in note.cards())

    # All due today, review-state, so a worker can grade continuously
    # without running dry mid-run.
    for cid in card_ids:
        card = col.get_card(cid)
        card.ivl = 10
        card.due = 0
        card.factor = 2500
        card.reps = 3
        card.ctype = CARD_TYPE_REV
        card.queue = QUEUE_TYPE_REV
        col.update_card(card, skip_undo_entry=True)

    col.close()
    print(f"Built {len(card_ids)}-card crash-test template -> {TEMPLATE_PATH}")


if __name__ == "__main__":
    build()
