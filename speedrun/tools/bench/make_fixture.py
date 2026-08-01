#!/usr/bin/env python3
"""Builds the shared 50k-card fixture deck PRD §10's benchmark table
requires ("Every row must be reported... on the shared 50k-card deck").
Used by both bench/ and crash-test/, so it lives here and crash-test
imports it rather than duplicating deck generation.

Cards are spread across 50 topic:: tags (1000 cards each) so the fixture
also exercises Speedrun's own mastery_query/give_up_gate/performance_query
paths realistically, not just raw card count. A slice of cards are given
review history (varied intervals/due dates) so the review queue is
non-trivial to build, which is what the timing numbers actually need to
stress - an all-new-card deck would understate real queue-build cost.
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "out" / "pylib"))

from anki import deck_config_pb2  # noqa: E402
from anki.collection import Collection  # noqa: E402
from anki.consts import CARD_TYPE_REV, QUEUE_TYPE_REV  # noqa: E402

FIXTURE_DIR = Path(__file__).parent / "output"
FIXTURE_PATH = FIXTURE_DIR / "fixture_50k.anki2"

TOTAL_CARDS = 50_000
TOPICS = 50
CARDS_PER_TOPIC = TOTAL_CARDS // TOPICS
REVIEWED_FRACTION = 0.6  # 60% have review history; rest are new


def build(seed: int = 42) -> None:
    rng = random.Random(seed)
    FIXTURE_DIR.mkdir(exist_ok=True)
    if FIXTURE_PATH.exists():
        FIXTURE_PATH.unlink()

    col = Collection(str(FIXTURE_PATH))
    # The legacy config_dict_for_deck_id()/decks.save() pair silently
    # no-ops on writes in this Anki version - found the hard way while
    # debugging why bench.py's queue kept reporting 0 due cards after a
    # couple of runs. update_deck_configs() is the write path that
    # actually persists. (bench.py itself no longer depends on this
    # limit being raised - it drives answerCard() directly from a raw
    # search rather than through the daily-limited queue - but the
    # fixture's own config should still be correct, not misleading.)
    info = col.decks.get_deck_configs_for_update(1)
    deck_config = info.all_config[0].config
    deck_config.config.new_per_day = TOTAL_CARDS
    deck_config.config.reviews_per_day = TOTAL_CARDS
    col.decks.update_deck_configs(
        deck_config_pb2.UpdateDeckConfigsRequest(
            target_deck_id=1, configs=[deck_config], removed_config_ids=[]
        )
    )

    notetype = col.models.by_name("Basic")
    deck_id = col.decks.current()["id"]

    start = time.monotonic()
    card_ids = []
    for topic_i in range(TOPICS):
        for card_i in range(CARDS_PER_TOPIC):
            note = col.new_note(notetype)
            note["Front"] = f"Topic {topic_i} question {card_i}"
            note["Back"] = f"Topic {topic_i} answer {card_i}"
            note.add_tag(f"topic::bench_topic_{topic_i:03d}")
            col.add_note(note, deck_id)
            card_ids.extend(c.id for c in note.cards())
        if topic_i % 10 == 0:
            print(f"  {topic_i}/{TOPICS} topics ({len(card_ids)} cards)...")

    # Give a majority of cards realistic review history so the fixture
    # stresses the review queue (relative-overdueness sort, FSRS state),
    # not just the new-card gather path.
    reviewed_ids = rng.sample(card_ids, int(len(card_ids) * REVIEWED_FRACTION))
    for i, cid in enumerate(reviewed_ids):
        card = col.get_card(cid)
        card.ivl = rng.randint(1, 365)
        card.due = rng.randint(-30, 5)  # spread of overdue/due-soon/future
        card.factor = rng.randint(1300, 3500)
        card.reps = rng.randint(1, 20)
        card.ctype = CARD_TYPE_REV
        card.queue = QUEUE_TYPE_REV
        card.flush()
        if i % 5000 == 0:
            print(f"  flushed {i}/{len(reviewed_ids)} review-history cards...")

    elapsed = time.monotonic() - start
    col.close()

    print(f"\nBuilt {len(card_ids)} cards across {TOPICS} topics in {elapsed:.1f}s")
    print(f"  {len(reviewed_ids)} with review history, {len(card_ids) - len(reviewed_ids)} new")
    print(f"-> {FIXTURE_PATH}")


if __name__ == "__main__":
    build()
