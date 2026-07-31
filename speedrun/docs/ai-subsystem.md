# AI subsystem: card generation, eval, and leakage check

Required by PRD §3 ("every AI output traces to a named source, passes an
eval, and beats a simpler method"), §7, and §8's "AI card check." This
covers the actual pipeline that was run, the real numbers it produced,
and — per the project's honesty rule — what's a real limitation versus
what's solid.

## Pipeline

```
speedrun/ai/source_material.md   original, MCAT-relevant, 14 chunks (kc-01..kc-14)
speedrun/ai/gold_set.json        50 hand-authored QA pairs, cutoff committed before generation ran
speedrun/tools/ai-cardgen/
  baseline.py                    regex/keyword extraction - the "simpler method" to beat
  generate.py                    real generator, Claude (Anthropic API) - source → cards, traced
  eval.py                        grades both card sets against the same rubric, LLM-as-judge
speedrun/tools/leakage-check/
  check.py                       confirms gold-set-specific content never reached the generator
```

**Source material is original content**, written for this project rather
than copied from any textbook or MCAT prep company — see the provenance
note at the top of `source_material.md` for why that matters (it has to
be something the pipeline is legally clear to chunk, generate from, and
reproduce excerpts of).

**The gold set was committed before any generation ran or was looked
at** — `gold_set.json` records a `cutoff_committed_at` timestamp. This is
what "set the cutoff before you look" (PRD §8) means in practice here.

## Provenance

Every generated card carries `source_chunk` (e.g. `kc-07`) and
`source_title`, tracing it back to the exact paragraph of
`source_material.md` it came from — the PRD §3 non-negotiable, checked
mechanically rather than by convention: nothing in the generator's output
schema allows a card without one.

## The baseline (what "beats a simpler method" is measured against)

`baseline.py` splits the source into sentences and pattern-matches
definitional phrasing ("X is/are/was Y") into crude Q&A pairs via regex.
No LLM, no understanding of the text — deliberately the same class of
approach the Brainlift teardown critiques competitor tools for leaning
on. It is not a strawman rigged to lose: it's a real, honest
implementation of "keyword extraction," and it produces exactly the kind
of broken output that approach actually produces (see results below) —
that's the finding, not a tuned outcome.

## Generation

`generate.py` calls Claude (`claude-haiku-4-5-20251001`) once per source
chunk, asking for a fixed number of flashcards per chunk (summing to the
PRD's "generate 50 cards from one real source"). The model is instructed
not to add facts beyond the passage. Every prompt actually sent is logged
to `output/generation_prompts.log`, which the leakage check reads.

## Leakage check

**What it verifies, precisely:** `generate.py`'s code never opens
`gold_set.json` — but that's a claim about the code, not proof. The
leakage check verifies it empirically: it checks whether any *gold-set-specific*
phrasing (n-grams from `gold_set.json` that are **not** already present in
`source_material.md`) shows up in the actual prompt log. If gold-set
content reached the generator through some path other than the expected,
harmless overlap with shared source material, this would catch it.

An earlier, cruder version of this check (comparing gold-set text
directly against the prompt log, without subtracting shared source
overlap) produced 19 false positives — the prompt log necessarily
contains the full source material, and gold answers necessarily share
wording with it, so a naive comparison always fires. Worth stating
plainly rather than hiding: the check itself needed a real fix before
it was trustworthy, and finding that bug is part of what "run a real
check" is supposed to produce.

**Result: passes.** All prompt-log overlap with the gold set is fully
explained by shared source material; zero gold-set-specific content
reached the generator.

## Eval: does the AI beat the baseline?

`eval.py` grades every card (both generators, same rubric, blind to
which method produced it) into the PRD §8 three buckets, using Claude as
an LLM judge given the source chunk and the card.

| | correct_and_useful | correct_but_bad_teaching | wrong |
|---|---|---|---|
| **AI generator** (n=50) | 49 (98%) | 0 (0%) | 1 (2%) |
| **Baseline** (n=18) | 0 (0%) | 17 (94%) | 1 (6%) |

**AI beats the baseline: 98% vs 0% correct-and-useful.** Per PRD §3
("beats a simpler method... or it doesn't ship"), this ships.

The one AI card graded `wrong` is a real, specific error worth naming
rather than glossing over: it described alpha-ketoglutarate being
"reduced" to succinyl-CoA, when the source (and biochemistry) says
"oxidized" — a genuine terminology slip, not a grading-harness quirk.
Reporting it here because a report with zero acknowledged errors is less
credible than one that shows the grader is actually discriminating, not
rubber-stamping.

Sample baseline failure (typical, not cherry-picked):

> Front: "What is Its job?"
> Back: "to finish oxidizing the carbon that entered as glucose,
> harvesting high-energy electrons along the way"

Broken pronoun reference, unanswerable as a standalone card — exactly
what a regex extractor produces when it has no model of what "its" or
"this" refers to.

## Stated limitations (not hidden)

- **Grading is LLM-as-judge, not human-graded.** A real limitation of
  this eval, stated in `eval_results.json`'s own `grading_limitation`
  field, not just in this doc.
- **The gold set and source material are hand-authored for this
  pipeline**, not real MCAT content (couldn't be, for copyright reasons)
  and not independently validated by a subject-matter expert beyond the
  author's own biochemistry knowledge.
- **The comparison is against one baseline implementation.** A more
  sophisticated baseline (e.g. vector-search retrieval, which the PRD
  also names as an acceptable comparison point) might close some of the
  gap; regex extraction is the honest "simpler method" that was actually
  built and measured, not the strongest possible one.

## AI-off behavior

None of the Scoring Service (`mastery_query`, `give_up_gate`,
`performance_query`, `readiness_query`) or the desktop dashboard touches
this pipeline at all — it's a standalone offline tool under
`speedrun/tools/ai-cardgen/`, not wired into the review loop or backend.
"Both apps run with AI off" (PRD non-negotiable) is true by construction
here: there's nothing to turn off because nothing in the required path
depends on it.

## Rerunning this

```bash
export ANTHROPIC_API_KEY=...   # or SPEEDRUN_ANTHROPIC_KEY
python speedrun/tools/ai-cardgen/baseline.py
python speedrun/tools/ai-cardgen/generate.py
python speedrun/tools/leakage-check/check.py
python speedrun/tools/ai-cardgen/eval.py
```
All four are pure-stdlib Python (no new dependency), matching the rest of
`speedrun/tools/`.
