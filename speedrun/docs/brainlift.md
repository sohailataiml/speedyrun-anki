# Speedrun Brainlift v1

Exam: **MCAT** (472–528 scale, four sections of 118–132, ±2-point total confidence band per AAMC). Chosen because it's the one exam on the PRD's list where both halves of the mission are simultaneously hard — a huge fact base (coverage is genuinely difficult) *and* passage-based transfer (DOK 3 reasoning is genuinely difficult) — so a tool that only measures recall has the most room to be quietly wrong.

Caveat on method, stated up front: the competitor teardown below is **desk research** — public docs, marketing pages, and reviews — not hands-on paid use. That's a real limitation (see §0), not something to paper over.

---

## 0. Purpose, and what's out of scope

**Purpose.** Speedrun gives MCAT students three separate, honest scores — Memory, Performance, Readiness — instead of the one blended confidence number every competitor sells. It measures the bridge from "I can recall this fact" to "I can answer a novel passage question" to "I would score X today," and it says so when it doesn't have enough data to claim any of the three.

**Out of scope for v1:**
- Teaching new content or curriculum design (Speedrun scores and schedules study; it doesn't replace a content course).
- Non-cognitive admissions coaching (personal statements, interviews, school selection).
- Any exam other than MCAT — the architecture is exam-agnostic where possible, but the Readiness scale, give-up thresholds, and coverage map are MCAT-specific for v1.
- Gamification/social features on the phone client — the phone is a companion for running real sessions and seeing the same three scores, not a separate product surface.
- A new spaced-repetition scheduling algorithm. FSRS stays FSRS; Speedrun's original work is the two bridges above it, not memory scheduling itself.
- Proving the Readiness number against real student outcomes (Section 10's bonus tier) — a week isn't enough to gather that honestly; this Brainlift is scoped to what's gradeable now.
- **iOS.** No Mac or cloud Mac CI is available for this project, and there is no supported way to build, sign, or run an iOS app on Windows. The phone companion ships as Android only (fork of AnkiDroid, which already embeds Anki's Rust backend). The PRD's phone-companion requirement and its grading hard limit are both phrased around having *a* working phone client sharing the engine and syncing, not specifically both platforms, so Android alone is the honest, achievable target — stated here rather than discovered as a gap on submission day.

**Desk-research limitation, named honestly.** The PRD asks for hands-on use of 3 competitor tools to log where they break. I did not create paid accounts or run study sessions inside UWorld, Blueprint, or the AnKing deck. What follows is built from their own documentation, marketing copy, and independent reviews — good enough to establish *what each tool claims to measure and what it visibly doesn't*, weaker than firsthand use for catching in-product failure modes (e.g., exactly how UWorld's UI behaves when a student is clearly guessing). Flagged wherever the evidence is inferred from marketing language rather than observed behavior.

---

## 1. Research part one — tearing down three real MCAT tools

Lead question for each: **what DOK level does this tool actually measure, and what level does it imply it measured?**

### UWorld MCAT QBank

- **What it measures:** Item-level accuracy on UWorld's own question bank (DOK 2/3 — these are novel, exam-style items, not the source flashcards).
- **What it implies:** A **scaled score, 472–528** — directly on the real exam's scale — derived from QBank performance. That is a DOK 4 claim (a projected real-world score) built on DOK 2/3 data.
- **The tell:** UWorld's own materials caution that "UWorld performance alone should not be treated as a reliable score predictor because UWorld questions are intentionally slightly harder than the real MCAT." That's UWorld admitting, in a footnote, exactly the failure mode the PRD calls an automatic fail: presenting a number on the real scale without the honesty layer (evidence, range, coverage, confidence) attached to it in the product itself. The caveat lives in support articles, not on the score screen.
- **Does it ever say "I don't know"?** Not in the product surface, per the docs found — the disclaimer is out-of-band.
- **Does it reword questions to test transfer vs. recall?** No paraphrase/rewording mechanic found — UWorld's own explanations are rich, but nothing separates "you got this exact item right" from "you'd get a reworded version right."
- **Content-as-progress?** Detailed performance reports break down by subject/topic, which is a real step toward decomposed feedback — better than a single number, but still folds straight back into the same 472–528 scaled score at the top.

### AnKing MCAT Deck (Anki / AnkiHub)

- **What it measures:** DOK 1 only — card-level recall, scheduled by SM-2/FSRS. ~6,200 cards merged from several community decks, tagged by subject/system/source, plus UWorld-question-ID cross-reference tags.
- **What it implies:** Nothing on the real exam scale — no score, no readiness claim. This is the most *honest* of the three by omission: it doesn't claim a DOK level it doesn't measure.
- **The tell:** the dishonesty isn't in the tool, it's in how students use it — "content volume sold as progress" shows up as the card count itself (6,200 cards, continuously updated) functioning as the de facto progress metric in the community, even though card-review completion says nothing about passage-level transfer. The tool is honest; the surrounding culture treats DOK 1 completion as a proxy for DOK 4 readiness anyway.
- **Timing:** no per-card timing signal surfaced to the student at all.

### Blueprint MCAT

- **What it measures:** Full-length practice exams (closest of the three to real DOK 4 conditions — same length, same timing, adaptive-feeling analytics) plus a large QBank, analyzed by "AAMC reasoning skill" via an AI tutor ("Blue").
- **What it implies:** Directional score improvement, explicitly *not* claimed as precise. Blueprint's own review copy: practice-test scores are "directionally accurate... but not precise enough for fine-grained predictions," positioned as "a directional baseline, not a final predictor."
- **The tell, and the most interesting finding of the teardown:** Blueprint is the one competitor whose public language already gestures at the honesty rule (calibration, don't over-claim precision) — but it still leads its marketing with a single predicted-score number and an analytics stack that decomposes by skill *without* ever showing a range or a give-up threshold. It has the right instinct and doesn't build the product around it.

### What the teardown actually exposes (cross-tool pattern)

| Question | UWorld | AnKing | Blueprint |
|---|---|---|---|
| DOK level measured | 2/3 | 1 | ~2/3 + simulated 4 |
| DOK level implied | 4 (scaled score) | none | 4 (directional) |
| Says "I don't know" in-product | No (caveat is out-of-band) | N/A (no score) | Partially (marketing hedge, not in-app) |
| Reword/paraphrase check | Not found | Not found | Not found |
| Volume sold as progress | Topic-count breakdowns | Card count (6,200) | Question count (5,000+) |
| Timing signal to student | Full-length only | None | Full-length only |
| Shows a range instead of one number | No | N/A | No |

Every tool examined either doesn't try to bridge DOK 1 → DOK 4 (AnKing) or bridges it with a single number and a footnote instead of a range (UWorld, Blueprint). None of the three appear to test whether a student's card-level recall predicts their performance on a *reworded* version of the same idea — which is exactly the DOK 1 vs. DOK 2 gap the PRD's paraphrase test is designed to catch. That gap is the opportunity.

---

## 2. Research part two — the learning science (DOK 1 and 2)

Ten primary sources: three establish the systems lineage (SuperMemo → FSRS → Anki), seven establish the learning-science claims the product design leans on.

### Systems lineage

**1. Piotr Woźniak, "Optimization of Learning" (1990 master's thesis; SM-2 published in *Computers & Education*).**
[SuperMemo: the true history of spaced repetition](https://www.supermemo.com/en/blog/the-true-history-of-spaced-repetition) · [Piotr Woźniak (researcher) — background](https://en.wikipedia.org/wiki/Piotr_Wo%C5%BAniak_(researcher))
- *Took:* SM-2's core insight — schedule review just before predicted forgetting, using an easiness factor updated from grading history — is the ancestor of every scheduler in this space, including Anki's. Empirically grounded in years of the author's own self-study data, not a lab experiment.
- *Rejected:* SM-2's fixed easiness-factor update rule is a hand-tuned heuristic, not a fitted probabilistic model of memory. It doesn't generalize well across card types or students, which is precisely why FSRS superseded it.

**2. FSRS / DSR model (Jarrett Ye and the open-spaced-repetition community).**
[The fundamental of FSRS](https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-fundamental-of-FSRS) · [ABC of FSRS](https://github.com/open-spaced-repetition/fsrs4anki/wiki/abc-of-fsrs)
- *Took:* the Difficulty/Stability/Retrievability decomposition is the right abstraction for Memory — Retrievability is exactly "chance of recalling this fact right now," which is the PRD's own definition of the Memory score. Speedrun's Memory score should be read directly off retrievability, not reinvented.
- *Rejected:* FSRS optimizes scheduling *efficiency* (minimize reviews for a target retention). That objective says nothing about whether the material being scheduled efficiently is the material that predicts exam performance — efficiency and transfer are orthogonal, which is exactly the gap Speedrun's Performance score has to cover that FSRS was never designed to.

**3. Anki's own scheduler design decisions.**
[What spaced repetition algorithm does Anki use? — Anki FAQs](https://faqs.ankiweb.net/what-spaced-repetition-algorithm.html) · [How to plug a scheduling algorithm into Anki](https://www.milchior.fr/blog_en/index.php/post/2020/02/22/How-to-plug-a-scheduling-algorithm-into-Anki)
- *Took:* Anki deliberately simplified SuperMemo's 6-point grading to 4 buttons (Again/Hard/Good/Easy) and made interval growth configurable — a product decision that trades some scheduling precision for usability. That's the right lesson for Speedrun's own UI: don't ask the student for more granularity than they can honestly give.
- *Rejected:* the 4-button grade is still a **self-reported** correctness signal, unverified by the system. Section 10's stress test — "a student tapping Good without reading" — exists precisely because Anki's own design never tried to detect this; it's an open problem Speedrun inherits, not one Anki solved.

### Learning science

**4. Bjork & Bjork — desirable difficulties.**
[Introducing Desirable Difficulties Into Practice and Instruction (UNH)](https://www.unh.edu/teaching-learning-resource-hub/sites/default/files/media/2023-06/itow-introducing-desirable-difficulties-into-practice-and-instruction-bjork-and-bjork.pdf)
- *Took:* conditions that feel harder *during* study (spacing, retrieval practice, interleaving) produce more durable learning than conditions that feel easy. Meta-analytic support: retrieval + spacing effect size g = 0.74 across 29 studies. This underwrites the whole premise that "feels harder" (a reworded question) is a legitimate, not unfair, test of learning.
- *Rejected:* Bjork's frame is about *durability* of memory, not about *transfer* to novel problems. It's necessary background for why spacing works at all, but it doesn't by itself justify a claim about passage-level performance — that's a different literature (interleaving, transfer), not an extension of this one.

**5. Rohrer & Taylor (2010), "The Effects of Interleaved Practice."**
[Taylor & Rohrer 2010 (full text PDF)](http://uweb.cas.usf.edu/~drohrer/pdfs/Taylor&Rohrer2010ACP.pdf)
- *Took:* interleaving (not just spacing) doubled next-day test scores over blocked practice, and error analysis showed the mechanism is discrimination — interleaved practice teaches you to *tell problem types apart and pick the right procedure*, which blocked/isolated practice never trains. This is the single strongest piece of evidence for Speedrun's core thesis: isolated flashcard review can raise recall without ever training the "which concept applies here" skill an MCAT passage demands.
- *Rejected:* the original study is math procedure learning (children, arithmetic problem types) — a substantial generalization gap to MCAT science passages and CARS reasoning. Treat the mechanism (discrimination training) as the transferable claim, not the effect size.

**6. Sweller — cognitive load theory.**
[Cognitive Load Theory, Learning Difficulty, and Instructional Design (1994)](https://pressbooks.pub/learningenvironmentsdesign/chapter/sweller-cognitive-load-theory-learning-difficulty-and-instructional-design/)
- *Took:* the intrinsic/extraneous/germane load distinction explains why "more cards reviewed" isn't the same as "more schema built" — germane load (effort spent building usable structure) is what predicts transfer, and it's not the same quantity as review count or even accuracy.
- *Rejected:* cognitive load is notoriously hard to measure directly (it's usually inferred from performance, not measured independently) — Speedrun should not pretend to measure "load" as a first-class number; use it as a design principle (don't let volume stand in for structure), not a metric to report to the student.

**7. Ericsson, Krampe & Tesch-Römer (1993) — deliberate practice — and its 2019 revisit.**
[The role of deliberate practice in expert performance (original)](https://eric.ed.gov/?id=EJ471947) · [Revisiting Ericsson, Krampe & Tesch-Römer (1993), Royal Society Open Science, 2019](https://royalsocietypublishing.org/rsos/article/6/8/190327/68523/The-role-of-deliberate-practice-in-expert)
- *Took:* deliberate practice requires a task just beyond current ability, with immediate, specific feedback, repeated with intent to improve — not just repetition. This is the standard against which "review a flashcard" should be judged: right/wrong is feedback, but it isn't *specific* feedback about why a passage-level answer was wrong.
- *Rejected — and this is a real DOK 3 disagreement, not a footnote:* the 2019 replication/re-analysis found deliberate practice explains a much smaller share of performance variance than the original claimed, and the field has since pushed back hard on "10,000 hours"-style overclaiming. Speedrun should use the deliberate-practice *design principles* (specific feedback, targeted difficulty) without importing the original's overstated causal claim about practice alone producing expertise.

**8. Dunlosky, Rawson, Marsh, Nathan & Willingham (2013) — effective learning techniques meta-analysis.**
[Improving Students' Learning With Effective Learning Techniques](https://journals.sagepub.com/doi/abs/10.1177/1529100612453266)
- *Took:* of ten common study techniques ranked by evidence quality, distributed practice and practice testing rank highest utility; rereading and highlighting rank lowest. This is the field's authoritative validation that spacing + testing (what SRS tools already do) is the right foundation — Speedrun isn't fighting the consensus on Memory, it's building past it.
- *Rejected:* in the 2013 paper, interleaving was rated "moderate" utility partly because it had *less* evidence behind it at the time, not because it was weaker — a caveat, not a demotion. (A larger follow-up meta-analysis in 2021, 242 studies, mean effect size 0.56, gives interleaving considerably stronger footing — noted here as "what changed" between sources, which is exactly the kind of update the honesty rule asks for.)

**9. Barnett & Ceci (2002) — taxonomy for far transfer.**
[When and Where Do We Apply What We Learn? (full text)](https://rapunselshair.pbworks.com/f/barnett_2002.pdf)
- *Took:* "near vs. far transfer" isn't one dial, it's nine dimensions (knowledge domain, physical/temporal/functional/social context, modality, and more). This gives Speedrun precise language for exactly what a rewritten exam question is testing: same knowledge domain, same temporal context, but a different surface/modality — a *specific*, nameable transfer distance, not just "harder."
- *Rejected:* the taxonomy is descriptive, not predictive — it doesn't tell you how much a given transfer distance will reduce accuracy. Speedrun's paraphrase test has to measure that gap empirically per-topic; the taxonomy only tells you what you're measuring.

**10. Metacognitive calibration / judgment-of-learning research.**
[Metacognitive Monitoring: Fixing Learner Overconfidence](https://www.structural-learning.com/post/metacognitive-monitoring-fixing-student) · [Calibration of metacognitive judgments: the underconfidence-with-practice effect](https://www.sciencedirect.com/science/article/abs/pii/S0749596X13000454)
- *Took:* students are systematically miscalibrated (usually overconfident), the miscalibration itself predicts *worse* study decisions (skipping unmastered material), and — critically — the direction and size of the bias *changes with practice* (the underconfidence-with-practice effect: calibration isn't a fixed offset you can just correct for). This is the direct evidence base for the PRD's honesty rule and for the give-up rule specifically: a system that trusts self-report without checking calibration will inherit the same overconfidence its users have.
- *Rejected:* most of this literature measures calibration via post-hoc judgment-of-learning ratings in lab settings, not via real-time signals like response latency in a live app — Speedrun will need its own instrumentation (see POV 3) to bring this into a shipping product; the lab findings establish *that* the problem is real, not exactly *how* to detect it in the wild.

---

## 3. DOK 3 — what the sources disagree on, what the field assumes, what the teardown exposed

- **Assumption nobody checks:** that a scheduler tuned for efficient recall (FSRS) is also, by implication, a reasonable proxy for exam readiness. It isn't — FSRS's objective function has nothing to do with transfer, and no competitor examined treats this as a distinct thing to measure.
- **Where sources disagree:** Ericsson's original deliberate-practice claim vs. its own field's 2019 replication — how much of performance practice actually explains is contested, not settled. Speedrun should build on the *design principles* (specific feedback, calibrated difficulty) without repeating the overclaim.
- **Where the field's evidence got stronger over time:** Dunlosky et al. (2013) hedged on interleaving; the 2021 meta-analysis (242 studies) gives it much firmer footing. Worth stating explicitly because it's an example of the honesty rule applied to the literature itself, not just to Speedrun's own numbers.
- **What the teardown exposed that the science predicts:** every competitor's headline number is near-transfer at best (UWorld/Blueprint QBank items resemble their own training questions) dressed as far-transfer prediction (a real exam score). Barnett & Ceci's taxonomy names exactly why that's a problem: transfer distance isn't binary, and none of these tools report where on that distance their evidence actually sits.
- **The metacognition problem the teardown didn't even get to test:** self-graded recall (Anki's 4-button grade) is a judgment-of-learning report, and the calibration literature says those reports are systematically biased. Every SRS-based tool, including AnKing, inherits this blind spot silently.

---

## 4. DOK 4 — Spiky POVs

Each shaped as: consensus says X, I think Y, evidence, what would prove me wrong.

### POV 1 — the thesis candidate for Section 9

**Consensus:** more spaced-repetition review predicts higher exam readiness (implicit in every competitor's progress bar and card count, and in AnKing's culture of tracking cards-reviewed as the proxy for "done").

**I think:** past a moderate threshold of card-level retention (roughly 80–90%), further gains in exam-style item accuracy come from transfer training, not more card repetitions — because SRS drills isolated recall of a single fact, while exam items require discriminating which of several similar-looking facts/procedures applies, which is a different skill Rohrer & Taylor showed blocked/isolated practice never builds.

**Evidence:** Rohrer & Taylor (2010) — interleaved practice doubled next-day scores over blocked practice via better discrimination, not better recall; the teardown found zero competitors testing paraphrase/rewording against card-level recall; MCAT-prep community sources describe plateaus explicitly caused by "familiarity" (recall/recognition) substituting for the actual tested skills.

**What would prove me wrong:** if, in the paraphrase test (30 cards, 2 reworded exam-style questions each), reworded-question accuracy tracks card-recall accuracy closely (say within ~5 points) across a range of topic-coverage levels, then recall and transfer aren't actually diverging in this population and the thesis fails. This is the feature Section 9's ablation should test: a topic-interleaved review mode, on vs. off vs. plain Anki.

### POV 2

**Consensus:** a single predicted score is the right product to ship — every competitor examined leads with one number (UWorld's scaled score, Blueprint's practice-test score).

**I think:** a blended number destroys the information a student needs to act, because a low score caused by low coverage, low transfer accuracy, and slow timing each demand a completely different next study session — and collapsing them into one number means the app can never tell the student which one it was.

**Evidence:** even Blueprint's own analytics decompose by section and "AAMC reasoning skill" internally, then re-blend it into one headline score for marketing — implicitly conceding decomposition is more useful while still shipping the blend. Deliberate-practice literature is unambiguous that feedback has to be specific to be actionable.

**What would prove me wrong:** if, in an ablation, students shown one blended number allocate their next study session to their actual weakest area about as often as students shown three separated scores, decomposition isn't earning its complexity and this POV fails.

### POV 3

**Consensus:** a student's self-graded recall (Again/Hard/Good/Easy) is a good enough signal to both schedule reviews and estimate knowledge state — every SRS tool, Anki included, treats it as ground truth.

**I think:** self-graded correctness is a metacognitively biased signal, not ground truth, and a nontrivial share of "Good" grades are the PRD's own named failure mode — a student tapping Good without reading — contaminating both the scheduler's inputs and any Performance model trained on top of it.

**Evidence:** the calibration literature's finding that judgment-of-learning accuracy is systematically biased and that the bias itself shifts with practice (not a fixed, correctable offset); the PRD independently names this exact failure mode as something the system will be tested against.

**What would prove me wrong:** if response-latency-flagged "suspiciously fast" grades show no detectable difference in downstream item accuracy from normal-latency grades of the same nominal rating, the contamination isn't real (or isn't detectable this way) and building latency-based flagging isn't worth it.

---

## 5. The AI consensus check

**Caveat, stated honestly:** a genuine consensus check means putting the POV to an independently-instantiated frontier model with no visibility into this document. I'm the same model family drafting this Brainlift, so I cannot be that independent check on myself — folding my own critique in here would be grading my own homework. What follows is a best-effort adversarial pass I ran against POV 1 in this session, clearly labeled as self-administered, not independent. **Before this Brainlift is treated as final, re-run POV 1 (and ideally 2 and 3) cold against a model in a fresh session with no prior context, and log that transcript here in its place.**

### Self-administered adversarial pass (not independent — see caveat)

**Pass 1, POV 1 stated cold, no evidence:**
> "Past a threshold of card-level retention, further review gains stop predicting exam-item accuracy — the skill that predicts scores past that point is transfer/discrimination training, which spaced-repetition review doesn't provide."

Objections raised: (1) this assumes a clean threshold exists, when in practice the retention-to-performance relationship is probably continuous and topic-dependent, not a step function; (2) MCAT science content still has a large enough raw fact base that for many students, coverage/recall gaps — not transfer — are still the binding constraint even late in prep, so the claim may only hold for students who've already covered most content; (3) "discrimination training" and "spaced repetition" aren't necessarily separable in practice — interleaved SRS decks already mix topics within a session, which muddies the clean distinction the POV draws.

**Pass 2, with evidence (Rohrer & Taylor's discrimination mechanism, the teardown's finding that no competitor tests paraphrase vs. recall, MCAT community plateau reports):**
The retention-vs-performance evidence (Rohrer & Taylor) was accepted as directly on point for the *mechanism* claim (discrimination is a trainable, distinct skill from recall). The objection that held up: the "threshold" language is still doing more work than the evidence supports — Rohrer & Taylor didn't establish a retention percentage at which transfer becomes the binding constraint, that number is this project's own hypothesis, not a cited finding. That's a real gap, not a communication problem — it means the paraphrase test needs to measure the *shape* of the recall-vs-transfer-accuracy relationship across a range of coverage levels, not assume a single cutoff going in.

**What moved, what didn't:** the discrimination mechanism (interleaving builds transfer, isolated review doesn't) held up under pressure and is the load-bearing part of POV 1. The specific "80–90% retention threshold" framing did not survive — it's restated above as "a range of coverage levels" rather than a fixed cutoff, which is the honest version of the claim going into Section 9.

---

## 6. Traceability table

| POV | What it forces us to build | How we'll know if it was wrong |
|---|---|---|
| POV 1 (thesis) | Performance model kept architecturally separate from the Memory (FSRS) score; paraphrase-test harness (30 cards × 2 rewordings); Section 9 ablation of a topic-interleaved review mode (on / off / plain Anki) | Reworded-question accuracy tracks card-recall accuracy closely across coverage levels — no meaningful recall/transfer gap to build a Performance model around |
| POV 2 (decomposed scores) | Three-score dashboard that never blends into one number; per-score give-up rule instead of one global threshold | Students shown one blended number allocate next-session study time to their true weak area about as accurately as students shown three separated scores |
| POV 3 (grade contamination) | Response-latency capture in the review loop; a confidence/flag signal feeding the mastery query so suspiciously-fast grades can be down-weighted | Latency-flagged "Good" grades show no detectable accuracy difference from normal-latency ones |

Every row points at a real component (performance model, dashboard, latency capture) and a real test that could fail. No row is decorative.

---

## 7. By Sunday — what changed

Placeholder for the final submission: after the ablation and calibration numbers come in, this section reports which POV survived contact with real held-back data and which didn't, with the evidence either way. Per the honesty rule, "POV 1 held on the mechanism but the specific threshold was wrong, here's the corrected shape" scores better than declaring victory.

---

## Open items carried into build

- Rust feature choice (mastery query vs. topic-aware scheduling vs. points-at-stake queue) — [ARCHITECTURE.md §3](../../ARCHITECTURE.md) recommends the mastery query by default; POV 1 being the thesis strengthens that pick, since the ablation needs per-topic mastery/coverage regardless of which scheduling approach ships.
- Re-run §5's AI consensus check independently before calling this Brainlift final.
- If time allows before Friday, replace desk research in §1 with real hands-on notes from at least one of the three tools (per the "you do the hands-on part" option, if that gets picked up later).
