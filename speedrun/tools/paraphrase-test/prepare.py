#!/usr/bin/env python3
"""Paraphrase test (PRD §8, Brainlift §9): selects 30 cards from the AI
subsystem's already-generated set, assigns each a topic tag, and commits
the selection (with a timestamp) before any rewording is generated - the
same cutoff-before-generation discipline speedrun/ai/gold_set.json uses,
so the selection can't be quietly adjusted after seeing results.

Card provenance: speedrun/tools/ai-cardgen/output/ai_cards.json (50 cards,
each already carrying source_chunk/source_title back to
speedrun/ai/source_material.md). Reusing these keeps one unbroken
provenance chain from source material through generation through this
test, rather than inventing a second card set.

Topic assignment is a deterministic grouping of the 14 source chunks into
5 topics, 6 cards each (first 6 cards per group in file order - no random
seed needed, no cherry-picking possible after the fact):

  topic::overview_and_entry  - kc-01, kc-02, kc-03
  topic::steps_early         - kc-04, kc-05, kc-06
  topic::steps_late          - kc-07, kc-08, kc-09
  topic::energy_yield        - kc-10, kc-11
  topic::regulation          - kc-12, kc-13, kc-14

5 topics x 6 cards is what makes an interleaved vs. blocked review order
mechanically different at a 10-card study budget: blocked covers 2
topics deeply, interleaved covers all 5 shallowly.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

AI_CARDGEN_OUTPUT = Path(__file__).parent.parent / "ai-cardgen" / "output"
AI_CARDS_PATH = AI_CARDGEN_OUTPUT / "ai_cards.json"
OUTPUT_DIR = Path(__file__).parent / "output"
CARDS_PATH = OUTPUT_DIR / "cards.json"

CARDS_PER_TOPIC = 6

TOPIC_CHUNK_GROUPS = {
    "overview_and_entry": ["kc-01", "kc-02", "kc-03"],
    "steps_early": ["kc-04", "kc-05", "kc-06"],
    "steps_late": ["kc-07", "kc-08", "kc-09"],
    "energy_yield": ["kc-10", "kc-11"],
    "regulation": ["kc-12", "kc-13", "kc-14"],
}


def select_cards(all_cards: list[dict]) -> list[dict]:
    by_chunk: dict[str, list[dict]] = {}
    for card in all_cards:
        by_chunk.setdefault(card["source_chunk"], []).append(card)

    selected = []
    next_id = 1
    for topic, chunks in TOPIC_CHUNK_GROUPS.items():
        pool = [c for chunk in chunks for c in by_chunk.get(chunk, [])]
        if len(pool) < CARDS_PER_TOPIC:
            raise ValueError(
                f"topic::{topic} only has {len(pool)} candidate cards "
                f"(chunks {chunks}), need {CARDS_PER_TOPIC}"
            )
        for card in pool[:CARDS_PER_TOPIC]:
            selected.append(
                {
                    "id": next_id,
                    "topic": f"topic::{topic}",
                    "front": card["front"],
                    "back": card["back"],
                    "source_chunk": card["source_chunk"],
                    "source_title": card["source_title"],
                }
            )
            next_id += 1
    return selected


def main() -> None:
    all_cards = json.loads(AI_CARDS_PATH.read_text(encoding="utf-8"))
    selected = select_cards(all_cards)

    assert len(selected) == 30, f"expected 30 cards, got {len(selected)}"
    topics = {c["topic"] for c in selected}
    assert len(topics) == 5, f"expected 5 topics, got {len(topics)}"

    OUTPUT_DIR.mkdir(exist_ok=True)
    CARDS_PATH.write_text(
        json.dumps(
            {
                "_provenance": (
                    "30 cards selected deterministically (first 6 per topic "
                    "group, in ai_cards.json file order) from "
                    "speedrun/tools/ai-cardgen/output/ai_cards.json, before "
                    "any rewording was generated or graded."
                ),
                "cutoff_committed_at": datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(),
                "topic_chunk_groups": TOPIC_CHUNK_GROUPS,
                "cards": selected,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Selected {len(selected)} cards across {len(topics)} topics -> {CARDS_PATH}")
    for topic in TOPIC_CHUNK_GROUPS:
        n = sum(1 for c in selected if c["topic"] == f"topic::{topic}")
        print(f"  topic::{topic}: {n} cards")


if __name__ == "__main__":
    main()
