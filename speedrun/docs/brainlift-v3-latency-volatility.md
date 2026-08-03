# Speedrun Brainlift: The Latency-Volatility Pivot

**Exam:** MCAT (Medical College Admission Test)  
**Target Scale:** 472–528  
**Spiky POV:** Retention is a vanity metric. **Latency Volatility** does not measure mastery — it measures whether a retention number can be trusted at all, and the app refuses to score when it can't.

---

## 1. Purpose and Scope

**Purpose:** To build a study engine that distinguishes between "Anki-Brain" (rote recognition) and actual MCAT readiness. The app predicts exam scores by auditing the *quality* of the student's retrieval (System 2 thinking) rather than just the *fact* of recall (System 1 recognition).

**Out of Scope:** 
- General-purpose Socratic tutoring (avoiding "hint dependency").
- Support for multiple exams (focusing exclusively on the MCAT DOK hierarchy).
- Replacing the FSRS scheduler (we extend the Rust core to include latency-based readiness logic).

---

## 2. DOK 1: The Systems Lineage (Sources)

1.  **SM-2 / SM-18 (SuperMemo):** [History of Spaced Repetition](https://supermemo.guru/wiki/History_of_spaced_repetition). Established the core mathematical modeling of memory stability ($S$).
2.  **FSRS (Free Spaced Repetition Scheduler):** [GitHub Repo](https://github.com/open-spaced-repetition/fsrs-rs). The modern standard for Anki. It models Retrievability ($R$) but ignores the *time* taken to retrieve (Latency).
3.  **Encoding Specificity Principle:** [Tulving & Thomson (1973)](https://www.sciencedirect.com/science/article/abs/pii/001002857390040X). Proves that memory is context-dependent. If the context is "an Anki card," the memory may not transfer to "an MCAT passage."
4.  **Fluency Illusions:** [Bjork & Bjork (2011)](https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/04/EBjork_RBjork_2011.pdf). Research into "Desirable Difficulties." Argues that ease of recall is a poor predictor of long-term learning.
5.  **System 1 vs. System 2:** [Kahneman (2011)](https://www.penguinrandomhouse.com/books/206969/thinking-fast-and-slow-by-daniel-kahneman/). Differentiates between fast, automatic recognition (System 1) and slow, analytical reasoning (System 2).

---

## 3. DOK 2: Summaries and Rejections

*   **FSRS (Accepted):** We use FSRS to handle the base "Memory" score. It is the gold standard for "Can you recall this?"
*   **FSRS (Rejected):** We reject the idea that FSRS alone equates to "Readiness." FSRS treats a 1.0s response and a 6.0s response as identical "Good" grades. For DOK-3 concepts, this is a fatal flaw.
*   **Anki 4-Button System (Rejected):** We reject the user's self-assessment ("Hard/Good/Easy") as the primary data point. Users are miscalibrated. We prioritize **Latency** (objective) over **Ease** (subjective).
*   **Desirable Difficulties (Accepted):** We accept that higher latency on complex cards is often a sign of "Productive Struggle" (DOK 3).

---

## 4. DOK 3: The Gap Analysis (Teardown)

Current MCAT tools (AnKing, UWorld, Blueprint) suffer from **The Readiness Illusion**:
- **Anki/AnKing:** Measures "Retention." If you hit 95% retention, the app implies "Mastery." **Gap:** Students hit 95% retention but plateau at 505 on the MCAT because they have mastered the *cards*, not the *science*.
- **UWorld:** Measures "Accuracy." **Gap:** It doesn't track decay over time or how much "Productive Failure" was required to reach that accuracy.
- **The "Spacebar Reflex":** None of these tools detect when a student is flipping cards so fast (System 1) that they aren't even reading the prompt. This is a "DOK 1 behavior" applied to "DOK 3 material."

---

## 5. DOK 4: The Spiky POVs

**POV 1: The Latency-Volatility Thesis**
- **Consensus:** Fast recall is a sign of mastery and should be rewarded.
- **I think:** Fast recall on DOK 3/4 concepts is a signal of **Recognition (System 1)**, not **Mastery (System 2)**. 
- **Evidence:** Bjork’s "Fluency Illusion" proves that ease of processing masks weak underlying mental models.
- **Falsification:** I am wrong if students with low latency/low volatility on complex cards perform *better* on unseen DOK-3 passages than those with high volatility.

**POV 2: The Honest "Give-Up" Rule**
- **Consensus:** A study app should always provide a progress percentage to keep the student motivated.
- **I think:** A score based on "Spacebar Reflex" is a lie. The app must **refuse to score** (Abstain) if behavioral data suggests the student is rote-memorizing card patterns.
- **Evidence:** Kapur’s "Productive Failure"—if there is no struggle, there is no conceptual transfer.
- **Falsification:** I am wrong if a "Penalized/Hidden" Readiness score is less accurate at predicting exam outcomes than a raw FSRS completion percentage.

**POV 3: The AI "Proctor" vs. "Tutor"**
- **Consensus:** AI should provide Socratic hints to help students when they are stuck.
- **I think:** AI hints create a "Dependency Loop." AI should only be used to **Jitter (Re-contextualize)** the card to prove the logic holds in a new scenario.
- **Evidence:** Tulving’s "Encoding Specificity"—memory tied to one specific card format fails in the "Far Transfer" of an exam.
- **Falsification:** I am wrong if "Jittered" performance shows no higher correlation with exam passage success than standard card retention.

---

## 6. AI Consensus Check

- **Pass 1 (Cold):** AI initially argued that speed is a sign of "Automaticity" and should be rewarded. It called the POV "counter-intuitive" and potentially frustrating for users.
- **Pass 2 (Evidence):** I supplied the Bjork "Desirable Difficulties" and Koriat "Easy come, easy go" citations.
- **Result:** The AI updated its stance, admitting that **"Latency Volatility"** is a missing dimension in SRS. It named the "Fluency Illusion" as the specific psychological risk that this tool addresses.

---

## 7. Traceability Table

| Spiky POV | What it forces you to build | How you will know if it was wrong |
| :--- | :--- | :--- |
| **1. Latency Volatility** | A **Rust-based Latency Monitor** and a SQL schema that stores `response_time` and `dok_level` per review. | If "System 1" (fast) reviewers outperform "System 2" (slow) reviewers on DOK-3 novel items. |
| **2. Honest Give-Up** | A **Readiness Logic Gate** that displays "Insufficient Data: Rote Pattern Detected" if latency SD is < 0.2. | If the "Abstention" rule triggers for students who go on to score 515+ on real practice exams. |
| **3. AI Proctoring** | An **AI Jitter Pipeline** that generates a "Context-Shifted" version of a card (e.g., changing the clinical patient) for every 3rd review. | If student performance on "Jittered" cards is identical to their performance on "Static" cards. |

---

## 8. Success Metrics

- **Memory Score:** Raw FSRS Retrievability.
- **Performance Score:** Accuracy on AI-generated "Jittered" cards.
- **Readiness Score:** A composite of Memory and Performance, weighted by **Latency Volatility**.
- **The Give-Up Rule:** Readiness score remains hidden until the student demonstrates a minimum Latency Variance on DOK-3 tagged topics.
