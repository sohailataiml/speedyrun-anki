# Implementation plan: the Latency-Volatility pivot

Plan only — no code changed yet.

## 0. Which file I read, and a discrepancy you should know about

The path you gave, `brainlift.md.docx`, is **0 bytes** — an empty file
(OneDrive placeholder or a save that didn't complete). I did not invent
content for it. Instead I found two real documents in the same folder:

| File | Size | Modified | Content |
|---|---|---|---|
| `UpdatedBrainlift.md` | 7,058 B | Aug 2 17:24 | **3 spiky POVs**, richest version |
| `brainlift.docx` | 20,227 B | Aug 2 17:30 | Titled "v1", **1 spiky POV** |

**I planned against `UpdatedBrainlift.md`** — it's a superset (3 POVs vs 1)
and it's the `.md` your message pointed at. `brainlift.docx` is newer by
timestamp but self-labels "v1" and is currently open in Word (there's a
`~$ainlift.docx` lock file), so its mtime reflects the editing session,
not newer content.

The two disagree on one thing that actually matters, in §8's give-up rule:

- `UpdatedBrainlift.md` §7: abstain *"if latency SD is < 0.2"*
- `UpdatedBrainlift.md` §8: hidden until *"minimum Latency Variance on DOK-3 tagged topics"*
- `brainlift.docx` §8: hidden if volatility *"< 0.2 for more than 40% of the deck"*

My plan reconciles all three (Phase 4). **If `brainlift.docx` is actually
the newer one, tell me** — dropping to 1 POV would cut Phases 5 and 6.

## 1. What actually changed from the old brainlift

| | Old (v2) | New |
|---|---|---|
| Core signal | latency × correctness → 4 branches | **latency volatility** |
| AI's job | Socratic **tutor** (bridge hints) | AI **proctor** (jitter/re-contextualise) |
| Give-up trigger | review count + topic coverage | **rote-pattern detection** |
| Performance score | model over topic mastery | **accuracy on jittered cards** |
| Readiness | maps performance → MCAT scale | composite **weighted by volatility** |

The new §1 puts *"general-purpose Socratic tutoring (avoiding 'hint
dependency')"* explicitly **out of scope**, and POV 3 argues hints create
a dependency loop. So cutting the Socratic hint isn't just permitted, the
new thesis requires it.

## 2. A useful irony worth keeping

The n=90 Socratic ablation already in this repo found bridges **hurt**
verbatim recall (97% → 83%) and were a wash on transfer. That was written
as a limitation of the old thesis. Under the new brainlift it becomes
**direct supporting evidence for POV 3** — our own data says hint-giving
didn't pay. I'd keep that document and re-frame it rather than delete it.
It's the strongest empirical thing the project owns, and it now points the
same way the new thesis does.

---

## Phase 1 — Retire the Socratic hint, keep the tested latency core — **DONE**

**Delete** (UI/tutor paths only):
- `qt/aqt/speedrun_socratic_gate.py`
- `apps/android/.../speedrun/SocraticGate.kt` dialog + gating paths
- the `_showAnswer` gating wrapper in `qt/aqt/reviewer.py` (restore the
  original body), the `main.py` hook, and `Reviewer.kt`'s call sites

**Keep and repurpose — do not delete:**
- `rslib/src/stats/socratic_gate.rs` → rename `latency_monitor.rs`. Its
  fast/slow threshold *is* traceability row 1's "tags reviews as System 1
  (Fast/Recognition) or System 2 (Slow/Analytical)". 6 passing unit tests
  carry over intact.
- `CurriculumGrounding.kt` + the desktop grounding/leak checkers. The
  Jitter engine needs exactly these two checks: a variant must stay
  grounded in the curriculum, and must **not** be a reworded restatement.
  Retarget, don't rebuild.
- The AAMC outline, coverage map, card generator, all three metrics, both
  clients, the fork. Untouched.

## Phase 2 — Latency Monitor in Rust (POV 1) — **DONE**

Results and caveats: [latency-volatility.md](latency-volatility.md).

New `rslib/src/stats/latency_monitor.rs`:

- **Minimum Reading Time**, computed per card from its text length rather
  than a flat 3s. The docx explicitly says *"faster than the calculated
  'Minimum Reading Time'"* — calculated, not constant. Words ÷ ~250wpm
  silent-reading floor. The current flat 3,000 ms becomes the fallback.
- `SystemType` classification per review from `RevlogEntry.taken_millis`
  (already exists on the struct — no schema change).
- `latency_volatility(entries) -> f32` per topic.

**Ambiguity I have to resolve, and will flag in code:** the brainlift says
*"latency SD is < 0.2"* **without units**. An SD of 0.2 *milliseconds* is
physically meaningless, so a literal reading can't be right. The reading
that makes 0.2 a sensible number is the **coefficient of variation**
(SD ÷ mean, dimensionless): CV < 0.2 means every response lands within
±20% of the same duration — machine-like uniformity, which is precisely
the "spacebar reflex" the POV describes. I'll implement CV, and say in
both the code and the doc that this is *my interpretation of an
underspecified threshold*, not a quote. Flagging rather than silently
picking is the point.

## Phase 3 — Proto + Android AAR, in ONE batch — **DONE**

Every proto change costs an `ALL_ARCHS=1` NDK cross-compile (~56 MB AAR,
per `rust-change-note.md`). So all proto edits landed together, once —
**including fields Phases 5 and 6 will need but nothing populates yet**,
specifically so those phases don't force a second cross-compile.

| Message | Added |
|---|---|
| `TopicMastery` | `optional latency_volatility`, `system1_review_count`, `system2_review_count`, `below_min_reading_time_count`, `graded_review_count` |
| `InsufficientData` | `repeated Reason reasons`, `rote_pattern_topic_fraction`, `rote_pattern_fraction_allowed`, `rote_pattern_cv_threshold` |
| `PerformanceData` | `optional jitter_accuracy`, `jitter_attempts` (Phase 5) |
| `ReadinessData` | `latency_volatility_weight`, `spacebar_reflex_reviews` (Phase 6) |

Three decisions in there worth stating:

**`optional` on `latency_volatility` is load-bearing, not style.** proto3
scalars default to 0.0 when absent, and 0.0 is *below* the rote-pattern
threshold — so a client reading a defaulted field would see every
unstudied topic as a confirmed spacebar reflex. Verified across the real
boundary: `amino_acids` (0 reviews) returns `HasField=False` with
`value=0.0`. The value is a trap; the presence bit is the answer. Same
reasoning applies to `jitter_accuracy`, where a defaulted 0.0 would read
as "gets every transfer question wrong".

**`reasons` is repeated, not a single enum.** More than one rule can fail
at once. A single-reason field would let a client send the student off to
fix review count while a second blocker still stands. Two tests pin this:
both reasons present when both fail, only one when only one fails.

**`latency_volatility_weight` defaults to 1.0, not 0.0.** Phase 6 hasn't
built the penalty yet, and 1.0 is the honest "no adjustment applied" —
0.0 would imply the score had been zeroed by a penalty that does not
exist.

## Phase 4 — Give-Up Rule v2 (POV 2) — **DONE**

Results: [give-up-rule-v2.md](give-up-rule-v2.md).

`give_up_gate.rs` gains a third abstention condition that reconciles all
three phrasings from §1: abstain when **more than 40% of topics** have
**CV < 0.2**, evaluated over **DOK-3 topics** where DOK is known.

DOK source, without inventing a new one: `mcat_outline.json` already
carries a per-section `dok_range` (added during the Socratic-policy work —
that part survives the pivot and gets reused). A `dok::N` note tag
overrides it per card when present.

Both clients render the new reason.

## Phase 5 — AI Jitter Engine (POV 3) — **DONE**

Results, and the measurement bug it shipped with: [jitter-engine.md](jitter-engine.md).

### Original plan

Design chosen to need **no new schema**:

- A jittered card is a **real card** in a `Speedrun::Jitter` deck, tagged
  `jitter::src::<nid>` and inheriting the source note's `topic::` tag.
- Generator `speedrun/tools/ai-jitter/`: takes a card, produces a
  context-shifted variant — swap the clinical scenario, the patient, the
  units — while the underlying logic must stay identical.
- **Two gates, both already built**: the variant must pass the grounding
  check (still true to curriculum) and must **fail** a
  paraphrase-similarity check (if it's just reworded, it tests nothing —
  that's the far-transfer requirement from Tulving).
- Trigger: every 3rd review of a DOK-3 card, per §7.
- Because jitter cards are ordinary cards, **accuracy on them is just the
  existing revlog math filtered to the `jitter::` tag**. Nothing new to
  store, and it syncs for free.

## Phase 6 — Readiness weighted by volatility (§8) — **DONE**

Results, and why the effect is smaller than "0.5x" sounds: [readiness-volatility-weighting.md](readiness-volatility-weighting.md).

- Composite of Memory and Performance, scaled by a volatility weight.
- The docx's 0.5× multiplier for any card answered below its minimum
  reading time.

**Correction — I got this wrong when planning.** This document originally
warned that redefining Performance would invalidate the held-back
**Brier 0.168** figure. It does not. That number measures the *FSRS
memory model's* calibration — `fsrs::current_retrievability` bucketed
against observed pass/fail on held-back reviews
([memory-calibration.md](memory-calibration.md)). It is independent of how
Performance and Readiness are defined, so nothing in Phases 5–6 touches
it. Checked before acting on it rather than after; recorded here because
the original claim was stated confidently and was simply incorrect.

What *would* invalidate it is a change to the memory model or to FSRS
parameters. Neither has happened.

## Phase 7 — Both clients — **DONE**

Both dashboards gained a **Latency volatility** panel (per-topic CV,
System 1 / System 2 split, spacebar-reflex count) and now render *every*
refusal reason rather than the bare review-count line.

Three deliberate choices, identical on both platforms:

- **A rote refusal gets its own headline** — "refusing to score — rote
  pattern detected", not "not enough data". There is plenty of data in
  that case; the data is the problem. Saying "not enough data" would
  understate the app's own strongest argument.
- **Topics with fewer than two reviews are hidden**, with a note saying
  why, rather than listed as 0.00. A displayed 0.00 sits below the rote
  line and would read as a confirmed spacebar reflex — the presence bit
  from Phase 3 is checked, never the defaulted value.
- **Rote lines are styled distinctly** (crimson on desktop) from the two
  volume rules (orange), so the thesis-critical refusal doesn't read as
  routine housekeeping.

Verified live on both, against the synthetic rote deck and the real
collection. Same numbers, same verdict, one engine.

**Known cosmetic difference:** Android prints the rote explanation once
(under Performance) while desktop prints it under both Performance and
Readiness. On a phone the duplicate paragraph is noise; the Readiness
headline still says "rote pattern detected".

### What live verification caught that CI would not

The first Android run showed **no latency panel and a projected score of
499** on the very deck desktop refuses. Neither was a logic bug:

1. An earlier background install had printed `adb: no devices/emulators
   found` — the emulator had died from memory pressure mid-build, so the
   device was still running an older APK.
2. The AAR predated Phase 4 entirely. Phase 4's rote rule is Rust, so it
   needed its own cross-compile; a fresh APK alone would still have
   scored 499.

Worth recording because the Phase 4 write-up said the APK ran "on the new
backend" — true of Phase 3's backend, but Phase 4's rule had never
reached Android. Only running the thing surfaced it.

## Phase 8 — Docs

The repo's convention is that `speedrun/docs/brainlift.md` is *current*
and superseded versions are kept beside it, never deleted:

```
brainlift.md                        <- v2 (Socratic), 30 KB, currently "current"
brainlift-v1.md                     <- preserved, 32 KB
brainlift-v1-observations.md
brainlift-v3-latency-volatility.md  <- NEW, copied in, 7 KB raw source
```

So Phase 8 is: rename v2 → `brainlift-v2-socratic.md`, and promote v3 to
`brainlift.md`.

**Not done as part of this plan step, deliberately.** The repo's
`brainlift.md` is a 30 KB worked document — traceability tables, the n=90
ablation, falsification records — while the new v3 is the 7 KB raw
source. Swapping the filenames now would look like an update but would
actually *lose* four times the content. v3 needs to be built up to the
same standard as the phases land and produce real results to cite. Until
then, both files sit side by side under their own names.

Also in Phase 8: `socratic-gate-mvp.md` retained and re-framed per §2
above; new `latency-volatility.md` and `jitter-engine.md`;
`ARCHITECTURE.md` updated.

---

## Sequencing, and where I'd cut if time is short

Phases 1 → 2 → 3 → 4 deliver **POV 1 and POV 2 end-to-end** — Rust,
proto, both clients — and are the smaller half. Phase 5 (Jitter) is the
single biggest build and carries Phase 6 with it.

If the deadline is tight, **1–4 is a coherent, honest shippable unit**:
latency volatility measured, rote patterns detected, the app abstaining
for a new and better-argued reason. Phase 5 is the part that most needs
real time, because a jitter variant that's secretly a paraphrase is worse
than no jitter at all.

## One thing I'd push back on

Making Performance **entirely** jitter-accuracy (§8) means the score goes
blank until enough jitter attempts exist — and jitter cards only appear
every 3rd review of DOK-3 cards, so that's a long warm-up on a small deck.
I'd rather add jitter accuracy as a **second input** alongside the current
model and let the give-up rule abstain when jitter data is thin. That's
faithful to POV 2's own logic (abstain rather than fake it) without
blanking a working metric on day one. Happy to do it literally as written
if you'd prefer — just flagging the consequence before building it.
