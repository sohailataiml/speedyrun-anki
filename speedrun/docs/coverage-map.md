# Coverage map (PRD §8)

PRD §8: *"Coverage map. Every topic on the official outline, marked
covered or not, percent on the dashboard. Below your line, the app
abstains."*

## The outline is the denominator, and that's the whole point

`speedrun/data/mcat_outline.json` holds the real AAMC content outline:
4 sections, 10 foundational concepts, **31 content categories** (9
bio/biochem + 10 chem/phys + 12 psych/soc). Coverage is measured against
*that*, not against the `topic::` tags that happen to exist in the
collection.

That distinction is the entire value of this feature. Measuring coverage
over "topics I have cards for" trends to 100% as you study whatever you
already own, no matter how little of the exam that represents — it is
precisely the *"content volume sold as progress"* failure the PRD's
teardown question asks you to find in competitors. Measuring against the
published outline means unstudied sections count against you, which is
uncomfortable and correct.

## Where the outline data came from

Transcribed, then spot-verified against AAMC directly — stated plainly
because an outline is a factual document and getting it from memory
would be exactly the kind of fabrication this project's honesty rule
forbids:

- **Verified verbatim against AAMC**: Foundational Concept 1's statement
  and categories 1A–1D, category 4A, category 10A.
- **Transcribed from a third-party compilation** that matched AAMC
  exactly on every one of those spot-checks:
  [medlifemastery's AAMC outline](https://medlifemastery.com/mcat/content-review/aamc-outline/).
  The remaining categories were **not** individually re-verified.
- **Deliberately omitted**: the statements for Foundational Concepts
  2–10. Only FC1's was fetched directly; paraphrasing the others from
  memory would have been inventing official wording.
- Authoritative source, if you want to check it:
  [AAMC — What's on the MCAT Exam?](https://students-residents.aamc.org/prepare-mcat-exam/whats-mcat-exam-pdf-outline)

One factual error was caught during the build and is worth recording:
the first draft said "30 content categories". Counting them
programmatically gave **31** (9 + 10 + 12). The code found the mistake
in the prose, not the other way round.

## The topic-tag mapping is ours, not AAMC's

Each content category carries a `topic_tags` array mapping this
collection's `topic::<name>` tags onto it — e.g. `topic::krebs_cycle`
and `topic::glycolysis` both sit under **1D** (bioenergetics and fuel
molecule metabolism). Most categories have no tags at all. That is the
honest state of a small demo deck, and surfacing it is the job.

## Three states, not two

A binary covered/uncovered would hide a real distinction, so:

| Status | Meaning |
|---|---|
| `covered` | ≥1 card exists under one of the category's tags **and** ≥1 has a graded review |
| `has_cards_unreviewed` | cards exist, none reviewed yet |
| `uncovered` | no cards at all |

Only `covered` counts toward the headline percentage. Having made a card
is not the same as having studied it.

## CARS is excluded — and that's a limitation, not a convenience

Critical Analysis and Reasoning Skills has no memorizable content
outline; it is pure reasoning over passages. A flashcard deck
structurally cannot "cover" it. Counting it as permanently 0% would
misrepresent the score, so it is excluded from the denominator — but
that means **even 100% coverage here leaves roughly a quarter of the
real exam unmeasured**. The dashboard says so on screen rather than
letting the number imply otherwise.

## Results on the current collection

```
Outline denominator: 31 content categories (excluded: cars)

  1D   covered                cards=2 reviewed=2  Principles of bioenergetics and fuel molecule metabolism
  2A   has_cards_unreviewed   cards=1 reviewed=0  Assemblies of molecules, cells, and groups of cells...
  3A   covered                cards=2 reviewed=1  Structure and functions of the nervous and endocrine systems...
  4B   covered                cards=1 reviewed=1  Importance of fluids for the circulation of blood...

by status: {'covered': 3, 'has_cards_unreviewed': 1, 'uncovered': 27}
COVERAGE: 9.7% (3/31 categories)
```

**9.7%.** That is the honest number for a six-card demo deck, and it is
the number the dashboard shows.

## Relationship to the Rust give-up gate (both still exist)

`rslib/src/stats/give_up_gate.rs`'s `topic_coverage()` computes something
different and easier: the proportion of the *requested* topics that have
a graded review. It gates the Readiness score's abstention rule.

**That is still the stand-in it always was, and this work did not replace
it.** Doing so properly means teaching the Rust layer to read the
outline file, which means a new proto message and RPC, which per
[rust-change-note.md](rust-change-note.md)'s `ALL_ARCHS` gotcha means a
full NDK cross-compile rebuild of the Android backend AAR to keep the two
apps on one engine. That is a real change with real risk, deliberately
not attempted late in the build.

So, precisely:
- **Readiness abstains** on the Rust gate's easier reviewed-topics
  measure (≥200 graded reviews and ≥50% of requested topics reviewed).
- **The coverage map** reports the honest outline-based number, on the
  dashboard, next to it.

### What building this exposed, and what was done about it

Putting both numbers on one screen made a real problem visible
immediately. On the current collection the dashboard showed:

> ✓ Give-up rule: 223 / 200 graded reviews · **67%** / 50% topic coverage
> **Projected MCAT: 503** (range 494–512, confidence Low)
> Coverage: **9.7%**

The gate *passed* — 67% against its 50% threshold — and the app emitted
a projected score, while genuine coverage of the exam was under 10%. The
gate wasn't wrong about what it measures; it was measuring the easy
thing. But the PRD is blunt about this class of failure: *"Inventing a
readiness number, or dressing a guess as a measurement, is an automatic
fail."* A 503 backed by 9.7% of the outline, presented without that
context, is uncomfortably close to that line.

The proper fix is to gate on outline coverage in Rust, which is the
proto-plus-AAR-rebuild change described above and was not safe to attempt
late in the build. The fix that *was* made: the Readiness panel now
carries an inline warning whenever real outline coverage is below 50%,
naming the exact gap and stating plainly that the give-up rule passed on
a different, easier measure. The number still appears — refusing to show
it would discard the working Performance model — but it can no longer be
read as a whole-exam prediction without the reader seeing why it isn't
one.

That warning is in `_outline_coverage_caveat()` in
`qt/aqt/speedrun_dashboard.py`, and it is deliberately styled as a
warning rather than a footnote.

## Reproducing this

```bash
python speedrun/tools/coverage-map/coverage.py <path/to/collection.anki2>
```

Writes `speedrun/tools/coverage-map/output/coverage_report.json`. The
desktop dashboard (`Ctrl+Shift+D`) calls the same `compute_coverage()`
function, so the panel and the script cannot drift.

## Not done

- Outline coverage feeding the Rust give-up gate (see above).
- Android has no coverage panel — its dashboard shows the three scores
  only.
- Topic-tag mappings exist for the 6 tags this deck actually uses. A
  real deck would need the other 25 categories mapped, which is data
  entry, not engineering.
