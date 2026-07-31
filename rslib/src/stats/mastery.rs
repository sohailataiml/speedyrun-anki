// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Speedrun addition: per-topic mastery and average recall, for the
//! three-score dashboard's Memory score and coverage map. See the design
//! note alongside this file for why this lives in Rust rather than Python.

use std::collections::HashMap;

use fsrs::FSRS5_DEFAULT_DECAY;

use crate::prelude::*;
use crate::revlog::RevlogEntry;
use crate::search::SortMode;

impl Collection {
    /// Computes mastery/recall for each requested topic. A topic is the
    /// suffix of a `topic::<name>` tag. One tag search plus two batched
    /// queries per topic; no per-card queries, so this stays fast at scale.
    pub(crate) fn mastery_query(
        &mut self,
        topics: &[String],
    ) -> Result<anki_proto::stats::MasteryQueryResponse> {
        let mut out = Vec::with_capacity(topics.len());
        for topic in topics {
            out.push(self.topic_mastery(topic)?);
        }
        Ok(anki_proto::stats::MasteryQueryResponse { topics: out })
    }

    fn topic_mastery(&mut self, topic: &str) -> Result<anki_proto::stats::TopicMastery> {
        // Wrapping the whole `tag:topic::x` clause in quotes lets topic names
        // contain spaces, matching how Anki's own UI quotes generated searches.
        let escaped = topic.replace('\\', "\\\\").replace('"', "\\\"");
        let search = format!("\"tag:topic::{escaped}\"");

        let guard = self.search_cards_into_table(search.as_str(), SortMode::NoOrder)?;
        let cards_total = guard.cards as u32;
        let cards = guard.col.storage.all_searched_cards()?;
        let revlog = guard.col.storage.get_revlog_entries_for_searched_cards()?;
        drop(guard);

        let mut by_card: HashMap<CardId, Vec<&RevlogEntry>> = HashMap::new();
        for entry in &revlog {
            by_card.entry(entry.cid).or_default().push(entry);
        }

        let now = TimestampSecs::now();
        let mut retrievability_sum = 0f32;
        let mut retrievability_count = 0u32;
        let mut correct = 0u32;
        let mut graded = 0u32;
        let mut cards_with_reviews = 0u32;

        for card in &cards {
            let entries = by_card.get(&card.id);

            // Fall back to deriving last-review time from the revlog we already
            // fetched, rather than persisting it onto the card as card_stats()
            // does for a single card — this query must stay read-only.
            let last_review = card.last_review_time.or_else(|| {
                entries.and_then(|entries| {
                    entries
                        .iter()
                        .map(|entry| entry.id.0)
                        .max()
                        .map(|ms| RevlogId(ms).as_secs())
                })
            });

            if let (Some(state), Some(last_review)) = (card.memory_state, last_review) {
                let seconds_elapsed = now.elapsed_secs_since(last_review) as u32;
                let decay = card.decay.unwrap_or(FSRS5_DEFAULT_DECAY);
                let r =
                    fsrs::current_retrievability(state.into(), seconds_elapsed as f32 / 86_400.0, decay);
                retrievability_sum += r;
                retrievability_count += 1;
            }

            if let Some(entries) = entries {
                let mut has_review = false;
                for entry in entries {
                    if entry.has_rating_and_affects_scheduling() {
                        has_review = true;
                        graded += 1;
                        // Matches the existing convention in stats/graphs/hours.rs:
                        // anything above "Again" counts as a correct recall.
                        if entry.button_chosen > 1 {
                            correct += 1;
                        }
                    }
                }
                if has_review {
                    cards_with_reviews += 1;
                }
            }
        }

        Ok(anki_proto::stats::TopicMastery {
            topic: topic.to_string(),
            mastery: if retrievability_count > 0 {
                retrievability_sum / retrievability_count as f32
            } else {
                0.0
            },
            average_recall: if graded > 0 {
                correct as f32 / graded as f32
            } else {
                0.0
            },
            cards_with_reviews,
            cards_total,
        })
    }
}

#[cfg(test)]
mod test {
    use super::*;
    use crate::card::FsrsMemoryState;
    use crate::revlog::RevlogReviewKind;

    /// Adds a basic note tagged `topic::<topic>` and returns its only card's
    /// id.
    fn add_card_with_topic(col: &mut Collection, topic: &str, fields: &[&str]) -> Result<CardId> {
        let mut note = NoteAdder::basic(&mut *col).fields(fields).note();
        note.tags = vec![format!("topic::{topic}")];
        col.add_note(&mut note, DeckId(1))?;
        Ok(col.search_cards(note.id, SortMode::NoOrder)?[0])
    }

    fn give_card_a_review(
        col: &mut Collection,
        cid: CardId,
        button_chosen: u8,
        stability: f32,
        difficulty: f32,
    ) -> Result<()> {
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
        let mut card = col.storage.get_card(cid)?.or_not_found(cid)?;
        card.memory_state = Some(FsrsMemoryState {
            stability,
            difficulty,
        });
        card.decay = Some(FSRS5_DEFAULT_DECAY);
        card.last_review_time = Some(TimestampSecs::now());
        col.storage.update_card(&card)?;
        Ok(())
    }

    #[test]
    fn reviewed_card_contributes_mastery_and_recall() -> Result<()> {
        let mut col = Collection::new();
        let cid = add_card_with_topic(&mut col, "krebs_cycle", &["front", "back"])?;

        // One correct (Good) and one incorrect (Again) review of the same card.
        give_card_a_review(&mut col, cid, 3, 20.0, 5.0)?;
        col.storage.add_revlog_entry(
            &RevlogEntry {
                id: RevlogId::new(),
                cid,
                button_chosen: 1,
                review_kind: RevlogReviewKind::Review,
                ..Default::default()
            },
            true,
        )?;

        let resp = col.mastery_query(&["krebs_cycle".to_string()])?;
        assert_eq!(resp.topics.len(), 1);
        let topic = &resp.topics[0];
        assert_eq!(topic.cards_total, 1);
        assert_eq!(topic.cards_with_reviews, 1);
        assert_eq!(topic.average_recall, 0.5); // 1 correct of 2 graded
        assert!(topic.mastery > 0.0 && topic.mastery <= 1.0);
        Ok(())
    }

    #[test]
    fn new_card_counts_toward_coverage_but_not_mastery() -> Result<()> {
        let mut col = Collection::new();
        add_card_with_topic(&mut col, "unstudied_topic", &["front", "back"])?;

        let resp = col.mastery_query(&["unstudied_topic".to_string()])?;
        let topic = &resp.topics[0];
        assert_eq!(topic.cards_total, 1);
        assert_eq!(topic.cards_with_reviews, 0);
        assert_eq!(topic.mastery, 0.0);
        assert_eq!(topic.average_recall, 0.0);
        Ok(())
    }

    #[test]
    fn topics_are_isolated_from_each_other() -> Result<()> {
        let mut col = Collection::new();
        add_card_with_topic(&mut col, "topic_a", &["front", "back"])?;
        add_card_with_topic(&mut col, "topic_b", &["other", ""])?;

        let resp = col.mastery_query(&["topic_a".to_string()])?;
        assert_eq!(resp.topics[0].cards_total, 1);

        let resp = col.mastery_query(&["topic_a".to_string(), "topic_b".to_string()])?;
        assert_eq!(resp.topics.len(), 2);
        assert_eq!(resp.topics[0].cards_total, 1);
        assert_eq!(resp.topics[1].cards_total, 1);
        Ok(())
    }
}
