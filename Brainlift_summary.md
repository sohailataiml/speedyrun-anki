# Speedrun Brainlift v1: The Latency-Volatility Pivot (MCAT)

Note: the full brainlink doc is at this location:
https://github.com/sohailataiml/speedyrun-anki/blob/63b0ab5893636f0d6f4957ced45ba022334f2880/brainlift.md

## 1. The Problem: The Readiness Illusion
Current MCAT tools (AnKing, UWorld) measure **Retention** or **Accuracy**, but fail to detect "Anki-Brain." Students often achieve 95% retention through rote recognition (System 1) but plateau on the actual exam because they haven't mastered the underlying science (System 2).

## 2. The Spiky POV: Latency > Retention
**Retention is a vanity metric. Latency Volatility does not measure mastery — it measures whether a retention number can be trusted at all, and the app refuses to score when it can't.**
*   **The Argument:** Fast recall on complex concepts is a signal of pattern recognition, not mastery.
*   **The Spacebar Reflex:** Answering DOK-3 cards (e.g., Enzyme Kinetics) in <2 seconds indicates a "Fluency Illusion" where ease of processing masks weak mental models.

## 3. The Systems Lineage (Evidence)
*   **FSRS (Free Spaced Repetition Scheduler):** Used for base memory modeling but extended to include time-based audits.
*   **Bjork & Bjork (2011):** "Desirable Difficulties" – Ease of recall is a poor predictor of long-term learning.
*   **Kahneman (2011):** System 1 (Fast/Automatic) vs. System 2 (Slow/Analytical). MCAT requires System 2.

## 4. The Solution: The Study Engine
*   **Latency Monitor:** A Rust-based engine tagging reviews as System 1 or System 2.
*   **Readiness Multiplier:** Applies a 0.5x penalty to cards answered faster than the "Minimum Reading Time."
*   **AI Jitter Engine:** An AI Proctor that generates novel variations of cards to test knowledge transfer rather than card memorization.

## 5. Success Metrics
*   **Memory Score:** Raw FSRS Retrievability.
*   **Performance Score:** Accuracy on AI-generated "Jittered" cards.
*   **Readiness Score:** A composite weighted by **Latency Volatility**.
*   **The Give-Up Rule:** No Readiness score is shown if Latency Volatility is < 0.2 (indicating rote recognition) for > 40% of the deck.
