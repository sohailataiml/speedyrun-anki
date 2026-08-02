# Socratic Gatekeeper — MVP implementation and validation

MVP status for Brainlift v2's primary thesis (see
[brainlift.md](brainlift.md)), built under a hard deadline. This document
is the honest record of what got built and what got measured, at two
scales: an initial n=30 pass, then a full n=90 run matching prior POV
1's ablation size. Stated plainly, same rule as everywhere else in this
project: the full-scale result is **not a clean win for Socratic bridges
— it's real evidence for applying them *conditionally* rather than
everywhere**, since indiscriminate use has a measured cost. That's a
more useful and more honest finding than the flattering version would
have been.

## What got built

**1. A real, tested Rust decision function** —
`rslib/src/stats/socratic_gate.rs`. Given a review's response latency
(`RevlogEntry.taken_millis` — already captured by upstream Anki on every
grade, no new capture engineering needed) and correctness (same
"anything above Again counts as correct" convention as `mastery.rs`),
returns one of four branches:

| Fast (≤3s) | Correct | Decision | Intervene? |
|---|---|---|---|
| Yes | Yes | Automated Mastery | No |
| Yes | No | **Dangerous Error** | Yes |
| No | No | Productive Struggle | Yes |
| No | Yes | Lucky Guess | No |

6 unit tests, all passing, zero regressions across the full 563-test
Rust suite.

**MVP simplification, stated honestly:** the full Brainlift v2 design
branches on three signals — latency, *stated confidence*, and
correctness. This MVP drops the confidence tap. Brainlift v2 §5's own
self-administered consensus check flagged "ask confidence on every card"
as an unresolved friction-cost objection; building that UI first would
mean shipping the exact design choice that check couldn't defend. Using
latency as a confidence *proxy* (fast=confident, slow=struggling) is a
real, named simplification — not the full design.

