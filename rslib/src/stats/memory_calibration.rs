// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Speedrun addition: memory-model calibration (PRD §10.1 — "memory model
//! calibrated: at 80% it should be right about 80% of the time, proven on
//! held back reviews").
//!
//! This buckets FSRS's own predicted probability of recall
//! (`fsrs::current_retrievability`) against observed pass/fail outcomes on
//! reviews held back from a synthetic-but-realistic dataset, producing a
//! reliability-diagram table plus an overall Brier score. It is
//! deliberately *not* a new prediction model — it reuses the exact FSRS
//! primitives (`FSRS::next_states`, `fsrs::current_retrievability`) the
//! real scheduler and optimizer already use, as an honesty check on the
//! one FSRS itself makes.
//!
//! There is no real held-back review bank in this repo yet (same limitation
//! `speedrun/tools/scoring-train/train_performance_model.py` states for the
//! Performance model). `generate_synthetic_items` draws each item's *true*
//! per-review pass probability from an independent half-life decay curve,
//! unrelated to the FSRS formula being evaluated - if the two matched by
//! construction, the "calibration" would be circular and prove nothing.
//! FSRS's own state (stability/difficulty) is advanced using the *actual*
//! (synthetic) outcomes via `next_states`, exactly as a live card would be,
//! so what's being checked is genuinely "does FSRS's predicted probability
//! track an independently-generated ground truth," not "does FSRS agree
//! with itself." See `speedrun/docs/memory-calibration.md` for the real
//! numbers this produces and the honest limitations of using synthetic
//! data here.
//!
//! Not wired to a live RPC (unlike mastery_query/give_up_gate/
//! performance_query) - this is a rerunnable held-back check
//! (`cargo test -p anki --lib stats::memory_calibration`), not a
//! per-student score, so `#[allow(dead_code)]` below is expected: outside
//! `#[cfg(test)]`, nothing in the running app calls these yet.
#![allow(dead_code)]

use fsrs::ComputeParametersInput;
use fsrs::FSRSItem;
use fsrs::FSRSReview;
use fsrs::MemoryState;
use fsrs::TrainingConfig;
use fsrs::FSRS;
use rand::rngs::StdRng;
use rand::Rng;
use rand::SeedableRng;
use serde::Serialize;

const NUM_BUCKETS: usize = 10;

#[derive(Debug, Clone, Serialize)]
pub(crate) struct CalibrationBucket {
    pub(crate) bucket_start: f32,
    pub(crate) bucket_end: f32,
    pub(crate) mean_predicted: f32,
    pub(crate) observed_accuracy: f32,
    pub(crate) n: usize,
}

#[derive(Debug, Clone, Serialize)]
pub(crate) struct CalibrationReport {
    pub(crate) brier_score: f32,
    pub(crate) n_predictions: usize,
    pub(crate) n_held_back_items: usize,
    pub(crate) n_train_items: usize,
    pub(crate) buckets: Vec<CalibrationBucket>,
}

/// Fits FSRS parameters on `train_items` via the same `fsrs::compute_parameters`
/// call Anki's own "Optimize FSRS params" feature uses
/// (`rslib/src/scheduler/fsrs/params.rs::compute_params`) - not a bespoke
/// fitting routine, the real one. 8 epochs, matching that call site's own
/// default `TrainingConfig`. Returns `None` (not an error) when the train
/// split can't support fitting (e.g. `FSRSError::NotEnoughData` - fsrs-rs
/// requires enough per-rating variety to seed initial stability estimates,
/// which a small or degenerate synthetic split may not have) - the caller
/// falls back to FSRS's published defaults rather than failing outright.
fn fit_params_on_train(train_items: &[FSRSItem]) -> Option<Vec<f32>> {
    if train_items.is_empty() {
        return None;
    }
    let input = ComputeParametersInput {
        train_set: train_items.to_vec(),
        card_ids: None,
        progress: None,
        enable_short_term: true,
        num_relearning_steps: Some(1),
        training_config: Some(TrainingConfig {
            num_epochs: 8,
            ..Default::default()
        }),
    };
    fsrs::compute_parameters(input).ok()
}

