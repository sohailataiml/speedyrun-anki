// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Speedrun addition: the give-up rule (PRD §5). Sits in front of the
//! Performance model — see the design note alongside this file. This module
//! only decides whether there's enough data to score at all; it does not
//! compute a score itself.

use anki_proto::stats::give_up_gate_response::Result as GateResult;
use anki_proto::stats::GiveUpGateData;
use anki_proto::stats::GiveUpGateResponse;
use anki_proto::stats::insufficient_data::Reason;
use anki_proto::stats::InsufficientData;
use anki_proto::stats::TopicMastery;

use super::latency_monitor::ROTE_PATTERN_CV_THRESHOLD;
use super::mastery::TopicLatency;
use crate::prelude::*;
use crate::search::SortMode;

/// PRD §5's own example thresholds ("no score below 200 graded reviews and
/// 50% topic coverage"), named here so the two numbers appear exactly once.
const MIN_GRADED_REVIEWS: u32 = 200;
const MIN_TOPIC_COVERAGE: f32 = 0.5;

/// Brainlift v3's rote-pattern rule. The brainlift states this three
/// different ways and they have to be reconciled:
///
/// - §7: abstain "if latency SD is < 0.2"
/// - §8: hidden until "minimum Latency Variance on **DOK-3 tagged topics**"
/// - the v1 docx §8: "< 0.2 for **more than 40% of the deck**"
///
/// Taken together: apply the < 0.2 volatility test to reasoning-heavy
/// topics, and abstain once more than 40% of them fail it. The 0.2
/// itself is a coefficient of variation, which is an interpretation of an
/// unitless brainlift figure - see `latency_monitor::ROTE_PATTERN_CV_THRESHOLD`.
const MAX_ROTE_PATTERN_TOPIC_FRACTION: f32 = 0.4;

/// What share of judgeable topics look like pattern-matching.
struct RotePatternShare {
    fraction: f32,
    #[allow(dead_code)]
    rote_topics: u32,
    #[allow(dead_code)]
    judgeable_topics: u32,
}

/// The denominator is the subtle part, and getting it wrong breaks the
/// rule in opposite directions:
///
/// - Topics with **fewer than two reviews** have no volatility to measure
///   (`volatility` is `None`). Counting them as "not rote" would dilute
///   the fraction toward zero on a fresh collection and stop the rule
///   ever firing; counting them as rote would fire it on everyone who
///   just started. They are excluded from **both** sides.
/// - Topics explicitly tagged `dok::1`/`dok::2` are excluded because
///   uniform latency on definitional material is automaticity, not a
///   reflex.
///
/// With nothing judgeable, the share is 0.0 - the rule cannot fire on
/// evidence it does not have.
fn rote_pattern_share(latency: &[TopicLatency]) -> RotePatternShare {
    let judgeable: Vec<&TopicLatency> = latency
        .iter()
        .filter(|t| t.volatility.is_some() && !t.is_exempt_from_rote_check())
        .collect();
    if judgeable.is_empty() {
        return RotePatternShare {
            fraction: 0.0,
            rote_topics: 0,
            judgeable_topics: 0,
        };
    }
    let rote = judgeable.iter().filter(|t| t.is_rote_pattern()).count();
    RotePatternShare {
        fraction: rote as f32 / judgeable.len() as f32,
        rote_topics: rote as u32,
        judgeable_topics: judgeable.len() as u32,
    }
}