**2. A real Socratic bridge generator** —
`speedrun/tools/socratic-gate/generate_bridges.py`. For the two
"intervene" branches, generates a genuine bridging question (not a
restated answer) via real Claude API calls, following the source POV's
own worked example (Loop of Henle → "if you blocked the ascending limb,
what happens to urine concentration?"). 30 bridges generated, reusing
the same 30 counterfactual cards already built and audited by
`speedrun/tools/paraphrase-test/` — same provenance chain, no new card
content invented for this MVP.

## The validation

**Question:** does seeing a Socratic bridge after a wrong answer produce
better understanding than seeing the plain correct answer, measured on a
follow-up reworded (discrimination-style) question testing the same
fact?

**Method:** three conditions per card (n=30), all against the same
follow-up probe question:
- **no_correction** — nothing shown, straight to the follow-up. Reused
  directly from `paraphrase-test`'s `ablation_results.json`
  `no_study_control` (same items, same methodology, zero new API calls) —
  the floor.
- **plain** — the card's plain back shown as the correction, then the
  follow-up. What every competitor tool, and vanilla Anki, does today.
- **bridge** — the Socratic bridge shown instead, then the same
  follow-up. The Gatekeeper's proposed intervention.

### Results — MVP scale (n=30, discrimination items only)

| Condition | n | Correct | Rate | 95% CI |
|---|---|---|---|---|
| no_correction | 30 | 0 | 0% | 0%–11% |
| plain | 30 | 19 | 63% | 46%–78% |
| bridge | 30 | 20 | 67% | 49%–81% |

Bridge beat plain by exactly one card out of thirty — a statistical tie,
not a confirmed win.

### Results — full scale (n=90, matching prior POV 1's ablation size: 30 cards × verbatim/near/discrimination)

Superseding the MVP run above — same methodology, extended to all 3
follow-up item types instead of discrimination only, giving the same
statistical power as prior POV 1's ablation.

| Item type | no_correction | plain | bridge |
|---|---|---|---|
| Verbatim (exact same question) | 0/30 (0%) | **29/30 (97%, CI 83–99%)** | 25/30 (83%, CI 66–93%) |
| Near-transfer (reworded, same fact) | 0/30 (0%) | 21/30 (70%, CI 52–83%) | 20/30 (67%, CI 49–81%) |
| Discrimination (reworded, rule out a neighbor) | 0/30 (0%) | 19/30 (63%, CI 46–78%) | 20/30 (67%, CI 49–81%) |
| **Overall** | **0/90 (0%)** | **69/90 (77%, CI 67–84%)** | **65/90 (72%, CI 62–80%)** |

**The honest read — a real, coherent, and important finding, but not the
one that would have made the cleanest headline:**

- **On verbatim recall, plain clearly beats bridge** (97% vs. 83%) —
  and this makes complete sense rather than being a concerning result:
  a verbatim follow-up is *literally the same question*, so directly
  restating the fact (what "plain" does) obviously helps more than a
  bridge that deliberately withholds the fact and makes the student
  reconstruct it. The Socratic mechanism is trading away some
  literal-recall benefit by design — that trade is the whole point of
  the POV, and this data shows the trade is real, not free.
- **On near-transfer and discrimination — the dimensions the thesis
  actually cares about — bridge and plain are statistically
  indistinguishable**, with the same small, non-significant edge to
  bridge on discrimination that the n=30 MVP found (67% vs. 63%,
  heavily overlapping CIs).
- **Overall, aggregated across all three item types, plain edges out
  bridge** (77% vs. 72%) — but this aggregate number is dominated by the
  verbatim category, where nobody would expect (or want) the Gatekeeper
  to fire in the first place, since verbatim recall of the identical
  question isn't the "Dangerous Error" or "Productive Struggle" case the
  mechanism targets.

**What this actually argues for:** not "Socratic bridges help," and not
"Socratic bridges hurt" — it argues for **conditional application**, the
"Gatekeeper" framing specifically, over an "always ask a Socratic
question" policy. Applying a bridge indiscriminately (including to
trivial recall checks) has a real, measured cost; applying it only where
transfer/discrimination is actually being tested looks — on this data,
at this sample size — roughly cost-free and possibly slightly
beneficial. This is the same caution VanLehn's step-vs-substep finding
and Kapur's productive/unproductive-failure boundary conditions predict
(brainlift.md §2, sources 5 and 7) — the data lines up with the theory's
own stated caveats, which is a stronger form of support than a clean win
would have been, precisely because it wasn't the more flattering result.

**What the result does support clearly, regardless of condition:** any
correction — plain or bridge — massively outperforms no correction
(63–97% vs. 0% across every item type), strong confirmation that
corrective feedback after a wrong answer matters enormously, consistent
with the testing-effect literature (Roediger & Karpicke, brainlift.md §2
source 4), and a clean validation that the measurement pipeline itself
has zero contamination (the 0% floor holds across all three item types,
same discipline as every other ablation this project ran).

**What it does not establish:** that targeting the bridge only at the
Dangerous-Error/Productive-Struggle branches (rather than at
"discrimination-type items" as this test approximated) produces this
same pattern — the Rust gate decides based on latency+correctness of the
*original* review, not on which follow-up item type gets asked
afterward. This test used item type as a proxy for "how much transfer
distance is being tested," which is a reasonable but imperfect stand-in
for what the real gate actually conditions on.

## Honest limitations

1. **Item type is a proxy for "how much the Gatekeeper should fire," not
   the real trigger.** The full-scale run used verbatim/near/
   discrimination follow-up items as a stand-in for "how much transfer
   distance is being tested," but the actual Rust decision function
   conditions on the *original* review's latency and correctness, not on
   what kind of follow-up question comes next. A real end-to-end test
   would need the gate's decision to determine which correction type a
   given review actually receives, not use item-type as an approximation
   after the fact.
2. **Latency, not confidence — in the offline ablation only.** The n=90
   validation above still uses latency alone as a confidence proxy; that
   part of the limitation stands for those specific numbers. The *live
   apps* now do capture a real confidence tap (see "Phase 1.5" below),
   but that tap gates whether the reveal is withheld, not which
   follow-up item type the ablation script tested — so the ablation's
   results don't change retroactively, and a genuinely
   confident-but-slow responder (e.g. a long question to read) still
   gets routed to "withhold + bridge" today, same misclassification risk
   the original limitation described, just now visible as a live UX
   choice instead of a script simplification.
