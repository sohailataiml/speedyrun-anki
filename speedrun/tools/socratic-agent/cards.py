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
    # Ground truth: which chunk this fact lives in, or None for cards
    # deliberately outside the corpus (used to check the retrieval gate
    # correctly *declines* to judge groundedness rather than guessing).
    source_chunk_id: str | None


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

# Real MCAT cards on topics source_material.md does NOT cover. The
# grounding check must *decline* to judge these rather than guess - a
# corpus about the Krebs cycle can't vouch for a claim about ribosomes.
# These exist because the retrieval gate is the part most likely to fail
# silently: an over-permissive gate produces a confident "verified" badge
# backed by nothing, which is worse than no badge at all. The glycolysis
# card (PFK-1) is the sharpest case - its *question* shares a lot of
# vocabulary with the corpus ("rate-limiting step", "enzyme"), so only
# scoring the answer separately catches it.
OUT_OF_CORPUS_CARDS: list[TestCard] = [
    TestCard(101, "Cell organelle responsible for protein synthesis", "Ribosome", None),
    TestCard(102, "Primary neurotransmitter released at the neuromuscular junction", "Acetylcholine", None),
    TestCard(103, "Gas law relating pressure and volume at constant temperature", "Boyle's Law (P1V1 = P2V2)", None),
    TestCard(104, "Enzyme that catalyzes the rate-limiting step of glycolysis", "Phosphofructokinase-1 (PFK-1)", None),
    TestCard(105, "Hormone secreted by pancreatic beta cells that lowers blood glucose", "Insulin", None),
]
