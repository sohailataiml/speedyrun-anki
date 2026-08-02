# Speedrun Brainlift v2 — the DOK 4 pivot

**This supersedes v1's primary thesis.** [brainlift-v1.md](brainlift-v1.md) is
preserved in full, not deleted — its POV 1 (topic-interleaved review) was
taken all the way through a real Rust feature and a real three-way
ablation (see [paraphrase-test.md](paraphrase-test.md)), and those results
are still true and still worth having. But the spiky POV driving this
project going forward has changed, to something sharper and more
mechanism-specific. This document explains the new POV, what evidence
backs it, and — stated plainly, per this project's own honesty rule —
**what is and isn't empirically tested yet.** Short version: the new POV
has a concrete design and real literature behind it, but it has not been
run through its own Section 9 ablation the way v1's POV was. That's a
real gap, named here rather than blurred.

**What did not change:** the exam (MCAT), the three-score architecture
(Memory/Performance/Readiness, never blended), the give-up gate, and
everything already shipped and verified (§3-§10 in
[ARCHITECTURE.md](../../ARCHITECTURE.md)). This pivot is about *what the
Performance/Readiness scores should be built to capture next* — it
doesn't undo the engine underneath them.

**A note on where this POV came from, stated honestly:** the DOK-framed
tool analysis and the "Socratic Gatekeeper" mechanism below originated
as a structured reflection I wrote outside this document and brought in
wholesale as the new spiky POV — not something re-derived from scratch
here. The learning-science sourcing, the self-administered consensus
check, and the honest accounting of what remains untested are this
document's own work, done to bring that reflection up to the same
evidentiary bar as v1.

---

## 0. Purpose, and what's out of scope

**Purpose (updated).** Speedrun still gives MCAT students three separate,
honest scores instead of one blended number. What's new: the product's
real point of leverage isn't just *scoring* recall vs. transfer
accurately — it's **protecting the moment where transfer would have been
learned, before the answer gets revealed and that moment is lost.**
Every DOK 1-3 tool in the market (flashcards, visual mnemonics,
practice questions) still ends the same way: you see the back of the
card or the correct answer, and whatever incomplete reasoning you were
mid-way through gets short-circuited. Speedrun's new thesis is that
*when* and *whether* the answer gets revealed — not just what score gets
computed afterward — is itself the highest-leverage design surface.

**Out of scope for v2** (mostly unchanged from v1, see
[brainlift-v1.md §0](brainlift-v1.md) for the full list; deltas noted):
- Same MCAT-only, Android-only, no-new-scheduler-algorithm, no-outcome-validation
  scope as v1.
- **New:** building a general-purpose Socratic dialogue tutor (open-ended
  back-and-forth conversation) is explicitly out of scope for v2 — the
  POV below is a bounded *gate* (show a hint or don't, ask one bridging
  question or don't), not a full tutoring chatbot. Scoping it that way
  keeps it buildable and testable in the time available; a full
  conversational tutor is a different, much bigger project.
- Proving this POV against real student outcomes remains out of scope,
  same reason as v1 (§10 bonus tier, needs longer than a week of real
  usage).

---

## 1. The tool landscape, reframed by Depth of Knowledge

v1's teardown (UWorld, AnKing, Blueprint — see
[brainlift-v1.md §1](brainlift-v1.md)) still holds; this section adds the
frame that motivates the new POV: **which DOK level does each category
of tool operate at, and where does the market have nothing at all?**

| DOK level | Focus | Tool landscape | What actually happens |
|---|---|---|---|
| DOK 1 — Recall & Reproduction | Fact retrieval, definitions | Anki/AnKing, Quizlet | Passive — the "task" is complete the instant the back of the card appears |
| DOK 2 — Skills & Concepts | Comparing, relating, summarizing | Sketchy MCAT, Pixorize | Assisted — the student follows someone else's mental map, not their own |
| DOK 3 — Strategic Thinking | Reasoning from evidence, multi-step | UWorld, AAMC Section Bank | Active — real struggle, but the tool doesn't manage *how* the struggle happens |
| DOK 4 — Extended Thinking | Synthesis, metacognition, generative logic | **None.** | Currently exists only in the discipline of individual students who refuse to flip early |

**The gap this exposes:** DOK 1-3 tools compete on *what* they show you
(better facts, better visuals, better questions). None of them manage
*when* they show it to you, or condition that on how you're actually
performing in the moment. That's the DOK 4 gap, and it's untouched
regardless of how good the DOK 1-3 content gets.

