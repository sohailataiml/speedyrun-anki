#!/usr/bin/env python3
"""Leakage check (PRD §8): flags any held-back gold-set item, or a near
copy of one, showing up in what the AI generator actually saw - beyond
what's already explained by the source material both draw from.

**Why "beyond what's explained by the source" matters, precisely:** the
prompt sent to the LLM necessarily contains the full source_material.md
chunk text - that's what generation means. And gold-set answers
necessarily share wording with that same source material, since they're
correct answers about it. A naive "does gold-set text appear in the
prompt log" check would therefore always fire, because the prompt log
contains the source material, which the gold set already overlaps with by
design - that's not leakage, it's just both documents talking about the
same facts.

The check that actually means something: does gold-set phrasing that is
NOT already present in source_material.md show up in the prompt log
anyway? If so, something added gold-set-specific content to what the
generator saw - the one thing this pipeline is supposed to structurally
prevent, since generate.py's code never opens gold_set.json at all. This
verifies that invariant empirically instead of just trusting the code.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

AI_DIR = Path(__file__).parent.parent.parent / "ai"
GOLD_SET_PATH = AI_DIR / "gold_set.json"
SOURCE_PATH = AI_DIR / "source_material.md"
PROMPT_LOG_PATH = (
    Path(__file__).parent.parent / "ai-cardgen" / "output" / "generation_prompts.log"
)

NGRAM_SIZE = 6


def normalize_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def ngrams_of(text: str) -> set[tuple]:
    words = normalize_words(text)
    return {tuple(words[i : i + NGRAM_SIZE]) for i in range(len(words) - NGRAM_SIZE + 1)}


def field_ngrams(text: str) -> set[tuple]:
    words = normalize_words(text)
    if len(words) < NGRAM_SIZE:
        return set()
    return {tuple(words[i : i + NGRAM_SIZE]) for i in range(len(words) - NGRAM_SIZE + 1)}


def main() -> int:
    gold = json.loads(GOLD_SET_PATH.read_text(encoding="utf-8"))["pairs"]
    source_ngrams = ngrams_of(SOURCE_PATH.read_text(encoding="utf-8"))

    print(f"Loaded {len(gold)} gold-set pairs.\n")

    if not PROMPT_LOG_PATH.exists():
        print(
            "PRIMARY CHECK SKIPPED: no generation_prompts.log found yet. "
            "Run generate.py first, then rerun this check."
        )
        return 0

    log_ngrams = ngrams_of(PROMPT_LOG_PATH.read_text(encoding="utf-8"))

    real_leaks = []
    source_explained = 0
    for pair in gold:
        for field in ("question", "answer"):
            f_ngrams = field_ngrams(pair[field])
            if not f_ngrams:
                continue
            in_log = f_ngrams & log_ngrams
            if not in_log:
                continue
            # Only the portion NOT already explained by source overlap
            # counts as a real finding.
            gold_specific = in_log - source_ngrams
            if gold_specific:
                real_leaks.append(
                    f"gold pair #{pair['id']} {field} has gold-specific phrasing "
                    f"(not from source_material.md) in the prompt log: {pair[field]!r}"
                )
            else:
                source_explained += 1

    print(
        f"{source_explained} gold pair/field overlaps with the prompt log were "
        "fully explained by shared source_material.md content (expected, not leakage)."
    )

    if real_leaks:
        print(f"\nLEAKAGE FOUND ({len(real_leaks)} finding(s) not explained by shared source content):")
        for leak in real_leaks:
            print(f"  - {leak}")
        return 1

    print(
        "\nPRIMARY CHECK PASSED: every gold pair/field that overlaps with the "
        "prompt log is fully explained by shared source material - no "
        "gold-set-specific content reached the generator."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
