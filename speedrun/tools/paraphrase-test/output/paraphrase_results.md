# Paraphrase test — Tier 0 results (item-side card-sufficiency)

**Method:** for each of 30 cards, 2 reworded exam-style questions (1 near-transfer, 1 discrimination) were generated via real Claude API calls, then a blind grader judged whether each rewording is answerable using only that card's front+back. Grading model: `claude-haiku-4-5-20251001`. No simulated student population — a direct per-item measurement of transfer distance.

| Condition | n | Sufficient | Rate | 95% CI |
|---|---|---|---|---|
| Overall | 60 | 50 | 83% | 72%–91% |
| Near-transfer | 30 | 28 | 93% | 79%–98% |
| Discrimination | 30 | 22 | 73% | 56%–86% |

**Near-vs-discrimination gap: 20%.**

This is a real, non-ceiling gap: single-card recall mostly carries to differently-worded questions testing the same fact (near-transfer), but degrades meaningfully once the question requires ruling out a plausible neighboring fact (discrimination) — directionally consistent with POV 1's claim that isolated card recall and discrimination are separable skills. **This does not by itself validate the topic-interleaved review mechanism** — it measures a static property of card-vs-question distance, not what training (interleaved practice) closes the gap. See the three-way ablation (if run) for that test.