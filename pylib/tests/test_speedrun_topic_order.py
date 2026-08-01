# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Python-side check for the Speedrun topic-interleaving toggle (Brainlift
Section 9 thesis ablation): the config key is readable and settable from
Python, and setting it changes the order returned by get_queued_cards()
without changing how many cards are returned - mirroring the Rust-side
integration test in rslib/src/scheduler/queue/builder/mod.rs, but
exercised through the same Python surface AnkiDroid/aqt actually use.
"""

from tests.shared import getEmptyCol


def _topics_in_queue_order(col) -> list[str]:
    queued = col.sched.get_queued_cards(fetch_limit=10)
    topics = []
    for queued_card in queued.cards:
        note = col.get_note(queued_card.card.note_id)
        topic = next((t for t in note.tags if t.startswith("topic::")), "")
        topics.append(topic)
    return topics


def _force_queue_rebuild(col, scratch_deck_id) -> None:
    """set_config's Op::UpdateConfig is deliberately NOT in
    requires_study_queue_rebuild() (rslib/src/ops.rs) - most config keys
    have nothing to do with the queue, so treating every config write as
    queue-dirtying would force needless rebuilds. Op::SetCurrentDeck IS in
    that list - but only fires it if the current-deck id actually
    *changes* (set_current_deck_inner short-circuits on a same-value
    write), so this bounces through a scratch deck and back rather than
    re-setting the same id, which would silently no-op."""
    col.decks.set_current(scratch_deck_id)
    col.decks.set_current(1)


def test_speedrun_topic_order():
    col = getEmptyCol()
    scratch_deck_id = col.decks.add_normal_deck_with_name("scratch").id
    for topic in ["a", "a", "b", "b"]:
        note = col.newNote()
        note["Front"] = f"front-{topic}"
        note.add_tag(f"topic::{topic}")
        col.addNote(note)

    default_order = _topics_in_queue_order(col)
    assert len(default_order) == 4

    col.set_config("speedrunTopicOrder", "blocked")
    _force_queue_rebuild(col, scratch_deck_id)
    blocked_order = _topics_in_queue_order(col)
    assert blocked_order == ["topic::a", "topic::a", "topic::b", "topic::b"]

    col.set_config("speedrunTopicOrder", "interleaved")
    _force_queue_rebuild(col, scratch_deck_id)
    interleaved_order = _topics_in_queue_order(col)
    assert interleaved_order == ["topic::a", "topic::b", "topic::a", "topic::b"]

    # counts are invariant across all modes
    assert len(blocked_order) == 4
    assert len(interleaved_order) == 4

    # removing the key restores the exact unmodified-Anki order
    col.remove_config("speedrunTopicOrder")
    _force_queue_rebuild(col, scratch_deck_id)
    assert _topics_in_queue_order(col) == default_order
