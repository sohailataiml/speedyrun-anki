#!/usr/bin/env python3
"""Builds a fixture Anki collection from the 30 counterfactual cards
(output/cards_counterfactual.json), tags each note with its topic, and
extracts the REAL queue order the Rust backend produces for each of the
three §9 ablation builds:

  - "interleaved": speedrunTopicOrder=interleaved (the thesis feature, on)
  - "blocked":      speedrunTopicOrder=blocked (same app, feature off)
  - "ankiDefault":  no config key set - genuinely unmodified Anki's own
                    new-card gather order

This is the only script in this tool that imports `anki` - the rest of
the pipeline is pure API-call scripting. Card budget N's "studied set"
for a build is simply the first N cards in that build's real queue order,
which is what makes the coverage-breadth difference between builds
mechanical rather than invented: blocked review genuinely finishes 1-2
topics before starting the next; interleaved genuinely visits all 5
topics from card 1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"
CARDS_CF_PATH = OUTPUT_DIR / "cards_counterfactual.json"
STUDY_ORDERS_PATH = OUTPUT_DIR / "study_orders.json"

# out/pylib has the built anki package (with buildinfo.py, the compiled
# rsbridge extension, etc.) - the raw pylib/ source tree lacks buildinfo
# and isn't directly importable. See rust-change-note.md's queue
# invalidation section for why set_current bounces through a scratch deck.
REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "out" / "pylib"))

from anki.collection import Collection  # noqa: E402

FIXTURE_DIR = OUTPUT_DIR / "fixture"
FIXTURE_PATH = FIXTURE_DIR / "collection.anki2"

BUILDS = {
    "interleaved": "interleaved",
    "blocked": "blocked",
    "ankiDefault": None,  # no config key set at all
}

COVERAGE_BUDGETS = [10, 20, 30]


def build_fixture_collection(cards: list[dict]) -> tuple[Collection, dict[int, int]]:
    """Returns the collection plus a note_id -> pipeline card_id (1-30,
    matching cards_counterfactual.json) map, so the real queue order can
    be translated back to *this pipeline's* cards - Anki's own internal
    note/card ids are unrelated to that numbering."""
    FIXTURE_DIR.mkdir(exist_ok=True)
    if FIXTURE_PATH.exists():
        FIXTURE_PATH.unlink()
    col = Collection(str(FIXTURE_PATH))
    # Default new-cards-per-day (20) would cap the queue below all 30
    # cards; the ablation needs the full study order, not a daily-limited
    # slice of it.
    conf = col.decks.config_dict_for_deck_id(1)
    conf["new"]["perDay"] = 100
    col.decks.save(conf)
    notetype = col.models.by_name("Basic")
    note_id_to_card_id: dict[int, int] = {}
    for card in cards:
        note = col.new_note(notetype)
        note["Front"] = card["front"]
        note["Back"] = card["back"]
        note.add_tag(card["topic"])
        col.add_note(note, col.decks.current()["id"])
        note_id_to_card_id[note.id] = card["id"]
    return col, note_id_to_card_id


def force_queue_rebuild(col: Collection, scratch_deck_id: int) -> None:
    """See rust-change-note.md: set_config alone doesn't invalidate the
    cached queue, and set_current_deck only clears it when the id
    actually changes - so this bounces through a scratch deck."""
    col.decks.set_current(scratch_deck_id)
    col.decks.set_current(1)


def queue_order(col: Collection, note_id_to_card_id: dict[int, int]) -> list[dict]:
    """Real queue order as (pipeline card_id, topic) pairs - card_id here
    is cards_counterfactual.json's 1-30 id, not Anki's internal one, so
    run.py can directly look cards up by it. Fetches every card
    (fetch_limit=30) so the full order is observed, not just the first
    page."""
    queued = col.sched.get_queued_cards(fetch_limit=30)
    order = []
    for queued_card in queued.cards:
        note = col.get_note(queued_card.card.note_id)
        topic = next((t for t in note.tags if t.startswith("topic::")), "")
        order.append(
            {"card_id": note_id_to_card_id[queued_card.card.note_id], "topic": topic}
        )
    return order


def topics_covered(order: list[dict], budget: int) -> int:
    return len({c["topic"] for c in order[:budget]})


def main() -> None:
    cards_data = json.loads(CARDS_CF_PATH.read_text(encoding="utf-8"))
    cards = cards_data["cards"]

    col, note_id_to_card_id = build_fixture_collection(cards)
    scratch_deck_id = col.decks.add_normal_deck_with_name("scratch").id

    results = {}
    for build_name, config_value in BUILDS.items():
        if config_value is None:
            col.remove_config("speedrunTopicOrder")
        else:
            col.set_config("speedrunTopicOrder", config_value)
        force_queue_rebuild(col, scratch_deck_id)
        order = queue_order(col, note_id_to_card_id)
        assert len(order) == 30, f"{build_name}: expected 30 queued cards, got {len(order)}"
        results[build_name] = {
            "order": order,
            "topics_covered_at_budget": {
                str(b): topics_covered(order, b) for b in COVERAGE_BUDGETS
            },
        }
        print(
            f"{build_name}: topics covered @10={results[build_name]['topics_covered_at_budget']['10']}, "
            f"@20={results[build_name]['topics_covered_at_budget']['20']}, "
            f"@30={results[build_name]['topics_covered_at_budget']['30']}"
        )

    # The three sanity checks the ablation depends on.
    for build_name, data in results.items():
        ids = {c["card_id"] for c in data["order"]}
        assert len(ids) == 30, f"{build_name}: not a permutation of 30 unique cards"

    interleaved_order = [c["card_id"] for c in results["interleaved"]["order"]]
    blocked_order = [c["card_id"] for c in results["blocked"]["order"]]
    default_order = [c["card_id"] for c in results["ankiDefault"]["order"]]
    assert interleaved_order != blocked_order, "interleaved and blocked produced identical order"
    print(f"\nOrders differ between builds: OK")

    # Confirm "build 3 is genuinely the unmodified path": removing the
    # config key entirely reproduces the exact order Anki's own gather/
    # sort would produce with no Speedrun code path taken.
    col.remove_config("speedrunTopicOrder")
    force_queue_rebuild(col, scratch_deck_id)
    reconfirm_default = [c["card_id"] for c in queue_order(col, note_id_to_card_id)]
    assert reconfirm_default == default_order, "ankiDefault order not stable/reproducible"
    print("ankiDefault order reproducible with no config key set: OK")

    STUDY_ORDERS_PATH.write_text(
        json.dumps(
            {
                "_provenance": (
                    "Real queue order from the Rust backend "
                    "(build_queues/apply_topic_order), one build per key, "
                    "extracted via study_order.py against a fixture "
                    "collection built from the 30 counterfactual cards. "
                    "Not invented - this is what the real app would "
                    "queue in each mode."
                ),
                "coverage_budgets": COVERAGE_BUDGETS,
                "builds": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n-> {STUDY_ORDERS_PATH}")

    col.close()


if __name__ == "__main__":
    main()
