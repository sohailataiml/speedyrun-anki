# §9 ablation results

**Method:** 3 builds (interleaved / blocked / unmodified Anki) x study budget, using the REAL Rust queue order per build (study_orders.json) against 30 counterfactual-renamed cards (fictional terms, so the model can't answer from real biochemistry knowledge - see counterfactualize.py). A 'student' (Claude, given only the studied cards) answers each card's verbatim front + 2 rewordings; a blind grader scores correct/partial/incorrect.

**No-study control: 0/90 correct (0%, 95% CI 0%-4%).** This is the contamination check: with nothing studied, the model should score at floor. It does - the counterfactual renaming eliminated prior-knowledge leakage.

## Budget = 10 cards

| Build | Topics covered | n | Correct | Rate | 95% CI |
|---|---|---|---|---|---|
| interleaved | 5 | 90 | 39 | 43% | 34%-54% |
| blocked | 2 | 90 | 25 | 28% | 20%-38% |
| ankiDefault | 2 | 90 | 27 | 30% | 22%-40% |

**Interleaved vs. blocked gap at budget 10: 16%.** The 95% CIs overlap - underpowered to confidently distinguish these conditions at this n.

## Budget = 20 cards

| Build | Topics covered | n | Correct | Rate | 95% CI |
|---|---|---|---|---|---|
| interleaved | 5 | 90 | 42 | 47% | 37%-57% |
| blocked | 4 | 90 | 43 | 48% | 38%-58% |
| ankiDefault | 4 | 90 | 53 | 59% | 49%-68% |

**Interleaved vs. blocked gap at budget 20: -1%.** The 95% CIs overlap - underpowered to confidently distinguish these conditions at this n.

**Limitation, stated per the project's honesty rule:** this ablation measures the effect of topic-coverage *breadth* at a fixed card budget, which is mechanically produced by the real Rust queue order - it does not measure Rohrer & Taylor's discrimination-training mechanism directly, since that operates on a human learner across repeated practice, not an LLM reading cards from a context window once. See speedrun/docs/paraphrase-test.md for the full discussion.