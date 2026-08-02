# Memory model calibration (PRD §10.1)

PRD §10 item 1: "Required: memory model calibrated. At 80% it should be
right about 80% of the time, proven on held back reviews." This document
is the honest record of validating FSRS — the memory model this fork
inherits from upstream Anki, unmodified — against that bar.

## What's actually being tested

This is **not** a new prediction model. It's an honesty check on the one
FSRS itself already makes: given a card's review history, FSRS predicts
a probability of recall (`fsrs::current_retrievability`) at any future
point. Does that predicted probability actually match how often the
prediction turns out true?

The check reuses the exact FSRS primitives Anki's own scheduler and
optimizer use — `fsrs::compute_parameters` (the same routine behind
"Optimize FSRS params"), `FSRS::next_states` (the same routine that
advances a card's memory state after every real grade), and
`fsrs::current_retrievability` (the same formula the Card Info screen's
retention graph uses). Implementation:
[`rslib/src/stats/memory_calibration.rs`](../../rslib/src/stats/memory_calibration.rs).

## Honest scope: synthetic data, stated plainly

**There is no real held-back review bank in this repo**, same limitation
[performance-model-eval.md](performance-model-eval.md) states for the
Performance model and `ARCHITECTURE.md` §8 flags generally. Rather than
skip this required test or fabricate a number, `generate_synthetic_items`
builds a labeled dataset where each item has its own "true" half-life,
**independent of the FSRS formula being evaluated** — reviews happen at
growing, spaced-repetition-style intervals (each pass grows the next
interval 1.5-2.5x, each fail resets to a 1-day relearning step, matching
real SRS usage patterns), and each review's pass/fail outcome is sampled
from that item's *own* exponential decay curve at the elapsed time, not
from anything FSRS computes.

This independence matters: if the ground truth were generated using
FSRS's own retrievability formula, "calibration" would be circular and
prove nothing. FSRS's state (stability/difficulty) is advanced using the
*actual* synthetic outcomes via `next_states`, exactly as a live card
would be — so what's measured is genuinely "does FSRS's predicted
probability track an independently-generated ground truth," not "does
FSRS agree with itself."

(An earlier version of this dataset used uniformly-random review
intervals instead of growing ones. That version made
`fit_params_on_train` fail outright with fsrs-rs's `NotEnoughData` error
on every split — FSRS's stability-initialization step needs
realistic-looking spacing to seed its estimates, the same as it would on
a real collection. Switching to growing intervals fixed this and is the
more honest choice anyway: real review history looks like this, not
like uniform noise.)

## Method: fit, then test only on what wasn't seen

- **5,000 synthetic items**, fixed seed `20260802`, each with 4-13
  reviews.
- **80/20 split**: the first 4,000 items are used to **fit real FSRS
  parameters** via `fsrs::compute_parameters` (8 epochs, the same
  routine `rslib/src/scheduler/fsrs/params.rs::compute_params` calls for
  "Optimize FSRS params") — this is not a placeholder, it's the actual
  optimizer.
- The remaining **1,000 items are never seen during fitting**. For each
  held-back item, the fitted model's predicted recall probability is
  computed *before* each review (from state built up through the prior
  reviews only), then compared against that review's real outcome.
- **7,505 individual (predicted, actual) pairs** collected from the
  held-back items, bucketed into a reliability diagram, plus an overall
  Brier score across all of them.

Rerunnable, deterministic:
```bash
cargo test -p anki --lib stats::memory_calibration
```
This writes the full report to
[`speedrun/tools/calibration/output/memory_calibration.json`](../tools/calibration/output/memory_calibration.json)
on every run.

## Results

**Brier score: 0.168** across 7,505 held-back predictions (lower is
better; 0 is perfect, 0.25 is what an always-guess-50% predictor scores,
1.0 is maximally wrong). FSRS's fitted predictions beat the naive
baseline by a wide margin.

| Predicted bucket | Mean predicted | Observed accuracy | n |
|---|---|---|---|
| 0.6–0.7 | 68.1% | 62.5% | 8 |
| 0.7–0.8 | 76.8% | 78.7% | 75 |
| 0.8–0.9 | 87.0% | 73.5% | 510 |
| 0.9–1.0 | 94.4% | 82.0% | 6,912 |

## The honest read

**Not perfectly calibrated — real, mild overconfidence at the high end,
stated plainly rather than smoothed over.** The 0.7–0.8 bucket is close
to ideal (76.8% predicted vs. 78.7% observed — within noise for n=75).
The 0.8–0.9 and 0.9–1.0 buckets both run **10-14 percentage points
overconfident**: FSRS predicts ~87-94% recall but the independent ground
truth actually delivers ~74-82%. Most predictions (6,912 of 7,505, 92%)
land in the top bucket, which is expected — successful reviews grow
FSRS's stability estimate, and confident predictions dominate a mature
review history, same as real SRS usage.

This is worth taking at face value rather than explaining away: FSRS,
even after fitting on 4,000 training items from the same synthetic
population, doesn't perfectly track an independently-generated forgetting
curve on the held-back 1,000. That's a real finding about the limits of
fitting FSRS's parametric family to *this particular* synthetic ground
truth, not a claim that upstream Anki's FSRS is broken on real user data
— this project didn't modify FSRS's model itself, only built the
honesty check the PRD asked for. A brier score of 0.168 with directional
overconfidence in the high-probability range is the actual result,
reported as measured — consistent with this project's discipline
elsewhere (see [socratic-gate-mvp.md](socratic-gate-mvp.md) and
[brainlift.md](brainlift.md) for the same standard applied to other
components).

## What this does and doesn't establish

**Does establish:** the fit → hold-back → predict → bucket pipeline is
wired correctly end to end, is deterministic and rerunnable by anyone,
and produces a real reliability diagram plus Brier score on data the
model never trained on — not a placeholder metric.

**Does not establish:** how well FSRS calibrates on *real* human review
data, since no real held-back review bank exists in this repo yet (same
caveat as the Performance model). It also doesn't retrain or modify
FSRS's model itself — this is a validation harness around upstream
Anki's existing, unmodified memory model, not a new one.

## Related

- [performance-model-eval.md](performance-model-eval.md) — the
  equivalent held-back honesty check for the Performance model, PRD §10
  item 2.
- `rslib/src/stats/readiness_mapper.rs` — the Readiness model's stated
  method and range, PRD §10 item 3.
