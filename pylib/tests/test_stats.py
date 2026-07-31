# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import os
import tempfile

from anki.collection import CardStats
from tests.shared import getEmptyCol


def test_stats():
    col = getEmptyCol()
    note = col.newNote()
    note["Front"] = "foo"
    col.addNote(note)
    c = note.cards()[0]
    # card stats
    card_stats = col.card_stats_data(c.id)
    assert card_stats.note_id == note.id
    c = col.sched.getCard()
    col.sched.answerCard(c, 3)
    col.sched.answerCard(c, 2)
    card_stats = col.card_stats_data(c.id)
    assert len(card_stats.revlog) == 2


def test_mastery_query():
    col = getEmptyCol()
    # Mastery is derived from FSRS's memory_state, which only exists on
    # FSRS-scheduled collections - without this, cards never get a
    # memory_state and mastery stays 0 regardless of review history.
    col.set_config("fsrs", True)
    note = col.newNote()
    note["Front"] = "foo"
    col.addNote(note)
    note.add_tag("topic::krebs_cycle")
    note.flush()

    # Unreviewed: counts toward coverage, not toward mastery/recall.
    (topic,) = col.mastery_query(["krebs_cycle"])
    assert topic.topic == "krebs_cycle"
    assert topic.cards_total == 1
    assert topic.cards_with_reviews == 0
    assert topic.mastery == 0.0
    assert topic.average_recall == 0.0

    # Answer the card "Good" once - should now count as reviewed, with
    # perfect recall and some non-zero mastery.
    c = col.sched.getCard()
    col.sched.answerCard(c, 3)

    (topic,) = col.mastery_query(["krebs_cycle"])
    assert topic.cards_with_reviews == 1
    assert topic.average_recall == 1.0
    assert 0.0 < topic.mastery <= 1.0

    # A topic with no matching cards should come back empty, not error.
    (empty_topic,) = col.mastery_query(["nonexistent_topic"])
    assert empty_topic.cards_total == 0


def test_give_up_gate():
    col = getEmptyCol()
    note = col.newNote()
    note["Front"] = "foo"
    col.addNote(note)
    note.add_tag("topic::krebs_cycle")
    note.flush()

    # No reviews yet: the gate must refuse rather than let a caller guess.
    resp = col.give_up_gate(["krebs_cycle"])
    assert resp.WhichOneof("result") == "insufficient"
    assert resp.insufficient.total_graded_reviews == 0
    assert resp.insufficient.reviews_required == 200
    assert resp.insufficient.coverage_required == 0.5

    # One review is still far short of the 200-review floor.
    c = col.sched.getCard()
    col.sched.answerCard(c, 3)
    resp = col.give_up_gate(["krebs_cycle"])
    assert resp.WhichOneof("result") == "insufficient"
    assert resp.insufficient.total_graded_reviews == 1


def test_performance_query():
    col = getEmptyCol()
    note = col.newNote()
    note["Front"] = "foo"
    col.addNote(note)
    note.add_tag("topic::krebs_cycle")
    note.flush()

    # Same give-up gate as test_give_up_gate: not enough reviews yet, so
    # the Performance model must never run, let alone return a number.
    resp = col.performance_query(["krebs_cycle"], average_difficulty=0.5, average_timing_seconds=70.0)
    assert resp.WhichOneof("result") == "insufficient"
    assert resp.insufficient.total_graded_reviews == 0


def test_readiness_query():
    col = getEmptyCol()
    note = col.newNote()
    note["Front"] = "foo"
    col.addNote(note)
    note.add_tag("topic::krebs_cycle")
    note.flush()

    # Same give-up gate cascade as performance_query: no reviews yet, so
    # the Readiness mapper must never invent a score.
    resp = col.readiness_query(["krebs_cycle"], average_difficulty=0.5, average_timing_seconds=70.0)
    assert resp.WhichOneof("result") == "insufficient"
    assert resp.insufficient.total_graded_reviews == 0


def test_graphs_empty():
    col = getEmptyCol()
    assert col.stats().report()


def test_graphs():
    dir = tempfile.gettempdir()
    col = getEmptyCol()
    g = col.stats()
    rep = g.report()
    with open(os.path.join(dir, "test.html"), "w", encoding="UTF-8") as note:
        note.write(rep)
    return
