#!/usr/bin/env python3
"""The real AI card generator (PRD §3/§7/§8): source -> chunks -> LLM ->
Q&A flashcards, each traced to a named source chunk.

Calls the Anthropic Messages API directly via urllib (no new dependency -
matches the rest of speedrun/tools/, which stays stdlib-only). Requires
ANTHROPIC_API_KEY (or SPEEDRUN_ANTHROPIC_KEY) in the environment. Every
prompt actually sent is appended to output/generation_prompts.log, which
is what speedrun/tools/leakage-check/check.py verifies against - the
generator never reads gold_set.json, and this log is how that claim gets
checked rather than just asserted.

Rerunnable: same source material in, cards may vary slightly run to run
(LLM sampling), but the chunking, prompts, and provenance format are
fixed and deterministic.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

SOURCE_PATH = Path(__file__).parent.parent.parent / "ai" / "source_material.md"
OUTPUT_DIR = Path(__file__).parent / "output"
CARDS_OUTPUT_PATH = OUTPUT_DIR / "ai_cards.json"
PROMPT_LOG_PATH = OUTPUT_DIR / "generation_prompts.log"

MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"

CHUNK_HEADER_RE = re.compile(r"^## (kc-\d+): (.+)$", re.MULTILINE)

# Per-chunk card counts, summing to 50 (PRD §8: "generate 50 cards from
# one real source"). Chunks with more distinct sub-facts get more cards.
CARDS_PER_CHUNK = {
    "kc-01": 4, "kc-02": 3, "kc-03": 3, "kc-04": 4, "kc-05": 3, "kc-06": 4,
    "kc-07": 4, "kc-08": 3, "kc-09": 4, "kc-10": 4, "kc-11": 3, "kc-12": 4,
    "kc-13": 4, "kc-14": 3,
}

SYSTEM_PROMPT = (
    "You write flashcards for MCAT students studying biochemistry. Given a "
    "short passage, write exam-style question/answer flashcards that test "
    "understanding of the passage - not just word-for-word recall. Each "
    "answer must be fully supported by the passage; do not add outside "
    "facts. Respond with a JSON object: "
    '{"cards": [{"front": "...", "back": "..."}, ...]}. '
    "Nothing else - no markdown, no commentary outside the JSON."
)


def load_chunks() -> list[tuple[str, str, str]]:
    text = SOURCE_PATH.read_text(encoding="utf-8")
    headers = list(CHUNK_HEADER_RE.finditer(text))
    chunks = []
    for i, match in enumerate(headers):
        start = match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[start:end].strip()
        chunks.append((match.group(1), match.group(2), body))
    return chunks


def call_anthropic(api_key: str, user_prompt: str) -> str:
    payload = json.dumps(
        {
            "model": MODEL,
            "max_tokens": 2048,
            "system": SYSTEM_PROMPT,
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
    text = body["content"][0]["text"]
    # Claude sometimes wraps JSON in a markdown fence despite instructions
    # not to; strip it if present rather than failing the parse.
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return text


def generate_cards_for_chunk(
    api_key: str, chunk_id: str, title: str, body: str, count: int, log
) -> list[dict]:
    user_prompt = (
        f"Passage (source: {chunk_id}, \"{title}\"):\n\n{body}\n\n"
        f"Write exactly {count} flashcards from this passage."
    )
    log.write(f"=== {chunk_id} ===\nSYSTEM: {SYSTEM_PROMPT}\nUSER: {user_prompt}\n\n")
    raw = call_anthropic(api_key, user_prompt)
    parsed = json.loads(raw)
    cards = []
    for card in parsed.get("cards", []):
        cards.append(
            {
                "front": card["front"],
                "back": card["back"],
                "source_chunk": chunk_id,
                "source_title": title,
                "method": "ai_generated",
                "model": MODEL,
            }
        )
    return cards


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
        "SPEEDRUN_ANTHROPIC_KEY"
    )
    if not api_key:
        raise SystemExit(
            "Set ANTHROPIC_API_KEY (or SPEEDRUN_ANTHROPIC_KEY) in the environment."
        )

    OUTPUT_DIR.mkdir(exist_ok=True)
    chunks = load_chunks()

    all_cards = []
    with open(PROMPT_LOG_PATH, "w", encoding="utf-8") as log:
        for chunk_id, title, body in chunks:
            count = CARDS_PER_CHUNK.get(chunk_id, 3)
            print(f"generating {count} cards for {chunk_id} ({title})...")
            cards = generate_cards_for_chunk(api_key, chunk_id, title, body, count, log)
            all_cards.extend(cards)

    CARDS_OUTPUT_PATH.write_text(json.dumps(all_cards, indent=2), encoding="utf-8")
    print(f"\ngenerated {len(all_cards)} AI cards -> {CARDS_OUTPUT_PATH}")
    print(f"prompt log -> {PROMPT_LOG_PATH}")


if __name__ == "__main__":
    main()
