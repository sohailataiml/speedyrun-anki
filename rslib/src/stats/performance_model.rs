// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Speedrun addition: the Performance model (PRD §10.2) — predicts accuracy
//! on held-back exam-style questions from topic mastery, question
//! difficulty, timing, and coverage. Runs the give-up gate first; nothing
//! here executes unless that gate passes.
//!
//! The trained weights are produced by
//! `speedrun/tools/scoring-train/train_performance_model.py` and embedded
//! at compile time, so desktop and Android run the identical model - the
//! same "one engine" guarantee `mastery_query` already provides. See that
//! script for why the current weights are trained on synthetic data, not
//! real held-back questions.

use anki_proto::stats::give_up_gate_response::Result as GateResult;
use anki_proto::stats::performance_query_response::Result as PerformanceResult;
use anki_proto::stats::PerformanceData;
use anki_proto::stats::PerformanceQueryResponse;
use serde::Deserialize;

use crate::prelude::*;
use crate::search::SortMode;

const WEIGHTS_JSON: &str =
    include_str!("../../../speedrun/tools/scoring-train/weights/performance_model.json");

#[derive(Deserialize)]
struct PerformanceModelWeights {
    bias: f32,
    weight_mastery: f32,
    weight_difficulty: f32,
    weight_timing_z: f32,
    weight_coverage: f32,
    timing_mean_seconds: f32,
    timing_std_seconds: f32,
}

impl PerformanceModelWeights {
    fn loaded() -> Self {
        // Parsing our own build-time-embedded, script-generated file: a
        // parse failure here means the weights file is corrupt, which is a
        // build-time problem, not a runtime one worth a Result.
        serde_json::from_str(WEIGHTS_JSON).expect("performance_model.json must be valid")
    }

    fn predict(&self, mastery: f32, difficulty: f32, timing_seconds: f32, coverage: f32) -> f32 {
        let timing_z = (timing_seconds - self.timing_mean_seconds) / self.timing_std_seconds;
        let logit = self.bias
            + self.weight_mastery * mastery
            + self.weight_difficulty * difficulty
            + self.weight_timing_z * timing_z
            + self.weight_coverage * coverage;
        sigmoid(logit)
    }
}

fn sigmoid(x: f32) -> f32 {
    1.0 / (1.0 + (-x).exp())
}

/// Mean mastery across the topics the give-up gate confirmed have enough
/// data. Unweighted: giving a heavily-reviewed topic more say than a
/// lightly-reviewed one would double-count what `total_graded_reviews`
/// already gates on.
fn mean_mastery(topics: &[anki_proto::stats::TopicMastery]) -> f32 {
    if topics.is_empty() {
        return 0.0;
    }
    topics.iter().map(|t| t.mastery).sum::<f32>() / topics.len() as f32
}

/// Accuracy on AI-generated "jitter" cards - context-shifted variants
/// that test whether a fact survives a change of scenario (Brainlift v3
/// POV 3). `accuracy` is `None` rather than 0.0 when there are no
/// attempts, because "no transfer questions answered yet" and "gets every
/// transfer question wrong" are opposite claims and a defaulted zero
/// would report the second.
pub(crate) struct JitterAccuracy {
    pub accuracy: Option<f32>,
    pub attempts: u32,
}

impl Collection {
    /// Jitter variants are ordinary cards carrying a `jitter::` tag, so
    /// their accuracy is the existing revlog math with a tag filter -
    /// no new schema, and it syncs like any other card. See
    /// speedrun/docs/jitter-engine.md for why that shape was chosen.
    pub(crate) fn jitter_accuracy(&mut self) -> Result<JitterAccuracy> {
        let guard = self.search_cards_into_table("tag:jitter::*", SortMode::NoOrder)?;
        let revlog = guard.col.storage.get_revlog_entries_for_searched_cards()?;
        drop(guard);
        let graded: Vec<_> = revlog
            .iter()
            .filter(|e| e.has_rating_and_affects_scheduling())
            .collect();
        if graded.is_empty() {
            return Ok(JitterAccuracy {
                accuracy: None,
                attempts: 0,
            });
        }
        // Same convention as mastery.rs: anything above "Again" counts as
        // a correct recall.
        let correct = graded.iter().filter(|e| e.button_chosen > 1).count();
        Ok(JitterAccuracy {
            accuracy: Some(correct as f32 / graded.len() as f32),
            attempts: graded.len() as u32,
        })
    }

    pub(crate) fn performance_query(
        &mut self,
        topics: &[String],
        average_difficulty: f32,
        average_timing_seconds: f32,
    ) -> Result<PerformanceQueryResponse> {
        let gate = self.give_up_gate(topics)?;
        let jitter = self.jitter_accuracy()?;
        let result = match gate.result.unwrap() {
            GateResult::Insufficient(insufficient) => PerformanceResult::Insufficient(insufficient),
            GateResult::Data(data) => {
                let weights = PerformanceModelWeights::loaded();
                let predicted_accuracy = weights.predict(
                    mean_mastery(&data.topics),
                    average_difficulty,
                    average_timing_seconds,
                    data.topic_coverage,
                );
                PerformanceResult::Data(PerformanceData {
                    jitter_accuracy: jitter.accuracy,
                    jitter_attempts: jitter.attempts,
                    predicted_accuracy,
                    inputs: Some(data),
                })
            }
        };
        Ok(PerformanceQueryResponse {
            result: Some(result),
        })
    }
}

