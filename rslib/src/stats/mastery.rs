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
use crate::tags::split_tags;

const TOPIC_TAG_PREFIX: &str = "topic::";
/// Depth of Knowledge, 1-4. See `dok_by_note` for why this is a tag.
const DOK_TAG_PREFIX: &str = "dok::";

impl Collection {
    /// Computes mastery/recall for each requested topic. A topic is the
    /// suffix of a `topic::<name>` tag.
    ///
    /// One combined search across ALL topic-tagged cards, not one search
    /// per requested topic. `bench.py` (speedrun/tools/bench/) caught this
    /// the hard way: at a 50k-card fixture, N per-topic `"tag:topic::x"`
    /// searches took 7-10s total, because `notes.tags` has no index -
    /// every tag search does a full notes-table scan, so N searches cost
    /// O(topics × collection_size) instead of O(collection_size). A single
    /// `tag:topic::*` search plus in-memory grouping by each note's topic
    /// tag turns that into one scan regardless of how many topics are
    /// requested. See rust-change-note.md for the before/after numbers.
    pub(crate) fn mastery_query(
        &mut self,
        topics: &[String],
    ) -> Result<anki_proto::stats::MasteryQueryResponse> {
        Ok(anki_proto::stats::MasteryQueryResponse {
            topics: self.mastery_and_latency_query(topics)?.0,
        })
    }

