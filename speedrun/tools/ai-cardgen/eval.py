#!/usr/bin/env python3
"""AI card check (PRD §8): grades generated cards into the three required
buckets - correct and useful / wrong / correct but bad teaching - and
compares the AI generator against the baseline it has to beat.

The rubric below was fixed before this script was run against real
results and is applied identically, blind to which method produced a
given card (the grader prompt never says which generator a card came
from). Grading is LLM-as-judge (Claude, given the source chunk and the
card, asked for a verdict) - a real limitation, not a substitute for
human grading, and stated as such in the report.
"""

from __future__ import annotations

import json
import os
import random
import re
import urllib.request
from collections import Counter
from pathlib import Path

AI_DIR = Path(__file__).parent.parent.parent / "ai"
SOURCE_PATH = AI_DIR / "source_material.md"
OUTPUT_DIR = Path(__file__).parent / "output"
AI_CARDS_PATH = OUTPUT_DIR / "ai_cards.json"
BASELINE_CARDS_PATH = OUTPUT_DIR / "baseline_cards.json"
RESULTS_PATH = OUTPUT_DIR / "eval_results.json"

MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"
CHUNK_HEADER_RE = re.compile(r"^## (kc-\d+): (.+)$", re.MULTILINE)

GRADER_SYSTEM_PROMPT = (
    "You are grading a flashcard against the source passage it was made "
    "from. Grade it into exactly one of three categories:\n"
    '- "correct_and_useful": factually accurate per the passage, and a '
    "clear, well-formed question a student could learn from.\n"
    '- "wrong": factually incorrect, unsupported by the passage, or the '
    "question doesn't logically make sense.\n"
    '- "correct_but_bad_teaching": factually accurate, but poorly designed '
    "as a learning tool - e.g. an ambiguous question, unresolved pronouns "
    "referring to nothing (\"What is This?\"), or so trivial it doesn't "
    "test real understanding.\n\n"
    "Respond in exactly this two-line format, nothing else:\n"
    "VERDICT: correct_and_useful|wrong|correct_but_bad_teaching\n"
    "REASONING: one sentence, no quotation marks"
)


def load_chunk_text() -> dict[str, str]:
    text = SOURCE_PATH.read_text(encoding="utf-8")
    headers = list(CHUNK_HEADER_RE.finditer(text))
    chunks = {}
    for i, match in enumerate(headers):
        start = match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        chunks[match.group(1)] = text[start:end].strip()
    return chunks


def call_grader(api_key: str, chunk_text: str, front: str, back: str) -> dict:
    user_prompt = (
        f"Source passage:\n{chunk_text}\n\n"
        f'Flashcard:\nQ: {front}\nA: {back}\n\nGrade it.'
    )
    payload = json.dumps(
        {
            "model": MODEL,
            "max_tokens": 200,
            "system": GRADER_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": 0,
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
    # Plain VERDICT:/REASONING: lines rather than JSON - a free-text
    # reasoning sentence containing a stray quote mark breaks JSON string
    # parsing, which is exactly what caused failures with the earlier
    # JSON-based format. This format has no escaping to get wrong.
    verdict_match = re.search(
        r"VERDICT:\s*(correct_and_useful|wrong|correct_but_bad_teaching)", text
    )
    reasoning_match = re.search(r"REASONING:\s*(.+)", text)
    if not verdict_match:
        raise ValueError(f"no VERDICT line found in grader response: {text!r}")
    return {
        "verdict": verdict_match.group(1),
        "reasoning": reasoning_match.group(1).strip() if reasoning_match else "",
    }


def grade_cards(api_key: str, cards: list[dict], chunks: dict[str, str]) -> list[dict]:
    graded = []
    for card in cards:
        chunk_text = chunks.get(card["source_chunk"], "")
        try:
            verdict = call_grader(api_key, chunk_text, card["front"], card["back"])
        except (ValueError, json.JSONDecodeError) as e:
            print(f"  grading failed for {card['front']!r}: {e}")
            verdict = {"verdict": "ungraded", "reasoning": f"grader parse error: {e}"}
        graded.append({**card, **verdict})
    return graded


def summarize(graded: list[dict], label: str) -> Counter:
    counts = Counter(c["verdict"] for c in graded)
    total = len(graded)
    print(f"\n{label} (n={total}):")
    for bucket in ("correct_and_useful", "correct_but_bad_teaching", "wrong", "ungraded"):
        n = counts.get(bucket, 0)
        if bucket == "ungraded" and n == 0:
            continue
        print(f"  {bucket}: {n} ({n / total:.0%})" if total else f"  {bucket}: 0")
    return counts


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
        "SPEEDRUN_ANTHROPIC_KEY"
    )
    if not api_key:
        raise SystemExit(
            "Set ANTHROPIC_API_KEY (or SPEEDRUN_ANTHROPIC_KEY) in the environment."
        )

    chunks = load_chunk_text()
    ai_cards = json.loads(AI_CARDS_PATH.read_text(encoding="utf-8"))
    baseline_cards = json.loads(BASELINE_CARDS_PATH.read_text(encoding="utf-8"))

    print(f"Grading {len(ai_cards)} AI cards and {len(baseline_cards)} baseline cards...")
    graded_ai = grade_cards(api_key, ai_cards, chunks)
    graded_baseline = grade_cards(api_key, baseline_cards, chunks)

    ai_counts = summarize(graded_ai, "AI generator")
    baseline_counts = summarize(graded_baseline, "Baseline (regex extraction)")

    ai_useful_rate = ai_counts.get("correct_and_useful", 0) / len(graded_ai)
    baseline_useful_rate = (
        baseline_counts.get("correct_and_useful", 0) / len(graded_baseline)
        if graded_baseline
        else 0.0
    )

    print(
        f"\nResult: AI correct_and_useful rate {ai_useful_rate:.0%} vs "
        f"baseline {baseline_useful_rate:.0%}."
    )
    beats_baseline = ai_useful_rate > baseline_useful_rate
    print(
        "AI beats the baseline - required to ship per PRD §3/§8."
        if beats_baseline
        else "AI does NOT beat the baseline - per PRD §3, it doesn't ship as-is."
    )

    OUTPUT_DIR.mkdir(exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "ai_cards": graded_ai,
                "baseline_cards": graded_baseline,
                "ai_correct_and_useful_rate": ai_useful_rate,
                "baseline_correct_and_useful_rate": baseline_useful_rate,
                "ai_beats_baseline": beats_baseline,
                "grading_method": "llm_as_judge",
                "grading_model": MODEL,
                "grading_limitation": (
                    "Automated LLM-as-judge grading, not human-graded. A real "
                    "limitation, stated per the project's honesty rule."
                ),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nFull results -> {RESULTS_PATH}")


if __name__ == "__main__":
    main()
