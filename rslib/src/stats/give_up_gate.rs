// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Speedrun addition: the give-up rule (PRD §5). Sits in front of the
//! Performance model — see the design note alongside this file. This module
//! only decides whether there's enough data to score at all; it does not
//! compute a score itself.

use anki_proto::stats::give_up_gate_response::Result as GateResult;
use anki_proto::stats::GiveUpGateData;
use anki_proto::stats::GiveUpGateResponse;
use anki_proto::stats::InsufficientData;
use anki_proto::stats::TopicMastery;

use crate::prelude::*;
use crate::search::SortMode;

/// PRD §5's own example thresholds ("no score below 200 graded reviews and
/// 50% topic coverage"), named here so the two numbers appear exactly once.
const MIN_GRADED_REVIEWS: u32 = 200;
const MIN_TOPIC_COVERAGE: f32 = 0.5;

impl Collection {
    /// Decides whether there's enough data to compute a score for the given
    /// topics. Read-only, same as `mastery_query` — refusing to score must
    /// never itself be something that can corrupt or mutate the collection.
    pub(crate) fn give_up_gate(&mut self, topics: &[String]) -> Result<GiveUpGateResponse> {
        let mastery = self.mastery_query(topics)?;
        let total_graded_reviews = self.total_graded_reviews()?;
        let topic_coverage = topic_coverage(&mastery.topics);

        let sufficient =
            total_graded_reviews >= MIN_GRADED_REVIEWS && topic_coverage >= MIN_TOPIC_COVERAGE;

        let result = if sufficient {
            GateResult::Data(GiveUpGateData {
                total_graded_reviews,
                topic_coverage,
                topics: mastery.topics,
            })
        } else {
            GateResult::Insufficient(InsufficientData {
                total_graded_reviews,
                topic_coverage,
                reviews_required: MIN_GRADED_REVIEWS,
                coverage_required: MIN_TOPIC_COVERAGE,
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
}