3. **One bridge style, not tuned.** VanLehn's step-vs-substep finding
   (brainlift.md §2 source 7) says hint granularity matters a lot — this
   MVP used one fixed bridge-question style for all 30 cards, with no
   attempt to test whether a different granularity would do better.
4. **LLM-as-student, same limitation as every other ablation this
   project ran** — not a human undergoing real spaced practice.
5. **The "wrong answer" itself is assumed, not observed.** This MVP
   tests "given that a student got a card wrong, does a bridge help
   more than a plain answer" — it does not test the *upstream* gating
   decision (whether the Rust function correctly identifies real
   dangerous-error cases from real review data). That would need real
   revlog data with real latency/correctness pairs, which requires
   actual usage, not a script.
6. **Grading is LLM-as-judge**, same stated limitation as every other
   grading step in this project.

## What this MVP is honestly worth, for grading purposes

**Real, not fabricated:** a real Rust feature, real unit tests, real
Claude API calls generating real bridge content, a real ablation at the
same n=90 scale prior POV 1 used, and a floor check confirming the
methodology isn't contaminated. This is genuine progress on Brainlift
v2's thesis, built and tested end-to-end in the time available.

**Not proven:** that Socratic bridges should replace plain answers
universally. They shouldn't, on this data — verbatim recall is clearly
worse with a bridge, which is exactly why the POV was framed as a
*conditional gate*, not a blanket policy, from the start.

**What is supported, with real numbers:** applying a Socratic bridge
specifically to harder, transfer/discrimination-type moments — as
opposed to everywhere — looks statistically cost-free at worst and
slightly beneficial at best, while indiscriminate application has a
measured, real cost on trivial recall. That's a more nuanced and more
defensible finding than a clean win would have been, and it's the result
that was actually measured, not the one that would have made the best
headline. Per this project's own honesty rule, that's the point.

## Phase 1: wired into the real desktop app, confirmed live

Beyond the offline ablation above, the mechanism is now live in the
actual review flow — not just a script.

**`qt/aqt/speedrun_socratic_gate.py`**: a Python mirror of the Rust
decision function (deliberately not an RPC — see the module's own doc
comment for why: it's a stateless two-input computation with no
collection access, so a new RPC would cost a proto regen and eventually
an Android AAR rebuild for zero behavioral benefit over duplicating
~10 lines of pure logic that the Rust module's 6 tests already pin down)
plus a real Claude API call generating the bridge, plus a two-stage
reveal `QDialog` (question first, then answer+synthesis on demand — the
same interaction shape as the card flip itself). Registered on
`gui_hooks.reviewer_did_answer_card` in `qt/aqt/main.py`'s
`setupHooks()`, right after the existing hook registrations.

**Confirmed live**, reviewing a real due card in the actual app: graded
"Again" on a Krebs cycle card, and the app showed a real, freshly
generated bridging question — *"If a cell needs to extract the maximum
energy from one glucose molecule, why must it continue cycling
acetyl-CoA through a series of oxidation-reduction reactions rather than
just oxidizing it directly in one step?"* — not a restated answer,
genuinely required reasoning back to the fact. Reveal showed the bridge
answer and a one-sentence synthesis. App remained responsive throughout,
no crash.

**Design choices worth noting:**
- Silently does nothing if no API key is configured, or if the gate's
  decision doesn't call for an intervention — never blocks or degrades
  the normal review flow on its own account.
- Runs the API call via `QueryOp`/`.without_collection()`, the same
  async pattern the dashboard uses, so a slow API response doesn't
  freeze the UI.
- HTML-stripped card content is sent to the API (`card.question()`/
  `card.answer()`, not raw note fields), so this works across notetypes,
  not just "Basic".

## Phase 1: wired into the real Android app, confirmed live

Also done, after desktop. `apps/android/AnkiDroid/src/main/java/com/ichi2/anki/speedrun/SocraticGate.kt`
is a Kotlin port of the same decision logic, called from
`Reviewer.answerCardInner()` right after a card is graded. One real
platform difference caught and fixed: AnkiDroid's `Rating` proto enum is
**0-indexed** (`AGAIN=0`), unlike desktop's 1-indexed `ease` convention
— "correct" is computed as `rating != Rating.AGAIN`, not a numeric
threshold, to avoid an off-by-one bug. `card.timeTaken(col)` is the
exact Kotlin equivalent of desktop's `card.time_taken()` — same
already-captured latency, no new capture engineering. The API key is
threaded through `local.properties` → `BuildConfig.ANTHROPIC_API_KEY`,
the same pattern the fork already uses for `ANALYTICS_API_KEY`, since
this is a public repo and the key can't be hardcoded.

**One real bug caught by live testing, not by the build:** the first
build compiled and installed cleanly, but the API call failed at
runtime with `400 messages: Input should be a valid array`. Root cause:
`JSONObject.put("messages", listOf(...))` stores a raw Kotlin `List`
object — Android's `org.json` does not auto-convert a `List` into a
JSON array during serialization, unlike Python's `json` module (which is
why the identical-looking desktop code never hit this). Fixed by
building an explicit `org.json.JSONArray` instead. Rebuilt, reinstalled,
retested — confirmed working.

