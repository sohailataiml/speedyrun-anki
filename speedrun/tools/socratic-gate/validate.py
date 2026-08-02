#!/usr/bin/env python3
"""The core MVP ablation for Brainlift v2's Socratic Gatekeeper thesis:
does seeing a Socratic bridge after a wrong answer produce better
understanding than seeing the plain correct answer, measured on a
follow-up reworded (discrimination-style) question testing the same
fact?

Three conditions per card, all against the same 30 counterfactual cards
and the same follow-up probe question (the "discrimination" reworded
variant already generated and audited by paraphrase-test/):

  - "no_correction": nothing shown at all after the (assumed) wrong
    answer, straight to the follow-up question. REUSED from
    paraphrase-test's ablation_results.json no_study_control - same
    items, same methodology, no new API calls needed for this arm. This
    is the floor: how much does ANY correction help.
  - "plain": the card's plain back is shown as the correction ("the
    answer is X"), then the follow-up question. This is what every
    competitor tool (and vanilla Anki) does today.
  - "bridge": the Socratic bridge question+answer+synthesis
    (bridges.json) is shown as the correction instead of the plain
    answer, then the follow-up question. This is the Gatekeeper's
    proposed intervention.

If "bridge" beats "plain" beats "no_correction" on the follow-up, that's
real, if small-n, support for the new POV's core claim: a Socratic
bridge fixes a wrong answer better than just re-stating the right one.

MVP scope, stated honestly: n=30 (one follow-up item per card, the
discrimination variant only - not also near-transfer, to keep this
achievable before the deadline). This is smaller than
paraphrase-test's own ablation and should be read as a first, real,
non-fabricated signal - not a definitive result. See
speedrun/docs/socratic-gate-mvp.md for the full limitations list.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SOCRATIC_OUTPUT = Path(__file__).parent / "output"
PARAPHRASE_OUTPUT = Path(__file__).parent.parent / "paraphrase-test" / "output"
BRIDGES_PATH = SOCRATIC_OUTPUT / "bridges.json"
ABLATION_RESULTS_PATH = PARAPHRASE_OUTPUT / "ablation_results.json"
REWORDINGS_CF_PATH = PARAPHRASE_OUTPUT / "rewordings_counterfactual.json"
CACHE_PATH = SOCRATIC_OUTPUT / "run_cache.json"
RESULTS_PATH = SOCRATIC_OUTPUT / "validation_results.json"

MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"
MAX_WORKERS = 8

STUDENT_SYSTEM_PROMPT = (
    "You are a student who just got a flashcard wrong. Below is either a "
    "correction you were shown, or nothing (if you weren't shown "
    "anything, say so isn't relevant - just do your best). Then answer "
    "the follow-up exam question using only what's in the correction, "
    "if any - the flashcards use made-up terminology on purpose, so do "
    "not substitute real-world biochemistry terms you may already know. "
    "If you don't know, say \"I don't know\" rather than guessing.\n\n"
    "Respond in exactly this format, nothing else:\n"
    "ANSWER: <your answer, one to two sentences, or \"I don't know\">"
)

GRADER_SYSTEM_PROMPT = (
    "Grade a student's answer against the gold answer for an exam "
    "question. Grade into exactly one of: \"correct\", \"partial\", "
    "\"incorrect\".\n\n"
    "Respond in exactly this two-line format, nothing else:\n"
    "VERDICT: correct|partial|incorrect\n"
    "REASONING: one sentence, no quotation marks"
)

ANSWER_RE = re.compile(r"ANSWER:\s*(.+)", re.DOTALL)
VERDICT_RE = re.compile(r"VERDICT:\s*(correct|partial|incorrect)")
REASONING_RE = re.compile(r"REASONING:\s*(.+)")


def load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def call_api(api_key: str, system: str, user_prompt: str, max_tokens: int) -> str:
    payload = json.dumps(
        {
            "model": MODEL,
            "max_tokens": max_tokens,
            "system": system,
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
    last_error = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.loads(response.read())
            return body["content"][0]["text"].strip()
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            last_error = e
            if attempt < 4:
                import time

                time.sleep(2**attempt)
                continue
            raise
    raise last_error  # pragma: no cover


def cached_call(cache: dict, key: str, api_key: str, system: str, user: str, max_tokens: int) -> str:
    if key in cache:
        return cache[key]
    result = call_api(api_key, system, user, max_tokens)
    cache[key] = result
    return result


def ask_student(api_key: str, cache: dict, correction_text: str, question: str) -> str:
    user_prompt = f"Correction shown: {correction_text}\n\nFollow-up question: {question}"
    key = "student:" + hashlib.sha256((STUDENT_SYSTEM_PROMPT + user_prompt).encode()).hexdigest()
    text = cached_call(cache, key, api_key, STUDENT_SYSTEM_PROMPT, user_prompt, 150)
    match = ANSWER_RE.search(text)
    return match.group(1).strip() if match else text


def grade(api_key: str, cache: dict, question: str, gold_answer: str, student_answer: str) -> dict:
    user_prompt = f"Question: {question}\nGold answer: {gold_answer}\nStudent answer: {student_answer}\n\nGrade it."
    key = "grade:" + hashlib.sha256((GRADER_SYSTEM_PROMPT + user_prompt).encode()).hexdigest()
    text = cached_call(cache, key, api_key, GRADER_SYSTEM_PROMPT, user_prompt, 100)
    v = VERDICT_RE.search(text)
    r = REASONING_RE.search(text)
    if not v:
        return {"verdict": "ungraded", "reasoning": f"parse error: {text!r}"}
    return {"verdict": v.group(1), "reasoning": r.group(1).strip() if r else ""}


def run_condition(api_key: str, cache: dict, name: str, items: list[dict]) -> list[dict]:
    def process(item: dict) -> dict:
        answer = ask_student(api_key, cache, item["correction_text"], item["question"])
        verdict = grade(api_key, cache, item["question"], item["gold_answer"], answer)
        return {**item, "student_answer": answer, **verdict}

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(process, item): item for item in items}
        done = 0
        for future in as_completed(futures):
            results.append(future.result())
            done += 1
            if done % 10 == 0:
                print(f"  [{name}] {done}/{len(items)}")
    return results


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def summarize(items: list[dict]) -> dict:
    correct = sum(1 for i in items if i["verdict"] == "correct")
    lo, hi = wilson_interval(correct, len(items))
    return {"n": len(items), "correct": correct, "rate": correct / len(items) if items else 0.0, "ci_lo": lo, "ci_hi": hi}


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("SPEEDRUN_ANTHROPIC_KEY")
    if not api_key:
        raise SystemExit("Set ANTHROPIC_API_KEY (or SPEEDRUN_ANTHROPIC_KEY) in the environment.")

    bridges = {b["card_id"]: b for b in json.loads(BRIDGES_PATH.read_text(encoding="utf-8"))["bridges"]}
    rewordings = json.loads(REWORDINGS_CF_PATH.read_text(encoding="utf-8"))["rewordings"]
    disc_by_card = {r["card_id"]: r for r in rewordings if r["variant"] == "discrimination"}

    ablation_data = json.loads(ABLATION_RESULTS_PATH.read_text(encoding="utf-8"))
    no_correction_items = [i for i in ablation_data["no_study_control"] if i["kind"] == "discrimination"]

    cache = load_cache()

    plain_items = []
    bridge_items = []
    for card_id, bridge in bridges.items():
        reword = disc_by_card.get(card_id)
        if not reword:
            continue
        plain_items.append(
            {
                "card_id": card_id,
                "question": reword["question"],
                "gold_answer": reword["gold_answer"],
                "correction_text": f"The correct answer is: {bridge['card_back']}",
            }
        )
        bridge_items.append(
            {
                "card_id": card_id,
                "question": reword["question"],
                "gold_answer": reword["gold_answer"],
                "correction_text": (
                    f"Bridge question: {bridge['bridge_question']}\n"
                    f"Bridge answer: {bridge['bridge_answer']}\n"
                    f"Synthesis: {bridge['synthesis']}"
                ),
            }
        )

    print(f"=== plain (n={len(plain_items)}) ===")
    plain_results = run_condition(api_key, cache, "plain", plain_items)
    save_cache(cache)

    print(f"=== bridge (n={len(bridge_items)}) ===")
    bridge_results = run_condition(api_key, cache, "bridge", bridge_items)
    save_cache(cache)

    no_correction_summary = summarize(no_correction_items)
    plain_summary = summarize(plain_results)
    bridge_summary = summarize(bridge_results)

    print(f"\nno_correction: {no_correction_summary}")
    print(f"plain:         {plain_summary}")
    print(f"bridge:        {bridge_summary}")

    RESULTS_PATH.write_text(
        json.dumps(
            {
                "_method": (
                    "MVP validation of Brainlift v2's Socratic Gatekeeper: "
                    "does a Socratic bridge after a wrong answer beat a "
                    "plain answer reveal on a follow-up discrimination-"
                    "style question? n=30 per condition. no_correction "
                    "reused from paraphrase-test's ablation_results.json "
                    "no_study_control (same items, same methodology, no "
                    "new API calls)."
                ),
                "summary": {
                    "no_correction": no_correction_summary,
                    "plain": plain_summary,
                    "bridge": bridge_summary,
                },
                "no_correction_items": no_correction_items,
                "plain_items": plain_results,
                "bridge_items": bridge_results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n-> {RESULTS_PATH}")


if __name__ == "__main__":
    main()