    /// Mastery *and* Brainlift v3's latency statistics, from a single
    /// scan. They are computed together rather than by two queries
    /// because they read the same cards and the same revlog entries, and
    /// `bench.py` already established that repeated scans over
    /// topic-tagged notes are this feature's main cost. The give-up gate
    /// (v3's rote-pattern rule) needs both at once anyway.
    pub(crate) fn mastery_and_latency_query(
        &mut self,
        topics: &[String],
    ) -> Result<(Vec<anki_proto::stats::TopicMastery>, Vec<TopicLatency>)> {
        if topics.is_empty() {
            return Ok((Vec::new(), Vec::new()));
        }

        let guard = self.search_cards_into_table("tag:topic::*", SortMode::NoOrder)?;
        let cards = guard.col.storage.all_searched_cards()?;
        let revlog = guard.col.storage.get_revlog_entries_for_searched_cards()?;
        let note_ids: Vec<NoteId> = {
            let mut ids: Vec<NoteId> = cards.iter().map(|c| c.note_id).collect();
            ids.sort_unstable();
            ids.dedup();
            ids
        };
        let note_tags = guard.col.storage.get_note_tags_by_id_list(&note_ids)?;
        // Note text, for the length-derived minimum reading time. Fetched
        // over the same id list we already built, inside the same guard,
        // so this is one extra bulk read rather than another scan.
        //
        // The note's joined fields stand in for the *rendered card* text:
        // rendering every card through its template would mean running
        // the template engine across the whole collection for an
        // aggregate stat. Cards of the same note therefore share a
        // reading-time estimate, and cloze deletions count their full
        // source text. Both make the estimate slightly generous, which
        // errs toward *not* accusing a review of being too fast to be
        // real - the safe direction for a signal that penalises the
        // student.
        let note_text_len: HashMap<NoteId, usize> = guard
            .col
            .storage
            .with_ids_in_searched_notes_table(&note_ids, || guard.col.storage.all_searched_notes())?
            .iter()
            .map(|note| (note.id, note.fields().join(" ").split_whitespace().count()))
            .collect();
        drop(guard);

        // Same tie-break as the Speedrun topic-order queue feature
        // (topic_order.rs): lexicographically smallest topic:: tag if a
        // note carries more than one.
        let mut topic_by_note: HashMap<NoteId, &str> = HashMap::new();
        for nt in &note_tags {
            if let Some(topic) = split_tags(&nt.tags)
                .filter(|t| t.starts_with(TOPIC_TAG_PREFIX))
                .map(|t| &t[TOPIC_TAG_PREFIX.len()..])
                .min()
            {
                topic_by_note.insert(nt.id, topic);
            }
        }

        // Depth of Knowledge, from a `dok::<1-4>` note tag.
        //
        // Read from tags rather than from speedrun/data/mcat_outline.json,
        // which is where the section-level `dok_profile` lives. rslib
        // cannot reach that file on Android - it ships as an app asset
        // there and as a repo file on desktop - and teaching the backend
        // two different lookup paths for one number would be a real
        // portability bug rather than a convenience. A tag namespace is
        // what `topic::` already does, syncs with the collection, and
        // works identically on both clients.
        let mut dok_by_note: HashMap<NoteId, u8> = HashMap::new();
        for nt in &note_tags {
            if let Some(dok) = split_tags(&nt.tags)
                .filter(|t| t.starts_with(DOK_TAG_PREFIX))
                .filter_map(|t| t[DOK_TAG_PREFIX.len()..].parse::<u8>().ok())
                .filter(|d| (1..=4).contains(d))
                .max()
            {
                dok_by_note.insert(nt.id, dok);
            }
        }

        let mut cards_by_topic: HashMap<&str, Vec<&crate::card::Card>> = HashMap::new();
        // Highest DOK seen on any note in the topic: a topic containing
        // one genuine reasoning card is a reasoning topic, even if most of
        // its cards are definitions.
        let mut dok_by_topic: HashMap<&str, u8> = HashMap::new();
        for card in &cards {
            if let Some(&topic) = topic_by_note.get(&card.note_id) {
                cards_by_topic.entry(topic).or_default().push(card);
                if let Some(&dok) = dok_by_note.get(&card.note_id) {
                    let slot = dok_by_topic.entry(topic).or_insert(dok);
                    *slot = (*slot).max(dok);
                }
            }
        }
        let mut revlog_by_card: HashMap<CardId, Vec<&RevlogEntry>> = HashMap::new();
        for entry in &revlog {
            revlog_by_card.entry(entry.cid).or_default().push(entry);
        }

        let mut mastery_out = Vec::with_capacity(topics.len());
        let mut latency_out = Vec::with_capacity(topics.len());
        for topic in topics {
            let topic_cards = cards_by_topic.get(topic.as_str()).map_or(&[][..], |v| v);
            let mut mastery = topic_mastery_from(topic, topic_cards, &revlog_by_card);
            let latency = topic_latency_from(
                topic,
                topic_cards,
                &revlog_by_card,
                &note_text_len,
                dok_by_topic.get(topic.as_str()).copied(),
            );
            // The latency numbers ride on TopicMastery so that every
            // existing caller (give-up gate, performance model, both
            // dashboards) gets them without a second RPC.
            mastery.latency_volatility = latency.volatility;
            mastery.system1_review_count = latency.system1_reviews;
            mastery.system2_review_count = latency.system2_reviews;
            mastery.below_min_reading_time_count = latency.below_reading_time_reviews;
            mastery.graded_review_count = latency.graded_reviews;
            mastery_out.push(mastery);
            latency_out.push(latency);
        }
        Ok((mastery_out, latency_out))
    }
}

/// Brainlift v3's per-topic latency statistics. Kept as a plain Rust
/// struct rather than a proto message for now; Phase 3 of
/// speedrun/docs/pivot-plan-latency-volatility.md batches the proto
/// change with the others so the Android backend AAR is cross-compiled
/// once rather than per-field.
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct TopicLatency {
    pub topic: String,
    /// Coefficient of variation of graded-review latencies. `None` when
    /// there are fewer than two reviews - deliberately not 0.0, which
    /// would be indistinguishable from a perfect rote pattern.
    pub volatility: Option<f32>,
    pub system1_reviews: u32,
    pub system2_reviews: u32,
    /// Reviews answered faster than the card could physically be read.
    pub below_reading_time_reviews: u32,
    pub graded_reviews: u32,
    /// Highest `dok::N` seen on this topic's notes, if any is tagged.
    /// `None` means "not labelled", which is treated as *eligible* for
    /// the rote-pattern check - see `is_exempt_from_rote_check`.
    pub dok_level: Option<u8>,
}