impl Collection {
    /// Decides whether there's enough data to compute a score for the given
    /// topics. Read-only, same as `mastery_query` — refusing to score must
    /// never itself be something that can corrupt or mutate the collection.
    pub(crate) fn give_up_gate(&mut self, topics: &[String]) -> Result<GiveUpGateResponse> {
        let (mastery_topics, latency) = self.mastery_and_latency_query(topics)?;
        let total_graded_reviews = self.total_graded_reviews()?;
        let topic_coverage = topic_coverage(&mastery_topics);
        let rote = rote_pattern_share(&latency);

        let sufficient = total_graded_reviews >= MIN_GRADED_REVIEWS
            && topic_coverage >= MIN_TOPIC_COVERAGE
            && rote.fraction <= MAX_ROTE_PATTERN_TOPIC_FRACTION;

        let result = if sufficient {
            GateResult::Data(GiveUpGateData {
                total_graded_reviews,
                topic_coverage,
                topics: mastery_topics,
            })
        } else {
            // Every failing rule is reported, not just the first: a client
            // that showed one reason could send the student off to fix
            // review count while a second, different blocker still stands.
            let mut reasons = Vec::new();
            if total_graded_reviews < MIN_GRADED_REVIEWS {
                reasons.push(Reason::NotEnoughReviews as i32);
            }
            if topic_coverage < MIN_TOPIC_COVERAGE {
                reasons.push(Reason::NotEnoughCoverage as i32);
            }
            if rote.fraction > MAX_ROTE_PATTERN_TOPIC_FRACTION {
                reasons.push(Reason::RotePatternDetected as i32);
            }
            GateResult::Insufficient(InsufficientData {
                total_graded_reviews,
                topic_coverage,
                reviews_required: MIN_GRADED_REVIEWS,
                coverage_required: MIN_TOPIC_COVERAGE,
                reasons,
                rote_pattern_topic_fraction: rote.fraction,
                rote_pattern_fraction_allowed: MAX_ROTE_PATTERN_TOPIC_FRACTION,
                rote_pattern_cv_threshold: ROTE_PATTERN_CV_THRESHOLD,
            })
        };
        Ok(GiveUpGateResponse {
            result: Some(result),
        })
    }

    /// Graded reviews across the whole collection, not just the requested
    /// topics — the PRD's give-up rule is a collection-wide floor, separate
    /// from per-topic coverage.
    fn total_graded_reviews(&mut self) -> Result<u32> {
        let guard = self.search_cards_into_table("", SortMode::NoOrder)?;
        let revlog = guard.col.storage.get_revlog_entries_for_searched_cards()?;
        drop(guard);
        Ok(revlog
            .iter()
            .filter(|entry| entry.has_rating_and_affects_scheduling())
            .count() as u32)
    }
}

/// Proportion of the requested topics that have at least one graded review.
/// Stands in for "official exam outline coverage" until that outline
/// mapping (ARCHITECTURE.md §8, not yet built) exists — once it does, this
/// should iterate the full outline rather than just the requested topics.
fn topic_coverage(topics: &[TopicMastery]) -> f32 {
    if topics.is_empty() {
        return 0.0;
    }
    let covered = topics.iter().filter(|t| t.cards_with_reviews > 0).count();
    covered as f32 / topics.len() as f32
}

#[cfg(test)]
mod test {
    use super::*;
    use crate::revlog::RevlogEntry;
    use crate::revlog::RevlogReviewKind;

    fn add_card_with_topic(col: &mut Collection, topic: &str) -> Result<CardId> {
        let mut note = NoteAdder::basic(&mut *col).fields(&["front", "back"]).note();
        note.tags = vec![format!("topic::{topic}")];
        col.add_note(&mut note, DeckId(1))?;
        Ok(col.search_cards(note.id, SortMode::NoOrder)?[0])
    }

    fn add_graded_review(col: &mut Collection, cid: CardId, button_chosen: u8) -> Result<()> {
        col.storage.add_revlog_entry(
            &RevlogEntry {
                id: RevlogId::new(),
                cid,
                button_chosen,
                review_kind: RevlogReviewKind::Review,
                ..Default::default()
            },
            true,
        )?;
        Ok(())
    }

    fn add_card_with_topic_and_dok(
        col: &mut Collection,
        topic: &str,
        dok: Option<u8>,
    ) -> Result<CardId> {
        let mut note = NoteAdder::basic(&mut *col).fields(&["front", "back"]).note();
        note.tags = vec![format!("topic::{topic}")];
        if let Some(d) = dok {
            note.tags.push(format!("dok::{d}"));
        }
        col.add_note(&mut note, DeckId(1))?;
        Ok(col.search_cards(note.id, SortMode::NoOrder)?[0])
    }

    fn review_with_latency(col: &mut Collection, cid: CardId, taken_millis: u32) -> Result<()> {
        col.storage.add_revlog_entry(
            &RevlogEntry {
                id: RevlogId::new(),
                cid,
                button_chosen: 3,
                taken_millis,
                review_kind: RevlogReviewKind::Review,
                ..Default::default()
            },
            true,
        )?;
        Ok(())
    }