#[cfg(test)]
mod test {
    use super::*;

    use crate::revlog::RevlogEntry;
    use crate::revlog::RevlogReviewKind;

    fn add_jitter_card(col: &mut Collection, src_nid: u64) -> Result<CardId> {
        let mut note = NoteAdder::basic(&mut *col).fields(&["variant", "answer"]).note();
        note.tags = vec![format!("jitter::src::{src_nid}"), "topic::krebs".to_string()];
        col.add_note(&mut note, DeckId(1))?;
        Ok(col.search_cards(note.id, SortMode::NoOrder)?[0])
    }

    fn grade(col: &mut Collection, cid: CardId, button_chosen: u8) -> Result<()> {
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
    fn no_jitter_attempts_reports_none_not_zero_accuracy() -> Result<()> {
        // "No transfer questions answered yet" and "gets every transfer
        // question wrong" are opposite claims. A defaulted 0.0 would
        // report the second and make an untested student look hopeless.
        let mut col = Collection::new();
        let jitter = col.jitter_accuracy()?;
        assert_eq!(jitter.accuracy, None);
        assert_eq!(jitter.attempts, 0);
        Ok(())
    }

    #[test]
    fn jitter_accuracy_counts_only_jitter_tagged_cards() -> Result<()> {
        let mut col = Collection::new();
        // An ordinary card, graded wrong - must not drag jitter accuracy
        // down, since it is not a transfer question.
        let mut plain = NoteAdder::basic(&mut col).fields(&["a", "b"]).note();
        plain.tags = vec!["topic::krebs".to_string()];
        col.add_note(&mut plain, DeckId(1))?;
        let plain_cid = col.search_cards(plain.id, SortMode::NoOrder)?[0];
        grade(&mut col, plain_cid, 1)?;

        let j = add_jitter_card(&mut col, 123)?;
        grade(&mut col, j, 3)?;
        grade(&mut col, j, 3)?;
        grade(&mut col, j, 1)?;

        let jitter = col.jitter_accuracy()?;
        assert_eq!(jitter.attempts, 3);
        assert!((jitter.accuracy.unwrap() - 2.0 / 3.0).abs() < 1e-5);
        Ok(())
    }

    #[test]
    fn jitter_accuracy_reaches_the_performance_response() -> Result<()> {
        let mut col = Collection::new();
        let j = add_jitter_card(&mut col, 123)?;
        for _ in 0..250 {
            grade(&mut col, j, 3)?;
        }
        let resp = col.performance_query(&["krebs".to_string()], 0.5, 70.0)?;
        match resp.result.unwrap() {
            PerformanceResult::Data(data) => {
                assert_eq!(data.jitter_attempts, 250);
                assert_eq!(data.jitter_accuracy, Some(1.0));
            }
            PerformanceResult::Insufficient(i) => {
                panic!("expected data, got insufficient: {:?}", i.reasons)
            }
        }
        Ok(())
    }

    /// A small hand-picked weights fixture, independent of the real trained
    /// file, so this test checks the math rather than the training run.
    fn test_weights() -> PerformanceModelWeights {
        PerformanceModelWeights {
            bias: 0.0,
            weight_mastery: 2.0,
            weight_difficulty: -2.0,
            weight_timing_z: 0.0,
            weight_coverage: 1.0,
            timing_mean_seconds: 70.0,
            timing_std_seconds: 30.0,
        }
    }

    #[test]
    fn higher_mastery_and_coverage_predict_higher_accuracy() {
        let weights = test_weights();
        let low = weights.predict(0.1, 0.5, 70.0, 0.2);
        let high = weights.predict(0.9, 0.5, 70.0, 0.9);
        assert!(high > low);
        assert!((0.0..=1.0).contains(&low));
        assert!((0.0..=1.0).contains(&high));
    }

    #[test]
    fn higher_difficulty_predicts_lower_accuracy() {
        let weights = test_weights();
        let easy = weights.predict(0.5, 0.1, 70.0, 0.5);
        let hard = weights.predict(0.5, 0.9, 70.0, 0.5);
        assert!(easy > hard);
    }

    #[test]
    fn real_embedded_weights_parse_and_predict_a_valid_probability() {
        let weights = PerformanceModelWeights::loaded();
        let p = weights.predict(0.7, 0.5, 90.0, 0.8);
        assert!((0.0..=1.0).contains(&p));
    }

    #[test]
    fn performance_query_refuses_when_give_up_gate_refuses() -> Result<()> {
        let mut col = Collection::new();
        let resp = col.performance_query(&["nonexistent_topic".to_string()], 0.5, 70.0)?;
        match resp.result.unwrap() {
            PerformanceResult::Insufficient(_) => {}
            PerformanceResult::Data(_) => panic!("expected insufficient data on an empty collection"),
        }
        Ok(())
    }
}
