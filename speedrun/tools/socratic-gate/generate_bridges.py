#!/usr/bin/env python3
"""MVP validation for Brainlift v2's Socratic Gatekeeper thesis
(rslib/src/stats/socratic_gate.rs): generates one real Socratic bridge
question per card, via real Claude API calls, for the two
`requires_socratic_bridge()` branches (DangerousError / ProductiveStruggle
- see the Rust module's doc comment for why this MVP collapses both into
one bridge-generation path rather than writing separate prompts per
branch: both branches share the same underlying need, a scaffold that
makes the student re-derive the fact rather than just re-reading it).

Reuses the 30 counterfactual cards already built and audited by
speedrun/tools/paraphrase-test/ (cards_counterfactual.json) rather than
regenerating - same provenance chain, no new card content invented for
this MVP.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

PARAPHRASE_OUTPUT = Path(__file__).parent.parent / "paraphrase-test" / "output"
CARDS_CF_PATH = PARAPHRASE_OUTPUT / "cards_counterfactual.json"
OUTPUT_DIR = Path(__file__).parent / "output"
BRIDGES_PATH = OUTPUT_DIR / "bridges.json"
PROMPT_LOG_PATH = OUTPUT_DIR / "prompts.log"

MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"

# Mirrors the source spiky POV's own worked example (Loop of Henle: "if I
# blocked the ascending limb, what happens to urine concentration?") -
# a bridging QUESTION the student answers themselves, not a restated fact.
BRIDGE_SYSTEM_PROMPT = (
    "You write Socratic bridge questions for a study app. The flashcards "
    "you'll see use deliberately fictional/renamed terminology (for a "
    "controlled research test) - treat every term in the card as given, "
    "correct, and internally consistent. Do not comment on the "
    "terminology, do not ask for clarification, do not flag it as "
    "non-standard - just follow the instructions below exactly as if the "
    "terms were real.\n\n"
    "Given a single flashcard (front/back), write ONE short bridging "
    "question that would help a student who answered wrong re-derive the "
    "fact themselves, rather than just being told the answer again. The "
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


def call_bridge_generator(api_key: str, front: str, back: str) -> dict:
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
    with urllib.request.urlopen(request, timeout=60) as response:
        body = json.loads(response.read())
    text = body["content"][0]["text"].strip()

    with PROMPT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"--- bridge ---\nUSER: {user_prompt}\nRESPONSE: {text}\n\n")

    match = RESPONSE_RE.search(text)
    if not match:
        raise ValueError(f"no BRIDGE_QUESTION/ANSWER/SYNTHESIS in response: {text!r}")
    return {
        "bridge_question": match.group(1).strip(),
        "bridge_answer": match.group(2).strip(),
        "synthesis": match.group(3).strip(),
    }


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
        "SPEEDRUN_ANTHROPIC_KEY"
    )
    if not api_key:
        raise SystemExit(
            "Set ANTHROPIC_API_KEY (or SPEEDRUN_ANTHROPIC_KEY) in the environment."
        )

    cards = json.loads(CARDS_CF_PATH.read_text(encoding="utf-8"))["cards"]

    if PROMPT_LOG_PATH.exists():
        PROMPT_LOG_PATH.unlink()

    bridges = []
    for i, card in enumerate(cards, 1):
        print(f"[{i}/{len(cards)}] generating bridge for card {card['id']}...")
        bridge = call_bridge_generator(api_key, card["front"], card["back"])
        bridges.append(
            {
                "card_id": card["id"],
                "topic": card["topic"],
                "card_front": card["front"],
                "card_back": card["back"],
                **bridge,
            }
        )

    OUTPUT_DIR.mkdir(exist_ok=True)
    BRIDGES_PATH.write_text(
        json.dumps(
            {
                "_provenance": (
                    "One Socratic bridge question+answer per card (30 "
                    "cards, reused from paraphrase-test's counterfactual "
                    "set), generated via real Claude API calls. Full "
                    "prompts in prompts.log."
                ),
                "model": MODEL,
                "bridges": bridges,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nGenerated {len(bridges)} bridges -> {BRIDGES_PATH}")


if __name__ == "__main__":
    main()
