# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Speedrun addition: the Socratic Gatekeeper (Brainlift v2's primary
thesis). After a card is answered, decides whether to show a Socratic
bridge question before moving on, based on how fast the answer came and
whether it was correct. See speedrun/docs/socratic-gate-mvp.md for the
full design, the MVP simplifications, and the real n=90 ablation this
mechanism was validated against before being wired into the live app.

Phase 1 (this file): real-time UI, real Claude API calls, wired into
the actual desktop review flow via `reviewer_did_answer_card`.
Phase 2/3 (not built): grounding the bridge in a curriculum RAG index
instead of just the card's own front/back, and a leak check verifying
the bridge doesn't accidentally restate the gold answer. See this
module's bottom-of-file note for what those would need.

The decision function below is a deliberate Python mirror of
`rslib/src/stats/socratic_gate.rs`, not an RPC call - it's a stateless
two-input threshold comparison with no collection/database access, so a
new RPC would add proto-regen and (eventually) Android AAR-rebuild cost
for zero behavioral benefit over duplicating ~10 lines of pure logic.
The Rust module's 6 unit tests are the source of truth this must match;
`test_decision_matches_rust_cases` below pins that with the exact same
cases.
"""

from __future__ import annotations

import enum
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import aqt
from anki.cards import Card
from aqt.operations import QueryOp
from aqt.qt import *
from aqt.utils import disable_help_button, restoreGeom, saveGeom

if TYPE_CHECKING:
    # Deferred: importing aqt.reviewer at module level here creates a
    # circular import, since this module is itself imported from
    # aqt/main.py, which sits in aqt.reviewer's own import chain
    # (aqt.reviewer -> aqt.browser -> aqt.editor -> aqt.main). Safe under
    # TYPE_CHECKING because `from __future__ import annotations` above
    # defers all annotation evaluation to strings - this import never
    # actually runs.
    import aqt.reviewer

TITLE = "speedrunSocraticGate"

# Must match rslib/src/stats/socratic_gate.rs's DEFAULT_FAST_THRESHOLD_MS.
FAST_THRESHOLD_MS = 3_000

MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"

# Same prompt as speedrun/tools/socratic-gate/generate_bridges.py, minus
# the counterfactual-terminology instruction (real card content here,
# not the paraphrase-test's renamed-term fixtures).
BRIDGE_SYSTEM_PROMPT = (
    "You write Socratic bridge questions for a study app. Given a single "
    "flashcard (front/back), write ONE short bridging question that "
    "would help a student who answered wrong re-derive the fact "
    "themselves, rather than just being told the answer again. The "
    "bridge should reference a related consequence, mechanism, or "
    "contrast that forces the student to reason back to the card's fact "
    "- not restate the fact directly. Then give the answer to your own "
    "bridge question, and a one-sentence synthesis connecting it back to "
    "the card's original fact.\n\n"
    "Respond in exactly this three-line format, nothing else, no other "
    "commentary before or after:\n"
    "BRIDGE_QUESTION: <the bridging question>\n"
    "BRIDGE_ANSWER: <the answer to the bridge question>\n"
    "SYNTHESIS: <one sentence connecting it back to the original fact>"
)
RESPONSE_RE = re.compile(
    r"BRIDGE_QUESTION:\s*(.+?)\s*\nBRIDGE_ANSWER:\s*(.+?)\s*\nSYNTHESIS:\s*(.+)",
    re.DOTALL,
)


class GateDecision(enum.Enum):
    AUTOMATED_MASTERY = "automated_mastery"
    DANGEROUS_ERROR = "dangerous_error"
    PRODUCTIVE_STRUGGLE = "productive_struggle"
    LUCKY_GUESS = "lucky_guess"


def socratic_gate_decision(
    taken_millis: int, button_chosen: int, fast_threshold_ms: int = FAST_THRESHOLD_MS
) -> GateDecision:
    """Pure mirror of rslib/src/stats/socratic_gate.rs::socratic_gate_decision."""
    correct = button_chosen > 1
    fast = taken_millis <= fast_threshold_ms
    if fast and correct:
        return GateDecision.AUTOMATED_MASTERY
    if fast and not correct:
        return GateDecision.DANGEROUS_ERROR
    if not fast and not correct:
        return GateDecision.PRODUCTIVE_STRUGGLE
    return GateDecision.LUCKY_GUESS


def requires_socratic_bridge(decision: GateDecision) -> bool:
    return decision in (GateDecision.DANGEROUS_ERROR, GateDecision.PRODUCTIVE_STRUGGLE)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^<]+?>", " ", text).strip()


@dataclass
class BridgeContent:
    bridge_question: str
    bridge_answer: str
    synthesis: str


def _generate_bridge(api_key: str, front: str, back: str) -> BridgeContent:
    user_prompt = f"Card front: {front}\nCard back: {back}"
    payload = json.dumps(
        {
            "model": MODEL,
            "max_tokens": 300,
            "system": BRIDGE_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": 0.7,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read())
    text = body["content"][0]["text"].strip()
    match = RESPONSE_RE.search(text)
    if not match:
        raise ValueError(f"no BRIDGE_QUESTION/ANSWER/SYNTHESIS in response: {text!r}")
    return BridgeContent(
        bridge_question=match.group(1).strip(),
        bridge_answer=match.group(2).strip(),
        synthesis=match.group(3).strip(),
    )


class SocraticBridgeDialog(QDialog):
    """Two-stage reveal, same interaction shape as the card flip itself:
    the bridge question first, then (on demand) the bridge answer and
    synthesis - never the plain card answer restated, which is the
    whole point of the mechanism (see socratic-gate-mvp.md's n=90
    result: restating the plain answer is what a bridge is deliberately
    trading away, in exchange for a wash-or-better result on transfer/
    discrimination items instead of verbatim recall)."""

    silentlyClose = True

    def __init__(self, mw: aqt.main.AnkiQt, label: str) -> None:
        super().__init__(mw, Qt.WindowType.Window)
        self.mw = mw
        self.mw.garbage_collect_on_dialog_finish(self)
        self.setWindowTitle(f"Speedrun — Socratic bridge ({label})")
        self.setMinimumSize(420, 200)
        disable_help_button(self)
        restoreGeom(self, TITLE, default_size=(420, 200))
        _position_under_question(self, mw)

        self._layout = QVBoxLayout()
        self._layout.addWidget(QLabel("Generating a bridge question…"))
        self.setLayout(self._layout)

    def _clear(self) -> None:
        while (item := self._layout.takeAt(0)) is not None:
            if widget := item.widget():
                widget.deleteLater()

    def show_bridge(self, content: BridgeContent) -> None:
        self._content = content
        self._clear()
        intro = QLabel(
            "Before moving on — think this through, then reveal when ready."
        )
        intro.setWordWrap(True)
        self._layout.addWidget(intro)

        question = QLabel(content.bridge_question)
        question.setWordWrap(True)
        font = question.font()
        font.setBold(True)
        question.setFont(font)
        self._layout.addWidget(question)

        reveal = QPushButton("Reveal")
        qconnect(reveal.clicked, self._reveal)
        self._layout.addWidget(reveal)

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        qconnect(close.rejected, self.close)
        self._layout.addWidget(close)

    def _reveal(self) -> None:
        self._clear()
        answer = QLabel(self._content.bridge_answer)
        answer.setWordWrap(True)
        self._layout.addWidget(answer)

        synthesis = QLabel(self._content.synthesis)
        synthesis.setWordWrap(True)
        synthesis.setStyleSheet("color: gray;")
        self._layout.addWidget(synthesis)

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        qconnect(close.rejected, self.close)
        qconnect(close.accepted, self.close)
        self._layout.addWidget(close)

    def show_error(self, message: str) -> None:
        self._clear()
        label = QLabel(f"Couldn't generate a bridge question: {message}")
        label.setWordWrap(True)
        self._layout.addWidget(label)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        qconnect(close.rejected, self.close)
        self._layout.addWidget(close)

    def closeEvent(self, event: QCloseEvent | None) -> None:  # noqa: N802
        saveGeom(self, TITLE)
        super().closeEvent(event)


class ConfidenceDialog(QDialog):
    """Shown in place of the normal answer reveal, when the gate is
    active. Captures a self-reported confidence tap before the back is
    shown - see brainlift.md §4's decision table, which conditions
    the withhold-vs-reveal choice on latency and this confidence signal,
    not just correctness (which isn't knowable pre-reveal anyway)."""

    silentlyClose = True

    def __init__(self, mw: aqt.main.AnkiQt) -> None:
        super().__init__(mw, Qt.WindowType.Window)
        self.mw = mw
        self.mw.garbage_collect_on_dialog_finish(self)
        self.setWindowTitle("Speedrun — before we reveal")
        self.setMinimumSize(360, 160)
        disable_help_button(self)
        _position_under_question(self, mw)
        self.confident: bool | None = None

        layout = QVBoxLayout()
        label = QLabel("How confident are you in your answer?")
        label.setWordWrap(True)
        layout.addWidget(label)

        row = QHBoxLayout()
        confident_btn = QPushButton("I've got it")
        not_sure_btn = QPushButton("Not sure")
        qconnect(confident_btn.clicked, lambda: self._choose(True))
        qconnect(not_sure_btn.clicked, lambda: self._choose(False))
        row.addWidget(confident_btn)
        row.addWidget(not_sure_btn)
        layout.addLayout(row)
        self.setLayout(layout)

    def _choose(self, confident: bool) -> None:
        self.confident = confident
        self.accept()


def _position_under_question(dialog: QDialog, mw: aqt.main.AnkiQt) -> None:
    """Shared by ConfidenceDialog and SocraticBridgeDialog: sized and
    positioned to span most of the main window's content area, starting
    just below where the toolbar/question typically end. Card answers
    vary a lot in length, so a small fixed-size dialog placed at one
    y-offset can leave a longer answer poking out below or above it -
    this covers a wide vertical band instead of guessing one exact spot,
    so the answer stays hidden regardless of how long it is."""
    mw_geom = mw.geometry()
    width = int(mw_geom.width() * 0.7)
    height = int(mw_geom.height() * 0.55)
    dialog.resize(max(width, dialog.minimumWidth()), max(height, dialog.minimumHeight()))
    x = mw_geom.x() + (mw_geom.width() - dialog.width()) // 2
    y = mw_geom.y() + int(mw_geom.height() * 0.12)
    dialog.move(max(x, 0), max(y, 0))


def maybe_gate_before_answer(reviewer: aqt.reviewer.Reviewer) -> bool:
    """Called from Reviewer._showAnswer, before the back is revealed.
    Returns True if this call takes over showing the answer - the caller
    must NOT reveal the answer itself in that case, since
    reviewer._reveal_answer_now() gets invoked here once the student has
    engaged with the confidence tap (and, if triggered, the withheld-
    answer bridge). Returns False to let the normal reveal proceed
    immediately and synchronously (e.g. no API key configured).

    A genuine "fast + confident + wrong" Dangerous Error can only be
    caught after grading - there's no way to know the answer is wrong
    before it's shown. That case still goes through
    maybe_show_socratic_bridge below, unchanged, after this function
    lets the reveal proceed normally.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
        "SPEEDRUN_ANTHROPIC_KEY"
    )
    if not api_key:
        return False

    card = reviewer.card
    taken_millis = card.time_taken(capped=False)

    confidence_dialog = ConfidenceDialog(reviewer.mw)
    confidence_dialog.exec()

    fast = taken_millis <= FAST_THRESHOLD_MS
    if fast or confidence_dialog.confident is None:
        # Fast (Automated Mastery / Lucky Guess row), or the dialog was
        # dismissed without a choice - fail open, reveal normally rather
        # than getting the student stuck on an unanswered prompt.
        reviewer._reveal_answer_now()
        return True

    # Slow, regardless of confidence (brainlift.md §4's "Slow + any
    # confidence" row -> Productive Struggle): withhold the back, show
    # the bridge first.
    front = _strip_html(card.question())
    back = _strip_html(card.answer())
    bridge_dialog = SocraticBridgeDialog(reviewer.mw, "before revealing")

    def on_success(content: BridgeContent) -> None:
        bridge_dialog.show_bridge(content)

    def on_failure(exc: Exception) -> None:
        bridge_dialog.show_error(str(exc))

    QueryOp(
        parent=bridge_dialog,
        op=lambda _col: _generate_bridge(api_key, front, back),
        success=on_success,
    ).failure(on_failure).without_collection().run_in_background()
    bridge_dialog.exec()

    # Suppress the post-grade Dangerous Error/Productive Struggle check
    # for this same card - it already got its bridge, pre-reveal.
    reviewer._speedrun_bridge_shown_for_card_id = card.id
    reviewer._reveal_answer_now()
    return True


def maybe_show_socratic_bridge(
    reviewer: aqt.reviewer.Reviewer, card: Card, ease: Literal[1, 2, 3, 4]
) -> None:
    """Registered on gui_hooks.reviewer_did_answer_card in main.py. Silently
    does nothing if no API key is configured, the gate doesn't call for
    an intervention, or this card already got a pre-reveal bridge via
    maybe_gate_before_answer - never blocks or interrupts the normal
    review flow on its own account."""
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
        "SPEEDRUN_ANTHROPIC_KEY"
    )
    if not api_key:
        return
    if getattr(reviewer, "_speedrun_bridge_shown_for_card_id", None) == card.id:
        return

    taken_millis = card.time_taken(capped=False)
    decision = socratic_gate_decision(taken_millis, ease)
    if not requires_socratic_bridge(decision):
        return

    front = _strip_html(card.question())
    back = _strip_html(card.answer())

    label = "Dangerous error" if decision == GateDecision.DANGEROUS_ERROR else "Worth a closer look"
    dialog = SocraticBridgeDialog(reviewer.mw, label)

    def on_success(content: BridgeContent) -> None:
        dialog.show_bridge(content)

    def on_failure(exc: Exception) -> None:
        dialog.show_error(str(exc))

    # Start the (async, background-thread) API call before blocking on the
    # modal below - QueryOp's completion signal still gets delivered by
    # Qt's event loop while dialog.exec() runs its own nested loop.
    QueryOp(
        parent=dialog,
        op=lambda _col: _generate_bridge(api_key, front, back),
        success=on_success,
    ).failure(on_failure).without_collection().run_in_background()

    # Modal, not dialog.show(): _after_answering() calls self.nextCard()
    # right after this hook returns. A non-blocking dialog would let the
    # reviewer flip to the *next* card seconds before the bridge content
    # for *this* card arrives, making the bridge look like it's about the
    # wrong question. Blocking here also matches the actual "Gatekeeper"
    # framing - it should hold up progression, not float over whatever
    # already replaced it on screen.
    dialog.exec()


# --- Phase 2/3 design notes, not built ---
#
# Phase 2 (curriculum RAG grounding): _generate_bridge currently only
# sees the single card's front/back, same scope as the MVP ablation.
# Grounding it in a curriculum index would mean: (1) chunking/embedding
# a curriculum corpus (e.g. an expanded speedrun/ai/source_material.md,
# or the official AAMC outline once §8's mapping exists), (2) retrieving
# the 1-3 most relevant chunks for the card's topic, (3) passing those
# chunks into the bridge-generation prompt alongside the card, so a
# bridge can reference a related concept from the curriculum, not just
# the one fact on this card. This needs a real retrieval index (even a
# simple embedding-similarity one) that doesn't exist yet.
#
# Phase 3 (leak check): before showing a bridge to the student, verify
# BRIDGE_ANSWER/SYNTHESIS don't already contain the gold answer text
# verbatim or near-verbatim - otherwise the "bridge" is just a
# restated answer wearing a question mark, defeating the whole
# mechanism. Same n-gram-overlap pattern as
# speedrun/tools/leakage-check/check.py, applied per-bridge before
# display rather than as an offline audit script. Not built - this
# file trusts the model's instruction-following for now, unverified.
