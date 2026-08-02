# Socratic bridge agent: RAG groundedness check + leak check

Standalone validation harness answering a question the live Socratic
Gatekeeper (`qt/aqt/speedrun_socratic_gate.py`, `SocraticGate.kt`) never
asked: is the bridge Claude generates actually **grounded** in a real,
named, retrievable curriculum source, and does it **leak** the gold
answer before the student has a chance to reason? Neither check existed
before this — the live apps' bridge generator only sees a single card's
front/back, with no retrieval and no post-generation verification. See
[socratic-gate-mvp.md](socratic-gate-mvp.md)'s Phase 2/3 design notes for
where this was originally scoped as "designed, not built."

Code: `speedrun/tools/socratic-agent/`. This validated the approach
standalone first, the same pattern this project uses everywhere else
(paraphrase-test, socratic-gate's own MVP ablation).

**Both checks are now live on desktop and Android** — see
[socratic-gate-mvp.md](socratic-gate-mvp.md)'s "Phase 2/3" section.
Wiring them in surfaced two real bugs this harness could not have
caught, because it feeds clean plain-text cards while the live apps feed
fully-rendered card HTML: the retrieval gate was ranking out-of-corpus
cards above in-corpus ones, and the card text reaching all three stages
was mostly the notetype's CSS block.

The fixes have since been ported **back** into this harness, so all
three implementations now share one approach: IDF-weighted concept
coverage (front and answer scored separately, minimum taken), a gate
that declines to judge topics the corpus doesn't cover, and a leak check
scoped to the bridge question. sklearn is no longer a dependency here.
One intentional divergence remains: the live apps retry a leaking bridge
once and then suppress it, while this harness records leaks instead,
because measuring how often they happen is the point.

## Architecture: a small graph, not a framework

Four nodes, one shared state object, threaded through explicitly:

```
retrieve_node -> generate_node -> check_grounded_node -> check_leak_node
```

This mirrors a LangGraph-style `StateGraph` (named nodes, one state
object, an explicit edge list) without adding the `langgraph` dependency
itself. For a 4-node linear pipeline, hand-rolling the same shape is
easier to read, debug, and defend than a framework wrapping one function
call — every node function has the `(state) -> state` signature a real
LangGraph node uses, so swapping in the actual library later is
mechanical, not a rewrite. `agent.py`'s `WORKFLOW` list is the literal
edge list; the one thing it doesn't do yet that a real graph port would
add is a conditional edge (`grounded=False` → loop back to
`generate_node` with the failure reason folded into a retry prompt) —
right now a failed check is recorded, not retried.

- **`retrieve_node`** — IDF-weighted concept coverage (`retrieval.py`)
  over the 14 chunks of `speedrun/ai/source_material.md`. No vector DB,
  no persisted index, no embeddings API — and, since the port back from
  the live desktop implementation, no sklearn either. Also produces a
  **gate score**: does the corpus cover this card's topic well enough for
  a groundedness verdict to mean anything at all?
- **`generate_node`** — the same Claude call, same prompt, as the live
  `_generate_bridge()`/`generateBridge()`.
- **`check_grounded_node`** — a second Claude call (LLM-as-judge, same
  methodology this project already uses for grading in paraphrase-test
  and the ai-cardgen eval): given the bridge and the retrieved passages,
  is the bridge's factual content actually supported by them? **Skipped
  entirely when the gate score is below threshold**, leaving the verdict
  as `None` rather than guessing — the same give-up-gate discipline as
  `give_up_gate.rs` refusing to emit a readiness score without data.
- **`check_leak_node`** — local, no API call. Checks whether the gold
  answer's phrasing shows up in the bridge *question* specifically (see
  below for why not the answer/synthesis too).

### Why retrieval is not cosine similarity

The first version used sklearn's `TfidfVectorizer` + cosine similarity.
Wiring the same idea into the live desktop app and instrumenting it
showed cosine measures the wrong thing for flashcards: it rewards
generic vocabulary overlap and penalises short queries against long
chunks. On the real card set it ranked an out-of-corpus ribosome card
(0.27) **above** a genuine citric-acid-cycle card (0.14) — backwards,
and enough to have produced a confident "verified" badge backed by
nothing.

The replacement asks a better question: *what fraction of this card's
information content does the chunk actually cover*, weighting each term
by how distinctive it is in the corpus, with terms the corpus has never
seen counting fully against the score. Front and answer are scored
separately and the **minimum** taken, because a card's answer is the
fact a bridge is grounded in — if the corpus has never heard of
"phosphofructokinase" it cannot vouch for a bridge about it however much
the question's framing ("rate-limiting step", "enzyme") overlaps
material the corpus does cover. That glycolysis card is the sharpest
case: 0.61 on its front, 0.00 on its answer.

## Honest scope: one topic, real numbers

**Corpus is narrow on purpose, stated plainly:** `source_material.md`
only covers the Krebs cycle (14 chunks). The 10 test cards
(`cards.py`) are real MCAT-relevant Krebs-cycle facts, each one drawn
directly from a specific chunk with the expected chunk ID recorded as
ground truth — not the counterfactual/renamed cards paraphrase-test and
socratic-gate use elsewhere (those exist for a different, leak-safe
grading purpose; this check needs real content with a real source to
verify against). This agent is not validated against the full breadth
of cards this session tested live in the apps (glycolysis, cell biology,
endocrine, gas laws) — there's no curriculum source for those topics in
this repo yet, and testing "groundedness" against a source that doesn't
cover the card's topic would be meaningless.

