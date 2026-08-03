// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Speedrun addition: the Readiness mapper (PRD §5/§6/§10.3) — maps the
//! Performance model's predicted accuracy onto the MCAT's real scale, with
//! a range and a confidence label. Runs `performance_query` first; nothing
//! here executes for a caller the give-up gate would refuse.
//!
//! **The method, stated plainly (PRD §10.3 requires this):** the MCAT total
//! score is designed by AAMC to be approximately normally distributed with
//! a published mean of 500.5 and standard deviation of ~10.6 (the scale
//! runs 472-528). This maps predicted accuracy on held-back exam-style
//! questions onto that distribution by treating it as an approximate
//! population percentile (accuracy 0.5 -> the 50th percentile -> the mean
//! score), via the inverse normal CDF.
//!
//! **What would prove this wrong:** this treats "chance of answering one
//! new question correctly" as interchangeable with "population percentile
//! of exam-day ability," which is a real, stated simplifying assumption,
//! not something validated against actual MCAT takers with real study
//! history and score outcomes (that validation is PRD §10's bonus tier).
//! If real student data ever becomes available, the honest fix is to fit
//! this mapping empirically instead of assuming a percentile equivalence.

use anki_proto::stats::performance_query_response::Result as PerformanceResult;
use anki_proto::stats::readiness_data::Confidence;
use anki_proto::stats::readiness_query_response::Result as ReadinessResult;
use anki_proto::stats::ReadinessData;
use anki_proto::stats::ReadinessQueryResponse;

use anki_proto::stats::TopicMastery;
use crate::prelude::*;

// AAMC's published MCAT score distribution. See module doc for the
// citation and the limitation of treating accuracy as a percentile of it.
const MCAT_MEAN: f64 = 500.5;
const MCAT_SD: f64 = 10.6;
const MCAT_MIN: u32 = 472;
const MCAT_MAX: u32 = 528;

// Confidence tiers, bottlenecked on whichever of reviews/coverage is
// weaker - matches the give-up gate's own AND logic, just at higher bars
// since passing the gate at all only guarantees the *minimum* usable data.
const HIGH_CONFIDENCE_REVIEWS: u32 = 1000;
const HIGH_CONFIDENCE_COVERAGE: f32 = 0.9;
const MEDIUM_CONFIDENCE_REVIEWS: u32 = 500;
const MEDIUM_CONFIDENCE_COVERAGE: f32 = 0.7;

const LOW_CONFIDENCE_RANGE_HALF_WIDTH: u32 = 9;
const MEDIUM_CONFIDENCE_RANGE_HALF_WIDTH: u32 = 5;
const HIGH_CONFIDENCE_RANGE_HALF_WIDTH: u32 = 3;

impl Collection {
    pub(crate) fn readiness_query(
        &mut self,
        topics: &[String],
        average_difficulty: f32,
        average_timing_seconds: f32,
    ) -> Result<ReadinessQueryResponse> {
        let performance =
            self.performance_query(topics, average_difficulty, average_timing_seconds)?;
        let result = match performance.result.unwrap() {
            PerformanceResult::Insufficient(insufficient) => {
                ReadinessResult::Insufficient(insufficient)
            }
            PerformanceResult::Data(data) => {
                let gate_data = data
                    .inputs
                    .as_ref()
                    .expect("performance_query always sets inputs on its data branch");
                let confidence =
                    confidence_tier(gate_data.total_graded_reviews, gate_data.topic_coverage);
                let reflex = spacebar_reflex_penalty(&gate_data.topics);
                let projected_score =
                    map_accuracy_to_mcat_score(data.predicted_accuracy * reflex.weight);
                let half_width = range_half_width(confidence);
                ReadinessResult::Data(ReadinessData {
                    latency_volatility_weight: reflex.weight,
                    spacebar_reflex_reviews: reflex.reflex_reviews,
                    projected_score,
                    range_low: projected_score.saturating_sub(half_width).max(MCAT_MIN),
                    range_high: (projected_score + half_width).min(MCAT_MAX),
                    confidence: confidence.into(),
                    inputs: Some(data),
                })
            }
        };
        Ok(ReadinessQueryResponse {
            result: Some(result),
        })
    }
}

