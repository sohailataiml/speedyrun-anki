# Performance model — held-back evaluation (PRD §10.2)

PRD §10 item 2: "Required: predict held back exam style questions from
topic mastery, difficulty, timing and coverage." This is what
`rslib/src/stats/performance_model.rs`'s `performance_query` RPC does —
this document is the honest record of validating it against genuinely
held-back data.

## What the model is

A logistic regression over four inputs — mean FSRS mastery across the
gated topics, question difficulty, a z-scored answer-timing signal, and
topic coverage — predicting the probability of answering a held-back
exam-style question correctly. Trained and evaluated by
[`speedrun/tools/scoring-train/train_performance_model.py`](../tools/scoring-train/train_performance_model.py),
weights embedded at compile time into the Rust binary
(`rslib/src/stats/performance_model.rs`'s `include_str!`), so desktop and
Android run the identical model.

## Honest scope: synthetic data, stated plainly

**There is no real held-back MCAT-style question bank in this repo.**
`ARCHITECTURE.md` §8 lists "Held-back sets" as not built. Rather than
skip the required held-back test entirely, or fabricate a number, the
training script generates a synthetic labeled dataset from a fixed seed
and a *known* ground-truth relationship (mastery and coverage help,
difficulty hurts, timing has a small effect for being far from a
comfortable pace) plus noise — so there's real signal to fit and a real
gap to measure, without pretending it's genuine exam data. The script's
own docstring is explicit: *"The weights this produces must NEVER be
presented to a real student as a genuine Performance score."* Once a
real held-back question bank exists, only `generate_synthetic_dataset` →
`load_real_dataset` needs to change — the split/train/evaluate/serialize
pipeline doesn't.

This mirrors this project's own stated discipline elsewhere (paraphrase
tests, crash tests, bench fixtures all use synthetic-but-labeled data
when real data doesn't exist) rather than inventing a number and hoping
nobody checks — the PRD's own words: "Inventing a readiness number, or
dressing a guess as a measurement, is an automatic fail." This
evaluation exists precisely so the Performance model doesn't join that
category by omission.

## Method: a real train/held-back split

- **600 synthetic rows**, fixed seed `20260731`, each with mastery,
  difficulty, timing, coverage, and a `correct` outcome drawn from a
  logistic ground-truth function plus noise.
- **80/20 split**: the first 480 rows (by generation order) are used to
  fit the logistic regression via gradient descent (400 epochs); the
  remaining **120 rows are never seen during training** — held back for
  evaluation only.
- **Majority-class baseline**, computed from the train split's class
  balance, evaluated on the same 120 held-back rows — the simplest
  possible comparison point.
- The script **refuses to write weights** if held-back accuracy doesn't
  beat the majority baseline (`SystemExit` if so) — a real gate, not
  just a printed warning.

Rerunnable, deterministic:
```bash
cd speedrun/tools/scoring-train
python train_performance_model.py
```

## Results

| | n | Accuracy |
|---|---|---|
| Held-back eval (120 rows, never trained on) | 120 | **69.2%** |
| Majority-class baseline (same 120 rows) | 120 | 59.2% |

The Performance model beats the naive baseline by **10 percentage
points** on data it never trained on. Not a large margin — the
synthetic ground-truth function has real noise mixed into the logit
deliberately (see `generate_synthetic_dataset`'s docstring), so a
perfect fit was never the point; the point was a real, rerunnable,
train/held-back split that the model has to actually pass, and does.

## What this does and doesn't establish

**Does establish:** the train → held-back-evaluate → serialize → embed →
Rust-apply pipeline is wired correctly end to end, is deterministic and
rerunnable by anyone, and the model genuinely generalizes beyond its
training rows on the (synthetic) relationship it was fit to — it isn't
memorizing.

**Does not establish:** that these specific weights, or this accuracy
number, describe real students on real MCAT-style questions. That
requires the real held-back question bank `ARCHITECTURE.md` §8 flags as
not built. Per this project's own honesty rule (see
[socratic-gate-mvp.md](socratic-gate-mvp.md) and
[brainlift.md](brainlift.md) for the same discipline applied elsewhere):
"we calibrated the pipeline but cannot yet prove the real-world number"
is the honest state here, not a polished accuracy figure presented
without this caveat.

## Related

- [memory-calibration.md](memory-calibration.md) — the equivalent
  held-back honesty check for the Memory model (FSRS), PRD §10 item 1.
- `rslib/src/stats/readiness_mapper.rs` — the Readiness model's stated
  method and range (inverse-normal-CDF mapping onto AAMC's published
  MCAT mean/SD), PRD §10 item 3.
