// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Speedrun addition (Brainlift v2, MVP): the "Socratic Gatekeeper"
//! decision function. Given a single review's real, already-captured
//! signals — response latency (`RevlogEntry::taken_millis`, captured by
//! upstream Anki on every grade, no new capture engineering needed) and
//! correctness (`button_chosen`, same "anything above Again counts as
//! correct" convention already used in `mastery.rs`) — decides which of
//! four responses applies.
//!
//! **MVP scope note, stated honestly:** the full Brainlift v2 design
//! branches on three signals (latency, stated confidence, correctness).
//! This MVP drops the confidence tap deliberately — Brainlift v2 §5's own
//! self-administered consensus check flagged "ask confidence on every
//! card" as an unresolved friction-cost objection, so building that UI
//! first would mean shipping the exact design choice that check couldn't
//! defend. Latency + correctness alone is a real simplification of the
//! decision table, not the full design — see
//! speedrun/docs/socratic-gate-mvp.md for what this trades away.

use crate::revlog::RevlogEntry;

/// 3 seconds, matching the "Does the student answer within 3 seconds?"
/// threshold in the source spiky POV note (see brainlift.md). A stated,
/// adjustable placeholder — not fitted to any data, same honesty as
/// `performance_model.rs`'s `ASSUMED_DIFFICULTY`/`ASSUMED_TIMING_SECONDS`.
pub(crate) const DEFAULT_FAST_THRESHOLD_MS: u32 = 3_000;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum GateDecision {
    /// Fast + correct: automated mastery. Move on, don't spend stamina.
    AutomatedMastery,
    /// Fast + incorrect: a confident misconception ("dangerous error" in
    /// the source POV). Highest-priority branch — the calibration
    /// literature's finding that confronting confident-wrong answers
    /// measurably reduces overconfidence is the strongest evidence this
    /// MVP is built to test (see brainlift.md §2, source 8).
    DangerousError,
    /// Slow + incorrect: productive-failure opportunity. Real struggle
    /// happened; per Kapur's boundary conditions this is exactly the
    /// case scaffolding should target.
    ProductiveStruggle,
    /// Slow + correct: a lucky-or-effortful guess, not automated
    /// recall. Lowest-priority branch.
    LuckyGuess,
}

impl GateDecision {
    /// The two branches the source POV marks as warranting an
    /// intervention (a Socratic bridge question) rather than a plain
    /// answer reveal.
    pub(crate) fn requires_socratic_bridge(self) -> bool {
        matches!(self, GateDecision::DangerousError | GateDecision::ProductiveStruggle)
    }
}

/// Pure and `Collection`-free, so it's cheap to test exhaustively and
/// cheap to call from any RPC that already has a `RevlogEntry` in hand.
pub(crate) fn socratic_gate_decision(
    taken_millis: u32,
    button_chosen: u8,
    fast_threshold_ms: u32,
) -> GateDecision {
    // Same convention as mastery.rs: anything above "Again" (1) counts
    // as a correct recall.
    let correct = button_chosen > 1;
    let fast = taken_millis <= fast_threshold_ms;
    match (fast, correct) {
        (true, true) => GateDecision::AutomatedMastery,
        (true, false) => GateDecision::DangerousError,
        (false, false) => GateDecision::ProductiveStruggle,
        (false, true) => GateDecision::LuckyGuess,
    }
}

pub(crate) fn socratic_gate_decision_for_entry(
    entry: &RevlogEntry,
    fast_threshold_ms: u32,
) -> GateDecision {
    socratic_gate_decision(entry.taken_millis, entry.button_chosen, fast_threshold_ms)
}

#[cfg(test)]
mod test {
    use super::*;
    use crate::revlog::RevlogId;

    fn entry(taken_millis: u32, button_chosen: u8) -> RevlogEntry {
        RevlogEntry {
            id: RevlogId(0),
            taken_millis,
            button_chosen,
            ..Default::default()
        }
    }

    #[test]
    fn fast_and_correct_is_automated_mastery() {
        assert_eq!(
            socratic_gate_decision(1_500, 3, DEFAULT_FAST_THRESHOLD_MS),
            GateDecision::AutomatedMastery
        );
        assert!(!GateDecision::AutomatedMastery.requires_socratic_bridge());
    }

    #[test]
    fn fast_and_incorrect_is_dangerous_error() {
        assert_eq!(
            socratic_gate_decision(1_500, 1, DEFAULT_FAST_THRESHOLD_MS),
            GateDecision::DangerousError
        );
        assert!(GateDecision::DangerousError.requires_socratic_bridge());
    }

    #[test]
    fn slow_and_incorrect_is_productive_struggle() {
        assert_eq!(
            socratic_gate_decision(9_000, 1, DEFAULT_FAST_THRESHOLD_MS),
            GateDecision::ProductiveStruggle
        );
        assert!(GateDecision::ProductiveStruggle.requires_socratic_bridge());
    }

    #[test]
    fn slow_and_correct_is_lucky_guess() {
        assert_eq!(
            socratic_gate_decision(9_000, 4, DEFAULT_FAST_THRESHOLD_MS),
            GateDecision::LuckyGuess
        );
        assert!(!GateDecision::LuckyGuess.requires_socratic_bridge());
    }

    #[test]
    fn threshold_boundary_is_inclusive_of_fast() {
        // Exactly at the threshold counts as fast, not slow - a
        // deliberate, documented choice so the boundary is
        // deterministic rather than an off-by-one landmine.
        assert_eq!(
            socratic_gate_decision(DEFAULT_FAST_THRESHOLD_MS, 3, DEFAULT_FAST_THRESHOLD_MS),
            GateDecision::AutomatedMastery
        );
    }

    #[test]
    fn revlog_entry_convenience_wrapper_matches_direct_call() {
        let e = entry(1_500, 1);
        assert_eq!(
            socratic_gate_decision_for_entry(&e, DEFAULT_FAST_THRESHOLD_MS),
            socratic_gate_decision(e.taken_millis, e.button_chosen, DEFAULT_FAST_THRESHOLD_MS)
        );
    }
}