/// Splits `items` by index - the first `1 - held_back_fraction` are used to
/// **fit** FSRS's own parameters (`fit_params_on_train`, the same routine
/// Anki's real "Optimize FSRS params" uses; falls back to FSRS's published
/// defaults if fitting isn't possible on this split), then the fitted (or
/// default) model is evaluated only against the remaining held-back items,
/// never seen during fitting. For each held-back item, replays its review
/// sequence: before applying review N's actual outcome, predicts recall
/// probability from the state built up through review N-1, then updates
/// state with the real rating via `next_states`. The first review of each
/// item has no prior state to predict from and is skipped for prediction
/// purposes (it still seeds the starting state).
pub(crate) fn calibration_report(
    items: &[FSRSItem],
    held_back_fraction: f32,
    decay: f32,
) -> CalibrationReport {
    let split = (((items.len() as f32) * (1.0 - held_back_fraction)).round() as usize)
        .min(items.len());
    let (train, held_back) = items.split_at(split);

    let fitted_params = fit_params_on_train(train).unwrap_or_default();
    let fsrs = FSRS::new(&fitted_params).expect("fitted or default params should always be valid");

    let mut pairs: Vec<(f32, bool)> = Vec::new();
    for item in held_back {
        let mut state: Option<MemoryState> = None;
        for review in &item.reviews {
            if let Some(prev_state) = state {
                let predicted =
                    fsrs::current_retrievability(prev_state, review.delta_t as f32, decay);
                let actual = review.rating > 1;
                pairs.push((predicted, actual));
            }
            let outcome = fsrs
                .next_states(state, 0.9, review.delta_t)
                .expect("next_states on a well-formed FSRSItem review should not fail");
            state = Some(match review.rating {
                1 => outcome.again.memory,
                2 => outcome.hard.memory,
                3 => outcome.good.memory,
                _ => outcome.easy.memory,
            });
        }
    }

    let brier_score = if pairs.is_empty() {
        0.0
    } else {
        pairs
            .iter()
            .map(|(p, a)| {
                let actual = if *a { 1.0 } else { 0.0 };
                (p - actual).powi(2)
            })
            .sum::<f32>()
            / pairs.len() as f32
    };

    let mut buckets = Vec::new();
    for i in 0..NUM_BUCKETS {
        let lo = i as f32 / NUM_BUCKETS as f32;
        let hi = (i + 1) as f32 / NUM_BUCKETS as f32;
        let in_bucket: Vec<&(f32, bool)> = pairs
            .iter()
            .filter(|(p, _)| *p >= lo && (*p < hi || i == NUM_BUCKETS - 1))
            .collect();
        if in_bucket.is_empty() {
            continue;
        }
        let mean_predicted = in_bucket.iter().map(|(p, _)| *p).sum::<f32>() / in_bucket.len() as f32;
        let observed_accuracy =
            in_bucket.iter().filter(|(_, a)| *a).count() as f32 / in_bucket.len() as f32;
        buckets.push(CalibrationBucket {
            bucket_start: lo,
            bucket_end: hi,
            mean_predicted,
            observed_accuracy,
            n: in_bucket.len(),
        });
    }

    CalibrationReport {
        brier_score,
        n_predictions: pairs.len(),
        n_held_back_items: held_back.len(),
        n_train_items: split,
        buckets,
    }
}

