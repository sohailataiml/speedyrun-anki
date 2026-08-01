#!/usr/bin/env python3
"""Tier 0 measurement (the guaranteed floor - see
speedrun/docs/paraphrase-test.md for the full tiering rationale): for each
of the 60 rewordings, asks a blind grader "is this reworded question
answerable using ONLY the card's front+back - i.e. everything a student
who perfectly memorized this one card would know?"

This requires no simulated student and no population of test subjects -
it's a direct, per-item measurement of how far a rewording sits from the
card's exact wording, which is a real (if narrower) version of POV 1's
question: does memorizing a card's exact phrasing carry to a differently
worded question testing the same fact?

The grader never sees which variant ("near" vs "discrimination") a
question is, or any other card - blind per the same discipline as
speedrun/tools/ai-cardgen/eval.py.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from collections import Counter
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"
REWORDINGS_PATH = OUTPUT_DIR / "rewordings.json"
PROMPT_LOG_PATH = OUTPUT_DIR / "prompts.log"
RESULTS_PATH = OUTPUT_DIR / "sufficiency_results.json"

MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"

GRADER_SYSTEM_PROMPT = (
    "You will be shown a single flashcard (front/back) and a separate "
    "exam-style question. Judge ONLY this: is the exam question fully "
    "answerable using just the information on this flashcard - i.e. would "
    "a student who has perfectly memorized this one flashcard, and "
    "nothing else, be able to answer it correctly?\n\n"
    "Grade into exactly one of three categories:\n"
    '- "sufficient": the card alone contains everything needed to answer '
    "correctly.\n"
    '- "insufficient": the question requires information, reasoning, or '
    "context beyond what's on the card.\n"
    '- "unrelated": the question does not actually test the same fact as '
    "the card.\n\n"
    "Respond in exactly this two-line format, nothing else:\n"
    "VERDICT: sufficient|insufficient|unrelated\n"
    "REASONING: one sentence, no quotation marks"
)

VERDICT_RE = re.compile(r"VERDICT:\s*(sufficient|insufficient|unrelated)")
REASONING_RE = re.compile(r"REASONING:\s*(.+)")


def call_grader(api_key: str, front: str, back: str, question: str) -> dict:
    user_prompt = (
        f"Flashcard:\nFront: {front}\nBack: {back}\n\n"
        f"Exam question: {question}\n\nGrade it."
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

    with PROMPT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"--- sufficiency grade ---\nUSER: {user_prompt}\nRESPONSE: {text}\n\n")

    verdict_match = VERDICT_RE.search(text)
    reasoning_match = REASONING_RE.search(text)
    if not verdict_match:
        raise ValueError(f"no VERDICT line found in grader response: {text!r}")
    return {
        "verdict": verdict_match.group(1),
        "reasoning": reasoning_match.group(1).strip() if reasoning_match else "",
    }


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval - more reliable than the normal
    approximation at small n, which is what a 30-item test has."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
        "SPEEDRUN_ANTHROPIC_KEY"
    )
    if not api_key:
        raise SystemExit(
            "Set ANTHROPIC_API_KEY (or SPEEDRUN_ANTHROPIC_KEY) in the environment."
        )

    data = json.loads(REWORDINGS_PATH.read_text(encoding="utf-8"))
    rewordings = data["rewordings"]

    graded = []
    for i, r in enumerate(rewordings, 1):
        print(f"[{i}/{len(rewordings)}] grading card {r['card_id']} ({r['variant']})...")
        try:
            verdict = call_grader(api_key, r["card_front"], r["card_back"], r["question"])
        except (ValueError, json.JSONDecodeError) as e:
            print(f"  grading failed: {e}")
            verdict = {"verdict": "ungraded", "reasoning": f"grader parse error: {e}"}
        graded.append({**r, **verdict})

    overall_counts = Counter(g["verdict"] for g in graded)
    near = [g for g in graded if g["variant"] == "near"]
    discrimination = [g for g in graded if g["variant"] == "discrimination"]
    near_counts = Counter(g["verdict"] for g in near)
    disc_counts = Counter(g["verdict"] for g in discrimination)

    def rate_with_ci(counts: Counter, n: int) -> dict:
        sufficient = counts.get("sufficient", 0)
        lo, hi = wilson_interval(sufficient, n)
        return {"n": n, "sufficient": sufficient, "rate": sufficient / n if n else 0.0,
                "ci_95_low": lo, "ci_95_high": hi}

    summary = {
        "overall": rate_with_ci(overall_counts, len(graded)),
        "near_transfer": rate_with_ci(near_counts, len(near)),
        "discrimination": rate_with_ci(disc_counts, len(discrimination)),
    }

    print(f"\nOverall (n={len(graded)}): {dict(overall_counts)}")
    print(
        f"  sufficient rate: {summary['overall']['rate']:.0%} "
        f"(95% CI {summary['overall']['ci_95_low']:.0%}-"
        f"{summary['overall']['ci_95_high']:.0%})"
    )
    print(
        f"  near-transfer sufficient: {summary['near_transfer']['rate']:.0%} | "
        f"discrimination sufficient: {summary['discrimination']['rate']:.0%}"
    )

    OUTPUT_DIR.mkdir(exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "_method": (
                    "Tier 0: item-side card-sufficiency measurement. Blind "
                    "LLM-as-judge grading (Claude), asking whether each "
                    "reworded question is answerable from its source card "
                    "alone. No simulated student population - a direct "
                    "per-item measurement, not an ablation."
                ),
                "grading_model": MODEL,
                "graded": graded,
                "summary": summary,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nFull results -> {RESULTS_PATH}")


if __name__ == "__main__":
    main()
