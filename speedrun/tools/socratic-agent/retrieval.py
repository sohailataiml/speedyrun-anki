"""Curriculum retrieval + a gate deciding whether grounding can be
meaningfully checked at all. No vector DB, no embeddings API, no
persisted index - and, as of this version, no sklearn either.

**Why this is not cosine similarity any more.** The first version of this
module used sklearn's TfidfVectorizer + cosine similarity. Wiring the
same idea into the live desktop app and instrumenting it exposed that
cosine measures the wrong thing for flashcards: it rewards generic
vocabulary overlap and penalises short queries against long chunks. On
the real card set it ranked an out-of-corpus ribosome card (0.27) ABOVE
a genuine citric-acid-cycle card (0.14) - backwards, and enough to have
produced a misleading "verified" badge. See
speedrun/docs/socratic-gate-mvp.md for the full write-up.

What replaced it: IDF-weighted *concept coverage*. For a given chunk,
what fraction of the card's information content does it actually cover,
weighting each term by how distinctive that term is within the corpus?
Deliberately asymmetric - a long chunk isn't penalised for containing
material beyond the card, and a two-word card isn't penalised for being
short. Terms the corpus has never seen count fully against the score,
which is what drives out-of-corpus cards to ~0.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from corpus import Chunk

# Real in-corpus cards score 0.37-1.00 with this scoring; cards on topics
# the corpus doesn't cover score exactly 0.00. 0.25 sits clear of both.
GROUNDING_COVERAGE_THRESHOLD = 0.25

# Dropped before measuring coverage: these say nothing about what a card
# is *about*, so counting them would let generic phrasing masquerade as
# topical relevance.
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


@dataclass
class RetrievalResult:
    chunk: Chunk
    score: float


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def content_terms(text: str) -> set[str]:
    """Terms carrying information about what a card or chunk is about.
    Exact-token matching, no stemming - a stated limitation:
    "mitochondria" and "mitochondrion" are one concept but two tokens, so
    a card using one form won't match a chunk using the other. The
    failure mode is conservative (skip the check rather than claim a
    false match), which is the safe direction."""
    return {t for t in tokenize(text) if t not in STOPWORDS and len(t) > 2}


def corpus_idf(chunks: list[Chunk]) -> tuple[dict[str, float], float]:
    """IDF over the chunks, plus the weight charged to terms appearing in
    no chunk at all. A term in every chunk carries no discriminative
    information (IDF 0); a term in one chunk carries a lot; a term the
    corpus has never heard of is maximally uncovered, so it's charged the
    same weight as the rarest possible in-corpus term."""
    n_docs = len(chunks)
    if n_docs == 0:
        return {}, 0.0
    doc_freq: Counter[str] = Counter()
    for chunk in chunks:
        doc_freq.update(content_terms(chunk.text))
    idf = {term: math.log(n_docs / df) for term, df in doc_freq.items()}
    return idf, math.log(n_docs)


def coverage(
    query: str, chunk_terms: set[str], idf: dict[str, float], oov_weight: float
) -> float:
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
    front: str, back: str, chunks: list[Chunk], top_k: int = 2
) -> tuple[list[RetrievalResult], float]:
    """Returns (top chunks to show the judge, gate score).

    The gate score is `min(front coverage, back coverage)` rather than
    coverage of the card as one blob, because both must hold. A card's
    *answer* is the fact a bridge would be grounded in: if the corpus has
    never heard of "phosphofructokinase" it cannot vouch for a bridge
    about it, no matter how much the *question's* framing ("rate-limiting
    step", "enzyme") overlaps material the corpus does cover. That exact
    case - a glycolysis card scoring 0.61 on its front and 0.00 on its
    back - is what the old cosine gate got wrong. Cards with an empty
    back fall back to front coverage alone.
    """
    if not chunks:
        return [], 0.0
    idf, oov_weight = corpus_idf(chunks)
    prepared = [(chunk, content_terms(chunk.text)) for chunk in chunks]

    combined = f"{front} {back}".strip()
    ranked = sorted(
        (
            RetrievalResult(chunk=chunk, score=coverage(combined, terms, idf, oov_weight))
            for chunk, terms in prepared
        ),
        key=lambda r: r.score,
        reverse=True,
    )[:top_k]

    best_front = max((coverage(front, t, idf, oov_weight) for _, t in prepared), default=0.0)
    if content_terms(back):
        best_back = max((coverage(back, t, idf, oov_weight) for _, t in prepared), default=0.0)
        gate_score = min(best_front, best_back)
    else:
        gate_score = best_front

    return ranked, gate_score
