# The Give-Up Rule v2 (Brainlift v3, POV 2)

> *"A score based on 'Spacebar Reflex' is a lie. The app must refuse to
> score if behavioral data suggests the student is rote-memorizing card
> patterns."*

The v1 rule refused on **quantity** — not enough reviews, not enough
topics. v2 adds a rule about **quality**: it refuses when the reviews
that exist look like pattern-matching rather than retrieval.

## The three conditions

| Condition | Threshold |
|---|---|
| Graded reviews | ≥ 200 |
| Topic coverage | ≥ 50% |
| **Rote-pattern share** | **≤ 40% of judgeable topics** |

All three must pass. Every failing one is reported.

## Reconciling three different statements of one rule

The brainlift states this rule three ways, and they don't agree:

- `UpdatedBrainlift.md` §7 — abstain *"if latency SD is < 0.2"*
- `UpdatedBrainlift.md` §8 — hidden until *"minimum Latency Variance on **DOK-3 tagged topics**"*
- `brainlift.docx` §8 — hidden if volatility *"< 0.2 for **more than 40% of the deck**"*

Taken together: **apply the < 0.2 volatility test to reasoning-heavy
topics, and abstain once more than 40% of them fail it.** That satisfies
all three without contradicting any. The 0.2 is a coefficient of
variation — an interpretation of an unitless figure, argued in
[latency-volatility.md](latency-volatility.md).

## The denominator is where this rule lives or dies

Getting it wrong breaks the rule in opposite directions, so both
exclusions are deliberate and both are tested:

**Topics with fewer than two reviews are excluded from *both* sides.**
They have no dispersion to measure. Counting them as "not rote" would
dilute the fraction toward zero and stop the rule ever firing on a real
collection; counting them as rote would fire it on everyone who just
started studying. There is a test for each direction — including one
proving a single rote topic can't be *hidden* behind five barely-studied
ones (that case reports 100%, not 17%).

**Topics tagged `dok::1` / `dok::2` are exempt.** Uniform latency on
definitional material is automaticity, which is the *goal*, not a
failure. The brainlift scopes the rule to DOK-3 topics for exactly this
reason.

**Untagged topics are eligible, not exempt.** Exempting everything
unlabelled would mean the rule silently never fires on a deck nobody
tagged — a give-up rule that gives up on itself. Erring toward abstaining
is the right direction for a rule whose job is to refuse to score.

## Where DOK comes from — a deviation from the plan

The plan said Rust would read the per-section `dok_range` from
`speedrun/data/mcat_outline.json`. **It doesn't, and shouldn't.** `rslib`
cannot reach that file on Android, where it ships as an app asset rather
than a repo file; teaching the backend two lookup paths for one number
would be a genuine portability bug. DOK comes from a **`dok::<1-4>` note
tag** instead — the same mechanism `topic::` already uses, which syncs
with the collection and behaves identically on both clients.

A topic takes the **highest** DOK of any note in it: a topic containing
one real reasoning card is a reasoning topic even if most of its cards
are definitions.

The outline's `dok_profile` still exists and is still useful for tooling
that *assigns* those tags. It just isn't read by the backend.

## Proof that it fires

The real dev collection **cannot** demonstrate this, because it contains
genuine study — volatility 0.60–1.06, three to five times the threshold.
That is the correct null result, but it left the positive case covered
only by unit tests.

So `speedrun/tools/rote-demo/make_rote_collection.py` builds a throwaway
synthetic collection that spacebar-reflexes through four topics and
genuinely studies two:

```
  krebs_cycle      vol= 0.005  reviews= 40  ROTE
  glycolysis       vol= 0.005  reviews= 40  ROTE
  central_dogma    vol= 0.005  reviews= 40  ROTE
  amino_acids      vol= 0.005  reviews= 40  ROTE
  gas_laws         vol= 0.809  reviews= 40
  water_solutions  vol= 0.809  reviews= 40

gate result: insufficient
  reasons             : ['ROTE_PATTERN_DETECTED']
  graded reviews      : 240 / 200      <- PASSES
  topic coverage      : 100% / 50%     <- PASSES
  rote topic fraction : 67% (allowed 40%)
```

**This is the whole thesis in one output.** Both v1 conditions pass
comfortably — 240 reviews against a 200 floor, 100% coverage against a
50% floor. By every metric AnKing or UWorld would report, this student
has done the work. The app refuses anyway, because the *way* the work was
done carries no evidence of retrieval.

### On fabricating this data

That fixture openly fabricates review history, and an earlier fabricated-
review feature was **cut** from the coverage-map importer for being
dishonest. The distinction is the direction it pushes:

- The cut feature would have marked unstudied cards as studied, inflating
  a readiness number the student had not earned.
- This fixture manufactures *bad* behaviour so the detector can be seen
  catching it. It can only ever make the product look worse.

A fixture that cannot flatter the product isn't a way of cheating the
product's honesty rule. It also writes to a temp path and never touches a
real collection.

## Verified across the proto boundary

On the real collection, through the regenerated Python bindings:

```
gate result: insufficient
  reasons              : ['NOT_ENOUGH_COVERAGE']
  graded reviews       : 223 / 200
  topic coverage       : 36% / 50%
  rote topic fraction  : 0% (allowed 40%)
  rote CV threshold    : 0.2
```

Only the rule that actually failed is blamed. The rote rule reports 0%
and stays quiet.

## Not done

- **Neither client renders the new reason yet.** The backend returns
  `ROTE_PATTERN_DETECTED` and its three detail fields; the desktop and
  Android dashboards still render the v1 review-count/coverage text. That
  is Phase 7 — until then, a rote-pattern refusal will show as a generic
  "not enough data" on screen, which understates it.
- No card in the real collection carries a `dok::` tag yet, so every
  topic is currently treated as eligible. The card generator should
  assign DOK at generation time.
- 40% and the CV threshold are both unfitted constants, named in one
  place each. They are configuration, not findings.
