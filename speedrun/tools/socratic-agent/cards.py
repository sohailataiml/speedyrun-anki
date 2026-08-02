"""Real MCAT-topic test cards, each fact drawn directly from a specific
chunk of speedrun/ai/source_material.md - not the counterfactual/renamed
cards paraphrase-test and socratic-gate use (those exist for a different
purpose: leak-safe LLM-as-judge grading with no prior model exposure).
These cards need to be real, plain Krebs-cycle content, because the
whole point here is checking whether the bridge Claude generates is
grounded in a real, named, retrievable source - a renamed/fictional
card would have no real source to check against.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TestCard:
    card_id: int
    front: str
    back: str
    source_chunk_id: str  # ground truth: which chunk this fact actually lives in


CARDS: list[TestCard] = [
    TestCard(1, "What are the two major products the citric acid cycle hands off to the electron transport chain?", "NADH and FADH2", "kc-01"),
    TestCard(2, "In which cellular compartment does the citric acid cycle take place?", "The mitochondrial matrix", "kc-02"),
    TestCard(3, "What enzyme converts pyruvate into acetyl-CoA before the citric acid cycle begins?", "The pyruvate dehydrogenase complex", "kc-03"),
    TestCard(4, "Which enzyme catalyzes the first step of the citric acid cycle, combining acetyl-CoA with oxaloacetate?", "Citrate synthase", "kc-04"),
    TestCard(5, "Which enzyme is generally considered the rate-limiting step of the citric acid cycle?", "Isocitrate dehydrogenase", "kc-06"),
    TestCard(6, "Which step of the citric acid cycle produces GTP or ATP directly via substrate-level phosphorylation?", "Succinyl-CoA synthetase (succinyl-CoA to succinate)", "kc-08"),
    TestCard(7, "Which citric acid cycle enzyme is also Complex II of the electron transport chain?", "Succinate dehydrogenase", "kc-09"),
    TestCard(8, "How many NADH, FADH2, and GTP/ATP does one turn of the citric acid cycle produce?", "3 NADH, 1 FADH2, 1 GTP (or ATP)", "kc-11"),
    TestCard(9, "What does it mean that the citric acid cycle is amphibolic?", "It runs both catabolically (breaking down fuel for energy) and anabolically (supplying biosynthesis precursors)", "kc-13"),
    TestCard(10, "How many times does the citric acid cycle turn per glucose molecule, and why?", "Twice - because one glucose yields two pyruvate, and therefore two acetyl-CoA", "kc-14"),
]
