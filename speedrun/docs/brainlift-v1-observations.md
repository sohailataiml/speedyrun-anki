# Post-implementation observations: Brainlift v1

Written after implementing and empirically testing what
[brainlift-v1.md](brainlift-v1.md) proposed, before the spiky POV pivoted
to v2 (see [brainlift.md](brainlift.md)). This is the honest accounting
of what v1 actually got right, what it got wrong, and — a distinct
question from either — which of the metrics it introduced were ever
proven to *help* a student, as opposed to just being built and computed
correctly. Kept as its own document rather than folded into brainlift.md
so it doesn't get lost or silently overwritten by the next pivot.

---

## 1. What v1's three POVs claimed, and what actually got tested

Only **POV 1** was taken through a real ablation. POV 2 and POV 3 were
built into the traceability table but never empirically tested — that's
stated here plainly, not implied by omission.

### POV 1 (the thesis) — partially right, corrected shape

**What v1 predicted:** past a point, more flashcard review stops
improving exam-item accuracy, because isolated card recall never trains
the discrimination skill ("which of several similar facts applies here")
that real exam questions require — interleaved review should close that
gap.

**What got proven right:**
- **The underlying mechanism held.** A real 20-point gap: 93% of
  near-transfer rewordings were answerable from a card alone, only 73%
  of discrimination-style rewordings were. Recall and discrimination are
  measurably separable skills — the thesis's core premise.
- **Interleaved review really does beat blocked review** — a real
  16-point gap at a 10-card study budget (43% vs. 28% on
  reworded/discrimination items), produced by an actual Rust scheduling
  feature (`speedrunTopicOrder`), not a simulation.
- **The measurement itself was clean.** A no-study control scored 0/90 —
  proof the test wasn't contaminated by the model already knowing
  biochemistry, which is what makes the other numbers trustworthy rather
  than an artifact.

**What v1 got wrong, and had to correct:** v1 assumed the interleaving
advantage would hold regardless of how deep or shallow the review
session was. It doesn't — the gap **closed entirely by a 20-card
budget**, once blocked review caught up on topic coverage anyway. The
honest revised claim is "interleaving matters early in a session, not
as a blanket always-interleave policy" — a materially weaker claim than
v1 shipped with, reported as such rather than as a clean win.

Full methodology and numbers: [paraphrase-test.md](paraphrase-test.md).

### POV 2 (decomposed scores) — never tested

The three-score dashboard got built and verified live on both desktop
and Android. But the actual claim behind it — that showing three
separate scores helps students target their weak area better than one
blended number would — was never run through any ablation. **Built, not
proven.**

### POV 3 (grade contamination) — never tested

The claim that self-graded "Good" taps are a metacognitively biased
signal, and that response-latency flagging could catch suspiciously-fast
grades, was never empirically tested. It was later folded into Brainlift
v2's Socratic Gatekeeper POV as a sharper, mechanism-level version of the
same underlying idea — but that's a new proposal, not a validated result
either (see [brainlift.md §7](brainlift.md)).

---

## 2. The metrics v1 introduced — built and real, but not proven to help

This is a distinct question from "was the POV right." A metric can be
computed correctly, live, end-to-end, with no fabrication — and still
never have been tested for whether *showing it to a student* actually
improves their decisions or outcomes. That distinction matters and is
easy to blur, so it's made explicit here.

| Metric | What it is | Proven *accurate*? | Proven to *help*? |
|---|---|---|---|
| **Memory** | FSRS retrievability, restated as a per-topic score | Yes — it's FSRS's own already-validated math, nothing new to prove | Never tested |
| **Performance** | Predicts exam-question accuracy from mastery/difficulty/timing/coverage | **No** — trained on synthetic data throughout, never checked against real exam-question outcomes | Never tested |
| **Readiness** | Projects Performance into an MCAT score range via a population-percentile mapping against AAMC's published distribution | **No** — stated in the dashboard's own copy: "a stated simplifying assumption, not validated against real student outcomes" | Never tested |
| **Give-up gate** (200 reviews / 50% coverage) | Refuses to show Performance/Readiness below these thresholds | Thresholds are round numbers picked by design, not fitted to any data | Never tested — no experiment checked whether refusing to score below this line produces better decisions than showing a number anyway |

**The one thing that came close to a real "does this help" test** wasn't
any of these metrics — it was the *scheduling change* (interleaved vs.
blocked review order), which tested whether changing what order cards
are studied in improves accuracy on transfer questions (POV 1, above).
That's a different claim from "does showing a Performance/Readiness
score help students," and it remains the only place in the project where
an actual behavioral/outcome ablation happened.

**Summary:** every new metric is real in the sense that matters for a
build — live RPCs, correct math, verified end-to-end. None of them
cleared the higher bar of "proven to help a student make a better
decision." One of them (Performance) isn't even proven *accurate* yet,
since its training data is synthetic rather than real held-back exam
questions — a gap flagged consistently in `ARCHITECTURE.md`'s status
line throughout the build, not something new surfaced here.

---

## 3. What this implies for next steps, if picked up

- **Nearest-term, clearest test design already implied:** POV 2's claim
  (does three-score decomposition change what students study next,
  compared to one blended number) has the most directly reusable
  measurement infrastructure — the same LLM-as-simulated-decision-maker
  pattern from `speedrun/tools/paraphrase-test/` could plausibly be
  adapted (show a simulated "student" either the blended or decomposed
  view, ask what they'd study next, check if it matches their actual
  weakest area) — not attempted, but the path is visible.
- **Performance's synthetic-data gap is the most consequential unproven
  claim in the whole scoring stack** — Readiness is built directly on
  top of Performance, so neither can be considered validated until real
  held-back exam-question data replaces the synthetic training set.
- **The give-up gate's thresholds (200 / 50%) are unvalidated defaults,**
  not fitted or tested values — worth flagging if anyone treats them as
  more principled than they are.