/// Brainlift v3 §8: Readiness is "a composite of Memory and Performance,
/// weighted by Latency Volatility".
///
/// **Memory is not added as a separate term, on purpose.** The Performance
/// model already takes mean topic mastery - which *is* the Memory score -
/// as one of its inputs (`performance_model.rs`). Adding it again here
/// would double-count the same quantity and make Readiness move twice for
/// one change in recall. So Readiness is a composite of Memory and
/// Performance in the sense that matters: Performance carries Memory,
/// and this function supplies the volatility weighting on top.
///
/// The weighting implements the v1 docx's rule literally: *"a 0.5x
/// multiplier to the score of any card answered faster than the calculated
/// Minimum Reading Time"*. Aggregated over the scored topics, reviews that
/// were too fast to be real count half, so the weight is
/// `1 - 0.5 * (reflex reviews / graded reviews)`. No reflexes leaves the
/// score untouched at 1.0; every review a reflex halves it.
///
/// Note this penalises the *spacebar reflex* (answering faster than the
/// card can be read) rather than low volatility. The two are different
/// signals and are used differently on purpose: low volatility makes the
/// app **refuse to score at all** (`give_up_gate.rs`), which is a
/// stronger response than a discount. Applying both to the same evidence
/// would punish it twice.
struct ReflexPenalty {
    weight: f32,
    reflex_reviews: u32,
}

fn spacebar_reflex_penalty(topics: &[TopicMastery]) -> ReflexPenalty {
    let graded: u32 = topics.iter().map(|t| t.graded_review_count).sum();
    let reflex: u32 = topics.iter().map(|t| t.below_min_reading_time_count).sum();
    if graded == 0 {
        return ReflexPenalty {
            weight: 1.0,
            reflex_reviews: 0,
        };
    }
    ReflexPenalty {
        weight: 1.0 - 0.5 * (reflex as f32 / graded as f32),
        reflex_reviews: reflex,
    }
}

fn map_accuracy_to_mcat_score(predicted_accuracy: f32) -> u32 {
    // Clamp away from the exact 0/1 boundary: the inverse CDF is undefined
    // there, and a single held-back-question model shouldn't claim
    // certainty at either extreme anyway.
    let p = (predicted_accuracy as f64).clamp(0.001, 0.999);
    let z = inverse_normal_cdf(p);
    let score = MCAT_MEAN + z * MCAT_SD;
    score.round().clamp(MCAT_MIN as f64, MCAT_MAX as f64) as u32
}

fn confidence_tier(total_graded_reviews: u32, topic_coverage: f32) -> Confidence {
    if total_graded_reviews >= HIGH_CONFIDENCE_REVIEWS
        && topic_coverage >= HIGH_CONFIDENCE_COVERAGE
    {
        Confidence::High
    } else if total_graded_reviews >= MEDIUM_CONFIDENCE_REVIEWS
        && topic_coverage >= MEDIUM_CONFIDENCE_COVERAGE
    {
        Confidence::Medium
    } else {
        Confidence::Low
    }
}

fn range_half_width(confidence: Confidence) -> u32 {
    match confidence {
        Confidence::Low => LOW_CONFIDENCE_RANGE_HALF_WIDTH,
        Confidence::Medium => MEDIUM_CONFIDENCE_RANGE_HALF_WIDTH,
        Confidence::High => HIGH_CONFIDENCE_RANGE_HALF_WIDTH,
    }
}

/// Peter Acklam's rational approximation of the inverse standard normal
/// CDF (probit function). Widely used, accurate to ~1.15e-9 relative
/// error. `p` must be in (0, 1).
fn inverse_normal_cdf(p: f64) -> f64 {
    const A: [f64; 6] = [
        -3.969_683_028_665_376e+01,
        2.209_460_984_245_205e+02,
        -2.759_285_104_469_687e+02,
        1.383_577_518_672_690e+02,
        -3.066_479_806_614_716e+01,
        2.506_628_277_459_239e+00,
    ];
    const B: [f64; 5] = [
        -5.447_609_879_822_406e+01,
        1.615_858_368_580_409e+02,
        -1.556_989_798_598_866e+02,
        6.680_131_188_771_972e+01,
        -1.328_068_155_288_572e+01,
    ];
    const C: [f64; 6] = [
        -7.784_894_002_430_293e-03,
        -3.223_964_580_411_365e-01,
        -2.400_758_277_161_838e+00,
        -2.549_732_539_343_734e+00,
        4.374_664_141_464_968e+00,
        2.938_163_982_698_783e+00,
    ];
    const D: [f64; 4] = [
        7.784_695_709_041_462e-03,
        3.224_671_290_700_398e-01,
        2.445_134_137_142_996e+00,
        3.754_408_661_907_416e+00,
    ];
    const P_LOW: f64 = 0.024_25;
    const P_HIGH: f64 = 1.0 - P_LOW;

    if p < P_LOW {
        let q = (-2.0 * p.ln()).sqrt();
        (((((C[0] * q + C[1]) * q + C[2]) * q + C[3]) * q + C[4]) * q + C[5])
            / ((((D[0] * q + D[1]) * q + D[2]) * q + D[3]) * q + 1.0)
    } else if p <= P_HIGH {
        let q = p - 0.5;
        let r = q * q;
        (((((A[0] * r + A[1]) * r + A[2]) * r + A[3]) * r + A[4]) * r + A[5]) * q
            / (((((B[0] * r + B[1]) * r + B[2]) * r + B[3]) * r + B[4]) * r + 1.0)
    } else {
        let q = (-2.0 * (1.0 - p).ln()).sqrt();
        -(((((C[0] * q + C[1]) * q + C[2]) * q + C[3]) * q + C[4]) * q + C[5])
            / ((((D[0] * q + D[1]) * q + D[2]) * q + D[3]) * q + 1.0)
    }
}