impl TopicLatency {
    /// True when this topic's latencies look machine-like. Absence of
    /// data is never a rote pattern - see `latency_monitor::is_rote_pattern`.
    pub(crate) fn is_rote_pattern(&self) -> bool {
        super::latency_monitor::is_rote_pattern(self.volatility)
    }

    /// Whether the rote-pattern rule should be applied to this topic.
    ///
    /// Uniform latency is only *evidence of a problem* where the material
    /// demands reasoning. At DOK 1-2 - naming a structure, recalling a
    /// definition - answering every card in the same second is
    /// automaticity, which is the goal, not a failure. Brainlift v3 says
    /// this itself: it scopes the rule to "DOK-3 tagged topics".
    ///
    /// Untagged topics are treated as **eligible**, not exempt. The
    /// alternative - exempting everything unlabelled - would mean the
    /// rule silently never fires on a deck nobody has tagged, which is a
    /// give-up rule that gives up on itself. Erring toward abstaining is
    /// the right direction for a rule whose whole job is to refuse to
    /// score. Tag a topic `dok::1` or `dok::2` to exempt it deliberately.
    pub(crate) fn is_exempt_from_rote_check(&self) -> bool {
        matches!(self.dok_level, Some(1 | 2))
    }
}

/// Pure: one topic's latency statistics from cards+revlog already scoped
/// to that topic.
fn topic_latency_from(
    topic: &str,
    cards: &[&crate::card::Card],
    revlog_by_card: &HashMap<CardId, Vec<&RevlogEntry>>,
    note_word_count: &HashMap<NoteId, usize>,
    dok_level: Option<u8>,
) -> TopicLatency {
    use super::latency_monitor::classify_review;
    use super::latency_monitor::latency_volatility;
    use super::latency_monitor::minimum_reading_time_ms_for_words;
    use super::latency_monitor::SystemType;
    use super::latency_monitor::DEFAULT_FAST_THRESHOLD_MS;

    let mut latencies: Vec<u32> = Vec::new();
    let mut system1 = 0u32;
    let mut system2 = 0u32;
    let mut below_reading_time = 0u32;

    for card in cards {
        let Some(entries) = revlog_by_card.get(&card.id) else {
            continue;
        };
        // 0 when the note's text is unavailable, which disables the
        // spacebar-reflex check for that card rather than defaulting to
        // the floor and accusing every fast review.
        let min_read_ms = note_word_count
            .get(&card.note_id)
            .map(|words| minimum_reading_time_ms_for_words(*words))
            .unwrap_or(0);

        for entry in entries {
            if !entry.has_rating_and_affects_scheduling() {
                continue;
            }
            latencies.push(entry.taken_millis);
            match classify_review(entry.taken_millis, DEFAULT_FAST_THRESHOLD_MS) {
                SystemType::System1Recognition => system1 += 1,
                SystemType::System2Analytical => system2 += 1,
            }
            if min_read_ms > 0 && entry.taken_millis < min_read_ms {
                below_reading_time += 1;
            }
        }
    }

    TopicLatency {
        topic: topic.to_string(),
        volatility: latency_volatility(&latencies),
        system1_reviews: system1,
        system2_reviews: system2,
        below_reading_time_reviews: below_reading_time,
        graded_reviews: latencies.len() as u32,
        dok_level,
    }
}

