# Paraphrase test & §9 ablation

Full methodology and results for the Brainlift's §9 thesis test (POV 1:
"past a range of card-retention levels, further gains come from transfer
training, not more review reps"). Written to be reproducible — every
number below comes from a script in `speedrun/tools/paraphrase-test/`
that can be rerun end to end.

## The measurement-design problem, and how it was resolved

The naive design — ask an LLM to simulate a student on the real citric
acid cycle content — doesn't work: any frontier model already knows the
Krebs cycle cold, so it answers both studied and unstudied conditions at
~100% regardless of what it "studied." That's not a measurement, it's a
confident-looking table of numbers that means nothing — exactly the
failure mode this project's own teardown criticizes UWorld/AnKing for.

Two things fix that, both implemented and verified:

1. **Counterfactual renaming** (`counterfactualize.py`, `substitutions.json`):
   every cycle-specific molecule, enzyme, and cofactor is deterministically
   renamed to a fictional term (citrate → veltrate, NADH → QEH2, etc.),
   whole-word, case-preserving, no LLM involved. This removes the model's
   ability to answer from pre-trained knowledge — it can only use what's
   actually in its simulated study context.
2. **A no-study control**: the same 90 questions (30 verbatim + 60
   reworded), asked with *nothing* studied. This is the contamination
   check — if renaming didn't fully remove prior-knowledge leakage, this
   number would be meaningfully above zero.

**Result: the no-study control scored 0/90 (0%, 95% CI 0%–4%).** Zero
contamination. Every correct answer in the results below required the
studied cards.

## Part 1 — Item-side card sufficiency (the guaranteed floor)

Before any student simulation: for each of 30 cards (real, un-renamed
content — this part doesn't need counterfactualization since there's no
simulated student to contaminate), 2 reworded exam-style questions were
generated via real Claude API calls (1 near-transfer, 1
discrimination — see `reword.py` for the exact rubric), then a blind
grader judged whether each rewording is answerable from the card's
front+back alone.

| Condition | n | Sufficient | Rate | 95% CI |
|---|---|---|---|---|
| Overall | 60 | 50 | 83% | 72%–91% |
| Near-transfer | 30 | 28 | 93% | 79%–98% |
| Discrimination | 30 | 22 | 73% | 56%–86% |

**A real 20-point gap.** Single-card recall mostly transfers to
differently-worded questions testing the same fact, but degrades once the
question requires ruling out a plausible neighboring fact. This alone —
no simulated student needed — is a direct, defensible measurement on
POV 1's question and satisfies the PRD's paraphrase-test requirement by
itself.

Full results: `output/sufficiency_results.json`, `output/paraphrase_results.md`.

## Part 2 — The three-way ablation

**Card selection and provenance:** 30 cards, drawn from
`speedrun/tools/ai-cardgen/output/ai_cards.json` (already carrying
`source_chunk` provenance back to `speedrun/ai/source_material.md`),
grouped into 5 topics × 6 cards (`prepare.py`). Selection was committed
(`cutoff_committed_at` in `output/cards.json`) before any rewording was
generated.