#[cfg(test)]
mod test {
    use super::*;

    fn topic_with(graded: u32, reflex: u32) -> TopicMastery {
        TopicMastery {
            graded_review_count: graded,
            below_min_reading_time_count: reflex,
            ..Default::default()
        }
    }

    #[test]
    fn no_spacebar_reflex_leaves_the_score_untouched() {
        // 1.0, not 0.0: a score that has not been penalised must not
        // imply that it has.
        let p = spacebar_reflex_penalty(&[topic_with(100, 0)]);
        assert_eq!(p.weight, 1.0);
        assert_eq!(p.reflex_reviews, 0);
    }

    #[test]
    fn every_review_a_reflex_halves_the_weight() {
        // The v1 docx's "0.5x multiplier" is the floor, not a slope that
        // can run past it into a negative score.
        let p = spacebar_reflex_penalty(&[topic_with(100, 100)]);
        assert_eq!(p.weight, 0.5);
        assert_eq!(p.reflex_reviews, 100);
    }

    #[test]
    fn penalty_scales_with_the_share_of_reflex_reviews() {
        let p = spacebar_reflex_penalty(&[topic_with(100, 40)]);
        assert!((p.weight - 0.8).abs() < 1e-6, "weight {}", p.weight);
    }

    #[test]
    fn penalty_aggregates_across_topics() {
        let p = spacebar_reflex_penalty(&[topic_with(50, 10), topic_with(50, 30)]);
        // 40 reflexes of 100 graded -> 1 - 0.5*0.4 = 0.8
        assert!((p.weight - 0.8).abs() < 1e-6, "weight {}", p.weight);
        assert_eq!(p.reflex_reviews, 40);
    }

    #[test]
    fn no_reviews_at_all_is_not_a_penalty() {
        // Absence of evidence is not evidence of the reflex - the same
        // rule the latency monitor applies to volatility.
        let p = spacebar_reflex_penalty(&[topic_with(0, 0)]);
        assert_eq!(p.weight, 1.0);
    }

    #[test]
    fn the_penalty_actually_lowers_the_projected_score() {
        // The point of the whole phase: a deck answered too fast to be
        // read must not project the same score as one that was read.
        let honest = map_accuracy_to_mcat_score(0.7 * 1.0);
        let reflexive = map_accuracy_to_mcat_score(0.7 * 0.5);
        assert!(
            reflexive < honest,
            "reflex-penalised {reflexive} should be below honest {honest}"
        );
    }

    #[test]
    fn inverse_normal_cdf_matches_known_values() {
        assert!((inverse_normal_cdf(0.5)).abs() < 1e-6);
        // Standard 95% CI z-value.
        assert!((inverse_normal_cdf(0.975) - 1.959_963_984_540).abs() < 1e-6);
        assert!((inverse_normal_cdf(0.025) - (-1.959_963_984_540)).abs() < 1e-6);
    }

    #[test]
    fn accuracy_of_half_maps_to_mcat_mean() {
        assert_eq!(map_accuracy_to_mcat_score(0.5), 501);
    }

    #[test]
    fn higher_accuracy_maps_to_higher_score_and_stays_in_bounds() {
        let low = map_accuracy_to_mcat_score(0.05);
        let mid = map_accuracy_to_mcat_score(0.5);
        let high = map_accuracy_to_mcat_score(0.95);
        assert!(low < mid);
        assert!(mid < high);
        assert!((MCAT_MIN..=MCAT_MAX).contains(&low));
        assert!((MCAT_MIN..=MCAT_MAX).contains(&high));
    }

    #[test]
    fn confidence_tier_and_range_narrow_as_data_grows() {
        assert_eq!(confidence_tier(200, 0.5), Confidence::Low);
        assert_eq!(confidence_tier(500, 0.7), Confidence::Medium);
        assert_eq!(confidence_tier(1000, 0.9), Confidence::High);

        assert!(range_half_width(Confidence::Low) > range_half_width(Confidence::Medium));
        assert!(range_half_width(Confidence::Medium) > range_half_width(Confidence::High));
    }

    #[test]
    fn readiness_query_refuses_when_give_up_gate_refuses() -> Result<()> {
        let mut col = Collection::new();
        let resp = col.readiness_query(&["nonexistent_topic".to_string()], 0.5, 70.0)?;
        match resp.result.unwrap() {
            ReadinessResult::Insufficient(_) => {}
            ReadinessResult::Data(_) => panic!("expected insufficient data on an empty collection"),
        }
        Ok(())
    }
}