Rerunnable:
```bash
cd speedrun/tools/socratic-agent
python run_agent.py
```
Requires `ANTHROPIC_API_KEY`. Writes real, checkable output to
[`output/results.json`](../tools/socratic-agent/output/results.json).

## Results

15 cards: 10 real Krebs-cycle cards the corpus covers, plus 5 real MCAT
cards on topics it does **not** (ribosomes, acetylcholine, Boyle's law,
glycolysis/PFK-1, insulin). The out-of-corpus cards exist to test the
part most likely to fail silently — an over-permissive gate produces a
confident badge backed by nothing, which is worse than no badge.

| | n | Result |
|---|---|---|
| In-corpus cards where the gate fired | 10/10 | 100% |
| …of those, judged grounded in the retrieved source | 10/10 | 100% |
| Out-of-corpus cards where the gate correctly declined | 5/5 | 100% |
| Retrievals that hit the card's actual source chunk | 10/10 | 100% |
| Bridges that leaked the gold answer in the question | 1/15 | 7% |
| Adversarial checker-validation cases | 3/3 | all passed |

**Gate score separation: in-corpus 0.371–1.000, out-of-corpus exactly
0.000.** No overlap, no threshold tuning needed to make it work — the
old cosine ranges overlapped so badly that no threshold could have
separated them.

Two things worth calling out honestly rather than rounding off:

- **Retrieval accuracy went 9/10 → 10/10** with the coverage metric. The
  card the old cosine version missed (card 10, "how many times does the
  cycle turn per glucose") now retrieves its expected chunk.
- **One real leak, caught in the wild.** Card 102's generated bridge
  question was *"If a toxin blocked the breakdown of acetylcholine at the
  neuromuscular junction, what would happen to muscle contraction…"* —
  it names the gold answer outright, before the student has any chance to
  reason. That is exactly the failure the leak check exists for, and it
  fired. Note the divergence from the live apps here: this harness
  **records** leaks for measurement, while the desktop and Android gates
  **retry once and then suppress the bridge entirely**. A student would
  never have seen that bridge.

## The real story: two bugs the adversarial tests actually caught

Per this project's standing discipline (see the leakage-check journey
in [ai-subsystem.md](ai-subsystem.md), or the JSONArray bug in
[socratic-gate-mvp.md](socratic-gate-mvp.md)), the adversarial
checker-validation tests weren't decoration — they found two real
design mistakes before this doc's numbers were trustworthy, both fixed
in the same session, not glossed over:

**Bug 1 — the leak checker couldn't fire on short answers.** A first
version straight-ported `leakage-check/check.py`'s `NGRAM_SIZE=6`. Most
flashcard "back" fields are an enzyme name or a location — "Citrate
synthase," "Mitochondria" — under 6 words. No 6-gram could ever form, so
the overlap check was trivially empty for almost every real card,
silently passing leaks it should have caught. The adversarial test
(`adversarial_leak_in_bridge_question`, a hand-crafted bridge that
verbatim-restates the gold answer) failed against the original
implementation, exposing this immediately. Fixed: below the n-gram
threshold, check for the whole gold phrase as a contiguous run in the
bridge text instead of requiring an n-gram that structurally can't
exist.

**Bug 2 — checking the wrong fields.** After fixing bug 1, the checker
started flagging 6 of 10 *real* cards as leaks. Inspecting them showed
why: it was checking `bridge_answer` + `synthesis` for the gold phrase —
but those fields are shown *after* the student taps Reveal, and the
system prompt explicitly asks for "a synthesis connecting it back to
the card's original fact." Card 4 made this obvious: its `bridge_answer`
never mentions "citrate synthase" at all — only the synthesis does,
exactly as instructed. The check was measuring the synthesis doing its
job, not catching leaks. Fixed: only `bridge_question` is checked now,
since that's the one field that must never give away the answer before
the student has a chance to reason.

Both fixes are in `agent.py`'s `check_leak_node` docstring, not hidden
in a commit message. The end state (0/10 leaked) looks the same as if
neither bug had ever existed — the difference is this version's 0/10 is
actually measuring the right thing, and the docstring says so.

## What this does and doesn't establish

**Does establish:** a real, rerunnable retrieval + generation + two-check
pipeline, with adversarial tests that have demonstrated actual
discriminative power (not rubber-stamping) by catching two real bugs in
this same build, on real Krebs-cycle content with a real, named,
citable source.

**Does not establish:** that bridges are *grounded* on topics outside
the Krebs cycle — no curriculum source exists for those, which is
exactly why the gate declines to judge them rather than guessing. The
5 out-of-corpus cards prove the gate correctly withholds a verdict;
they prove nothing about whether those bridges are factually sound. The
honest state is "unverified", not "verified" and not "wrong".

The single biggest limitation remains the corpus itself: 14 chunks on
one topic. Every headline number here is conditional on that. Extending
`source_material.md` to more of the AAMC outline would do more for this
check's real-world value than any further refinement of the retrieval
maths.

## Reproducing this

```bash
cd speedrun/tools/socratic-agent
python run_agent.py   # real Claude API calls, ~2-3 min
```
`ANTHROPIC_API_KEY` (or `SPEEDRUN_ANTHROPIC_KEY`) must be set.