    /// Machine-like: every review the same duration.
    fn study_rotely(col: &mut Collection, cid: CardId, n: usize) -> Result<()> {
        for i in 0..n {
            review_with_latency(col, cid, 1_000 + (i % 3) as u32 * 5)?;
        }
        Ok(())
    }

    /// Real study: some cards instant, some take thought.
    fn study_thoughtfully(col: &mut Collection, cid: CardId, n: usize) -> Result<()> {
        let pattern = [800u32, 4_500, 1_500, 11_000, 2_200, 7_000];
        for i in 0..n {
            review_with_latency(col, cid, pattern[i % pattern.len()])?;
        }
        Ok(())
    }

    #[test]
    fn refuses_when_below_review_count_threshold() -> Result<()> {
        let mut col = Collection::new();
        let cid = add_card_with_topic(&mut col, "krebs_cycle")?;
        // Well under MIN_GRADED_REVIEWS.
        add_graded_review(&mut col, cid, 3)?;

        let resp = col.give_up_gate(&["krebs_cycle".to_string()])?;
        match resp.result.unwrap() {
            GateResult::Insufficient(data) => {
                assert_eq!(data.total_graded_reviews, 1);
                assert_eq!(data.reviews_required, MIN_GRADED_REVIEWS);
            }
            GateResult::Data(_) => panic!("expected insufficient data"),
        }
        Ok(())
    }

    #[test]
    fn refuses_when_below_coverage_threshold_even_with_enough_reviews() -> Result<()> {
        let mut col = Collection::new();
        let covered = add_card_with_topic(&mut col, "covered_topic")?;
        add_card_with_topic(&mut col, "uncovered_topic_1")?;
        add_card_with_topic(&mut col, "uncovered_topic_2")?;
        for _ in 0..MIN_GRADED_REVIEWS {
            add_graded_review(&mut col, covered, 3)?;
        }

        // 1 of 3 requested topics has reviews: ~33% coverage is below 50%.
        let resp = col.give_up_gate(&[
            "covered_topic".to_string(),
            "uncovered_topic_1".to_string(),
            "uncovered_topic_2".to_string(),
        ])?;
        match resp.result.unwrap() {
            GateResult::Insufficient(data) => {
                assert!(data.topic_coverage < MIN_TOPIC_COVERAGE);
            }
            GateResult::Data(_) => panic!("expected insufficient data below the coverage threshold"),
        }
        Ok(())
    }

    #[test]
    fn passes_when_both_thresholds_met() -> Result<()> {
        let mut col = Collection::new();
        let cid = add_card_with_topic(&mut col, "krebs_cycle")?;
        for _ in 0..MIN_GRADED_REVIEWS {
            add_graded_review(&mut col, cid, 3)?;
        }

        let resp = col.give_up_gate(&["krebs_cycle".to_string()])?;
        match resp.result.unwrap() {
            GateResult::Data(data) => {
                assert_eq!(data.total_graded_reviews, MIN_GRADED_REVIEWS);
                assert_eq!(data.topic_coverage, 1.0);
                assert_eq!(data.topics.len(), 1);
            }
            GateResult::Insufficient(_) => panic!("expected sufficient data"),
        }
        Ok(())
    }

    #[test]
    fn every_failing_rule_is_reported_not_just_the_first() -> Result<()> {
        let mut col = Collection::new();
        let covered = add_card_with_topic(&mut col, "covered_topic")?;
        add_card_with_topic(&mut col, "uncovered_topic_1")?;
        add_card_with_topic(&mut col, "uncovered_topic_2")?;
        // Too few reviews AND too little coverage - both must surface, or
        // the student fixes one and is told they still can't be scored.
        add_graded_review(&mut col, covered, 3)?;

        let resp = col.give_up_gate(&[
            "covered_topic".to_string(),
            "uncovered_topic_1".to_string(),
            "uncovered_topic_2".to_string(),
        ])?;
        match resp.result.unwrap() {
            GateResult::Insufficient(data) => {
                assert!(data.reasons.contains(&(Reason::NotEnoughReviews as i32)));
                assert!(data.reasons.contains(&(Reason::NotEnoughCoverage as i32)));
                assert_eq!(data.reasons.len(), 2);
            }
            GateResult::Data(_) => panic!("expected insufficient data"),
        }
        Ok(())
    }

