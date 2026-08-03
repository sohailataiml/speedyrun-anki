// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Speedrun addition (Brainlift v3): the Latency Monitor.
//!
//! Brainlift v3's traceability table asks for "a Rust-based Latency
//! Monitor that tags reviews as System 1 (Fast/Recognition) or System 2
//! (Slow/Analytical)", and a give-up rule that abstains when latency
//! volatility indicates rote pattern-matching rather than reasoning.
//!
//! This module is the direct successor to `socratic_gate.rs` (v2). The
//! fast/slow threshold and its inclusive-boundary semantics are carried
//! over unchanged, because that part was always a latency classifier;
//! what is dropped is the four-branch decision table, which existed only
//! to choose between Socratic interventions that v3 removes. The tests
//! were adapted rather than inherited — same boundary behaviour, new
//! vocabulary.
//!
//! Everything here is pure and `Collection`-free, so it is cheap to test
//! exhaustively and cheap to call from any RPC that already holds
//! `RevlogEntry` values. Both inputs — `taken_millis` and `button_chosen`
//! — are already captured by upstream Anki on every grade, so there is no
//! new capture engineering and no schema change.

use crate::revlog::RevlogEntry;

/// Fallback fast/slow threshold, used when a card's text isn't available
/// to compute a reading-time-aware one. Carried over from v2's
/// `DEFAULT_FAST_THRESHOLD_MS`: a stated, adjustable placeholder, not
/// fitted to data.
pub(crate) const DEFAULT_FAST_THRESHOLD_MS: u32 = 3_000;

/// Silent reading rate used to derive a card's minimum reading time.
/// 250 wpm is a conventional mid-range figure for adult silent reading of
/// ordinary prose; dense technical material is typically slower, which
/// makes this a *conservative* floor — it will under-estimate the time a
/// real MCAT card needs, so a review flagged as "faster than possible" is
/// very unlikely to be a false accusation.
pub(crate) const READING_WPM: f32 = 250.0;

/// Even a one-word card cannot honestly be read, recognised, and graded
/// faster than this. Prevents short cards from producing a minimum
/// reading time so small that every review clears it.
pub(crate) const MIN_READING_TIME_FLOOR_MS: u32 = 800;

/// Below this coefficient of variation, a topic's latencies are treated
/// as machine-like — the "spacebar reflex" of Brainlift v3 §4.
///
/// **This number is an interpretation, not a quotation.** The brainlift
/// says to abstain when "latency SD is < 0.2" but never gives units, and
/// a standard deviation of 0.2 *milliseconds* is physically meaningless
/// for human response times. The reading that makes 0.2 a sensible
/// quantity is the coefficient of variation (SD ÷ mean), which is
/// dimensionless: CV < 0.2 means essentially every response lands within
/// ±20% of the same duration, which is what pattern-matching without
/// reading looks like. Recorded here rather than silently chosen, so the
/// assumption is auditable — see
/// speedrun/docs/pivot-plan-latency-volatility.md §Phase 2.
pub(crate) const ROTE_PATTERN_CV_THRESHOLD: f32 = 0.2;

/// A single review's cognitive mode, in Kahneman's terms.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum SystemType {
    /// Fast enough to be recognition rather than reasoning. On DOK-3
    /// material this is the "Anki-Brain" signal the whole thesis is
    /// about, *not* a mastery signal.
    System1Recognition,
    /// Slow enough to be consistent with analytical retrieval.
    System2Analytical,
}

/// The shortest time in which a card's text could honestly be read.
///
/// Derived from length rather than fixed, because Brainlift v3's own
/// wording is "faster than the *calculated* Minimum Reading Time". A flat
/// threshold punishes long cards and lets short ones through: three
/// seconds is leisurely for "Citrate synthase" and impossible for a
/// four-line clinical vignette.
pub(crate) fn minimum_reading_time_ms(text: &str) -> u32 {
    minimum_reading_time_ms_for_words(text.split_whitespace().count())
}

/// The word-count entry point, for callers that already counted (the
/// per-topic aggregate query counts once per note and reuses it across
/// that note's cards, rather than re-splitting text per review).
pub(crate) fn minimum_reading_time_ms_for_words(words: usize) -> u32 {
    let ms = (words as f32 / READING_WPM * 60_000.0) as u32;
    ms.max(MIN_READING_TIME_FLOOR_MS)
}

/// Classifies one review. The boundary is inclusive of "fast": a review
/// taking exactly the threshold counts as System 1. Deliberate and
/// documented, so the boundary is deterministic rather than an
/// off-by-one landmine — same choice v2 made, kept for continuity.
pub(crate) fn classify_review(taken_millis: u32, threshold_ms: u32) -> SystemType {
    if taken_millis <= threshold_ms {
        SystemType::System1Recognition
    } else {
        SystemType::System2Analytical
    }
}

pub(crate) fn classify_entry(entry: &RevlogEntry, threshold_ms: u32) -> SystemType {
    classify_review(entry.taken_millis, threshold_ms)
}

/// True when a review was answered faster than its card could be read —
/// the "spacebar reflex". Distinct from merely being System 1: fast
/// recognition of a genuinely known fact is plausible, but answering
/// before the prompt could physically have been read is not.
pub(crate) fn below_minimum_reading_time(taken_millis: u32, card_text: &str) -> bool {
    taken_millis < minimum_reading_time_ms(card_text)
}