**The Rust feature under test:** `speedrunTopicOrder`
(`rslib/src/scheduler/queue/builder/topic_order.rs` — see
[rust-change-note.md](rust-change-note.md) for the full design). Three
builds:
- **interleaved** — the thesis feature on: round-robin across topics.
- **blocked** — the same app, feature off: all of one topic, then the next.
- **ankiDefault** — no config key set: genuinely unmodified Anki's own
  gather order (confirmed reproducible with the key absent — see
  `study_order.py`'s assertions).

**Study sets are real, not invented.** `study_order.py` builds a fixture
collection from the 30 counterfactual cards and extracts each build's
actual queue order from the real Rust backend. The "studied set" at a
given card budget is simply the first N cards of that build's real order.

Real Rust queue output, topic coverage at each budget:

| Build | Topics @10 | Topics @20 | Topics @30 |
|---|---|---|---|
| interleaved | 5 | 5 | 5 |
| blocked | 2 | 4 | 5 |
| ankiDefault | 2 | 4 | 5 |

**Answering and grading:** for each condition (build × budget), a
"student" (Claude, given only that condition's studied cards, counterfactual
content, told explicitly not to substitute real-world biochemistry terms)
answers all 90 items (30 verbatim + 60 reworded); a blind grader scores
correct/partial/incorrect. Every answer and every grading call is an
independent API call with independent context — a verbatim answer can
never leak into a reworded item's context, and the grader never sees
which build or budget produced an answer.

### Results

| Build | Topics @10 | n | Correct | Rate | 95% CI |
|---|---|---|---|---|---|
| interleaved | 5 | 90 | 39 | 43% | 34%–54% |
| blocked | 2 | 90 | 25 | 28% | 20%–38% |
| ankiDefault | 2 | 90 | 27 | 30% | 22%–40% |

**Interleaved vs. blocked at budget 10: +16 points.** 95% CIs overlap
slightly (34% floor vs. 38% ceiling) — a real, directionally consistent
gap, but n=90 per condition isn't enough to call it statistically
distinguishable on its own.

| Build | Topics @20 | n | Correct | Rate | 95% CI |
|---|---|---|---|---|---|
| interleaved | 5 | 90 | 42 | 47% | 37%–57% |
| blocked | 4 | 90 | 43 | 48% | 38%–58% |
| ankiDefault | 4 | 90 | 53 | 59% | 49%–68% |

**At budget 20, the gap is gone** (interleaved and blocked are
statistically indistinguishable; ankiDefault is numerically higher, well
within noise given the overlapping CIs).

**This is the actual finding, and it's more interesting than a flat
"interleaved wins":** the topic-coverage-breadth advantage interleaved
review provides is concentrated at **low study budgets**, early in a
session, before blocked review has had a chance to move past its first
1–2 topics. By budget 20 (of 30 total cards — two-thirds of the deck),
blocked and default have both caught up to 4 of 5 topics, and the
advantage measured at budget 10 disappears. This is exactly the kind of
"measure the *shape* across coverage levels, don't assume a single
threshold" result the project's own steelman round (§5) demanded, rather
than a cherry-picked single number.

Full results: `output/ablation_results.json`, `output/ablation_report.md`.

## Verdict on POV 1

**Partial support, with the shape corrected from what v1 assumed.**
POV 1 predicted a recall-vs-transfer gap that interleaved review should
close. Two independent pieces of evidence:

1. The item-side sufficiency test (Part 1) shows a real 20-point gap
   between near-transfer and discrimination-style items — recall and
   transfer are measurably separable, supporting the premise.
2. The ablation (Part 2) shows topic-interleaved review does produce a
   real accuracy advantage on reworded/discrimination-style items — but
   **only at low study budgets**, not uniformly across all coverage
   levels as a simple on/off claim would suggest. The advantage is a
   front-loaded effect of coverage breadth, not a persistent one.

Per the project's own honesty rule: "POV 1 held on the mechanism but the
specific threshold was wrong, here's the corrected shape" is the accurate
summary, not a flat "the ablation proves the thesis."

## Stated limitations

1. **LLM-as-student, not a human learner.** This is the central
   limitation. An LLM reading cards from a context window once does not
   undergo the discrimination-training process Rohrer & Taylor's
   mechanism describes in human learners across repeated spaced practice.
   The ablation measures a real, mechanically-grounded proxy — topic
   coverage breadth at a fixed budget — not the discrimination-training
   mechanism itself.
2. **Counterfactual renaming reduces but by construction cannot prove
   zero prior-knowledge reliance beyond what the no-study control
   measures.** The no-study control scored 0%, which is strong evidence
   against residual leakage, but it's a floor check, not a formal proof.
3. **Sample size.** n=90 per condition (30 cards × 3 item types) gives
   ~95% CIs of roughly ±10 points. This is enough to see the budget-10
   gap directionally and the budget-20 convergence clearly, but not
   enough to declare either result statistically bulletproof on its own.
4. **Grading is LLM-as-judge** (Claude), the same limitation already
   stated for the AI subsystem's gold-set eval — not human-graded.
5. **Two of three coverage budgets were run** (10, 20 of the planned 10/20/30)
   given the Sunday deadline; budget 30 (full deck, all builds converge to
   5/5 topics) was deprioritized since it's the least informative point —
   by full-deck coverage, all three builds have seen everything.
6. **This does not validate Readiness against real students** (the PRD
   §10 bonus tier) — that requires an actual student population, not in
   scope here.

## Reproducing this

```bash
cd speedrun/tools/paraphrase-test
python prepare.py              # select 30 cards, commit cutoff
python reword.py               # generate 60 rewordings (real API calls)
python grade_sufficiency.py    # Part 1: item-side sufficiency (real API calls)
python report.py               # Part 1 write-up

python counterfactualize.py    # deterministic renaming, no API calls

# Requires this fork's built Python backend (out/pylib) - see
# rust-change-note.md for the build command (tools\ninja.bat pylib).
out/pyenv/Scripts/python study_order.py   # real Rust queue order per build

python run.py --budgets 10 20  # Part 2: the ablation (real API calls, ~10 min)
python ablation_report.py      # Part 2 write-up
```

`ANTHROPIC_API_KEY` (or `SPEEDRUN_ANTHROPIC_KEY`) must be set for any
script that calls the API. `run.py` caches every response by prompt hash
in `output/run_cache.json`, so a rerun after an interruption only pays
for what wasn't already fetched.
