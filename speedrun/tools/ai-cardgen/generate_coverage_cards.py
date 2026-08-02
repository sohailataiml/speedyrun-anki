#!/usr/bin/env python3
"""Generates source-traced cards for the curriculum sources listed in
speedrun/ai/sources.json, so the coverage map (PRD §8) has real content
behind more than one AAMC content category.

Deliberately a separate script from generate.py rather than a rewrite of
it. generate.py's 50-card output feeds the gold-set eval (98% vs 0%) and
the leakage check, both already run and reported in
speedrun/docs/ai-subsystem.md - regenerating that output would invalidate
published numbers for no benefit. This script reuses generate.py's prompt
and provenance format verbatim so the two produce interchangeable cards.

Every generated card carries:
  - the chunk ID it came from (PRD §3: "traces to a named source")
  - the topic:: tag its content category maps to
  - the content category id itself

Prompts are appended to output/coverage_generation_prompts.log, which the
leakage check can be pointed at the same way it checks generate.py's log.

Usage:  python generate_coverage_cards.py [--cards-per-chunk N]
Requires ANTHROPIC_API_KEY (or SPEEDRUN_ANTHROPIC_KEY).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AI_DIR = Path(__file__).parent.parent.parent / "ai"
SOURCES_PATH = AI_DIR / "sources.json"
OUTPUT_DIR = Path(__file__).parent / "output"
CARDS_OUTPUT_PATH = OUTPUT_DIR / "coverage_cards.json"
PROMPT_LOG_PATH = OUTPUT_DIR / "coverage_generation_prompts.log"

MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"

# Identical to generate.py's, so cards from either script are comparable.
SYSTEM_PROMPT = (
    "You write flashcards for MCAT students studying biochemistry. Given a "
    "short passage, write exam-style question/answer flashcards that test "
    "understanding of the passage - not just word-for-word recall. Each "
    "answer must be fully supported by the passage; do not add outside "
    "facts. Respond with a JSON object: "
    '{"cards": [{"front": "...", "back": "..."}, ...]}. '
    "Nothing else - no markdown, no commentary outside the JSON."
)


def load_sources() -> list[dict]:
    manifest = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    return [s for s in manifest["sources"] if s["generated_by"].startswith("generate_coverage")]


def load_chunks(path: Path, prefix: str) -> list[tuple[str, str, str]]:
    text = path.read_text(encoding="utf-8")
    header_re = re.compile(rf"^## ({prefix}-\d+): (.+)$", re.MULTILINE)
    headers = list(header_re.finditer(text))
    chunks = []
    for i, match in enumerate(headers):
        start = match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        chunks.append((match.group(1), match.group(2), text[start:end].strip()))
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
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cards-per-chunk", type=int, default=3)
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("SPEEDRUN_ANTHROPIC_KEY")
    if not api_key:
        raise SystemExit("Set ANTHROPIC_API_KEY (or SPEEDRUN_ANTHROPIC_KEY) in the environment.")

    OUTPUT_DIR.mkdir(exist_ok=True)
    sources = load_sources()
    all_cards: list[dict] = []

    with open(PROMPT_LOG_PATH, "w", encoding="utf-8") as log:
        for source in sources:
            path = AI_DIR / source["file"]
            chunks = load_chunks(path, source["chunk_prefix"])
            print(f"\n{source['content_category']} — {source['title']} ({len(chunks)} chunks)")
            for chunk_id, title, body in chunks:
                prompt = (
                    f'Passage (source: {chunk_id}, "{title}"):\n\n{body}\n\n'
                    f"Write exactly {args.cards_per_chunk} flashcards from this passage."
                )
                log.write(f"=== {chunk_id} ===\nSYSTEM: {SYSTEM_PROMPT}\nUSER: {prompt}\n\n")
                parsed = json.loads(call_anthropic(api_key, prompt))
                cards = parsed.get("cards", [])
                for card in cards:
                    all_cards.append(
                        {
                            "front": card["front"],
                            "back": card["back"],
                            "source_chunk": chunk_id,
                            "source_title": title,
                            "source_file": source["file"],
                            "topic_tag": source["topic_tag"],
                            "content_category": source["content_category"],
                            "method": "ai_generated",
                            "model": MODEL,
                        }
                    )
                print(f"  {chunk_id}: {len(cards)} cards")

    CARDS_OUTPUT_PATH.write_text(
        json.dumps(
            {
                "_provenance": (
                    "Cards generated from the original curriculum sources listed in "
                    "speedrun/ai/sources.json, via real Claude API calls. Each card "
                    "cites the chunk it came from and carries the topic:: tag for its "
                    "AAMC content category. Full prompts in "
                    "coverage_generation_prompts.log."
                ),
                "model": MODEL,
                "cards_per_chunk": args.cards_per_chunk,
                "total_cards": len(all_cards),
                "by_category": {
                    s["content_category"]: sum(
                        1 for c in all_cards if c["content_category"] == s["content_category"]
                    )
                    for s in sources
                },
                "cards": all_cards,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nGenerated {len(all_cards)} cards across {len(sources)} content categories")
    print(f"-> {CARDS_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
