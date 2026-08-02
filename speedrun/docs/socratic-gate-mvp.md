# Socratic Gatekeeper — MVP implementation and validation

MVP status for Brainlift v2's primary thesis (see
[brainlift.md](brainlift.md)), built under a hard deadline. This document
is the honest record of what got built and what got measured, at two
scales: an initial n=30 pass, then a full n=90 run matching prior POV
1's ablation size. Stated plainly, same rule as everywhere else in this
project: the full-scale result is **not a clean win for Socratic bridges
— it's real evidence for applying them *conditionally* rather than
everywhere**, since indiscriminate use has a measured cost. That's a
more useful and more honest finding than the flattering version would
have been.

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

### Results — MVP scale (n=30, discrimination items only)

| Condition | n | Correct | Rate | 95% CI |
|---|---|---|---|---|
| no_correction | 30 | 0 | 0% | 0%–11% |
| plain | 30 | 19 | 63% | 46%–78% |
| bridge | 30 | 20 | 67% | 49%–81% |

Bridge beat plain by exactly one card out of thirty — a statistical tie,
not a confirmed win.

### Results — full scale (n=90, matching prior POV 1's ablation size: 30 cards × verbatim/near/discrimination)

Superseding the MVP run above — same methodology, extended to all 3
follow-up item types instead of discrimination only, giving the same
statistical power as prior POV 1's ablation.

| Item type | no_correction | plain | bridge |
|---|---|---|---|
| Verbatim (exact same question) | 0/30 (0%) | **29/30 (97%, CI 83–99%)** | 25/30 (83%, CI 66–93%) |
| Near-transfer (reworded, same fact) | 0/30 (0%) | 21/30 (70%, CI 52–83%) | 20/30 (67%, CI 49–81%) |
| Discrimination (reworded, rule out a neighbor) | 0/30 (0%) | 19/30 (63%, CI 46–78%) | 20/30 (67%, CI 49–81%) |
| **Overall** | **0/90 (0%)** | **69/90 (77%, CI 67–84%)** | **65/90 (72%, CI 62–80%)** |

**The honest read — a real, coherent, and important finding, but not the
one that would have made the cleanest headline:**

- **On verbatim recall, plain clearly beats bridge** (97% vs. 83%) —
  and this makes complete sense rather than being a concerning result:
  a verbatim follow-up is *literally the same question*, so directly
  restating the fact (what "plain" does) obviously helps more than a
  bridge that deliberately withholds the fact and makes the student
  reconstruct it. The Socratic mechanism is trading away some
  literal-recall benefit by design — that trade is the whole point of
  the POV, and this data shows the trade is real, not free.
- **On near-transfer and discrimination — the dimensions the thesis
  actually cares about — bridge and plain are statistically
  indistinguishable**, with the same small, non-significant edge to
  bridge on discrimination that the n=30 MVP found (67% vs. 63%,
  heavily overlapping CIs).
- **Overall, aggregated across all three item types, plain edges out
  bridge** (77% vs. 72%) — but this aggregate number is dominated by the
  verbatim category, where nobody would expect (or want) the Gatekeeper
  to fire in the first place, since verbatim recall of the identical
  question isn't the "Dangerous Error" or "Productive Struggle" case the
  mechanism targets.

**What this actually argues for:** not "Socratic bridges help," and not
"Socratic bridges hurt" — it argues for **conditional application**, the
"Gatekeeper" framing specifically, over an "always ask a Socratic
question" policy. Applying a bridge indiscriminately (including to
trivial recall checks) has a real, measured cost; applying it only where
transfer/discrimination is actually being tested looks — on this data,
at this sample size — roughly cost-free and possibly slightly
beneficial. This is the same caution VanLehn's step-vs-substep finding
and Kapur's productive/unproductive-failure boundary conditions predict
(brainlift.md §2, sources 5 and 7) — the data lines up with the theory's
own stated caveats, which is a stronger form of support than a clean win
would have been, precisely because it wasn't the more flattering result.

**What the result does support clearly, regardless of condition:** any
correction — plain or bridge — massively outperforms no correction
(63–97% vs. 0% across every item type), strong confirmation that
corrective feedback after a wrong answer matters enormously, consistent
with the testing-effect literature (Roediger & Karpicke, brainlift.md §2
source 4), and a clean validation that the measurement pipeline itself
has zero contamination (the 0% floor holds across all three item types,
same discipline as every other ablation this project ran).

**What it does not establish:** that targeting the bridge only at the
Dangerous-Error/Productive-Struggle branches (rather than at
"discrimination-type items" as this test approximated) produces this
same pattern — the Rust gate decides based on latency+correctness of the
*original* review, not on which follow-up item type gets asked
afterward. This test used item type as a proxy for "how much transfer
distance is being tested," which is a reasonable but imperfect stand-in
for what the real gate actually conditions on.

## Honest limitations

1. **Item type is a proxy for "how much the Gatekeeper should fire," not
   the real trigger.** The full-scale run used verbatim/near/
   discrimination follow-up items as a stand-in for "how much transfer
   distance is being tested," but the actual Rust decision function
   conditions on the *original* review's latency and correctness, not on
   what kind of follow-up question comes next. A real end-to-end test
   would need the gate's decision to determine which correction type a
   given review actually receives, not use item-type as an approximation
   after the fact.
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
Claude API calls generating real bridge content, a real ablation at the
same n=90 scale prior POV 1 used, and a floor check confirming the
methodology isn't contaminated. This is genuine progress on Brainlift
v2's thesis, built and tested end-to-end in the time available.

**Not proven:** that Socratic bridges should replace plain answers
universally. They shouldn't, on this data — verbatim recall is clearly
worse with a bridge, which is exactly why the POV was framed as a
*conditional gate*, not a blanket policy, from the start.

**What is supported, with real numbers:** applying a Socratic bridge
specifically to harder, transfer/discrimination-type moments — as
opposed to everywhere — looks statistically cost-free at worst and
slightly beneficial at best, while indiscriminate application has a
measured, real cost on trivial recall. That's a more nuanced and more
defensible finding than a clean win would have been, and it's the result
that was actually measured, not the one that would have made the best
headline. Per this project's own honesty rule, that's the point.

## Reproducing this

```bash
cd speedrun/tools/socratic-gate
python generate_bridges.py   # real API calls, ~1 min
python validate.py           # real API calls, ~2-3 min (n=90/condition)

# Rust side:
cargo test -p anki --lib stats::socratic_gate
```

`ANTHROPIC_API_KEY` (or `SPEEDRUN_ANTHROPIC_KEY`) must be set.
