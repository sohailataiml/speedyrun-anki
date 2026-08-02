"""TF-IDF retrieval over the source_material.md chunks - no vector DB,
no embeddings API, no persistent index. sklearn's TfidfVectorizer +
cosine similarity, computed fresh in-memory on every run. For a 14-chunk,
single-document corpus this is the right amount of machinery: a vector
DB would be solving a scale problem this corpus doesn't have.
"""

from __future__ import annotations

from dataclasses import dataclass

from corpus import Chunk
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class RetrievalResult:
    chunk: Chunk
    score: float


def retrieve(query: str, chunks: list[Chunk], top_k: int = 2) -> list[RetrievalResult]:
    """Returns the top_k chunks most lexically similar to `query`, ranked
    by TF-IDF cosine similarity. `query` is typically a card's front+back
    text; chunk text is the corpus documents. Fit fresh on this call's
    corpus + query together (no persisted vocabulary) - the whole point
    of avoiding a vector DB is that there's nothing to keep in sync."""
    documents = [c.text for c in chunks] + [query]
    vectorizer = TfidfVectorizer(stop_words="english")
    matrix = vectorizer.fit_transform(documents)
    query_vec = matrix[-1]
    chunk_vecs = matrix[:-1]
    scores = cosine_similarity(query_vec, chunk_vecs)[0]
    ranked = sorted(zip(chunks, scores), key=lambda pair: pair[1], reverse=True)
    return [RetrievalResult(chunk=c, score=float(s)) for c, s in ranked[:top_k]]
