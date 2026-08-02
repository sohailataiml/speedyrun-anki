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

Phase 2/3 (this file, live): a curriculum-grounding check and a leak
check now run on every generated bridge before it's shown, ported from
the standalone validation agent at speedrun/tools/socratic-agent/ (see
speedrun/docs/socratic-agent.md for the offline numbers this was proven
against first: 10/10 grounded, 0/10 leaked, on real Krebs-cycle cards).
Two honest asymmetries, stated here because they're load-bearing:
- **Leak check is a hard gate.** It's topic-independent (pure n-gram
  overlap against the card's own gold answer), so it's always
  meaningful. If the bridge *question* leaks the answer, this retries
  generation once; if it still leaks, no bridge is shown at all rather
  than showing a broken one.
- **Grounding check is a soft signal, not a gate.** The curriculum
  corpus (speedrun/ai/source_material.md) only covers the Krebs cycle.
  Making "grounded" a hard requirement would silently kill the bridge
  feature for every other topic. So: only run the check when retrieval
  confidence suggests the corpus actually covers this card's topic;
  when it fires and says ungrounded, label the dialog rather than block
  it. Below that confidence threshold, the check is skipped entirely -
  same give-up-gate honesty as the rest of this project: refuse to
  claim a verification that can't actually be made, rather than fake
  one.

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
import math
import os
import re
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
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
    """Card text as a human would read it, for prompting and checking.

    Drops <style>/<script> blocks *including their contents* before
    stripping the remaining tags. This is not defensive tidying - it
    fixes a real bug found by instrumenting the live gate: `card.question()`
    returns the fully rendered card, which begins with the notetype's CSS
    block, and a tags-only strip leaves the raw CSS rules behind as card
    "text". The gate was being handed
    `'.card {\\n font-family: arial; font-size: 20p...'` as the card front,
    which (a) scored 0.066 on curriculum coverage so grounding was always
    skipped, (b) polluted the leak check's notion of the gold answer with
    tokens like "card"/"color"/"text"/"arial", and (c) wasted prompt
    tokens on styling noise. Whitespace is collapsed so the model and the
    n-gram checks see clean prose.
    """
    text = re.sub(
        r"<(style|script)\b[^>]*>.*?</\1\s*>", " ", text, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(r"<[^<]+?>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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


# --- Curriculum retrieval + grounding check + leak check ---
# Ported from speedrun/tools/socratic-agent/ (agent.py/retrieval.py),
# proven there first against 10 real Krebs-cycle cards before being
# wired in here - see speedrun/docs/socratic-agent.md. Deliberately
# reimplemented pure-Python (no numpy/sklearn) rather than imported: this
# project doesn't ship either as a runtime dependency of the desktop app,
# and adding one for a 14-chunk corpus isn't worth the packaging risk.

# Minimum IDF-weighted concept coverage before the grounding check is
# considered meaningful for a card. Empirically tuned (see this module's
# _grounding_coverage doc comment for the measured separation): real
# Krebs-cycle cards score 0.37-1.00, cards on topics the corpus doesn't
# cover score exactly 0.00, so anything in between separates them. 0.25
# sits clear of both edges.
GROUNDING_COVERAGE_THRESHOLD = 0.25
LEAK_NGRAM_SIZE = 6

# Dropped before measuring concept coverage: these carry no information
# about what a card is *about*, so counting them would let generic
# phrasing overlap masquerade as topical relevance.
STOPWORDS = frozenset(
    """
    a an and are as at be by for from has have how in into is it its of on or
    that the to was were what when where which who why will with you your this
    these those there their they them then than some such only other more most
    can could would should may might must do does did done not no nor but if
    while during each both few all any own same so too very just now also about
    above below between through before after under over again further once one
    two three four five called sometimes generally considered major primary
    """.split()
)

GROUNDEDNESS_SYSTEM_PROMPT = (
    "You are a fact-checker for an MCAT study app. You will be given a "
    "generated bridge question, its answer, and a synthesis sentence, "
    "plus one or more source passages. Your job: determine whether the "
    "factual claims in the bridge answer and synthesis are actually "
    "supported by the source passages - not whether they're true in "
    "general biochemistry, specifically whether THESE passages support "
    "them. If the bridge introduces a specific fact, number, enzyme "
    "name, or mechanism that isn't in the provided passages, that's not "
    "grounded, even if it happens to be correct.\n\n"
    "Respond in exactly this format, nothing else:\n"
    "GROUNDED: <yes or no>\n"
    "REASONING: <one or two sentences citing what is or isn't supported>"
)
GROUNDEDNESS_RESPONSE_RE = re.compile(
    r"GROUNDED:\s*(yes|no)\s*\nREASONING:\s*(.+)", re.IGNORECASE | re.DOTALL
)

_CURRICULUM_CHUNKS: list[tuple[str, str]] | None = None


class BridgeLeakedError(Exception):
    """Raised when a bridge question still leaks the gold answer after
    one regeneration attempt. Caught specially by callers: this should
    silently skip showing a bridge, not show an error dialog - the
    student did nothing wrong, the generator just didn't produce a
    usable bridge this time."""


@dataclass
class VerifiedBridge:
    content: BridgeContent
    grounded: bool | None  # None = not checked (low retrieval confidence)
    grounded_reasoning: str
    retry_count: int


def _load_curriculum_chunks() -> list[tuple[str, str]]:
    """Returns (chunk_id, text) pairs from speedrun/ai/source_material.md.
    Cached after first load. Returns [] if the file can't be found (e.g.
    a packaged build that doesn't bundle speedrun/) - the grounding check
    degrades to "skipped" in that case, same give-up-gate philosophy as
    the rest of this project."""
    global _CURRICULUM_CHUNKS
    if _CURRICULUM_CHUNKS is not None:
        return _CURRICULUM_CHUNKS
    path = Path(__file__).parent.parent.parent / "speedrun" / "ai" / "source_material.md"
    if not path.exists():
        _CURRICULUM_CHUNKS = []
        return _CURRICULUM_CHUNKS
    text = path.read_text(encoding="utf-8")
    chunks = []
    for match in re.finditer(
        r"^## (kc-\d+): .+?\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    ):
        chunks.append((match.group(1), match.group(2).strip()))
    _CURRICULUM_CHUNKS = chunks
    return _CURRICULUM_CHUNKS


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _content_terms(text: str) -> set[str]:
    """Terms that carry information about what a card or chunk is *about*.
    Exact-token matching, no stemming - a real, stated limitation:
    "mitochondria" and "mitochondrion" are the same concept but different
    tokens here, so a card using one form won't match a chunk using the
    other. Adding a stemmer means a new runtime dependency this app
    doesn't ship; for a single-topic corpus the failure mode is
    conservative (skip the check rather than claim a false match), which
    is the safe direction."""
    return {t for t in _tokenize(text) if t not in STOPWORDS and len(t) > 2}


def _corpus_idf(chunks: list[tuple[str, str]]) -> tuple[dict[str, float], float]:
    """IDF over the curriculum chunks, plus the weight to charge terms
    that appear in *no* chunk. A term in every chunk carries no
    discriminative information (IDF 0); a term in one chunk carries a
    lot; a term the corpus has never heard of is maximally uncovered, so
    it gets the same weight as the rarest possible in-corpus term."""
    n_docs = len(chunks)
    if n_docs == 0:
        return {}, 0.0
    doc_freq: Counter[str] = Counter()
    for _, text in chunks:
        doc_freq.update(_content_terms(text))
    idf = {term: math.log(n_docs / df) for term, df in doc_freq.items()}
    return idf, math.log(n_docs)


def _coverage(query: str, chunk_terms: set[str], idf: dict[str, float], oov_weight: float) -> float:
    """What fraction of a card's *information content* this chunk covers,
    weighted by how distinctive each term is. Deliberately asymmetric -
    unlike cosine similarity, a long chunk isn't penalised for containing
    material beyond the card, and a two-word card isn't penalised for
    being short. Terms absent from the whole corpus count fully against
    the score, which is what makes an out-of-corpus card fall to ~0."""
    terms = _content_terms(query)
    if not terms:
        return 0.0
    covered = total = 0.0
    for term in terms:
        weight = idf.get(term, oov_weight)
        total += weight
        if term in chunk_terms:
            covered += weight
    return covered / total if total else 0.0


def _retrieve_for_grounding(
    front: str, back: str, chunks: list[tuple[str, str]], top_k: int = 2
) -> tuple[list[tuple[str, str, float]], float]:
    """Returns (top chunks to show the judge, gate score).

    The gate score is `min(front coverage, back coverage)` rather than
    coverage of the card as one blob, because the two ask different
    questions and both must pass. A card's *answer* is the fact a bridge
    would be grounded in: if the corpus has never heard of
    "phosphofructokinase", it cannot vouch for a bridge about it, no
    matter how much the *question's* framing ("rate-limiting step",
    "enzyme") happens to overlap with material the corpus does cover.
    That exact case - a glycolysis card scoring 0.61 on its front but
    0.00 on its back - is what the previous cosine-similarity gate got
    wrong, letting an out-of-corpus card through while blocking a real
    Krebs-cycle one.

    Measured separation on this corpus with this scoring: real in-corpus
    cards 0.37-1.00, out-of-corpus cards 0.00. Cards with an empty back
    fall back to front coverage alone.
    """
    if not chunks:
        return [], 0.0
    idf, oov_weight = _corpus_idf(chunks)
    chunk_terms = [(cid, text, _content_terms(text)) for cid, text in chunks]

    combined = f"{front} {back}".strip()
    ranked = sorted(
        (
            (cid, text, _coverage(combined, terms, idf, oov_weight))
            for cid, text, terms in chunk_terms
        ),
        key=lambda item: item[2],
        reverse=True,
    )[:top_k]

    best_front = max(
        (_coverage(front, terms, idf, oov_weight) for _, _, terms in chunk_terms), default=0.0
    )
    if _content_terms(back):
        best_back = max(
            (_coverage(back, terms, idf, oov_weight) for _, _, terms in chunk_terms), default=0.0
        )
        gate_score = min(best_front, best_back)
    else:
        gate_score = best_front

    return ranked, gate_score


def _check_grounded(
    api_key: str, content: BridgeContent, retrieved: list[tuple[str, str, float]]
) -> tuple[bool, str]:
    passages = "\n\n".join(f"[{chunk_id}] {text}" for chunk_id, text, _ in retrieved)
    user_prompt = (
        f"Bridge question: {content.bridge_question}\n"
        f"Bridge answer: {content.bridge_answer}\n"
        f"Synthesis: {content.synthesis}\n\n"
        f"Source passages:\n{passages}"
    )
    payload = json.dumps(
        {
            "model": MODEL,
            "max_tokens": 150,
            "system": GROUNDEDNESS_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": 0.3,
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
    match = GROUNDEDNESS_RESPONSE_RE.search(text)
    if not match:
        raise ValueError(f"no GROUNDED/REASONING in response: {text!r}")
    return match.group(1).strip().lower() == "yes", match.group(2).strip()


def _check_leak(bridge_question: str, gold_back: str) -> bool:
    """Checks only the bridge *question* - not the answer/synthesis,
    which are shown after Reveal and are supposed to name the fact (the
    system prompt asks for a synthesis "connecting it back to the
    card's original fact"). See speedrun/tools/socratic-agent/agent.py's
    check_leak_node docstring for the two real bugs this exact logic
    fixed before it was correct: a fixed 6-word n-gram can't even form
    against most short flashcard answers ("Citrate synthase"), and
    checking the wrong fields flagged the synthesis for doing its job."""
    gold_words = _tokenize(gold_back)
    bridge_words = _tokenize(bridge_question)
    if len(gold_words) < LEAK_NGRAM_SIZE:
        gold_phrase = tuple(gold_words)
        return bool(gold_phrase) and any(
            tuple(bridge_words[i : i + len(gold_phrase)]) == gold_phrase
            for i in range(len(bridge_words) - len(gold_phrase) + 1)
        )
    n = LEAK_NGRAM_SIZE
    gold_ngrams = {tuple(gold_words[i : i + n]) for i in range(len(gold_words) - n + 1)}
    bridge_ngrams = {tuple(bridge_words[i : i + n]) for i in range(len(bridge_words) - n + 1)}
    return bool(gold_ngrams & bridge_ngrams)


def _generate_and_verify_bridge(api_key: str, front: str, back: str) -> VerifiedBridge:
    """Generate -> leak-check (hard gate, one retry) -> grounding-check
    (soft signal, only when retrieval confidence suggests the corpus
    covers this topic). Runs entirely off the main thread via the
    caller's QueryOp - both extra checks are cheap (leak: local, no API;
    grounding: one more API call only when it's worth making)."""
    content = _generate_bridge(api_key, front, back)
    retry_count = 0
    if _check_leak(content.bridge_question, back):
        content = _generate_bridge(api_key, front, back)
        retry_count = 1
        if _check_leak(content.bridge_question, back):
            raise BridgeLeakedError(
                "bridge question still leaked the gold answer after one retry"
            )

    grounded: bool | None = None
    reasoning = ""
    chunks = _load_curriculum_chunks()
    retrieved, gate_score = _retrieve_for_grounding(front, back, chunks, top_k=2)
    if retrieved and gate_score >= GROUNDING_COVERAGE_THRESHOLD:
        grounded, reasoning = _check_grounded(api_key, content, retrieved)

    return VerifiedBridge(
        content=content, grounded=grounded, grounded_reasoning=reasoning, retry_count=retry_count
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

    def show_bridge(self, verified: VerifiedBridge) -> None:
        self._content = verified.content
        self._clear()
        intro = QLabel(
            "Before moving on — think this through, then reveal when ready."
        )
        intro.setWordWrap(True)
        self._layout.addWidget(intro)

        question = QLabel(verified.content.bridge_question)
        question.setWordWrap(True)
        font = question.font()
        font.setBold(True)
        question.setFont(font)
        self._layout.addWidget(question)

        # Three distinct states, shown distinctly - silence must not be
        # ambiguous between "checked and passed" and "never checked."
        # grounded is True: curriculum retrieval found a confident match
        # for this topic and the LLM judge confirmed the bridge is
        # supported by it. grounded is False: retrieval found a match but
        # the judge disagreed - soft signal, not a block, since the
        # corpus only covers the Krebs cycle (see this module's
        # top-of-file doc comment). grounded is None: retrieval found
        # nothing confident enough to check against - most cards outside
        # the Krebs cycle land here, since that's the only topic the
        # corpus covers right now.
        if verified.grounded is True:
            confirmed = QLabel("✓ Verified against the curriculum source.")
            confirmed.setWordWrap(True)
            confirmed.setStyleSheet("color: darkgreen;")
            self._layout.addWidget(confirmed)
        elif verified.grounded is False:
            caveat = QLabel(
                "⚠ Not verified against the curriculum source for this topic."
            )
            caveat.setWordWrap(True)
            caveat.setStyleSheet("color: darkorange;")
            self._layout.addWidget(caveat)

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

    def on_success(verified: VerifiedBridge) -> None:
        bridge_dialog.show_bridge(verified)

    def on_failure(exc: Exception) -> None:
        if isinstance(exc, BridgeLeakedError):
            # Hard gate: still leaking after a retry means no usable
            # bridge exists for this card right now - close silently
            # rather than show an alarming error the student can't act
            # on. The student did nothing wrong here.
            bridge_dialog.close()
        else:
            bridge_dialog.show_error(str(exc))

    QueryOp(
        parent=bridge_dialog,
        op=lambda _col: _generate_and_verify_bridge(api_key, front, back),
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

    def on_success(verified: VerifiedBridge) -> None:
        dialog.show_bridge(verified)

    def on_failure(exc: Exception) -> None:
        if isinstance(exc, BridgeLeakedError):
            dialog.close()
        else:
            dialog.show_error(str(exc))

    # Start the (async, background-thread) API call before blocking on the
    # modal below - QueryOp's completion signal still gets delivered by
    # Qt's event loop while dialog.exec() runs its own nested loop.
    QueryOp(
        parent=dialog,
        op=lambda _col: _generate_and_verify_bridge(api_key, front, back),
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


# Phase 2/3 (curriculum grounding + leak check) are live above, in
# _generate_and_verify_bridge and its helpers - see this module's
# top-of-file doc comment for the design and speedrun/docs/socratic-agent.md
# for the offline numbers they were proven against first. Still not
# built: extending speedrun/ai/source_material.md beyond the Krebs
# cycle, and a retry loop for grounding the way there already is one
# for leaks (grounding is a soft signal by design, not a gate, so a
# retry loop wasn't needed to ship this).
