// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Speedrun addition: an optional topic-interleaving toggle on the review
//! queue, built for the Brainlift §9 thesis ablation (three-way build:
//! interleaved vs. blocked vs. unmodified Anki - see
//! speedrun/docs/rust-change-note.md for the full rationale).
//!
//! Deliberately a config key (`speedrunTopicOrder`), not a new protobuf
//! RPC or deck-config field: it needs no proto regeneration and rides
//! Anki's existing config sync for free, which matters because this
//! fork's Android build requires a full NDK cross-compile of the AAR for
//! any RPC surface change (see ARCHITECTURE.md §4) - a config key avoids
//! that entirely.
//!
//! Scope: reorders `QueueBuilder::review` and `QueueBuilder::new` only.
//! Does NOT touch `learning`/`day_learning` - those are due-time-ordered
//! by `sort_learning` for correct intraday scheduling semantics, and
//! reordering them would break that for no benefit to the thesis, which
//! is about review-session topic exposure, not learning-step timing.
//! Undo-safe by construction: `QueueUpdate` restores queue *entries*, not
//! positions, and queues are always rebuilt from scratch on invalidation.

use std::collections::BTreeMap;
use std::collections::HashMap;
use std::collections::VecDeque;

use super::DueCard;
use super::NewCard;
use super::QueueBuilder;
use crate::prelude::*;
use crate::tags::split_tags;

const CONFIG_KEY: &str = "speedrunTopicOrder";
const TOPIC_TAG_PREFIX: &str = "topic::";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub(crate) enum TopicOrder {
    /// No reorder at all - byte-identical to upstream Anki. This is the
    /// "build 3: unmodified Anki" arm of the ablation.
    #[default]
    AnkiDefault,
    /// All of topic A, then all of topic B, ... ("build 2: mode off").
    Blocked,
    /// Round-robin across topics: A, B, C, A, B, C, ... ("build 1: mode
    /// on", the thesis feature).
    Interleaved,
}

impl TopicOrder {
    /// Reads the `speedrunTopicOrder` config key. Missing, unset, or an
    /// unrecognized value all fall back to `AnkiDefault` - the toggle is
    /// additive and opt-in, never a silent behavior change for existing
    /// collections.
    pub(crate) fn from_config(col: &Collection) -> Self {
        match col
            .get_config_optional::<String, _>(CONFIG_KEY)
            .as_deref()
        {
            Some("blocked") => TopicOrder::Blocked,
            Some("interleaved") => TopicOrder::Interleaved,
            _ => TopicOrder::AnkiDefault,
        }
    }
}

/// Pure and `Collection`-free by design, so it's cheap to test
/// exhaustively without spinning up a collection. Items with no resolved
/// topic keep their relative order and are appended after all topic
/// buckets. Topic buckets are ordered alphabetically by topic name -
/// deterministic across runs and across all three ablation builds, which
/// the comparison depends on.
fn reorder_by_topic<T: Copy>(
    items: &[T],
    topic_of: impl Fn(&T) -> Option<String>,
    order: TopicOrder,
) -> Vec<T> {
    if order == TopicOrder::AnkiDefault {
        return items.to_vec();
    }

    let mut buckets: BTreeMap<String, VecDeque<T>> = BTreeMap::new();
    let mut no_topic: Vec<T> = Vec::new();
    for item in items {
        match topic_of(item) {
            Some(topic) => buckets.entry(topic).or_default().push_back(*item),
            None => no_topic.push(*item),
        }
    }

    let mut out = Vec::with_capacity(items.len());
    match order {
        TopicOrder::Blocked => {
            for bucket in buckets.into_values() {
                out.extend(bucket);
            }
        }
        TopicOrder::Interleaved => {
            let mut queues: Vec<VecDeque<T>> = buckets.into_values().collect();
            loop {
                let mut progressed = false;
                for queue in queues.iter_mut() {
                    if let Some(item) = queue.pop_front() {
                        out.push(item);
                        progressed = true;
                    }
                }
                if !progressed {
                    break;
                }
            }
        }
        TopicOrder::AnkiDefault => unreachable!("handled by early return above"),
    }
    out.extend(no_topic);
    out
}

