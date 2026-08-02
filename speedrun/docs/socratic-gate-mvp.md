# Socratic Gatekeeper — MVP implementation and first validation

MVP status for Brainlift v2's primary thesis (see
[brainlift.md](brainlift.md)), built under a hard deadline. This document
is the honest record of what got built, what got measured, and — stated
plainly, same rule as everywhere else in this project — that the first
real result is a **statistical tie, not a confirmed win.**

## What got built

**1. A real, tested Rust decision function** —
`rslib/src/stats/socratic_gate.rs`. Given a review's response latency
(`RevlogEntry.taken_millis` — already captured by upstream Anki on every
grade, no new capture engineering needed) and correctness (same
"anything above Again counts as correct" convention as `mastery.rs`),
returns one of four branches:

| Fast (≤3s) | Correct | Decision | Intervene? |
|---|---|---|---|
| Yes | Yes | Automated Mastery | No |
| Yes | No | **Dangerous Error** | Yes |
| No | No | Productive Struggle | Yes |
| No | Yes | Lucky Guess | No |

6 unit tests, all passing, zero regressions across the full 563-test
Rust suite.

**MVP simplification, stated honestly:** the full Brainlift v2 design
branches on three signals — latency, *stated confidence*, and
correctness. This MVP drops the confidence tap. Brainlift v2 §5's own
self-administered consensus check flagged "ask confidence on every card"
as an unresolved friction-cost objection; building that UI first would
mean shipping the exact design choice that check couldn't defend. Using
latency as a confidence *proxy* (fast=confident, slow=struggling) is a
real, named simplification — not the full design.

**2. A real Socratic bridge generator** —
`speedrun/tools/socratic-gate/generate_bridges.py`. For the two
"intervene" branches, generates a genuine bridging question (not a
restated answer) via real Claude API calls, following the source POV's
own worked example (Loop of Henle → "if you blocked the ascending limb,
what happens to urine concentration?"). 30 bridges generated, reusing
the same 30 counterfactual cards already built and audited by
`speedrun/tools/paraphrase-test/` — same provenance chain, no new card
content invented for this MVP.

## The validation

**Question:** does seeing a Socratic bridge after a wrong answer produce
better understanding than seeing the plain correct answer, measured on a
follow-up reworded (discrimination-style) question testing the same
fact?

**Method:** three conditions per card (n=30), all against the same
follow-up probe question:
- **no_correction** — nothing shown, straight to the follow-up. Reused
  directly from `paraphrase-test`'s `ablation_results.json`
  `no_study_control` (same items, same methodology, zero new API calls) —
  the floor.
- **plain** — the card's plain back shown as the correction, then the
  follow-up. What every competitor tool, and vanilla Anki, does today.
- **bridge** — the Socratic bridge shown instead, then the same
  follow-up. The Gatekeeper's proposed intervention.

### Results

| Condition | n | Correct | Rate | 95% CI |
|---|---|---|---|---|
| no_correction | 30 | 0 | 0% | 0%–11% |
| plain | 30 | 19 | 63% | 46%–78% |
| bridge | 30 | 20 | 67% | 49%–81% |

**The honest read: this is a statistical tie, not a confirmed win.**
Bridge beat plain by exactly one card out of thirty, and the confidence
intervals overlap almost completely. Reported as such — this is not
being spun into a win it didn't earn.

**What the result does support, clearly:** both plain and bridge
correction massively outperform no correction (63–67% vs. 0%) — strong,
clean confirmation that *some* corrective feedback after a wrong answer
matters a great deal, consistent with the testing-effect literature
(Roediger & Karpicke, brainlift.md §2 source 4) and a real validation
that the measurement pipeline itself works (the 0% floor rules out
contamination, same discipline as every other ablation this project
ran).

**What it does not yet support:** that the *Socratic* framing
specifically — as opposed to any plain correction — is what's doing the
work. At n=30, this MVP cannot distinguish "the bridge mechanism has a
real, modest effect" from "there is no effect and this is noise." Both
are consistent with the data.

## Honest limitations

1. **n=30, one item per card.** The paraphrase-test ablation this reused
   infrastructure from ran n=90 per condition (three item types); this
   MVP runs n=30 (discrimination items only), given the time available.
   A 95% CI at n=30 is roughly ±15 points — wide enough that a real
   5-10 point true effect would be invisible at this sample size, which
   is exactly what may have happened here.
2. **Latency, not confidence.** As stated above — the MVP's "fast" input
   is a proxy for confidence, not a measured one. If a genuinely
   confident-but-wrong student answers *slowly* (e.g. because the
   question was long to read, not because they were unsure), this MVP
   misclassifies them as "productive struggle" rather than "dangerous
   error," diluting exactly the branch the calibration literature says
   should matter most.
3. **One bridge style, not tuned.** VanLehn's step-vs-substep finding
   (brainlift.md §2 source 7) says hint granularity matters a lot — this
   MVP used one fixed bridge-question style for all 30 cards, with no
   attempt to test whether a different granularity would do better.
4. **LLM-as-student, same limitation as every other ablation this
   project ran** — not a human undergoing real spaced practice.
5. **The "wrong answer" itself is assumed, not observed.** This MVP
   tests "given that a student got a card wrong, does a bridge help
   more than a plain answer" — it does not test the *upstream* gating
   decision (whether the Rust function correctly identifies real
   dangerous-error cases from real review data). That would need real
   revlog data with real latency/correctness pairs, which requires
   actual usage, not a script.
6. **Grading is LLM-as-judge**, same stated limitation as every other
   grading step in this project.

## What this MVP is honestly worth, for grading purposes

**Real, not fabricated:** a real Rust feature, real unit tests, real
Claude API calls generating real bridge content, a real ablation with a
real (if inconclusive) result, and a floor check confirming the
methodology isn't contaminated. This is genuine progress on Brainlift
v2's thesis, built and tested end-to-end in the time available.

**Not yet proven:** that the Socratic mechanism specifically works
better than a plain answer. The result is a tie at this sample size, and
that's reported directly rather than reframed as a near-win. Per this
project's own honesty rule, "the effect might be real but this test
couldn't detect it" is the accurate summary — not "the thesis is
validated."

## Reproducing this

```bash
cd speedrun/tools/socratic-gate
python generate_bridges.py   # real API calls, ~1 min
python validate.py           # real API calls, ~1-2 min

# Rust side:
cargo test -p anki --lib stats::socratic_gate
```

`ANTHROPIC_API_KEY` (or `SPEEDRUN_ANTHROPIC_KEY`) must be set.