**The specific failure mode this names — "the spacebar reflex":** most
students use Anki at DOK 1 even when the card content is DOK 2/3-worthy.
Front appears, a fuzzy-match feeling fires, spacebar gets hit, back
appears, "yeah I knew that" — and the extended-thinking moment the card
could have prompted was killed before it started. This is a real,
observable behavior pattern (not literature-backed on its own, see
§2's sourcing for what *is* backed), and it's the concrete target the
new POV is designed against.

---

## 2. Learning science backing the new POV

Sources 1-3, 6, and 9 below are carried over from v1 because they remain
directly applicable (spaced repetition's own lineage, desirable
difficulties, transfer taxonomy) — marked **[carried over]**. Sources 4,
5, 7, and 8 are new, chosen specifically to evaluate the Socratic
Gatekeeper mechanism rather than the topic-interleaving one.

### Systems lineage **[carried over from v1, unchanged — see brainlift-v1.md §2 for full entries]**

1. Woźniak / SM-2 — the ancestor of every SRS scheduler, including this one.
2. FSRS / DSR model — Retrievability is still exactly what the Memory
   score should read, regardless of which POV is primary.
3. Anki's own 4-button design — still the right lesson (don't ask for
   more granularity than a student can honestly give), now directly
   relevant to *how* a confidence input gets added without over-asking.

### Learning science for the new POV

