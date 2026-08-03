# The AI Jitter Engine (Brainlift v3, POV 3)

> *"AI hints create a Dependency Loop. AI should only be used to Jitter
> (Re-contextualise) the card to prove the logic holds in a new
> scenario."*

v2 used the AI as a **tutor**: when you got a card wrong, it wrote you a
hint. v3 uses it as a **proctor**: it takes a card you claim to know and
asks the same principle somewhere you haven't seen it.

The theory is Tulving's encoding specificity — a fact welded to one
card's phrasing may not survive transfer to an MCAT passage. The only way
to find out is to move it.

## What a variant looks like

Real output from the engine:

| | |
|---|---|
| **Original** | *What structural feature of amino acids is responsible for the chemical differences between the 20 standard amino acids?* |
| **Variant** | *A biochemist observes two polypeptides with identical backbone atoms but very different reactivity…* |
| **Shifted** | changed from amino acids to nucleotides; from side chains to nitrogenous bases; kept the principle that a constant backbone with variable substituents creates chemical diversity |

Memorising "side chains" answers the original. It does not answer the
variant.

## Four gates, and why the split matters

A variant can fail in opposite directions, and catching only one is worse
than useless:

- **Too similar** → a paraphrase. It proves nothing new but *looks* like
  transfer evidence, so it would inflate Performance with recall dressed
  as reasoning. This is what POV 3 is actually about.
- **Too different** → it tests some other fact. Accuracy on it says
  nothing about the original.

Both are enforced, but by **different kinds of check**:

| Gate | Kind | Catches |
|---|---|---|
| `term_reuse ≤ 60%` | deterministic | paraphrase |
| judge: `SAME_PRINCIPLE` | LLM | drifted to a different fact |
| judge: `NEW_SITUATION` | LLM | reworded, not re-contextualised |
| `leaks_answer` | deterministic | variant gives away its own answer |
| grounding | LLM, **soft** | invented facts |

Cheap deterministic checks run first, so an obvious paraphrase costs one
API call rather than three. Grounding is *reported*, never enforced — the
corpus covers six topics, so hard-gating it would silently kill variants
on every other topic. Same discipline as the retired bridge.

## The measurement bug this shipped with, and the fix

The first version used **symmetric Jaccard** over content terms, with
both a ceiling and a floor. On the first real run it rejected 4 of 10
variants as *"unrelated: surface overlap < 0.08"*. Every one of those
four had `same_principle: True` **and** `new_situation: True` — the judge
said they were exactly right.

The cause: Jaccard is length-sensitive. A four-word original ("Cell
organelle responsible for protein synthesis") against a rich clinical
vignette scores near zero even when every original term appears. It
punishes precisely the asymmetry jitter is *supposed* to produce — short
prompt in, rich scenario out.

This is the same mistake, in the same shape, as the cosine similarity
that once broke curriculum retrieval in this project. Symmetric
similarity measures keep being the wrong tool for asymmetric comparisons.

Two fixes:

1. **Asymmetric measure.** `term_reuse` = what fraction of the
   *original's* terms the variant reuses. The denominator is the original
   alone, so variant length can't drag it down.
2. **The floor was deleted, not retuned.** "Too different" is a question
   about *meaning*, and the judge's `SAME_PRINCIPLE` check already
   answers it properly. A lexical floor was a worse proxy for a question
   something else was already answering correctly.

The fix moved results in **both** directions, which is the real evidence
it was right:

| Card | Old (Jaccard) | New (term reuse) |
|---|---|---|
| *Cell organelle…* | 0.06 → **rejected** (wrongly) | 60% → **accepted** |
| *Gas law…* | 0.09 → **accepted** (wrongly) | 71% → **rejected** as paraphrase |

The gas-law variant had been reusing most of the original's vocabulary
all along; because it was long, symmetric Jaccard hid it. A metric that
only stopped over-rejecting would be suspicious. This one also started
catching things it used to wave through.

## Results on the real collection

14 cards in, 8 variants accepted (57%):

```
accepted 8/14   rejected 6/14
rejection reasons:
    4  paraphrase          (71-83% term reuse)
    2  judge               (tests a different principle)
    1  variant question contains its own answer
    1  not grounded in the curriculum corpus
```

A 57% acceptance rate is the system working, not failing. The rejected
6 include a variant that leaked its own answer and one that invented
material outside the curriculum — both would have quietly corrupted the
Performance score.

## How it reaches the score, without new schema

A jitter variant is an **ordinary card** in a `Speedrun::Jitter` deck:

```
jitter::src::<source note id>   provenance, and what Rust filters on
topic::<name>                   inherited, so it scores under the same topic
```

Because it's just a card, *"accuracy on jitter cards"* is the existing
revlog math with a tag filter — no new table, no new sync path, no new
failure mode. `Collection::jitter_accuracy()` returns
`Option<f32>`: **`None`, never 0.0**, when there are no attempts.
"No transfer questions answered yet" and "gets every transfer question
wrong" are opposite claims, and a defaulted zero reports the second. The
dashboard checks the presence bit and says "not measured yet" rather than
"0%".

Generation and import are **separate commands on purpose**.
`run_jitter.py` only writes JSONL; a generator that silently injects
cards into a deck a student will study is not auditable after the fact.
`import_jitter.py` is idempotent — re-running never duplicates a variant.

## Not done — stated plainly

- **The positive path is not demonstrated on real data.** Eight variants
  are in the collection; nobody has studied them, so live jitter accuracy
  is correctly `None`. The populated path is covered by unit tests
  (`jitter_accuracy_reaches_the_performance_response`), not by a real
  student.
- **Performance does not yet blend jitter accuracy into its prediction.**
  It is *reported* alongside the model's output, not folded in. Making it
  the sole input, as §8 literally says, would blank the metric until
  enough variants exist — the trade-off flagged in the pivot plan. That
  decision belongs with Phase 6.
- **No "every 3rd review" trigger.** v3 §7 asks for automatic generation
  during review. Generation is currently a batch tool. Wiring it into the
  reviewer means live API calls on the study path — the exact latency
  cost that made the v2 bridge unpleasant — so it needs its own design.
- **Android shows nothing yet.** `jitter_accuracy` is populated by Rust
  added in this phase, so the Android backend AAR needs another
  cross-compile before the phone can display it. The proto fields are
  already there from Phase 3.
- The 60% threshold is unfitted. It is configuration, not a finding.