/// Coefficient of variation (SD ÷ mean) of review latencies — the
/// "Latency Volatility" of Brainlift v3.
///
/// Returns `None` rather than a number when there are fewer than two
/// reviews, or when the mean is zero. This is the give-up rule applied to
/// the give-up rule's own input: a single review has no dispersion to
/// measure, and reporting 0.0 for it would look exactly like a perfect
/// rote-pattern detection and cause a spurious abstention. Callers must
/// decide what to do with "not enough data" rather than being handed a
/// misleading zero.
///
/// Uses the sample standard deviation (n−1), which is the less biased
/// estimator at the small review counts a single topic will realistically
/// have.
pub(crate) fn latency_volatility(latencies: &[u32]) -> Option<f32> {
    if latencies.len() < 2 {
        return None;
    }
    let n = latencies.len() as f64;
    let mean = latencies.iter().map(|&l| l as f64).sum::<f64>() / n;
    if mean <= 0.0 {
        return None;
    }
    let variance = latencies
        .iter()
        .map(|&l| {
            let d = l as f64 - mean;
            d * d
        })
        .sum::<f64>()
        / (n - 1.0);
    Some((variance.sqrt() / mean) as f32)
}

/// Whether a topic's latencies look like rote pattern-matching. `None`
/// volatility (too few reviews) is *not* a rote pattern — absence of
/// evidence is not evidence of the spacebar reflex.
pub(crate) fn is_rote_pattern(volatility: Option<f32>) -> bool {
    matches!(volatility, Some(cv) if cv < ROTE_PATTERN_CV_THRESHOLD)
}

#[cfg(test)]
mod test {
    use super::*;
    use crate::revlog::RevlogId;

    fn entry(taken_millis: u32) -> RevlogEntry {
        RevlogEntry {
            id: RevlogId(0),
            taken_millis,
            button_chosen: 3,
            ..Default::default()
        }
    }

    #[test]
    fn fast_review_is_system_1() {
        assert_eq!(
            classify_review(1_500, DEFAULT_FAST_THRESHOLD_MS),
            SystemType::System1Recognition
        );
    }

    #[test]
    fn slow_review_is_system_2() {
        assert_eq!(
            classify_review(9_000, DEFAULT_FAST_THRESHOLD_MS),
            SystemType::System2Analytical
        );
    }

    #[test]
    fn threshold_boundary_is_inclusive_of_fast() {
        // Carried over from the v2 gate: exactly at the threshold counts
        // as fast, so the boundary is deterministic.
        assert_eq!(
            classify_review(DEFAULT_FAST_THRESHOLD_MS, DEFAULT_FAST_THRESHOLD_MS),
            SystemType::System1Recognition
        );
    }

    #[test]
    fn entry_wrapper_matches_direct_call() {
        let e = entry(1_500);
        assert_eq!(
            classify_entry(&e, DEFAULT_FAST_THRESHOLD_MS),
            classify_review(e.taken_millis, DEFAULT_FAST_THRESHOLD_MS)
        );
    }

    #[test]
    fn minimum_reading_time_scales_with_length() {
        // 50 words at 250wpm = 12s. A long vignette must not be judged
        // against the same threshold as a two-word card.
        let long_card = "word ".repeat(50);
        assert_eq!(minimum_reading_time_ms(&long_card), 12_000);
    }

    #[test]
    fn minimum_reading_time_has_a_floor() {
        assert_eq!(
            minimum_reading_time_ms("Citrate synthase"),
            MIN_READING_TIME_FLOOR_MS
        );
        assert_eq!(minimum_reading_time_ms(""), MIN_READING_TIME_FLOOR_MS);
    }

    #[test]
    fn spacebar_reflex_detected_only_below_reading_time() {
        let card = "word ".repeat(50); // 12s minimum
        assert!(below_minimum_reading_time(2_000, &card));
        assert!(!below_minimum_reading_time(15_000, &card));
    }

    #[test]
    fn uniform_latencies_are_a_rote_pattern() {
        // The spacebar reflex: every review the same length.
        let v = latency_volatility(&[1_000, 1_010, 990, 1_005]).unwrap();
        assert!(v < ROTE_PATTERN_CV_THRESHOLD, "cv was {v}");
        assert!(is_rote_pattern(Some(v)));
    }

    #[test]
    fn varied_latencies_are_not_a_rote_pattern() {
        // Real study: some cards are instant, some take thought.
        let v = latency_volatility(&[800, 4_500, 2_000, 11_000]).unwrap();
        assert!(v >= ROTE_PATTERN_CV_THRESHOLD, "cv was {v}");
        assert!(!is_rote_pattern(Some(v)));
    }

    #[test]
    fn volatility_is_scale_invariant() {
        // The whole point of using CV over SD: doubling every latency
        // must not change the verdict, because the *pattern* is what is
        // being measured, not the speed.
        let base = [1_000u32, 2_000, 3_000, 4_000];
        let doubled: Vec<u32> = base.iter().map(|l| l * 2).collect();
        let a = latency_volatility(&base).unwrap();
        let b = latency_volatility(&doubled).unwrap();
        assert!((a - b).abs() < 1e-5, "{a} vs {b}");
    }

    #[test]
    fn too_few_reviews_is_none_not_zero() {
        // A single review has no dispersion. Returning 0.0 would be
        // indistinguishable from a perfect rote pattern and would cause
        // a spurious abstention.
        assert_eq!(latency_volatility(&[]), None);
        assert_eq!(latency_volatility(&[1_500]), None);
        assert!(!is_rote_pattern(None));
    }
}
