#!/usr/bin/env python3
"""Applies substitutions.json's deterministic renaming table to
output/cards.json and output/rewordings.json, producing
output/cards_counterfactual.json and output/rewordings_counterfactual.json.

No LLM involved - pure text substitution, fully auditable. This is what
makes the student-simulation ablation (run.py) a real measurement rather
than a ceiling-effect no-op: a frontier model already knows the real
citric acid cycle cold, so it would answer both studied and unstudied
conditions at ~100% regardless of what it "studied." Renamed to fictional
terms, the model can only answer correctly using what's actually in its
simulated study context.

Case-preserving: a substitution's replacement is case-matched to the
original occurrence (Title Case in -> Title Case out, etc.), and each
substitution is applied at word boundaries only, longest terms first, so
e.g. "alpha-ketoglutarate dehydrogenase" doesn't get double-mangled by
also matching the standalone "alpha-ketoglutarate" and "dehydrogenase"
substitutions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"
SUBSTITUTIONS_PATH = Path(__file__).parent / "substitutions.json"
CARDS_PATH = OUTPUT_DIR / "cards.json"
REWORDINGS_PATH = OUTPUT_DIR / "rewordings.json"
CARDS_CF_PATH = OUTPUT_DIR / "cards_counterfactual.json"
REWORDINGS_CF_PATH = OUTPUT_DIR / "rewordings_counterfactual.json"


def build_pattern(term: str) -> re.Pattern:
    # \b doesn't work well around '+' (NAD+) or hyphens at the edges, so
    # bound on whitespace/punctuation/string-edges explicitly instead.
    escaped = re.escape(term)
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


def match_case(replacement: str, original: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def apply_substitutions(text: str, substitutions: list[tuple[str, str]]) -> str:
    for term, replacement in substitutions:
        pattern = build_pattern(term)
        text = pattern.sub(lambda m: match_case(replacement, m.group(0)), text)
    return text


def counterfactualize_text(text: str, substitutions: list[tuple[str, str]]) -> str:
    # Longest terms first, so multi-word terms are consumed before their
    # single-word substrings get a chance to partially match them.
    ordered = sorted(substitutions, key=lambda t: len(t[0]), reverse=True)
    return apply_substitutions(text, ordered)


def main() -> None:
    sub_data = json.loads(SUBSTITUTIONS_PATH.read_text(encoding="utf-8"))
    substitutions = [tuple(pair) for pair in sub_data["substitutions"]]

    cards_data = json.loads(CARDS_PATH.read_text(encoding="utf-8"))
    cf_cards = []
    for card in cards_data["cards"]:
        cf_cards.append(
            {
                **card,
                "front": counterfactualize_text(card["front"], substitutions),
                "back": counterfactualize_text(card["back"], substitutions),
            }
        )
    CARDS_CF_PATH.write_text(
        json.dumps({**cards_data, "cards": cf_cards, "_counterfactual": True}, indent=2),
        encoding="utf-8",
    )

    rewordings_data = json.loads(REWORDINGS_PATH.read_text(encoding="utf-8"))
    cf_rewordings = []
    for r in rewordings_data["rewordings"]:
        cf_rewordings.append(
            {
                **r,
                "question": counterfactualize_text(r["question"], substitutions),
                "gold_answer": counterfactualize_text(r["gold_answer"], substitutions),
                "card_front": counterfactualize_text(r["card_front"], substitutions),
                "card_back": counterfactualize_text(r["card_back"], substitutions),
            }
        )
    REWORDINGS_CF_PATH.write_text(
        json.dumps(
            {**rewordings_data, "rewordings": cf_rewordings, "_counterfactual": True},
            indent=2,
        ),
        encoding="utf-8",
    )

    # Assertions: every original term is gone, every substitution fired
    # at least once somewhere in the corpus.
    all_cf_text = " ".join(c["front"] + " " + c["back"] for c in cf_cards) + " " + " ".join(
        r["question"] + " " + r["gold_answer"] for r in cf_rewordings
    )
    all_orig_text = " ".join(
        c["front"] + " " + c["back"] for c in cards_data["cards"]
    ) + " " + " ".join(
        r["question"] + " " + r["gold_answer"] for r in rewordings_data["rewordings"]
    )

    leaked, unused = [], []
    for term, replacement in substitutions:
        pattern = build_pattern(term)
        if pattern.search(all_cf_text):
            leaked.append(term)
        if not build_pattern(term).search(all_orig_text):
            unused.append(term)

    print(f"Counterfactualized {len(cf_cards)} cards -> {CARDS_CF_PATH}")
    print(f"Counterfactualized {len(cf_rewordings)} rewordings -> {REWORDINGS_CF_PATH}")
    if leaked:
        print(f"WARNING: original terms still present after substitution: {leaked}")
    else:
        print("OK: no original terms leaked into counterfactual text.")
    if unused:
        print(f"NOTE: substitution terms never appeared in source (harmless): {unused}")


if __name__ == "__main__":
    main()
