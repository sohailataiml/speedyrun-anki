"""The Socratic bridge generator as a standalone agent workflow: a small
graph of nodes threading a shared state through retrieve -> generate ->
check_grounded -> check_leak, printing a trace at each step. Structured
to mirror a LangGraph-style StateGraph (named nodes, one shared state
object, an explicit edge list) without adding the langgraph dependency
itself - for a 4-node linear pipeline like this, hand-rolling the same
shape is simpler to read, debug, and defend than a framework wrapping
one function call. Swapping in real langgraph later is a mechanical
change: each node function below already has the (state) -> state
signature LangGraph nodes use.

This does NOT replace the live `_generate_bridge`/`generateBridge` wired
into the desktop and Android apps (qt/aqt/speedrun_socratic_gate.py,
SocraticGate.kt) - it's a standalone validation harness answering a
question those don't: is the bridge Claude generates actually grounded
in a real, named, retrievable curriculum source, and does it leak the
gold answer's exact wording? See speedrun/docs/socratic-agent.md for
why this is scoped as a check, not generation-time injection, "for now."
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass, field

from cards import TestCard
from corpus import Chunk, load_chunks
from retrieval import (
    GROUNDING_COVERAGE_THRESHOLD,
    RetrievalResult,
    retrieve_for_grounding,
)

MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"
NGRAM_SIZE = 6

# Same prompt as qt/aqt/speedrun_socratic_gate.py's BRIDGE_SYSTEM_PROMPT
# and speedrun/tools/socratic-gate/generate_bridges.py's (minus that
# tool's counterfactual-terminology instruction - these are real cards).
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
BRIDGE_RESPONSE_RE = re.compile(
    r"BRIDGE_QUESTION:\s*(.+?)\s*\nBRIDGE_ANSWER:\s*(.+?)\s*\nSYNTHESIS:\s*(.+)",
    re.DOTALL,
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


@dataclass
class BridgeContent:
    bridge_question: str
    bridge_answer: str
    synthesis: str


@dataclass
class GroundednessResult:
    grounded: bool
    reasoning: str


@dataclass
class LeakResult:
    leaked: bool
    leaked_phrases: list[str]


@dataclass
class AgentState:
    card: TestCard
    retrieved: list[RetrievalResult] = field(default_factory=list)
    gate_score: float = 0.0
    bridge: BridgeContent | None = None
    # None means the grounding check deliberately did not run: retrieval
    # said the corpus doesn't cover this card's topic well enough for a
    # verdict to mean anything. Distinct from a False verdict.
    grounded: GroundednessResult | None = None
    leak: LeakResult | None = None
    trace: list[str] = field(default_factory=list)


def _call_claude(api_key: str, system_prompt: str, user_prompt: str, max_tokens: int = 300) -> str:
    payload = json.dumps(
        {
            "model": MODEL,
            "max_tokens": max_tokens,
            "system": system_prompt,
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
    with urllib.request.urlopen(request, timeout=60) as response:
        body = json.loads(response.read())
    return body["content"][0]["text"].strip()


# --- Nodes. Each takes (state, api_key) and returns the updated state, ---
# --- matching a LangGraph node's (state) -> state signature.           ---


def retrieve_node(state: AgentState, chunks: list[Chunk], **_) -> AgentState:
    state.retrieved, state.gate_score = retrieve_for_grounding(
        state.card.front, state.card.back, chunks, top_k=2
    )
    covers = state.gate_score >= GROUNDING_COVERAGE_THRESHOLD
    state.trace.append(
        f"retrieve: gate={state.gate_score:.3f} "
        f"({'corpus covers this topic' if covers else 'corpus does NOT cover this topic'}) "
        "top chunks = "
        + ", ".join(f"{r.chunk.chunk_id} ({r.score:.3f})" for r in state.retrieved)
    )
    return state


def generate_node(state: AgentState, api_key: str, **_) -> AgentState:
    user_prompt = f"Card front: {state.card.front}\nCard back: {state.card.back}"
    text = _call_claude(api_key, BRIDGE_SYSTEM_PROMPT, user_prompt)
    match = BRIDGE_RESPONSE_RE.search(text)
    if not match:
        raise ValueError(f"no BRIDGE_QUESTION/ANSWER/SYNTHESIS in response: {text!r}")
    state.bridge = BridgeContent(
        bridge_question=match.group(1).strip(),
        bridge_answer=match.group(2).strip(),
        synthesis=match.group(3).strip(),
    )
    state.trace.append(f"generate: {state.bridge.bridge_question!r}")
    return state


def check_grounded_node(state: AgentState, api_key: str, **_) -> AgentState:
    assert state.bridge is not None
    if not state.retrieved or state.gate_score < GROUNDING_COVERAGE_THRESHOLD:
        # Refuse to render a verdict the corpus can't support. Leaving
        # `grounded` as None is the honest outcome - same give-up-gate
        # discipline as give_up_gate.rs declining to emit a readiness
        # score without enough data.
        state.trace.append("check_grounded: skipped - corpus doesn't cover this topic")
        return state
    passages = "\n\n".join(f"[{r.chunk.chunk_id}] {r.chunk.text}" for r in state.retrieved)
    user_prompt = (
        f"Bridge question: {state.bridge.bridge_question}\n"
        f"Bridge answer: {state.bridge.bridge_answer}\n"
        f"Synthesis: {state.bridge.synthesis}\n\n"
        f"Source passages:\n{passages}"
    )
    text = _call_claude(api_key, GROUNDEDNESS_SYSTEM_PROMPT, user_prompt, max_tokens=150)
    match = GROUNDEDNESS_RESPONSE_RE.search(text)
    if not match:
        raise ValueError(f"no GROUNDED/REASONING in response: {text!r}")
    state.grounded = GroundednessResult(
        grounded=match.group(1).strip().lower() == "yes",
        reasoning=match.group(2).strip(),
    )
    state.trace.append(f"check_grounded: {state.grounded.grounded} - {state.grounded.reasoning}")
    return state


def _normalize_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _ngrams(text: str, n: int = NGRAM_SIZE) -> set[tuple]:
    words = _normalize_words(text)
    if len(words) < n:
        return set()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def check_leak_node(state: AgentState, **_) -> AgentState:
    """Checks only `bridge_question` for the gold answer's phrasing - not
    `bridge_answer`/`synthesis`, which are shown *after* the student taps
    Reveal and are explicitly supposed to name the original fact (the
    system prompt asks for "a synthesis connecting it back to the card's
    original fact"). Flagging those would just measure the synthesis
    doing its job. The one field that must never give away the answer is
    the bridge *question*, since that's the only thing shown before the
    student has a chance to reason - a leak there is a real leak.

    This module's own adversarial test caught two real bugs while getting
    here, not written defensively up front: (1) a straight port of
    leakage-check's NGRAM_SIZE=6 silently passed every short gold answer,
    because most flashcard "back" fields (an enzyme name, a location -
    "Citrate synthase", "Mitochondria") are under 6 words, so no 6-gram
    could ever form; (2) checking bridge_answer+synthesis instead of just
    bridge_question flagged 6 of 10 real cards as "leaks" that were
    actually the synthesis correctly doing what it was asked to do -
    e.g. card 4's bridge_answer never mentions "citrate synthase" at all,
    only the synthesis does, exactly as designed. Below NGRAM_SIZE words,
    check for the whole gold phrase appearing verbatim as a contiguous
    run instead of requiring an n-gram that can't exist."""
    assert state.bridge is not None
    gold_words = _normalize_words(state.card.back)
    bridge_words = _normalize_words(state.bridge.bridge_question)

    if len(gold_words) < NGRAM_SIZE:
        gold_phrase = tuple(gold_words)
        leaked = bool(gold_phrase) and any(
            tuple(bridge_words[i : i + len(gold_phrase)]) == gold_phrase
            for i in range(len(bridge_words) - len(gold_phrase) + 1)
        )
        leaked_phrases = [" ".join(gold_phrase)] if leaked else []
    else:
        gold_ngrams = _ngrams(state.card.back)
        bridge_ngrams = _ngrams(state.bridge.bridge_question)
        overlap = gold_ngrams & bridge_ngrams
        leaked = bool(overlap)
        leaked_phrases = [" ".join(ng) for ng in overlap]

    state.leak = LeakResult(leaked=leaked, leaked_phrases=leaked_phrases)
    state.trace.append(f"check_leak: {state.leak.leaked} ({len(leaked_phrases)} phrase(s))")
    return state


# --- Orchestrator: the "graph" - an explicit, ordered node list. ---
# Linear today; a real LangGraph port would add conditional edges here
# (e.g. grounded=False -> loop back to generate_node with the failure
# reason appended to the prompt) rather than just recording the failure,
# which is the one thing this hand-rolled version doesn't do yet.
WORKFLOW = [retrieve_node, generate_node, check_grounded_node, check_leak_node]


def run_agent(card: TestCard, chunks: list[Chunk], api_key: str) -> AgentState:
    state = AgentState(card=card)
    for node in WORKFLOW:
        state = node(state, chunks=chunks, api_key=api_key)
    return state
