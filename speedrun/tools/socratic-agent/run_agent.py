#!/usr/bin/env python3
"""Runs the standalone Socratic-bridge agent (agent.py) over real
Krebs-cycle test cards (cards.py, each fact traced to a
speedrun/ai/source_material.md chunk), plus two adversarial checker
tests that verify check_grounded_node/check_leak_node actually have
discriminative power - not just rubber-stamping every bridge as fine.
Real Claude API calls throughout (bridge generation + groundedness
judging); the leak check is local n-gram overlap, no API call.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

# Windows consoles default to cp1252, which can't encode characters like
# subscript digits Claude sometimes uses (e.g. "CO₂"). Only affects
# printing here - the JSON output file is UTF-8 either way.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agent import AgentState, BridgeContent, check_grounded_node, check_leak_node, run_agent
from cards import CARDS, OUT_OF_CORPUS_CARDS, TestCard
from corpus import load_chunks
from retrieval import retrieve_for_grounding

OUTPUT_DIR = Path(__file__).parent / "output"


def run_adversarial_checks(chunks, api_key: str) -> list[dict]:
    """Hand-crafted bad bridges, run directly through the check nodes
    (skipping generate_node) to prove the checkers can actually fail
    something, not just pass everything they're given."""
    results = []

    # Adversarial leak case: the bridge QUESTION itself already names the
    # gold answer - the one field that must never do this, since it's
    # the only thing shown before the student has a chance to reason.
    leak_card = TestCard(901, "dummy front", "Citrate synthase", "kc-04")
    leak_state = AgentState(card=leak_card)
    leak_state.bridge = BridgeContent(
        bridge_question="Citrate synthase catalyzes the first step - why is that reaction thermodynamically favorable?",
        bridge_answer="Because coupling it to CoA hydrolysis releases enough free energy to drive the condensation forward.",
        synthesis="This coupling is what makes the first step of the cycle proceed spontaneously.",
    )
    leak_state = check_leak_node(leak_state)
    results.append(
        {
            "case": "adversarial_leak_in_bridge_question",
            "expected": "leaked=True",
            "actual_leaked": leak_state.leak.leaked,
            "leaked_phrases": leak_state.leak.leaked_phrases,
            "pass": leak_state.leak.leaked is True,
        }
    )

    # Adversarial *non-leak* case: the gold answer is named in the
    # answer/synthesis (the reveal-stage fields, shown after Reveal),
    # but never in the bridge question. This should NOT be flagged -
    # naming the fact in the reveal stage is the synthesis doing its
    # job, not a leak. This is the exact pattern that caught this
    # module's own bug: an earlier version checked answer+synthesis and
    # flagged 6/10 real cards this way.
    no_leak_card = TestCard(902, "dummy front", "Citrate synthase", "kc-04")
    no_leak_state = AgentState(card=no_leak_card)
    no_leak_state.bridge = BridgeContent(
        bridge_question="Why can't acetyl-CoA and oxaloacetate combine spontaneously without a catalyst?",
        bridge_answer="Because the condensation reaction has too high an activation energy to proceed at a useful rate without enzymatic catalysis.",
        synthesis="Citrate synthase provides that catalysis, making the first step of the cycle proceed.",
    )
    no_leak_state = check_leak_node(no_leak_state)
    results.append(
        {
            "case": "adversarial_legitimate_synthesis_mention",
            "expected": "leaked=False",
            "actual_leaked": no_leak_state.leak.leaked,
            "leaked_phrases": no_leak_state.leak.leaked_phrases,
            "pass": no_leak_state.leak.leaked is False,
        }
    )

    # Adversarial groundedness case: a bridge that invents a specific,
    # plausible-sounding but fabricated fact not in the retrieved
    # source_material.md passages (a fictional "step 9" and a made-up
    # enzyme name).
    ungrounded_card = TestCard(903, "citric acid cycle overview", "the cycle oxidizes acetyl-CoA", "kc-01")
    ungrounded_state = AgentState(card=ungrounded_card)
    ungrounded_state.retrieved, ungrounded_state.gate_score = retrieve_for_grounding(
        ungrounded_card.front, ungrounded_card.back, chunks, top_k=2
    )
    ungrounded_state.bridge = BridgeContent(
        bridge_question="What happens in step 9 of the cycle?",
        bridge_answer=(
            "Step 9 is catalyzed by fumarate reductase-beta, which converts "
            "leftover citrate directly into glucose, bypassing gluconeogenesis."
        ),
        synthesis="This fictional step 9 shows the cycle can directly regenerate glucose.",
    )
    ungrounded_state = check_grounded_node(ungrounded_state, api_key=api_key)
    results.append(
        {
            "case": "adversarial_fabricated_step_9",
            "expected": "grounded=False",
            "actual_grounded": ungrounded_state.grounded.grounded,
            "reasoning": ungrounded_state.grounded.reasoning,
            "pass": ungrounded_state.grounded.grounded is False,
        }
    )
    return results


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("SPEEDRUN_ANTHROPIC_KEY")
    if not api_key:
        raise SystemExit("Set ANTHROPIC_API_KEY (or SPEEDRUN_ANTHROPIC_KEY) in the environment.")

    chunks = load_chunks()
    print(f"Loaded {len(chunks)} source chunks.\n")

    all_cards = [(c, True) for c in CARDS] + [(c, False) for c in OUT_OF_CORPUS_CARDS]
    card_results = []
    for i, (card, in_corpus) in enumerate(all_cards, 1):
        tag = "IN " if in_corpus else "OUT"
        print(f"[{i}/{len(all_cards)}] {tag} card {card.card_id}: {card.front!r}")
        state = run_agent(card, chunks, api_key)
        for line in state.trace:
            print(f"    {line}")
        card_results.append(
            {
                "card_id": card.card_id,
                "in_corpus": in_corpus,
                "front": card.front,
                "back": card.back,
                "expected_source_chunk": card.source_chunk_id,
                "gate_score": round(state.gate_score, 4),
                "grounding_was_checked": state.grounded is not None,
                "retrieved_chunks": [r.chunk.chunk_id for r in state.retrieved],
                "retrieved_expected_chunk": (
                    card.source_chunk_id in [r.chunk.chunk_id for r in state.retrieved]
                    if card.source_chunk_id
                    else None
                ),
                "bridge": asdict(state.bridge),
                "grounded": state.grounded.grounded if state.grounded else None,
                "grounded_reasoning": state.grounded.reasoning if state.grounded else "",
                "leaked": state.leak.leaked,
                "leaked_phrases": state.leak.leaked_phrases,
            }
        )
        print()

    print("Running adversarial checker validation (hand-crafted bad bridges)...")
    adversarial_results = run_adversarial_checks(chunks, api_key)
    for r in adversarial_results:
        print(f"  {r['case']}: {'PASS' if r['pass'] else 'FAIL'}")

    in_rows = [r for r in card_results if r["in_corpus"]]
    out_rows = [r for r in card_results if not r["in_corpus"]]

    # The gate must fire on in-corpus cards and decline on out-of-corpus
    # ones. An over-permissive gate is the dangerous failure: it produces
    # a confident "verified" badge backed by a corpus that never covered
    # the topic.
    gate_correct = all(r["grounding_was_checked"] for r in in_rows) and all(
        not r["grounding_was_checked"] for r in out_rows
    )

    summary = {
        "n_cards": len(card_results),
        "n_in_corpus": len(in_rows),
        "n_out_of_corpus": len(out_rows),
        "in_corpus_grounding_checked": sum(1 for r in in_rows if r["grounding_was_checked"]),
        "in_corpus_grounded": sum(1 for r in in_rows if r["grounded"]),
        "out_of_corpus_correctly_skipped": sum(
            1 for r in out_rows if not r["grounding_was_checked"]
        ),
        "gate_discrimination_correct": gate_correct,
        "gate_score_range_in_corpus": [
            round(min(r["gate_score"] for r in in_rows), 4),
            round(max(r["gate_score"] for r in in_rows), 4),
        ],
        "gate_score_range_out_of_corpus": [
            round(min(r["gate_score"] for r in out_rows), 4),
            round(max(r["gate_score"] for r in out_rows), 4),
        ],
        "n_leaked": sum(1 for r in card_results if r["leaked"]),
        "n_retrieval_hit_expected_chunk": sum(
            1 for r in in_rows if r["retrieved_expected_chunk"]
        ),
        "adversarial_checks_all_passed": all(r["pass"] for r in adversarial_results),
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "results.json").write_text(
        json.dumps(
            {
                "_provenance": (
                    "Real Claude API calls for bridge generation and "
                    "groundedness judging, against 10 real Krebs-cycle "
                    "cards traced to speedrun/ai/source_material.md "
                    "chunks, plus 5 real MCAT cards on topics the corpus "
                    "does NOT cover (to check the retrieval gate declines "
                    "to judge rather than guessing). Leak check and "
                    "retrieval gate are local, no API call. Adversarial "
                    "cases are hand-crafted, not from the live model, to "
                    "prove the checkers discriminate."
                ),
                "summary": summary,
                "cards": card_results,
                "adversarial_checks": adversarial_results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    s = summary
    print()
    print(f"Retrieval gate: in-corpus scores {s['gate_score_range_in_corpus']}, "
          f"out-of-corpus {s['gate_score_range_out_of_corpus']}")
    print(f"  {s['in_corpus_grounding_checked']}/{s['n_in_corpus']} in-corpus cards checked "
          f"(gate fired), {s['in_corpus_grounded']} judged grounded")
    print(f"  {s['out_of_corpus_correctly_skipped']}/{s['n_out_of_corpus']} out-of-corpus cards "
          "correctly declined (gate withheld a verdict)")
    print(f"  gate discrimination correct: {s['gate_discrimination_correct']}")
    print(f"{s['n_leaked']}/{s['n_cards']} bridges leaked gold-answer phrasing.")
    print(f"{s['n_retrieval_hit_expected_chunk']}/{s['n_in_corpus']} retrievals hit the card's "
          "actual source chunk.")
    print(f"Adversarial checks all passed: {s['adversarial_checks_all_passed']}")
    print(f"\nWrote {OUTPUT_DIR / 'results.json'}")


if __name__ == "__main__":
    main()
