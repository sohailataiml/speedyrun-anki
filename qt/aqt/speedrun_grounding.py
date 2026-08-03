# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Speedrun addition: curriculum grounding and answer-leak checking.

Extracted from the retired Socratic gate (Brainlift v2) because the checks
themselves outlived the feature that motivated them. Under the v3
Latency-Volatility thesis the AI is a *proctor*, not a tutor: it generates
context-shifted "jitter" variants of a card to test far transfer instead of
generating hints. But a jitter variant has the same two ways of being
worthless, and they need the same two checks:

- **Grounding** - does the generated text stay inside the curriculum, or
  has the model invented an enzyme, a number, or a mechanism?
- **Leakage** - does the generated text hand over the very answer the card
  is supposed to elicit?

So this module is deliberately free of any notion of bridges, hints, or
gating. It takes strings and returns verdicts. See
speedrun/docs/pivot-plan-latency-volatility.md Phase 1 for why these
survived the cut.

The retrieval here is IDF-weighted concept *coverage*, not cosine
similarity, and that difference was load-bearing - see
`retrieve_for_grounding` for the specific failure that forced the change.
"""

from __future__ import annotations

import json
import math
import re
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"

# Below this coverage score the corpus is judged unable to speak to the
# card at all, and the grounding check is *skipped* rather than failed.
#
# 0.25 was chosen against a 9-chunk, Krebs-only corpus where in-corpus
# cards scored 0.37-1.00 and out-of-corpus cards scored exactly 0.00 -
# a wide, comfortable gap.
#
# THAT GAP HAS SINCE NARROWED, and the threshold has not been re-tuned.
# The corpus is now 54 chunks across six topics, so a card the corpus
# genuinely doesn't cover can still pick up partial credit from shared
# vocabulary: an out-of-corpus ribosome/SRP card now scores 0.216, only
# 0.034 below the line, because the central-dogma material added later
# talks about ribosomes in another context. A real in-corpus water card
# scores 0.298. The ordering is still correct, but the margin is thin
# enough that adding more source documents could plausibly push a
# not-really-covered card over the line.
#
# Left as-is for now rather than nudged, because moving a threshold to
# fix one hand-picked example without re-measuring the whole set is how
# thresholds stop meaning anything. Re-measuring against the full card
# set is the honest fix; see Phase 5 in
# speedrun/docs/pivot-plan-latency-volatility.md, which is where this
# check next gets real use.
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
    "You are a fact-checker for an MCAT study app. You will be given "
    "generated study material and one or more source passages. Your job: "
    "determine whether the factual claims in the generated material are "
    "actually supported by the source passages - not whether they're true "
    "in general science, specifically whether THESE passages support "
    "them. If the generated material introduces a specific fact, number, "
    "enzyme name, or mechanism that isn't in the provided passages, "
    "that's not grounded, even if it happens to be correct.\n\n"
    "Respond in exactly this format, nothing else:\n"
    "GROUNDED: <yes or no>\n"
    "REASONING: <one or two sentences citing what is or isn't supported>"
)
GROUNDEDNESS_RESPONSE_RE = re.compile(
    r"GROUNDED:\s*(yes|no)\s*\nREASONING:\s*(.+)", re.IGNORECASE | re.DOTALL
)

_CURRICULUM_CHUNKS: list[tuple[str, str]] | None = None


@dataclass
class GroundingVerdict:
    """`grounded` is deliberately tri-state. None means the check did not
    run because the corpus can't speak to this topic, which is a different
    statement from "checked and failed" and must not be rendered as one."""

    grounded: bool | None
    reasoning: str
    gate_score: float
    passages: list[tuple[str, str, float]]


def strip_html(text: str) -> str:
    """Card text as a human would read it, for prompting and checking.

    Drops <style>/<script> blocks *including their contents* before
    stripping the remaining tags. This is not defensive tidying - it
    fixes a real bug found by instrumenting the live gate: `card.question()`
    returns the fully rendered card, which begins with the notetype's CSS
    block, and a tags-only strip leaves the raw CSS rules behind as card
    "text". The checker was being handed
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


def load_curriculum_chunks() -> list[tuple[str, str]]:
    """Returns (chunk_id, text) pairs for *every* curriculum source
    document listed in speedrun/ai/sources.json.

    Driving this off the manifest rather than a hardcoded filename is what
    keeps the grounding corpus and the coverage map honest about the same
    set of content. When only source_material.md was loaded, every
    chem/phys card retrieved nothing and grounding silently reported "not
    checked" - the check wasn't wrong, it just had no material to check
    against, which is indistinguishable from a passing card unless you
    look. Adding a source doc to the manifest now extends retrieval
    automatically.

    Cached after first load. Returns [] if the manifest can't be found
    (e.g. a packaged build that doesn't bundle speedrun/) - grounding
    degrades to "skipped", same give-up-gate philosophy as the rest of
    this project.
    """
    global _CURRICULUM_CHUNKS
    if _CURRICULUM_CHUNKS is not None:
        return _CURRICULUM_CHUNKS
    ai_dir = Path(__file__).parent.parent.parent / "speedrun" / "ai"
    manifest = ai_dir / "sources.json"
    if not manifest.exists():
        _CURRICULUM_CHUNKS = []
        return _CURRICULUM_CHUNKS
    try:
        sources = json.loads(manifest.read_text(encoding="utf-8"))["sources"]
    except (ValueError, KeyError):
        _CURRICULUM_CHUNKS = []
        return _CURRICULUM_CHUNKS

    chunks: list[tuple[str, str]] = []
    for source in sources:
        path = ai_dir / source["file"]
        if not path.exists():
            continue
        prefix = re.escape(source["chunk_prefix"])
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(
            rf"^## ({prefix}-\d+): .+?\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
        ):
            chunks.append((match.group(1), match.group(2).strip()))
    _CURRICULUM_CHUNKS = chunks
    return _CURRICULUM_CHUNKS


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def content_terms(text: str) -> set[str]:
    """Terms that carry information about what a card or chunk is *about*.
    Exact-token matching, no stemming - a real, stated limitation:
    "mitochondria" and "mitochondrion" are the same concept but different
    tokens here, so a card using one form won't match a chunk using the
    other. Adding a stemmer means a new runtime dependency this app
    doesn't ship; the failure mode is conservative (skip the check rather
    than claim a false match), which is the safe direction."""
    return {t for t in tokenize(text) if t not in STOPWORDS and len(t) > 2}


