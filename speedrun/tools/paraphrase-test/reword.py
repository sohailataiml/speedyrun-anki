#!/usr/bin/env python3
"""Generates 2 reworded exam-style questions per card (60 total from the
30 cards in output/cards.json), via real Claude API calls - one call per
card per variant, each seeing only that single card, never the answer
transcripts or other cards' text.

Two variants per card, named against the transfer-distance framing in
speedrun/docs/brainlift.md's teardown (Barnett & Ceci):
  - "near": same fact, different surface wording - an exam-style stem
    testing the same recall a student who knows the card would need.
  - "discrimination": requires picking this fact over a plausible
    neighbouring fact from the same topic, rather than just recognizing
    reworded phrasing.

The rubric below is fixed before any card is reworded and applied
identically to all 30 - the same "commit before you look" discipline as
speedrun/tools/ai-cardgen/eval.py's grading rubric.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"
CARDS_PATH = OUTPUT_DIR / "cards.json"
REWORDINGS_PATH = OUTPUT_DIR / "rewordings.json"
PROMPT_LOG_PATH = OUTPUT_DIR / "prompts.log"

MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"

REWORD_SYSTEM_PROMPT = {
    "near": (
        "You write MCAT-style exam questions. Given a single flashcard "
        "(front/back), write ONE new exam-style question that tests the "
        "exact same fact as the card, but with different surface wording "
        "and framing than the card's front - not a copy, not a trivial "
        "synonym swap, but the same underlying recall target. Do not "
        "reference \"the card\" or \"the passage\" - write it as a "
        "standalone exam item.\n\n"
        "Respond in exactly this two-line format, nothing else:\n"
        "QUESTION: <the reworded question>\n"
        "ANSWER: <the correct answer, one sentence>"
    ),
    "discrimination": (
        "You write MCAT-style exam questions. Given a single flashcard "
        "(front/back) from a specific topic area, write ONE new exam-style "
        "question that requires distinguishing this card's fact from a "
        "plausible neighboring fact in the same general topic (e.g. a "
        "different step, enzyme, or product from the same pathway) - the "
        "kind of question where knowing the card's fact in isolation "
        "isn't enough, the student has to correctly rule out a confusable "
        "alternative. Do not reference \"the card\" or \"the passage\" - "
        "write it as a standalone exam item.\n\n"
        "Respond in exactly this two-line format, nothing else:\n"
        "QUESTION: <the reworded question>\n"
        "ANSWER: <the correct answer, one sentence>"
    ),
}

RESPONSE_RE = re.compile(r"QUESTION:\s*(.+?)\s*\nANSWER:\s*(.+)", re.DOTALL)


def call_reworder(api_key: str, variant: str, front: str, back: str) -> dict:
    user_prompt = f"Card front: {front}\nCard back: {back}"
    payload = json.dumps(
        {
            "model": MODEL,
            "max_tokens": 300,
            "system": REWORD_SYSTEM_PROMPT[variant],
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
    with urllib.request.urlopen(request, timeout=60) as response:
        body = json.loads(response.read())
    text = body["content"][0]["text"].strip()

    with PROMPT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(
            f"--- reword variant={variant} ---\n"
            f"SYSTEM: {REWORD_SYSTEM_PROMPT[variant]}\n"
            f"USER: {user_prompt}\n"
            f"RESPONSE: {text}\n\n"
        )

    match = RESPONSE_RE.search(text)
    if not match:
        raise ValueError(f"no QUESTION/ANSWER lines found in response: {text!r}")
    return {"question": match.group(1).strip(), "gold_answer": match.group(2).strip()}


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
        "SPEEDRUN_ANTHROPIC_KEY"
    )
    if not api_key:
        raise SystemExit(
            "Set ANTHROPIC_API_KEY (or SPEEDRUN_ANTHROPIC_KEY) in the environment."
        )

    data = json.loads(CARDS_PATH.read_text(encoding="utf-8"))
    cards = data["cards"]

    if PROMPT_LOG_PATH.exists():
        PROMPT_LOG_PATH.unlink()

    rewordings = []
    for i, card in enumerate(cards, 1):
        print(f"[{i}/{len(cards)}] rewording card {card['id']} ({card['topic']})...")
        for variant in ("near", "discrimination"):
            reworded = call_reworder(api_key, variant, card["front"], card["back"])
            rewordings.append(
                {
                    "card_id": card["id"],
                    "topic": card["topic"],
                    "variant": variant,
                    "question": reworded["question"],
                    "gold_answer": reworded["gold_answer"],
                    "card_front": card["front"],
                    "card_back": card["back"],
                }
            )

    assert len(rewordings) == 60, f"expected 60 rewordings, got {len(rewordings)}"

    REWORDINGS_PATH.write_text(
        json.dumps(
            {
                "_provenance": (
                    "60 rewordings (2 per card x 30 cards: 1 near-transfer, "
                    "1 discrimination), generated via real Claude API calls, "
                    "each call seeing only its single source card. Full "
                    "prompts in prompts.log."
                ),
                "model": MODEL,
                "rewordings": rewordings,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nGenerated {len(rewordings)} rewordings -> {REWORDINGS_PATH}")


if __name__ == "__main__":
    main()