**4. Roediger & Karpicke (2006), "The Power of Testing Memory."**
[Full text (PDF)](http://psychnet.wustl.edu/memory/wp-content/uploads/2018/04/Roediger-Karpicke-2006_PPS.pdf)
- *Took:* repeated testing beat repeated rereading on one-week retention,
  61% to 40% — and critically, the effect held *even when the tests were
  given without feedback*. This is the direct evidence that the act of
  retrieving (or attempting to, and failing) is where the learning
  happens, not the moment the correct answer is revealed. It's the
  strongest single justification for "don't flip yet" as a design
  principle rather than just an inconvenience.
- *Rejected:* this literature measures retention of the *tested material
  itself* — it doesn't by itself establish that forcing a longer
  pre-flip reasoning chain (the "reconstruct the countercurrent
  multiplier" step in the new POV's example) produces *better* retention
  than a shorter one. The dosage question — how much forced reasoning is
  optimal before it becomes friction without added benefit — isn't
  answered here and needs the ablation §7 proposes.

**5. Kapur (2016), "Productive Failure, Productive Success, Unproductive
Failure, and Unproductive Success."**
[Full text](https://www.tandfonline.com/doi/full/10.1080/00461520.2016.1155457)
- *Took:* letting students struggle with and fail at a problem *before*
  receiving instruction produces stronger conceptual understanding and
  transfer than instruction-first designs (effect sizes up to d=0.58) —
  directly supports the new POV's core move of withholding the "back of
  the card" until reasoning has been attempted.
- *Rejected — and this is the load-bearing caveat for the whole POV:*
  Kapur's own framework names *boundary conditions* — failure is only
  productive under specific conditions (the right problem difficulty,
  the right scaffolding *afterward*, students with enough prior
  knowledge to generate something). "Unproductive failure" is a named
  failure mode in the same paper. This directly implies the Socratic
  Gatekeeper cannot just withhold answers indiscriminately — it has to
  target the withholding at moments where struggle is likely to be
  productive (this is exactly what the latency/confidence-based
  branching in §4 is trying to operationalize, not just a UX
  nicety).

**6. Bjork & Bjork — desirable difficulties. [carried over from v1 §2]**
Still directly relevant: "feels harder now, helps more later" is the
premise under both the old and new POV. What's new in v2 is a specific
mechanism for *which* difficulties to introduce and when, rather than a
general spacing/retrieval prescription.

**7. VanLehn (2011), "The Relative Effectiveness of Human Tutoring,
Intelligent Tutoring Systems, and Other Tutoring Systems."**
[Overview and effect sizes](https://journals.sagepub.com/doi/10.3102/0034654315581420)
- *Took:* step-based tutoring (hints/feedback delivered at the level of
  a solution step) reached ~0.76 effect size, nearly matching average
  human tutors. This is real evidence that *well-targeted* hint-giving
  works, not just that struggle-then-reveal works in the abstract —
  directly supports building a real Socratic-hint mechanism rather than
  a plain timer-based reveal delay.
- *Rejected — the second load-bearing caveat:* VanLehn found *substep*-level
  tutoring (hints broken down further, more granular hand-holding) was
  meaningfully *less* effective (~0.40) than step-level tutoring. More
  scaffolding is not better scaffolding — over-decomposing the Socratic
  hint (spelling out too much before the student reasons) actively hurts
  the mechanism the POV is trying to protect. This is a concrete design
  constraint on the hint content itself, not just on when to show it.

**8. Metacognitive calibration and confidence — extends v1 source 10.**
[Metacognitive Monitoring: Fixing Learner Overconfidence](https://www.structural-learning.com/post/metacognitive-monitoring-fixing-student)
· [Improving metacognitive accuracy: how failing to retrieve practice
items reduces overconfidence](https://www.sciencedirect.com/science/article/abs/pii/S1053810014001469)
- *Took:* students are systematically miscalibrated (usually
  overconfident), and — the piece that's new here — retrieval *failure*
  specifically is shown to reduce subsequent overconfidence, i.e.
  confronting a wrong-but-confident answer has a real, measurable
  calibration-improving effect. This is the direct evidence base for the
  new POV's highest-priority branch: "High Confidence + Incorrect Answer
  → mandatory intervention," which the design calls a "Dangerous Error."
- *Rejected:* still true as in v1 — this is mostly lab-based, judgment-
  of-learning-rating research, not real-time in-app signal. Confidence
  as a construct has to be operationalized as an actual UI input
  (a tap, not an inference), and that operationalization is untested —
  named directly in §7.

**9. Barnett & Ceci — transfer taxonomy. [carried over from v1 §2]**
Still the right language for the new POV's own worked example ("would
you have known this if the MCAT asked about a desert-dwelling rodent
instead?") — same near/far transfer framing, now applied to *what a
Socratic bridge question should probe* rather than to a paraphrase test.

---

## 3. DOK 3 — the tensions the new POV has to hold at once

- **Productive failure vs. unproductive failure aren't self-selecting.**
  Kapur's own boundary conditions mean the gate has to actually *target*
  interventions, not apply them uniformly — this is why the decision
  table in §4 branches on latency *and* confidence *and* correctness
  together, not on any single signal.
- **More scaffolding isn't more learning.** VanLehn's step vs. substep
  finding is in direct tension with the intuitive design instinct to
  make hints more detailed when a student is struggling more. The
  correct response to "the hint didn't work" is probably a *different*
  hint, not a *more detailed* one — an open design question, not
  resolved by any source here.
- **Confidence is self-reported, same blind spot as v1's original POV 3.**
  Asking "how confident are you?" is still asking the student to
  self-assess, which is exactly the biased signal the metacognitive
  calibration literature warns about. The new POV doesn't escape this —
  it *uses* the known bias (confident-and-wrong is diagnostic) rather
  than pretending confidence reports are unbiased ground truth. That's a
  meaningful difference from treating self-report as truth, but it's a
  reframe, not a fix.
- **Latency is a noisy proxy for "struggling."** A 3-second answer could
  be genuine fast recall or a lucky guess; a 15-second answer could be
  productive reasoning or getting distracted. The decision table treats
  latency as one input among three, not the sole trigger — worth stating
  explicitly since it's the easiest signal to over-trust.

---

## 4. DOK 4 — Spiky POVs

### POV 1 (new primary thesis) — the Socratic Gatekeeper

**Consensus:** the flashcard "flip" is a neutral, binary event — you
either know it or you don't, and revealing the answer is just how you
find out which.

**I think:** the flip is not neutral — it's the single highest-leverage
moment in the whole review loop, because it's the exact instant that
determines whether a struggling or overconfident student gets to fix
their own reasoning or just gets told the answer. Most tools treat every
flip identically; the flip should instead be *gated* on three signals
already available in every review — response latency, a stated
confidence level, and correctness — and only some combinations of those
three should trigger an intervention before the answer is shown.

**The mechanism, concretely (the "Socratic Gatekeeper" decision table):**

| Signal combination | What it means | Response |
|---|---|---|
| Fast + high confidence + correct | Automated mastery | Move on immediately — don't waste stamina on cards that don't need it |
| Fast + high confidence + **incorrect** | **Dangerous error** — a confident misconception | Mandatory Socratic bridge question before revealing the answer, forcing the student to locate where their certainty was wrong |
| Slow (struggling) + any confidence | Productive-failure opportunity | Withhold the back; show a scaffolded hint (not the answer) to nudge reconstruction, per VanLehn's step-level (not substep) granularity |
| Fast + low confidence + correct | Lucky guess | Optional "verify your logic" prompt — cheap to offer, not mandatory |

**Evidence:** Roediger & Karpicke's testing effect (retrieval attempts,
even failed ones, drive retention); Kapur's productive failure (struggle
before instruction beats instruction-first, within named boundary
conditions); VanLehn's tutoring meta-analysis (targeted, step-level
hints work; over-granular ones don't); the metacognitive-calibration
literature's specific finding that confronting confident-wrong answers
measurably improves calibration. Four independent literatures converge
on the same structural claim: *what happens in the seconds before the
answer is revealed matters more than what happens after.*

**What would prove me wrong:** if, in an ablation comparing (a) the
Gatekeeper's conditional intervention, (b) unconditional Socratic
prompts on every card, and (c) plain immediate-flip Anki, condition (a)
shows no advantage over (c) on next-session reworded-question accuracy —
or if it shows no advantage over (b), meaning the *conditioning* logic
itself isn't earning its complexity and a dumber "always ask" policy
would have done just as well.

### POV 2 — decomposed scores **[unchanged from v1, still standing]**

See [brainlift-v1.md](brainlift-v1.md) — a blended number destroys
actionable information; three separate scores let a student act on
*which* of Memory/Performance/Readiness is actually weak. This POV is
orthogonal to the pivot above and doesn't need to change.

### Prior POV 1 (v1's primary thesis) — topic-interleaved review, now a validated secondary finding

v1's original thesis — that isolated card review never trains
discrimination, and topic-interleaved review should close that gap —
**was taken all the way to a real ablation and produced a real,
if narrower-than-hoped, result:** interleaved review beat blocked review
by 16 points at a 10-card study budget, but that gap closed by 20 cards.
Full writeup: [paraphrase-test.md](paraphrase-test.md), summarized in
[brainlift-v1.md §7](brainlift-v1.md). This isn't retracted — it's real,
it's shipped (`speedrunTopicOrder` in `rslib/`), and it remains true. It's
demoted from *primary* thesis because the new POV above is a sharper,
more mechanism-specific claim about *why* isolated review falls short
(it never interrupts the flip, not just that it under-covers topics) —
but the two aren't in conflict, and a future iteration could plausibly
combine them (e.g. the Gatekeeper's hint content could itself draw on
under-covered neighboring topics).

**v1's original POV 3** (self-graded correctness is a biased signal) is
**absorbed into the new POV 1 above**, not carried forward as a separate
POV — the Socratic Gatekeeper *is* a concrete, buildable answer to POV
3's problem (confidence-contingent intervention rather than just latency
flagging), so keeping both as separate open POVs would be double-counting
the same underlying claim.

---

## 5. The AI consensus check

Same caveat as v1: this is a self-administered adversarial pass, not an
independent one, since I'm the same model family drafting this document.
**Before this Brainlift is treated as final, run this cold against an
independently-instantiated model with no prior context.**

### Self-administered adversarial pass on the new POV 1

**Pass 1, POV stated cold, no evidence:**
> "Gating the flashcard flip on latency, stated confidence, and
> correctness — intervening with a Socratic question only on confident-
> wrong answers or genuine struggle — produces better transfer than an
> unconditional flip or an unconditional Socratic prompt."

Objections raised: (1) confidence is an extra tap on every single card,
forever — the friction cost of asking it at scale, across thousands of
reviews, could easily outweigh the benefit on the (likely large) share
of cards where the answer is just "yes, correct, move on"; (2) latency
is confounded by things that have nothing to do with reasoning quality —
phone notifications, re-reading a long front, interruptions — and the
design doesn't yet say how to distinguish "productively struggling" from
"got distracted"; (3) the "Dangerous Error" branch assumes a confident
wrong answer always reflects a genuine, fixable misconception, but it
could just as easily be a careless misread of the question, which a
Socratic bridge question wouldn't meaningfully help with.

**Pass 2, with evidence (Kapur's boundary conditions, VanLehn's
step-vs-substep finding, the retrieval-failure-reduces-overconfidence
result):**
The core mechanism claim (confident-wrong answers are diagnostic and
worth intervening on) held up — it's directly supported by the
calibration literature, not just intuition. The objection that survived:
objection (1), the friction cost, isn't resolved by any source cited
here. Every piece of evidence gathered is about whether the
*intervention itself* works once triggered — none of it measures the
tolerance cost of asking for confidence on every card. That's a real,
unaddressed gap, not a communication problem.

**What moved, what didn't:** the confident-wrong branch is the
load-bearing, best-evidenced part of the POV and survives cleanest. The
"ask confidence on every card" implementation detail does not survive
unscathed — the honest revision is that confidence capture should
probably be sampled or made optional/lightweight rather than mandatory
on every single review, to avoid the friction cost nothing here rules
out. That revision is carried into §7's proposed test design below,
not left as a loose end.

---

## 6. Traceability table

| POV | What it forces us to build | How we'll know if it was wrong |
|---|---|---|
| POV 1 (Socratic Gatekeeper, new primary) | Response-latency capture in the review loop (partially free — Anki's card model already tracks `time_taken()`); a lightweight confidence input at grading time; a decision-table function combining latency/confidence/correctness (natural fit for a Rust RPC, same shape as `give_up_gate`); AI-generated Socratic bridge questions (reuses the existing `ai-cardgen`/Claude API infrastructure, new prompt design) | An ablation (proposed, not run — see §7) shows the conditional Gatekeeper doing no better than unconditional prompting or plain Anki on reworded-question accuracy |
| POV 2 (decomposed scores) | Unchanged — three-score dashboard, per-score give-up rule. Already built. | Unchanged from v1 |
| Prior POV 1 (topic interleaving) | Already built and tested — `speedrunTopicOrder`, the ablation in paraphrase-test.md | Already answered: partial support, front-loaded effect only |

---

## 7. What's actually validated right now, stated plainly

**Empirically tested, real results, nothing invented:** prior POV 1
(topic-interleaved review) — see [paraphrase-test.md](paraphrase-test.md)
and [brainlift-v1.md §7](brainlift-v1.md). That work stands regardless of
this pivot.

**Not yet empirically tested:** the new POV 1 (Socratic Gatekeeper) above.
This document gives it real literature support and a self-administered
adversarial pass, but — unlike prior POV 1 — **no ablation has been run
for it.** Stated directly rather than implied by omission.

**What that ablation would need to look like, if built:** the same
three-arm structure that worked for prior POV 1 — (a) the full Gatekeeper
with conditional intervention, (b) unconditional Socratic prompting on
every card, (c) plain immediate-flip review — run through the same kind
of counterfactual-content, no-study-control-verified measurement
methodology already proven out in `speedrun/tools/paraphrase-test/`
(that pipeline's `run.py`/`report.py` machinery is largely reusable; what's
new is the *stimulus*: cards would need to carry a scaffolded hint field,
and the "student" simulation would need to model a confidence report,
which has no existing analog in the current harness and would need real
design work, not just a parameter change).

**Given the deadline, this ablation was not attempted.** Building it
properly — including resolving objection (2) from §5's consensus check
(distinguishing productive struggle from mere latency) — is real,
unscoped design work, not a quick rerun of the existing pipeline. Listed
in "Open items" below as the top priority for whoever picks this up
next, rather than rushed into an unreliable result under time pressure.

---

## Open items carried into build

- **New, highest priority:** design and run a Section 9-style ablation
  for the new POV 1 (Socratic Gatekeeper), per §7 above. Not started.
- **New:** resolve the friction-cost objection from §5's consensus pass —
  should confidence be asked every card, sampled, or optional? No
  evidence gathered here answers this; needs either new literature or a
  pilot.
- Re-run §5's AI consensus check independently (both the original v1 pass
  and this document's new pass) — carried over from v1, still not done.
- POV 2 remains untested (unchanged from v1).
- Desk-research limitation in §1 (competitor teardown, hands-on use)
  remains unaddressed — carried over from v1.
- **Not a gap, but worth flagging:** many other docs in this repo
  (ARCHITECTURE.md, demo.md, demo-script.md, rust-change-note.md) still
  describe prior POV 1 (topic interleaving) as "the thesis" without
  reference to this pivot. They weren't rewritten as part of producing
  this document — that's a real, separate follow-up if this new POV is
  adopted going forward, not done here.
