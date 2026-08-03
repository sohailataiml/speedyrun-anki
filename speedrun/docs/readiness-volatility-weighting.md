# Readiness, weighted by latency (Brainlift v3 §8)

> *"Readiness Score: A composite of Memory and Performance, weighted by
> Latency Volatility."*
> *"A 0.5x multiplier to the score of any card answered faster than the
> calculated Minimum Reading Time."*

## Memory is already in there — adding it again would double-count

§8 calls Readiness a composite of Memory *and* Performance. It already is,
and saying so precisely matters:

`performance_model.rs` takes **mean topic mastery** — which *is* the
Memory score — as one of its four inputs. Performance therefore carries
Memory. Adding a separate Memory term to Readiness would make the score
move twice for one change in recall, which is a real modelling error, not
a rounding detail.

So Readiness = `map(Performance × latency weight)`, and Performance
already contains Memory. That satisfies §8 without double-counting.

## The multiplier applies to accuracy, not to the score

Read literally, "a 0.5x multiplier to the **score**" would halve a
projected MCAT of 500 to 250 — below the scale's 472 floor and
meaningless, since the MCAT scale has no true zero.

The only coherent reading is to apply it to the **predicted accuracy**
before that accuracy is mapped onto the scale. Aggregated over the scored
topics:

```
weight = 1 - 0.5 × (reviews below minimum reading time / graded reviews)
```

No reflexes leaves the score untouched at `1.0`; every review a reflex
gives `0.5`, exactly the docx's multiplier as a floor rather than a slope
that could run past it.

## Reflex, not volatility — and why they are used differently

This penalises the **spacebar reflex** (answering faster than the card
could be read), *not* low volatility. The two are different signals and
get deliberately different responses:

| Signal | Response | Where |
|---|---|---|
| Low latency volatility | **Refuse to score at all** | `give_up_gate.rs` |
| Reviews faster than readable | **Discount the score** | here |

A refusal is strictly stronger than a discount. Applying both to the same
evidence would punish it twice, and in practice the refusal fires first
and the discount never runs — which is the correct ordering, and is why
demonstrating the discount needs a deck that is *not* rote.

## What it actually does to the number

Verified end to end on a synthetic deck that studies honestly on two
topics and taps through on two:

```
  cell_division    vol=0.98  graded= 60  too_fast= 30
  gas_laws         vol=0.37  graded= 60  too_fast=  0
  neuromuscular    vol=0.98  graded= 60  too_fast= 30
  water_solutions  vol=0.37  graded= 60  too_fast=  0

  raw model accuracy   : 0.451
  volatility weight    : 0.875   (60 reflex reviews of 240)
  weighted accuracy    : 0.395
  PROJECTED MCAT       : 498     (range 489-507)
```

Note the volatility column: all four topics are well clear of the 0.20
rote line, so the give-up rule stays quiet and the score is produced —
then discounted.

### The effect is smaller than the multiplier sounds

Worth stating plainly, because "0.5x" reads as dramatic and isn't:

| reflex share | weight | weighted accuracy | MCAT | drop |
|---|---|---|---|---|
| 0% | 1.000 | 0.451 | 499 | — |
| 25% | 0.875 | 0.395 | 498 | −1 |
| 50% | 0.750 | 0.338 | 496 | −3 |
| 100% | 0.500 | 0.226 | 493 | −6 |

Even halving the accuracy moves the projected score by about **six
points**. That is not a bug in the implementation — it is what happens
when a multiplicative penalty passes through a *percentile* transform.
The MCAT scale is compressed near its mean (SD ≈ 10.6), so large moves in
probability become small moves in score.

Anyone expecting "answering everything too fast halves your score" should
know that it does not, and cannot, under the mapping this project already
uses. If a stronger penalty is wanted, it has to be argued for on its own
terms rather than smuggled in as a reading of "0.5x".

## The penalty is shown, not folded in silently

`ReadinessData` carries `latency_volatility_weight` and
`spacebar_reflex_reviews`, and the desktop dashboard renders a warning
whenever the weight is below 1.0:

> ⚠ Score reduced to 88% of the model's estimate: 60 review(s) were
> answered faster than the card could be read. Those count half, because a
> review that outran the prompt is not evidence of recall.

Hiding the adjustment would leave a student comparing a marked-down score
against someone else's unmarked one without knowing the difference — the
same "dressing a guess as a measurement" failure the PRD calls an
automatic fail. No line is shown when no penalty applied; "no penalty" on
every honest deck is noise.

## A correction to an earlier claim in the pivot plan

The plan warned that this phase would invalidate the held-back **Brier
0.168** calibration figure. **That was wrong**, and it was checked before
being acted on. Brier 0.168 measures the *FSRS memory model's*
calibration — `fsrs::current_retrievability` against observed pass/fail
([memory-calibration.md](memory-calibration.md)). It is independent of how
Performance and Readiness are defined. Nothing in Phases 5–6 touches it.
What would invalidate it is a change to the memory model or to FSRS
parameters; neither has happened.

## Not done

- **The weight uses only the spacebar-reflex share.** Per-topic
  volatility is computed and displayed but does not itself scale the
  score, because the give-up rule already acts on it — more strongly.
  Whether a *graduated* volatility discount should exist below the
  refusal threshold is a real open question, not an oversight.
- **Android does not render the penalty.** The proto fields shipped in
  Phase 3, but the Rust that populates them is new here, so the backend
  AAR needs another cross-compile before the phone can show it.
- The 0.5 floor is the brainlift's number, unfitted. Configuration, not a
  finding.