def corpus_idf(chunks: list[tuple[str, str]]) -> tuple[dict[str, float], float]:
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
        doc_freq.update(content_terms(text))
    idf = {term: math.log(n_docs / df) for term, df in doc_freq.items()}
    return idf, math.log(n_docs)


def coverage(query: str, chunk_terms: set[str], idf: dict[str, float], oov_weight: float) -> float:
    """What fraction of a card's *information content* this chunk covers,
    weighted by how distinctive each term is. Deliberately asymmetric -
    unlike cosine similarity, a long chunk isn't penalised for containing
    material beyond the card, and a two-word card isn't penalised for
    being short. Terms absent from the whole corpus count fully against
    the score, which is what makes an out-of-corpus card fall to ~0."""
    terms = content_terms(query)
    if not terms:
        return 0.0
    covered = total = 0.0
    for term in terms:
        weight = idf.get(term, oov_weight)
        total += weight
        if term in chunk_terms:
            covered += weight
    return covered / total if total else 0.0


def retrieve_for_grounding(
    front: str, back: str, chunks: list[tuple[str, str]], top_k: int = 2
) -> tuple[list[tuple[str, str, float]], float]:
    """Returns (top chunks to show the judge, gate score).

    The gate score is `min(front coverage, back coverage)` rather than
    coverage of the card as one blob, because the two ask different
    questions and both must pass. A card's *answer* is the fact generated
    material would be grounded in: if the corpus has never heard of
    "phosphofructokinase", it cannot vouch for anything written about it,
    no matter how much the *question's* framing ("rate-limiting step",
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
    idf, oov_weight = corpus_idf(chunks)
    chunk_terms = [(cid, text, content_terms(text)) for cid, text in chunks]

    combined = f"{front} {back}".strip()
    ranked = sorted(
        (
            (cid, text, coverage(combined, terms, idf, oov_weight))
            for cid, text, terms in chunk_terms
        ),
        key=lambda item: item[2],
        reverse=True,
    )[:top_k]

    best_front = max(
        (coverage(front, terms, idf, oov_weight) for _, _, terms in chunk_terms), default=0.0
    )
    if content_terms(back):
        best_back = max(
            (coverage(back, terms, idf, oov_weight) for _, _, terms in chunk_terms), default=0.0
        )
        gate_score = min(best_front, best_back)
    else:
        gate_score = best_front

    return ranked, gate_score


def check_grounded(
    api_key: str, generated_text: str, retrieved: list[tuple[str, str, float]]
) -> tuple[bool, str]:
    """LLM-as-judge: are the claims in `generated_text` supported by the
    retrieved passages? Callers pass whatever they generated as one
    string - this module has no opinion about its shape."""
    passages = "\n\n".join(f"[{chunk_id}] {text}" for chunk_id, text, _ in retrieved)
    user_prompt = f"Generated material:\n{generated_text}\n\nSource passages:\n{passages}"
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


def verify_grounding(api_key: str, front: str, back: str, generated_text: str) -> GroundingVerdict:
    """Retrieve, gate, then judge. Returns a tri-state verdict: the check
    is *skipped* (grounded=None) when the corpus can't speak to the card's
    topic, rather than being reported as a failure."""
    chunks = load_curriculum_chunks()
    passages, gate_score = retrieve_for_grounding(front, back, chunks)
    if not passages or gate_score < GROUNDING_COVERAGE_THRESHOLD:
        return GroundingVerdict(None, "", gate_score, passages)
    grounded, reasoning = check_grounded(api_key, generated_text, passages)
    return GroundingVerdict(grounded, reasoning, gate_score, passages)


def leaks_answer(generated_text: str, gold_back: str) -> bool:
    """True when `generated_text` hands over the card's own answer.

    Two real bugs shaped this, both caught by adversarial testing rather
    than by review: (1) a fixed 6-word n-gram cannot even *form* against
    most short flashcard answers ("Citrate synthase"), so short golds need
    a whole-phrase containment check instead; (2) checking too many fields
    flagged text that was correctly doing its job. Callers should pass
    only the part of their output that must not give the game away.
    """
    gold_words = tokenize(gold_back)
    text_words = tokenize(generated_text)
    if len(gold_words) < LEAK_NGRAM_SIZE:
        gold_phrase = tuple(gold_words)
        return bool(gold_phrase) and any(
            tuple(text_words[i : i + len(gold_phrase)]) == gold_phrase
            for i in range(len(text_words) - len(gold_phrase) + 1)
        )
    n = LEAK_NGRAM_SIZE
    gold_ngrams = {tuple(gold_words[i : i + n]) for i in range(len(gold_words) - n + 1)}
    text_ngrams = {tuple(text_words[i : i + n]) for i in range(len(text_words) - n + 1)}
    return bool(gold_ngrams & text_ngrams)