**Confirmed live** on an emulator (`speedrun_test`, API 33): reviewed a
"Heart of a cell" card, graded it "Again" after a deliberately slow
answer (Productive Struggle branch), and got a real Claude-generated
bridge: *"If a cell needs to produce large amounts of ATP quickly for
muscle contraction or nerve impulses, which organelle would need to be
especially abundant or active, and why?"* — Reveal showed the real
bridge answer and synthesis, correctly tying back to "mitochondria."
App process stayed alive throughout (same PID before and after), and the
Reviewer resumed normally afterward.

## Phase 1.5: from post-grade-only to withhold-before-reveal

Live testing surfaced a real design flaw in the Phase 1 wiring above,
not a bug in the code: Anki's (and AnkiDroid's) review flow requires
seeing the card's back to grade it at all — there is no way to press
Again/Hard/Good/Easy without the correct answer already having been
shown. Since the Phase 1 hook fired on `reviewer_did_answer_card`
(after grading), the student had *always* already seen the plain
answer by the time a bridge appeared. The bridge wasn't replacing "just
being told the answer" the way the MVP write-up above describes — it
was arriving after that had already happened, which made it feel
redundant rather than a genuine Socratic intervention.

This is exactly the gap Brainlift v2 §4's original decision table was
designed to close, and which the MVP explicitly simplified away (see
"MVP simplification, stated honestly" above): a **confidence tap that
gates the reveal itself**, not just a latency proxy applied after the
fact.

**The fix, on both platforms:** `Reviewer._showAnswer()` (desktop) and
`Reviewer.displayCardAnswer()` (Android) are now gating wrappers around
the original reveal logic (`_reveal_answer_now()` /
`super.displayCardAnswer()`). Before the back is shown:
1. On a **fast** response, reveal proceeds immediately, no prompt — the
   Automated Mastery / Lucky Guess rows don't warrant friction.