    #[test]
    fn only_the_rule_that_failed_is_reported() -> Result<()> {
        let mut col = Collection::new();
        let cid = add_card_with_topic(&mut col, "krebs_cycle")?;
        // Full coverage (the one requested topic has reviews), but far too
        // few of them.
        add_graded_review(&mut col, cid, 3)?;

        let resp = col.give_up_gate(&["krebs_cycle".to_string()])?;
        match resp.result.unwrap() {
            GateResult::Insufficient(data) => {
                assert_eq!(data.reasons, vec![Reason::NotEnoughReviews as i32]);
            }
            GateResult::Data(_) => panic!("expected insufficient data"),
        }
        Ok(())
    }

    // --- Brainlift v3 POV 2: the rote-pattern rule ---

    #[test]
    fn refuses_when_most_topics_show_a_rote_pattern() -> Result<()> {
        let mut col = Collection::new();
        // Three topics, all heavily studied so review count and coverage
        // both pass - the ONLY thing that can refuse here is the pattern.
        let a = add_card_with_topic(&mut col, "a")?;
        let b = add_card_with_topic(&mut col, "b")?;
        let c = add_card_with_topic(&mut col, "c")?;
        study_rotely(&mut col, a, 100)?;
        study_rotely(&mut col, b, 100)?;
        study_thoughtfully(&mut col, c, 100)?;

        // 2 of 3 judgeable topics are rote = 67% > 40%.
        let resp =
            col.give_up_gate(&["a".to_string(), "b".to_string(), "c".to_string()])?;
        match resp.result.unwrap() {
            GateResult::Insufficient(data) => {
                assert!(
                    data.reasons.contains(&(Reason::RotePatternDetected as i32)),
                    "reasons: {:?}",
                    data.reasons
                );
                // The other two rules must NOT be blamed - they passed.
                assert!(!data.reasons.contains(&(Reason::NotEnoughReviews as i32)));
                assert!(!data.reasons.contains(&(Reason::NotEnoughCoverage as i32)));
                assert!((data.rote_pattern_topic_fraction - 2.0 / 3.0).abs() < 1e-5);
                assert_eq!(data.rote_pattern_fraction_allowed, 0.4);
                assert_eq!(data.rote_pattern_cv_threshold, ROTE_PATTERN_CV_THRESHOLD);
            }
            GateResult::Data(_) => panic!("expected refusal on a rote pattern"),
        }
        Ok(())
    }

    #[test]
    fn scores_normally_when_studying_looks_like_real_thinking() -> Result<()> {
        let mut col = Collection::new();
        let a = add_card_with_topic(&mut col, "a")?;
        let b = add_card_with_topic(&mut col, "b")?;
        study_thoughtfully(&mut col, a, 100)?;
        study_thoughtfully(&mut col, b, 100)?;

        let resp = col.give_up_gate(&["a".to_string(), "b".to_string()])?;
        assert!(
            matches!(resp.result.unwrap(), GateResult::Data(_)),
            "varied latencies must not trip the rote rule"
        );
        Ok(())
    }

    #[test]
    fn a_minority_of_rote_topics_is_tolerated() -> Result<()> {
        let mut col = Collection::new();
        let a = add_card_with_topic(&mut col, "a")?;
        let b = add_card_with_topic(&mut col, "b")?;
        let c = add_card_with_topic(&mut col, "c")?;
        study_rotely(&mut col, a, 100)?;
        study_thoughtfully(&mut col, b, 100)?;
        study_thoughtfully(&mut col, c, 100)?;

        // 1 of 3 = 33%, under the 40% line.
        let resp =
            col.give_up_gate(&["a".to_string(), "b".to_string(), "c".to_string()])?;
        assert!(matches!(resp.result.unwrap(), GateResult::Data(_)));
        Ok(())
    }

