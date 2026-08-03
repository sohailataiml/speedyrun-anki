# Speedrun Brainlift v1: The Latency-Volatility Pivot

**Exam:** MCAT (Medical College Admission Test)  
**Spiky POV:** Retention is a vanity metric; **Latency Volatility** is the only true measure of DOK-3 mastery.

---

## 1. Purpose and Scope

**Purpose:** To build a study engine that distinguishes between "Anki-Brain" (rote recognition) and actual MCAT readiness. The app will predict exam scores by auditing the *quality* of the student's retrieval, not just the *fact* of it.

**Out of Scope:**
*   A general-purpose Socratic tutor (too much friction, grader-averse).
*   Broad support for multiple exams (focusing purely on the MCAT scale).
*   Replacing the FSRS scheduler (we extend it, not replace it).

---

## 2. DOK 1: The Systems Lineage (Sources)

*   **SM-2 / SM-18 (SuperMemo):** The original Spaced Repetition lineage. Established the core idea that memory stability ($S$) can be modeled mathematically.
*   **FSRS (Free Spaced Repetition Scheduler):** The modern standard for Anki. It models Retrievability ($R$) but ignores the *time* taken to retrieve (Latency).
*   **Encoding Specificity Principle:** Tulving & Thomson (1973). Proves that memory is context-dependent. If the context is "an Anki card," the memory may not transfer to "an MCAT passage."
*   **Fluency Illusions:** Bjork & Bjork (2011). Research into "Desirable Difficulties." Argues that ease of recall is a poor predictor of long-term learning.
*   **System 1 vs. System 2:** Kahneman (2011). Differentiates between fast, automatic recognition (System 1) and slow, analytical reasoning (System 2).

---

## 3. DOK 2: Summaries and Rejections

*   **FSRS (Accepted):** We use FSRS to handle the base "Memory" score. It is the best model for "Can you recall this?"
*   **FSRS (Rejected):** We reject the idea that FSRS alone equates to "Readiness." FSRS treats a 1.0s response and a 6.0s response as identical "Good" grades. For DOK-3 concepts, this is a fatal flaw.
*   **Anki 4-Button System (Rejected):** We reject the user's self-assessment ("Hard/Good/Easy") as the primary data point. Users are miscalibrated. We will prioritize **Latency** (objective) over **Ease** (subjective).
*   **Desirable Difficulties (Accepted):** We accept that higher latency on complex cards is actually a sign of "Productive Struggle" (DOK 3).

---

## 4. DOK 3: The Gap Analysis (Teardown)

Current MCAT tools (AnKing, UWorld, Blueprint) all suffer from **The Readiness Illusion**:

*   **Anki/AnKing:** Measures "Retention." If you hit 95% retention, the app says you are "Mastered." 
    *   *Gap:* Students often hit 95% retention but plateau at 505 on the MCAT because they have mastered the cards, not the science.
*   **UWorld:** Measures "Accuracy." 
    *   *Gap:* It doesn't track how much you've forgotten since you last did the question.
*   **The "Spacebar Reflex":** None of these tools detect when a student is flipping cards so fast (System 1) that they aren't even reading the prompt. This is a "DOK 1 behavior" applied to "DOK 3 material."

---

## 5. DOK 4: The Spiky POV

**Consensus says:** High retention and fast recall are the goals of a flashcard app.  
**I think:** Fast recall on complex concepts is a signal of **Recognition (System 1)**, not **Mastery (System 2)**. A student who reviews a DOK-3 card (e.g., Enzyme Kinetics) in under 2 seconds is likely suffering from "Anki-Brain."

*   **The Evidence:** Bjork's "Fluency Illusion" proves that ease of processing masks weak underlying mental models. Kahneman proves that System 2 (required for MCAT) is slow and effortful.
*   **What would prove me wrong:** If data shows that students who answer Anki cards faster than the "Minimum Reading Time" actually score higher on DOK-3 passage questions than those who take longer to process.

---

## 6. AI Consensus Check

*   **Pass 1 (Cold):** AI initially argued that speed is a sign of "Automaticity" and should be rewarded. It called my POV "counter-intuitive."
*   **Pass 2 (Evidence):** I supplied the Bjork "Desirable Difficulties" and Koriat "Easy come, easy go" citations.
*   **Result:** The AI updated its stance, admitting that **"Latency Volatility"** is a missing dimension in SRS. It named the "Fluency Illusion" as the specific psychological risk that my tool addresses.

---

## 7. Traceability Table

| Spiky POV | What it forces you to build | How you will know if it was wrong |
| :--- | :--- | :--- |
| "Latency Volatility is a signal of Recognition, not Mastery." | A Rust-based **Latency Monitor** that tags reviews as "System 1" (Fast) or "System 2" (Slow). | If students with high "System 1" speed actually perform better on novel DOK-3 questions than "System 2" students. |
| "Readiness must be penalized for 'Spacebar Reflex'." | A **Readiness Model** that applies a 0.5x multiplier to the score of any card answered faster than the "Minimum Reading Time." | If the "Penalized Readiness Score" is less accurate at predicting real exam scores than a raw FSRS score. |
| "AI should be a Proctor, not a Tutor." | An **AI Jitter Engine** that generates novel variations of high-complexity cards to test transfer. | If "Jittered" cards do not show a higher correlation with MCAT passage success than standard cards. |

---

## 8. Success Metrics (Section 9 Preview)

*   **Memory Score:** Raw FSRS Retrievability.
*   **Performance Score:** Accuracy on AI-generated "Jittered" cards.
*   **Readiness Score:** A composite of Memory and Performance, weighted by **Latency Volatility**.
*   **The Give-Up Rule:** No Readiness score will be shown if the student's Latency Volatility is < 0.2 (indicating rote pattern recognition) for more than 40% of the deck.