/// Pure: computes one topic's mastery/recall from cards+revlog already
/// scoped to that topic. Same math as the original per-topic-search
/// version, just fed from in-memory grouped data instead of a fresh SQL
/// search per topic.
fn topic_mastery_from(
    topic: &str,
    cards: &[&crate::card::Card],
    revlog_by_card: &HashMap<CardId, Vec<&RevlogEntry>>,
) -> anki_proto::stats::TopicMastery {
    let cards_total = cards.len() as u32;
    let now = TimestampSecs::now();
    let mut retrievability_sum = 0f32;
    let mut retrievability_count = 0u32;
    let mut correct = 0u32;
    let mut graded = 0u32;
    let mut cards_with_reviews = 0u32;

    for card in cards {
        let entries = revlog_by_card.get(&card.id);

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
            let r = fsrs::current_retrievability(
                state.into(),
                seconds_elapsed as f32 / 86_400.0,
                decay,
            );
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

    anki_proto::stats::TopicMastery {
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
        // Filled in by the caller from the matching TopicLatency; kept
        // out of this function so the mastery math stays exactly what it
        // was before v3 (there is a test pinning that).
        latency_volatility: None,
        system1_review_count: 0,
        system2_review_count: 0,
        below_min_reading_time_count: 0,
        graded_review_count: 0,
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

    // --- Brainlift v3: per-topic latency statistics ---

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

    fn latency_for(col: &mut Collection, topic: &str) -> Result<TopicLatency> {
        let (_, latency) = col.mastery_and_latency_query(&[topic.to_string()])?;
        Ok(latency.into_iter().next().unwrap())
    }

    #[test]
    fn uniform_latencies_flag_a_rote_pattern_for_the_topic() -> Result<()> {
        let mut col = Collection::new();
        let cid = add_card_with_topic(&mut col, "krebs", &["Front", "Back"])?;
        // The spacebar reflex: same duration every time.
        for ms in [1_000, 1_020, 980, 1_010] {
            review_with_latency(&mut col, cid, ms)?;
        }
        let latency = latency_for(&mut col, "krebs")?;
        assert_eq!(latency.graded_reviews, 4);
        assert!(
            latency.is_rote_pattern(),
            "volatility {:?}",
            latency.volatility
        );
        Ok(())
    }

    #[test]
    fn varied_latencies_do_not_flag_a_rote_pattern() -> Result<()> {
        let mut col = Collection::new();
        let cid = add_card_with_topic(&mut col, "krebs", &["Front", "Back"])?;
        for ms in [700, 3_500, 1_200, 9_000] {
            review_with_latency(&mut col, cid, ms)?;
        }
        let latency = latency_for(&mut col, "krebs")?;
        assert!(
            !latency.is_rote_pattern(),
            "volatility {:?}",
            latency.volatility
        );
        Ok(())
    }

    #[test]
    fn system1_and_system2_reviews_are_counted_separately() -> Result<()> {
        let mut col = Collection::new();
        let cid = add_card_with_topic(&mut col, "krebs", &["Front", "Back"])?;
        review_with_latency(&mut col, cid, 1_000)?; // fast
        review_with_latency(&mut col, cid, 2_000)?; // fast
        review_with_latency(&mut col, cid, 8_000)?; // slow
        let latency = latency_for(&mut col, "krebs")?;
        assert_eq!(latency.system1_reviews, 2);
        assert_eq!(latency.system2_reviews, 1);
        assert_eq!(latency.graded_reviews, 3);
        Ok(())
    }

    #[test]
    fn reviews_faster_than_the_card_can_be_read_are_counted() -> Result<()> {
        let mut col = Collection::new();
        // ~60 words across both fields -> minimum reading time well above
        // the 800ms floor, so a 500ms answer is physically impossible.
        let long = "word ".repeat(30);
        let cid = add_card_with_topic(&mut col, "long", &[&long, &long])?;
        review_with_latency(&mut col, cid, 500)?;
        review_with_latency(&mut col, cid, 30_000)?;
        let latency = latency_for(&mut col, "long")?;
        assert_eq!(latency.below_reading_time_reviews, 1);
        Ok(())
    }

    #[test]
    fn a_short_card_answered_quickly_is_not_a_spacebar_reflex() -> Result<()> {
        let mut col = Collection::new();
        // "Citrate synthase" can honestly be read and graded fast; the
        // floor must not turn ordinary fluency into an accusation.
        let cid = add_card_with_topic(&mut col, "short", &["Enzyme?", "Citrate synthase"])?;
        review_with_latency(&mut col, cid, 900)?;
        let latency = latency_for(&mut col, "short")?;
        assert_eq!(latency.below_reading_time_reviews, 0);
        Ok(())
    }

    #[test]
    fn a_topic_with_one_review_has_no_volatility_and_is_not_rote() -> Result<()> {
        let mut col = Collection::new();
        let cid = add_card_with_topic(&mut col, "krebs", &["Front", "Back"])?;
        review_with_latency(&mut col, cid, 1_000)?;
        let latency = latency_for(&mut col, "krebs")?;
        assert_eq!(latency.volatility, None);
        assert!(!latency.is_rote_pattern());
        Ok(())
    }

    #[test]
    fn latency_is_isolated_between_topics() -> Result<()> {
        let mut col = Collection::new();
        let rote = add_card_with_topic(&mut col, "rote", &["Front", "Back"])?;
        let real = add_card_with_topic(&mut col, "real", &["Front", "Back"])?;
        for ms in [1_000, 1_005, 995, 1_010] {
            review_with_latency(&mut col, rote, ms)?;
        }
        for ms in [700, 4_000, 1_500, 11_000] {
            review_with_latency(&mut col, real, ms)?;
        }
        let (_, latency) =
            col.mastery_and_latency_query(&["rote".to_string(), "real".to_string()])?;
        assert!(latency[0].is_rote_pattern(), "{:?}", latency[0]);
        assert!(!latency[1].is_rote_pattern(), "{:?}", latency[1]);
        Ok(())
    }

    #[test]
    #[ignore]
    fn probe_real_collection_latency() -> Result<()> {
        let path = std::env::var("SPEEDRUN_COL").expect("set SPEEDRUN_COL");
        let mut col = crate::collection::CollectionBuilder::new(path).build()?;
        let mut topics: Vec<String> = Vec::new();
        for nt in col.storage.get_note_tags_by_predicate(|tags| {
            tags.split(' ').any(|x| x.starts_with(TOPIC_TAG_PREFIX))
        })? {
            for tag in split_tags(&nt.tags).filter(|x| x.starts_with(TOPIC_TAG_PREFIX)) {
                let name = tag[TOPIC_TAG_PREFIX.len()..].to_string();
                if !topics.contains(&name) {
                    topics.push(name);
                }
            }
        }
        topics.sort();
        println!(
            "\n{:<24} {:>7} {:>10} {:>5} {:>5} {:>6}  {}",
            "topic", "reviews", "volatility", "S1", "S2", "<read", "verdict"
        );
        let (_, latency) = col.mastery_and_latency_query(&topics)?;
        for l in &latency {
            let v = l
                .volatility
                .map(|x| format!("{x:.3}"))
                .unwrap_or_else(|| "n/a".into());
            println!(
                "{:<24} {:>7} {:>10} {:>5} {:>5} {:>6}  {}",
                l.topic,
                l.graded_reviews,
                v,
                l.system1_reviews,
                l.system2_reviews,
                l.below_reading_time_reviews,
                if l.is_rote_pattern() {
                    "ROTE PATTERN"
                } else {
                    "ok"
                }
            );
        }
        let rote = latency.iter().filter(|l| l.is_rote_pattern()).count();
        println!(
            "\n{rote}/{} topics flagged as rote pattern ({:.0}%)",
            latency.len(),
            100.0 * rote as f32 / latency.len().max(1) as f32
        );
        Ok(())
    }

    #[test]
    fn mastery_query_is_unchanged_by_the_latency_addition() -> Result<()> {
        // The latency work rides the same scan; the existing Memory score
        // must not shift because of it.
        let mut col = Collection::new();
        let cid = add_card_with_topic(&mut col, "krebs", &["Front", "Back"])?;
        give_card_a_review(&mut col, cid, 3, 100.0, 5.0)?;
        let via_wrapper = col.mastery_query(&["krebs".to_string()])?;
        let (via_combined, _) = col.mastery_and_latency_query(&["krebs".to_string()])?;
        assert_eq!(via_wrapper.topics, via_combined);
        Ok(())
    }
}
