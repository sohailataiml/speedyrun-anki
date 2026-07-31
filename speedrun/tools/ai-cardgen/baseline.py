#!/usr/bin/env python3
"""The "simpler method" the AI generator has to beat (PRD §3/§8).

Deliberately dumb: splits the source into sentences and turns anything
matching a definitional pattern ("X is/are/was Y", "X catalyzes Y") into a
crude Q&A pair via regex, with no understanding of the text. This is the
kind of keyword/pattern-matching approach the Brainlift teardown critiques
competitor tools for leaning on - it's the honest baseline to compare
against, not a strawman built to lose.

No LLM call, no API key needed. Rerunnable and deterministic.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SOURCE_PATH = Path(__file__).parent.parent.parent / "ai" / "source_material.md"
OUTPUT_PATH = Path(__file__).parent / "output" / "baseline_cards.json"

CHUNK_HEADER_RE = re.compile(r"^## (kc-\d+): (.+)$", re.MULTILINE)

# "X is/are/was/were Y" and "X catalyzes/produces/converts Y" - covers most
# of the definitional sentences in the source material without any real
# language understanding.
DEFINITIONAL_RE = re.compile(
    r"^(?P<subject>[A-Z][\w\s\-']{2,60}?)\s+"
    r"(?P<verb>is|are|was|were|catalyzes|catalyzed by|produces|converts)\s+"
    r"(?P<predicate>.{10,150}?)\.$"
)


def load_chunks() -> list[tuple[str, str, str]]:
    """Returns (chunk_id, title, body) for each ## kc-NN section."""
    text = SOURCE_PATH.read_text(encoding="utf-8")
    headers = list(CHUNK_HEADER_RE.finditer(text))
    chunks = []
    for i, match in enumerate(headers):
        start = match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[start:end].strip()
        chunks.append((match.group(1), match.group(2), body))
    return chunks


def sentences(body: str) -> list[str]:
    # Collapse markdown line-wrapping, then split on sentence boundaries.
    flat = " ".join(line.strip() for line in body.splitlines())
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", flat) if s.strip()]


def generate_baseline_cards() -> list[dict]:
    cards = []
    for chunk_id, title, body in load_chunks():
        for sentence in sentences(body):
            match = DEFINITIONAL_RE.match(sentence)
            if not match:
                continue
            subject = match.group("subject").strip()
            predicate = match.group("predicate").strip()
            cards.append(
                {
                    "front": f"What {match.group('verb')} {subject}?",
                    "back": predicate,
                    "source_chunk": chunk_id,
                    "source_title": title,
                    "method": "baseline_regex",
                }
            )
    return cards


def main() -> None:
    cards = generate_baseline_cards()
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(cards, indent=2), encoding="utf-8")
    print(f"generated {len(cards)} baseline cards -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
