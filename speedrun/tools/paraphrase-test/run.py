#!/usr/bin/env python3
"""The three-way §9 ablation: for each build (interleaved / blocked /
ankiDefault) at a fixed study budget, plus a no-study control, a
"student" (Claude, given only the studied cards' front+back in context)
answers the 30 verbatim card fronts and 60 rewordings from
output/rewordings_counterfactual.json, then a blind grader scores each
answer. Counterfactual content only - see counterfactualize.py for why:
without it, a frontier model already knows the real citric acid cycle
and every condition ceilings at ~100%, measuring nothing.

Each condition's studied set comes from output/study_orders.json - the
REAL Rust queue order for that build, not an invented one.

Threaded with a persistent cache keyed by prompt hash, so a crash or
rate-limit mid-run doesn't restart from zero.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"
STUDY_ORDERS_PATH = OUTPUT_DIR / "study_orders.json"
CARDS_CF_PATH = OUTPUT_DIR / "cards_counterfactual.json"
REWORDINGS_CF_PATH = OUTPUT_DIR / "rewordings_counterfactual.json"
CACHE_PATH = OUTPUT_DIR / "run_cache.json"
ABLATION_RESULTS_PATH = OUTPUT_DIR / "ablation_results.json"

MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"
MAX_WORKERS = 8

STUDENT_SYSTEM_PROMPT = (
    "You are a student who has just studied a set of flashcards (shown "
    "below, or none if you studied nothing). Answer the following exam "
    "question using ONLY what's on the flashcards you studied. If the "
    "studied material doesn't cover it, say \"I don't know\" rather than "
    "guessing from outside knowledge - the flashcards use made-up "
    "terminology on purpose, so do not substitute real-world biochemistry "
    "terms you may already know.\n\n"
    "Respond in exactly this format, nothing else:\n"
    "ANSWER: <your answer, one to two sentences, or \"I don't know\">"
)

GRADER_SYSTEM_PROMPT = (
    "Grade a student's answer against the gold answer for an exam "
    "question. Grade into exactly one of: \"correct\" (matches the key "
    "fact(s) in the gold answer), \"partial\" (some correct elements but "
    "incomplete or with an error), \"incorrect\" (wrong or "
    "\"I don't know\").\n\n"
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
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code in (429, 529) and attempt < 4:
                import time

                time.sleep(2**attempt)
                continue
            raise
    raise last_error  # pragma: no cover


def cached_call(cache: dict, cache_key: str, api_key: str, system: str, user: str, max_tokens: int) -> str:
    if cache_key in cache:
        return cache[cache_key]
    result = call_api(api_key, system, user, max_tokens)
    cache[cache_key] = result
    return result


def ask_student(api_key: str, cache: dict, studied_cards: list[dict], question: str) -> str:
    if studied_cards:
        studied_text = "\n\n".join(
            f"Card {i + 1}:\nFront: {c['front']}\nBack: {c['back']}"
            for i, c in enumerate(studied_cards)
        )
    else:
        studied_text = "(You studied nothing.)"
    user_prompt = f"Studied flashcards:\n{studied_text}\n\nExam question: {question}"
    cache_key = "student:" + hashlib.sha256(
        (STUDENT_SYSTEM_PROMPT + user_prompt).encode("utf-8")
    ).hexdigest()
    text = cached_call(cache, cache_key, api_key, STUDENT_SYSTEM_PROMPT, user_prompt, 150)
    match = ANSWER_RE.search(text)
    return match.group(1).strip() if match else text


def grade(api_key: str, cache: dict, question: str, gold_answer: str, student_answer: str) -> dict:
    user_prompt = (
        f"Question: {question}\nGold answer: {gold_answer}\n"
        f"Student answer: {student_answer}\n\nGrade it."
    )
    cache_key = "grade:" + hashlib.sha256(
        (GRADER_SYSTEM_PROMPT + user_prompt).encode("utf-8")
    ).hexdigest()
    text = cached_call(cache, cache_key, api_key, GRADER_SYSTEM_PROMPT, user_prompt, 100)
    verdict_match = VERDICT_RE.search(text)
    reasoning_match = REASONING_RE.search(text)
    if not verdict_match:
        return {"verdict": "ungraded", "reasoning": f"parse error: {text!r}"}
    return {
        "verdict": verdict_match.group(1),
        "reasoning": reasoning_match.group(1).strip() if reasoning_match else "",
    }


def run_condition(
    api_key: str,
    cache: dict,
    condition_name: str,
    studied_cards: list[dict],
    cards: list[dict],
    rewordings: list[dict],
) -> list[dict]:
    """Tests all 30 cards' verbatim front + both rewordings under one
    studied-set condition. Each of the 3 items per card is an
    independent API call with independent context - never batched -
    so a verbatim answer can't leak into a reworded item's context."""
    items = []
    for card in cards:
        items.append({"card_id": card["id"], "kind": "verbatim", "question": card["front"], "gold_answer": card["back"]})
    for r in rewordings:
        items.append({"card_id": r["card_id"], "kind": r["variant"], "question": r["question"], "gold_answer": r["gold_answer"]})

    def process(item: dict) -> dict:
        student_answer = ask_student(api_key, cache, studied_cards, item["question"])
        verdict = grade(api_key, cache, item["question"], item["gold_answer"], student_answer)
        return {**item, "student_answer": student_answer, **verdict}

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(process, item): item for item in items}
        done = 0
        for future in as_completed(futures):
            results.append(future.result())
            done += 1
            if done % 15 == 0:
                print(f"    [{condition_name}] {done}/{len(items)}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--budgets", type=int, nargs="+", default=[10], help="coverage budgets to run (default: 10)"
    )
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("SPEEDRUN_ANTHROPIC_KEY")
    if not api_key:
        raise SystemExit("Set ANTHROPIC_API_KEY (or SPEEDRUN_ANTHROPIC_KEY) in the environment.")

    study_orders = json.loads(STUDY_ORDERS_PATH.read_text(encoding="utf-8"))
    cards = json.loads(CARDS_CF_PATH.read_text(encoding="utf-8"))["cards"]
    rewordings = json.loads(REWORDINGS_CF_PATH.read_text(encoding="utf-8"))["rewordings"]
    cards_by_id = {c["id"]: c for c in cards}

    cache = load_cache()
    all_results = {}

    print("=== no-study control ===")
    all_results["no_study_control"] = run_condition(
        api_key, cache, "no_study_control", [], cards, rewordings
    )
    save_cache(cache)

    for budget in args.budgets:
        for build_name, build_data in study_orders["builds"].items():
            # study_order.py's card_id is already this pipeline's 1-30 id
            # (mapped via note_id at fixture-build time), so this is a
            # direct lookup of the REAL per-build queue order - not an
            # assumption about insertion order.
            studied_card_ids = [c["card_id"] for c in build_data["order"][:budget]]
            studied_cards = [cards_by_id[cid] for cid in studied_card_ids]
            assert len(studied_cards) == budget
            condition_name = f"{build_name}@{budget}"
            print(f"=== {condition_name} ===")
            all_results[condition_name] = run_condition(
                api_key, cache, condition_name, studied_cards, cards, rewordings
            )
            save_cache(cache)

    ABLATION_RESULTS_PATH.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    print(f"\n-> {ABLATION_RESULTS_PATH}")


if __name__ == "__main__":
    main()