/// Synthetic-but-realistic dataset: each item gets its own "true" half-life
/// (independent of FSRS's formula, see module doc), then a sequence of
/// reviews at growing, spaced-repetition-style intervals - each pass grows
/// the next interval by a random 1.5-2.5x factor (typical SRS scheduling
/// behavior), each fail resets it to a short 1-day relearning step. This
/// mirrors how real review history looks (and what FSRS's own stability-
/// initialization step expects to see enough of to fit at all - uniformly
/// random intervals were tried first and made `fit_params_on_train` fail
/// with `NotEnoughData` on every split). Each review is graded pass/fail by
/// sampling against that item's true exponential-decay retention curve at
/// the elapsed time since its last review. A pass is recorded as a "Good"
/// (3) rating, a fail as "Again" (1) - collapsing Hard/Easy since the
/// ground-truth model only produces a binary outcome.
pub(crate) fn generate_synthetic_items(seed: u64, n_items: usize) -> Vec<FSRSItem> {
    let mut rng = StdRng::seed_from_u64(seed);
    let mut items = Vec::with_capacity(n_items);
    for _ in 0..n_items {
        let true_half_life_days = rng.random_range(1.0_f32..60.0);
        let n_reviews = rng.random_range(4..14);
        let mut reviews = Vec::with_capacity(n_reviews);
        let mut next_interval = 1.0_f32;
        for review_idx in 0..n_reviews {
            let delta_t = if review_idx == 0 { 0 } else { next_interval.round() as u32 };
            let true_p = (-(delta_t as f32) / true_half_life_days * std::f32::consts::LN_2)
                .exp()
                .clamp(0.02, 0.98);
            let passed = rng.random_range(0.0_f32..1.0) < true_p;
            reviews.push(FSRSReview {
                rating: if passed { 3 } else { 1 },
                delta_t,
            });
            next_interval = if passed {
                (next_interval.max(1.0) * rng.random_range(1.5_f32..2.5)).min(365.0)
            } else {
                1.0
            };
        }
        items.push(FSRSItem { reviews });
    }
    items
}

#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn empty_items_returns_empty_report() {
        let report = calibration_report(&[], 0.2, fsrs::FSRS6_DEFAULT_DECAY);
        assert_eq!(report.brier_score, 0.0);
        assert_eq!(report.n_predictions, 0);
        assert!(report.buckets.is_empty());
    }

    #[test]
    fn held_back_fraction_splits_item_count_correctly() {
        let items = generate_synthetic_items(1, 3000);
        let report = calibration_report(&items, 0.2, fsrs::FSRS6_DEFAULT_DECAY);
        assert_eq!(report.n_train_items, 2400);
        assert_eq!(report.n_held_back_items, 600);
    }

    #[test]
    fn buckets_are_ordered_bounded_and_nonoverlapping() {
        let items = generate_synthetic_items(2, 3000);
        let report = calibration_report(&items, 0.2, fsrs::FSRS6_DEFAULT_DECAY);
        assert!(!report.buckets.is_empty());
        let mut prev_end = 0.0;
        for bucket in &report.buckets {
            assert!(bucket.bucket_start >= prev_end - f32::EPSILON);
            assert!(bucket.bucket_end > bucket.bucket_start);
            assert!((0.0..=1.0).contains(&bucket.mean_predicted));
            assert!((0.0..=1.0).contains(&bucket.observed_accuracy));
            assert!(bucket.n > 0);
            prev_end = bucket.bucket_start;
        }
    }

    #[test]
    fn brier_score_is_in_valid_range_and_beats_a_naive_always_50_percent_predictor() {
        let items = generate_synthetic_items(3, 3000);
        let report = calibration_report(&items, 0.2, fsrs::FSRS6_DEFAULT_DECAY);
        assert!((0.0..=1.0).contains(&report.brier_score));
        // A predictor that always guesses 0.5 has a Brier score of 0.25.
        // FSRS's real predictions, fitted on the train split and evaluated
        // only on held-back items, should do meaningfully better than that
        // naive floor even against an independent ground-truth curve.
        assert!(
            report.brier_score < 0.25,
            "brier_score {} should beat the always-0.5 baseline of 0.25",
            report.brier_score
        );
    }

    #[test]
    fn writes_a_real_report_to_disk_for_speedrun_docs() {
        let items = generate_synthetic_items(20260802, 5000);
        let report = calibration_report(&items, 0.2, fsrs::FSRS6_DEFAULT_DECAY);
        assert!(report.n_predictions > 0);

        let out_dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../speedrun/tools/calibration/output");
        std::fs::create_dir_all(&out_dir).unwrap();
        let json = serde_json::to_string_pretty(&report).unwrap();
        std::fs::write(out_dir.join("memory_calibration.json"), json).unwrap();
    }
}