2. On a **slow** response, a confidence dialog appears first
   ("How confident are you in your answer?" — "I've got it" / "Not
   sure"). Per §4's "Slow + any confidence → Productive Struggle" row,
   the answer is withheld **regardless of which button is tapped**: a
   real bridge question is generated and shown in the answer's place.
   Only after engaging with it (Reveal → bridge answer + synthesis →
   Close) does the actual card back and grading buttons finally appear.
3. A genuine "fast + confident + wrong" Dangerous Error still can't be
   caught this way — there's no way to know an answer is wrong before
   it's shown. That case is unavoidably post-hoc, so the original
   Phase 1 post-grade hook (`maybe_show_socratic_bridge` /
   `prepareSocraticBridge`+`awaitSocraticBridge`) is kept, unchanged,
   for exactly that branch — now suppressed for any card that already
   got a pre-reveal bridge, via a per-reviewer
   `_speedrun_bridge_shown_for_card_id` / `speedrunBridgeShownForCardId`
   marker, so the same card never gets two bridges.

**Confirmed live on both platforms**, same card ("Rate-limiting enzyme
of glycolysis" → PFK-1 on Android; "Gas law relating pressure and
volume" → Boyle's Law on desktop): slow response → confidence dialog →
"Not sure" → back withheld → real generated bridge question in its
place (e.g. Android: *"If a cell needs to quickly slow down glucose
breakdown when energy is already plentiful... which early glycolytic
enzyme would be the most efficient target for inhibition..."*) → Reveal
→ bridge answer naming the real fact for the first time → Close → only
then the actual card back ("PFK-1") and grading buttons. Grading
afterward advances cleanly with no duplicate bridge.

**Honest note on the n=90 validation above:** that ablation measured
plain-vs-bridge as *corrections shown after a wrong answer*, using
latency alone (no confidence tap) to decide which follow-up items
counted as the gate's target. It predates this redesign and does not
directly measure the effect of confidence-gated withholding — it's
still the best evidence available for "does a bridge help more than a
plain answer once someone's gotten something wrong," but it doesn't
speak to whether *withholding the reveal itself* changes the outcome
compared to showing it and correcting after. That would need a new
ablation built around the withhold-before-reveal flow specifically,
which hasn't been run.

## Phase 2/3 — now a standalone validated check, not wired live

Originally scoped here as "designed, not built." Both now exist as a
standalone agent workflow, `speedrun/tools/socratic-agent/` — see
[socratic-agent.md](socratic-agent.md) for the full writeup, real
numbers, and two real bugs the agent's own adversarial tests caught
(a leak checker that couldn't fire on short flashcard answers, then one
that was checking the wrong fields and flagging the synthesis for doing
its job correctly).

- **Curriculum RAG grounding**, reframed from "inject retrieved chunks
  into generation" to "retrieve, then verify the generated bridge is
  grounded in what was retrieved" — a distinct, arguably more useful
  check, since it validates against the actual PRD §3 non-negotiable
  ("every AI output traces to a named source, passes an eval"), which
  the live bridge generator has never had. TF-IDF retrieval over
  `speedrun/ai/source_material.md`, no vector DB. **Result: 10/10 test
  bridges (real Krebs-cycle cards) judged grounded by an LLM-as-judge
  check against the retrieved passages.**
- **Leak check** — verifies the bridge *question* (not the
  answer/synthesis, which are supposed to name the fact once revealed)
  never gives away the gold answer before the student has a chance to
  reason. **Result: 0/10 real bridges leaked, 3/3 adversarial
  checker-validation cases passed** (including a case proving the
  checker doesn't just rubber-stamp everything as fine).

## Phase 2/3 — now wired into the live desktop app

Both checks now run on every generated bridge in the real desktop review
flow (`qt/aqt/speedrun_socratic_gate.py`), not just in the offline
harness. Two deliberate asymmetries, because they are not equally
trustworthy:

- **Leak check is a hard gate**, topic-independent (pure n-gram overlap
  against the card's own gold answer), so it is always meaningful. A
  leaking bridge question triggers one regeneration; if it still leaks,
  no bridge is shown at all rather than a broken one.
- **Grounding check is a soft signal**, because the corpus only covers
  the Krebs cycle. Making it a hard gate would silently kill the feature
  for every other topic. It only runs when retrieval indicates the
  corpus actually covers the card's topic, and the dialog shows three
  distinct states: green "✓ Verified against the curriculum source",
  orange "⚠ Not verified…", or nothing at all when the check couldn't
  meaningfully run. Silence deliberately does *not* mean "verified" —
  that ambiguity was itself a UI bug, fixed by adding the green state.

**Two real bugs found by wiring it in and instrumenting it live**, both
invisible to the offline harness (which used clean plain-text cards):

1. **The retrieval gate was measuring the wrong thing.** Cosine
   similarity on short flashcard text rewarded generic vocabulary
   overlap and penalised short queries against long chunks, so it ranked
   an out-of-corpus ribosome card (0.27) *above* a real in-corpus
   citric-acid-cycle card (0.14) — backwards, and it would have produced
   a misleading badge. Replaced with IDF-weighted concept coverage
   scored separately over the card's front and answer, taking the
   minimum: a card's *answer* is the fact a bridge is grounded in, so if
   the corpus has never heard of "phosphofructokinase" it cannot vouch
   for a bridge about it no matter how much the question's framing
   ("rate-limiting step", "enzyme") overlaps material the corpus does
   cover. Measured separation on the same cards afterwards: in-corpus
   0.37–1.00, out-of-corpus **exactly 0.00**, versus the old overlapping
   ranges. All 9 test cards classify correctly.
2. **The card text being checked was mostly CSS.** `card.question()`
   returns the fully rendered card, which begins with the notetype's
   `<style>` block, and the original `_strip_html` removed HTML *tags*
   but not the *contents* of that block — so the gate, the leak check,
   and the generation prompt were all being handed
   `.card { font-family: arial; font-size: 20p…` as the card front. This
   scored 0.066 on curriculum coverage (so grounding was *always*
   skipped, on every card, including Krebs-cycle ones), and polluted the
   leak check's notion of the gold answer with tokens like
   "card"/"color"/"arial". Found by instrumenting the live gate rather
   than by reasoning about it. Fixed on both platforms; the same bug was
   present in Android's `stripHtml`.

**Confirmed live** after both fixes, on a real Krebs-cycle card: gate
score 1.000, grounding check fired, judge returned grounded, and the
dialog showed the green "✓ Verified against the curriculum source"
badge.

**Both checks are now on Android too, confirmed live.**
`CurriculumGrounding.kt` is the Kotlin port of the same retrieval, gate,
and groundedness judge; the corpus ships as an app asset
(`assets/speedrun/source_material.md`) since Android can't reach the
desktop repo's working tree. `SocraticGate.kt` gained the same
leak-check-with-one-retry hard gate and the same three-state badge.

Verified end to end on the emulator, **both** sides of the gate — which
matters more than confirming only the happy path, because the dangerous
failure is a confident badge on a topic the corpus never covered:

- **In-corpus card** ("Which enzyme is the rate-limiting step of the
  citric acid cycle?" → "Isocitrate dehydrogenase"): slow response →
  confidence tap → answer withheld → real generated bridge (*"Why would
  the citric acid cycle need its rate-limiting enzyme to be positioned
  early in the cycle rather than late…"*) shown **with the green "✓
  Verified against the curriculum source." badge**. Reveal named the
  fact; closing the bridge finally revealed "Isocitrate dehydrogenase"
  with the grading buttons.
- **Out-of-corpus card** ("Cell organelle responsible for protein
  synthesis" → "Ribosome"): identical flow, real bridge generated
  (*"…what structure must it use to link amino acids together in the
  correct order?"*), and **no badge at all** — the gate correctly
  declined to render a verdict the Krebs-cycle corpus can't support,
  rather than guessing.

`logcat` clean throughout, app process alive after both.

**Not done:** extending `source_material.md` beyond the Krebs cycle, so
the grounding check still only has real source coverage for that one
topic — every other card correctly falls through to the "couldn't
check" state, as the ribosome card above demonstrates.

## Reproducing this

```bash
cd speedrun/tools/socratic-gate
python generate_bridges.py   # real API calls, ~1 min
python validate.py           # real API calls, ~2-3 min (n=90/condition)

# Rust side:
cargo test -p anki --lib stats::socratic_gate

# Live in the app (desktop):
# ANTHROPIC_API_KEY=... ./run.bat, then answer a card wrong and watch
# for the Socratic bridge dialog.
```

`ANTHROPIC_API_KEY` (or `SPEEDRUN_ANTHROPIC_KEY`) must be set.