    #[test]
    fn dok_1_and_2_topics_are_exempt_because_automaticity_is_the_goal() -> Result<()> {
        let mut col = Collection::new();
        // Definitional content, answered uniformly fast. That is fluency,
        // not a spacebar reflex, and must not cause a refusal.
        let d1 = add_card_with_topic_and_dok(&mut col, "definitions", Some(1))?;
        let d2 = add_card_with_topic_and_dok(&mut col, "terms", Some(2))?;
        let reasoning = add_card_with_topic_and_dok(&mut col, "mechanisms", Some(3))?;
        study_rotely(&mut col, d1, 100)?;
        study_rotely(&mut col, d2, 100)?;
        study_thoughtfully(&mut col, reasoning, 100)?;

        let resp = col.give_up_gate(&[
            "definitions".to_string(),
            "terms".to_string(),
            "mechanisms".to_string(),
        ])?;
        match resp.result.unwrap() {
            GateResult::Data(_) => {}
            GateResult::Insufficient(d) => panic!(
                "DOK 1/2 topics must be exempt; refused with {:?} at fraction {}",
                d.reasons, d.rote_pattern_topic_fraction
            ),
        }
        Ok(())
    }

    #[test]
    fn a_rote_dok_3_topic_still_refuses_even_beside_exempt_ones() -> Result<()> {
        let mut col = Collection::new();
        let d1 = add_card_with_topic_and_dok(&mut col, "definitions", Some(1))?;
        let reasoning = add_card_with_topic_and_dok(&mut col, "mechanisms", Some(3))?;
        study_rotely(&mut col, d1, 100)?;
        study_rotely(&mut col, reasoning, 100)?;

        // Only "mechanisms" is judgeable, and it is rote: 1/1 = 100%.
        let resp =
            col.give_up_gate(&["definitions".to_string(), "mechanisms".to_string()])?;
        match resp.result.unwrap() {
            GateResult::Insufficient(data) => {
                assert!(data.reasons.contains(&(Reason::RotePatternDetected as i32)));
                assert_eq!(data.rote_pattern_topic_fraction, 1.0);
            }
            GateResult::Data(_) => panic!("a rote DOK-3 topic must still refuse"),
        }
        Ok(())
    }

    #[test]
    fn barely_studied_topics_cannot_trigger_the_rote_rule() -> Result<()> {
        let mut col = Collection::new();
        // One review each: no dispersion to measure. If these counted as
        // rote, the app would refuse hardest on students who just began.
        let a = add_card_with_topic(&mut col, "a")?;
        let b = add_card_with_topic(&mut col, "b")?;
        let c = add_card_with_topic(&mut col, "c")?;
        review_with_latency(&mut col, a, 1_000)?;
        review_with_latency(&mut col, b, 1_000)?;
        study_thoughtfully(&mut col, c, 200)?;

        let resp =
            col.give_up_gate(&["a".to_string(), "b".to_string(), "c".to_string()])?;
        match resp.result.unwrap() {
            GateResult::Data(_) => {}
            GateResult::Insufficient(d) => {
                assert!(
                    !d.reasons.contains(&(Reason::RotePatternDetected as i32)),
                    "single-review topics must not count as rote: {:?}",
                    d.reasons
                );
            }
        }
        Ok(())
    }

    #[test]
    fn rote_share_ignores_unjudgeable_topics_in_the_denominator_too() -> Result<()> {
        // The mirror of the test above: unmeasurable topics must not
        // *dilute* the fraction either, or one rote topic could be hidden
        // behind a pile of barely-studied ones.
        let mut col = Collection::new();
        let rote = add_card_with_topic(&mut col, "rote")?;
        study_rotely(&mut col, rote, 100)?;
        for name in ["n1", "n2", "n3", "n4", "n5"] {
            let cid = add_card_with_topic(&mut col, name)?;
            review_with_latency(&mut col, cid, 1_000)?;
        }

        let topics: Vec<String> = ["rote", "n1", "n2", "n3", "n4", "n5"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        let resp = col.give_up_gate(&topics)?;
        match resp.result.unwrap() {
            GateResult::Insufficient(data) => {
                // 1 rote of 1 judgeable = 100%, not 1/6 = 17%.
                assert_eq!(data.rote_pattern_topic_fraction, 1.0);
                assert!(data.reasons.contains(&(Reason::RotePatternDetected as i32)));
            }
            GateResult::Data(_) => panic!("expected refusal"),
        }
        Ok(())
    }
}
