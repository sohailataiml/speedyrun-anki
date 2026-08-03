# Latency Volatility (Brainlift v3, POV 1)

The Memory score answers *"can you recall this?"*. This answers a
different question: *"does the way you recall it look like reasoning, or
like pattern-matching?"*

FSRS treats a 1.0s "Good" and a 6.0s "Good" as the same event. On DOK-3
material they are not the same event, and the gap between them is where
the Readiness Illusion lives.

## What is measured

`rslib/src/stats/latency_monitor.rs` — pure functions, no `Collection`,
exhaustively unit-tested. `rslib/src/stats/mastery.rs` aggregates them
per topic.

| Quantity | Meaning |
|---|---|
| **System 1 / System 2** | Per review: faster than the threshold = recognition; slower = analytical |
| **Minimum reading time** | The shortest time this card's text could honestly be read |
| **Spacebar reflex** | Reviews answered *faster than the card can be read* |
| **Latency volatility** | Coefficient of variation (SD ÷ mean) of a topic's latencies |

Both inputs — `taken_millis` and `button_chosen` — are already captured
by upstream Anki on every grade. **No new capture, no schema change.**

## The threshold has no units in the brainlift, and that matters

Brainlift v3 §7 says to abstain when *"latency SD is < 0.2"*. It never
says 0.2 **of what**. A standard deviation of 0.2 *milliseconds* is
physically meaningless for human response times, so the literal reading
cannot be what was meant.

The reading that makes 0.2 a sensible quantity is the **coefficient of
variation** (SD ÷ mean), which is dimensionless. CV < 0.2 means
essentially every response lands within ±20% of the same duration — which
is what pressing space without reading looks like.

**This is an interpretation, not a quotation**, and it is written that
way in the code. CV also has a property a raw SD does not: it is
**scale-invariant**. A student who is uniformly slow and a student who is
uniformly fast are both pattern-matching; only a dimensionless measure
calls both of them out. There is a test pinning exactly this
(`volatility_is_scale_invariant`).

## Minimum reading time is calculated, not constant

v2 used a flat 3-second threshold. v3's own wording is "faster than the
*calculated* Minimum Reading Time", and the calculation matters: three
seconds is leisurely for "Citrate synthase" and impossible for a
four-line clinical vignette. A flat threshold punishes long cards and
lets short ones through.

So: words ÷ 250 wpm, with an 800 ms floor. Two deliberate conservative
choices, both in the direction of *not* accusing the student:

- **250 wpm** is a mid-range adult silent-reading figure for ordinary
  prose. Dense technical material is slower, so this **under-estimates**
  the time a real MCAT card needs.
- **The note's joined fields** stand in for the rendered card text.
  Rendering every card through its template would mean running the
  template engine across the whole collection for an aggregate stat.
  Cards of one note therefore share an estimate, and cloze deletions
  count their full source text — both make the estimate *generous*.

When note text is unavailable the check is **disabled for that card**
rather than defaulting to the floor, so a missing lookup can never
manufacture an accusation.

## Absence of evidence is not evidence of the spacebar reflex

`latency_volatility` returns `Option<f32>`, and returns `None` — not
`0.0` — for fewer than two reviews.

This is the give-up rule applied to the give-up rule's own input. A
single review has no dispersion to measure. Returning 0.0 would be
numerically reasonable and behaviourally disastrous: 0.0 is *below* the
rote threshold, so every barely-studied topic would be flagged as
pattern-matching, and the app would abstain hardest on exactly the
students who had just started. There is a test for it
(`too_few_reviews_is_none_not_zero`), and `is_rote_pattern(None)` is
false by construction.

Sample SD (n−1) is used rather than population SD, since real topics have
small review counts.

## What the real collection says

Run against the actual dev collection (`probe_real_collection_latency`,
an `#[ignore]`d diagnostic):

```
topic                    reviews volatility    S1    S2  <read  verdict
amino_acids                    0        n/a     0     0      0  ok
cell_biology                   0        n/a     0     0      0  ok
cell_division                  0        n/a     0     0      0  ok
central_dogma                  0        n/a     0     0      0  ok
endocrine                      0        n/a     0     0      0  ok
gas_laws                       5      0.621     0     5      0  ok
glycolysis                     7      0.605     0     7      0  ok
krebs_cycle                    6      1.060     2     4      2  ok
neuromuscular                  6      0.750     0     6      0  ok
thermo_kinetics                0        n/a     0     0      0  ok
water_solutions                0        n/a     0     0      0  ok

0/11 topics flagged as rote pattern (0%)
```

Two honest readings of that table:

**The detector does not fire on real study.** Genuine human review
produces volatility of 0.6–1.06, three to five times the 0.2 threshold.
That is the correct null result — a rote-pattern detector that flagged
ordinary studying would be useless.

**But it also means there is no positive real-data case yet.** Rote-pattern
detection is currently demonstrated by unit tests only, because this
collection contains no spacebar-reflex behaviour to detect. That is a
genuine gap in the evidence, not an oversight, and it should not be
described as "validated on real data" until someone actually
spacebar-reflexes through a deck. Note also that six of eleven topics
have zero reviews (the coverage cards were imported unreviewed and never
studied), so they correctly report `n/a` rather than being flagged.

The `krebs_cycle` row is the most interesting: 2 of its 6 reviews came in
*below the card's minimum reading time*. Those are real — they are the
fast taps from earlier UI testing. The signal works; there just isn't a
sustained pattern of it.

## Relationship to the retired v2 gate

`socratic_gate.rs` became this module. The fast/slow threshold and its
**inclusive** boundary (a review taking exactly the threshold counts as
fast) carried over unchanged, because that part was always a latency
classifier. What was dropped is the four-branch decision table, which
existed only to choose between Socratic interventions v3 removes.

The tests were **adapted, not inherited** — same boundary behaviour, new
vocabulary. Claiming the old tests "still pass" would overstate it.

## Not done

- **Nothing is exposed to either client yet.** `TopicLatency` is a plain
  Rust struct; the proto fields land in Phase 3, batched so the Android
  backend AAR is cross-compiled once rather than per-field.
- The give-up rule does not consult volatility yet — that is Phase 4.
- The fast/slow threshold is still the flat `DEFAULT_FAST_THRESHOLD_MS`
  for System 1/2 classification; only the *spacebar reflex* check is
  reading-time aware. Making classification per-card reading-time aware
  is a one-line change once there is reason to believe it is better.
- `dok_range` per section now lives in `speedrun/data/mcat_outline.json`
  as `dok_profile` (it survived the Socratic cull because v3 needs to
  know which content is reasoning-heavy). Phase 4 consumes it. Its
  provenance note is blunt that these ranges are an editorial judgement,
  not an AAMC-published fact.