/// One batched query for the note ids actually gathered into this queue
/// build - not the whole collection. If a note carries more than one
/// `topic::` tag, the lexicographically smallest is used; deterministic,
/// and worth stating rather than leaving as an implicit tie-break.
fn topic_map(col: &Collection, note_ids: &[NoteId]) -> Result<HashMap<NoteId, String>> {
    let mut ids: Vec<NoteId> = note_ids.to_vec();
    ids.sort_unstable();
    ids.dedup();

    let mut map = HashMap::new();
    for note_tags in col.storage.get_note_tags_by_id_list(&ids)? {
        if let Some(topic) = split_tags(&note_tags.tags)
            .filter(|tag| tag.starts_with(TOPIC_TAG_PREFIX))
            .min()
        {
            map.insert(note_tags.id, topic.to_string());
        }
    }
    Ok(map)
}

impl QueueBuilder {
    /// No-op unless `speedrunTopicOrder` is set to `"blocked"` or
    /// `"interleaved"`. Must run after `gather_cards` (needs the gathered
    /// note ids) and before `build()` (which consumes `review`/`new`).
    pub(super) fn apply_topic_order(&mut self, col: &mut Collection) -> Result<()> {
        let order = TopicOrder::from_config(col);
        if order == TopicOrder::AnkiDefault {
            return Ok(());
        }

        let note_ids: Vec<NoteId> = self
            .review
            .iter()
            .map(|c| c.note_id)
            .chain(self.new.iter().map(|c| c.note_id))
            .collect();
        let topics = topic_map(col, &note_ids)?;

        self.review = reorder_by_topic(
            &self.review,
            |c: &DueCard| topics.get(&c.note_id).cloned(),
            order,
        );
        self.new = reorder_by_topic(
            &self.new,
            |c: &NewCard| topics.get(&c.note_id).cloned(),
            order,
        );
        Ok(())
    }
}

#[cfg(test)]
mod test {
    use super::*;

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    struct Item {
        id: u32,
        topic: Option<char>,
    }

    fn items(spec: &[(u32, Option<char>)]) -> Vec<Item> {
        spec.iter()
            .map(|&(id, topic)| Item { id, topic })
            .collect()
    }

    fn topic_of(item: &Item) -> Option<String> {
        item.topic.map(|c| c.to_string())
    }

    fn ids(items: &[Item]) -> Vec<u32> {
        items.iter().map(|i| i.id).collect()
    }

    #[test]
    fn anki_default_returns_the_input_unchanged() {
        let input = items(&[(1, Some('b')), (2, Some('a')), (3, None)]);
        let out = reorder_by_topic(&input, topic_of, TopicOrder::AnkiDefault);
        assert_eq!(out, input);
    }

    #[test]
    fn blocked_groups_each_topic_contiguously_and_preserves_within_topic_order() {
        // Interleaved input; each topic's original relative order (by id)
        // must survive being grouped into a contiguous block.
        let input = items(&[
            (1, Some('b')),
            (2, Some('a')),
            (3, Some('b')),
            (4, Some('a')),
            (5, None),
        ]);
        let out = reorder_by_topic(&input, topic_of, TopicOrder::Blocked);
        // alphabetical bucket order: 'a' before 'b'; no-topic items last.
        assert_eq!(ids(&out), vec![2, 4, 1, 3, 5]);
    }

    #[test]
    fn interleaved_never_repeats_a_topic_back_to_back_while_topics_remain() {
        let input = items(&[
            (1, Some('a')),
            (2, Some('a')),
            (3, Some('a')),
            (4, Some('b')),
            (5, Some('c')),
        ]);
        let out = reorder_by_topic(&input, topic_of, TopicOrder::Interleaved);
        // 3 topics, round-robin: a, b, c, a, a (b and c exhausted after 1
        // each, so the only back-to-back repeat is the trailing 'a','a',
        // once every other topic has run out - exactly what this test
        // name asserts).
        assert_eq!(ids(&out), vec![1, 4, 5, 2, 3]);
    }

    #[test]
    fn untagged_items_are_appended_after_all_topic_buckets() {
        let input = items(&[(1, None), (2, Some('a')), (3, None)]);
        let blocked = reorder_by_topic(&input, topic_of, TopicOrder::Blocked);
        assert_eq!(ids(&blocked), vec![2, 1, 3]);
        let interleaved = reorder_by_topic(&input, topic_of, TopicOrder::Interleaved);
        assert_eq!(ids(&interleaved), vec![2, 1, 3]);
    }
}
