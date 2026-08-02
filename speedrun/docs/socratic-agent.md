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

Code: `speedrun/tools/socratic-agent/`. Not wired into the live apps —
this validates the approach standalone first, the same pattern this
project uses everywhere else (paraphrase-test, socratic-gate's own MVP
ablation) before considering whether to wire something into the review
flow.

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

- **`retrieve_node`** — TF-IDF cosine similarity (`retrieval.py`, via
  sklearn) over the 14 chunks of `speedrun/ai/source_material.md`, no
  vector DB, no persisted index, no embeddings API. Fit fresh in-memory
  on every call. For a 14-chunk, single-document corpus, a vector DB
  would be solving a scale problem this corpus doesn't have.
- **`generate_node`** — the same Claude call, same prompt, as the live
  `_generate_bridge()`/`generateBridge()`.
- **`check_grounded_node`** — a second Claude call (LLM-as-judge, same
  methodology this project already uses for grading in paraphrase-test
  and the ai-cardgen eval): given the bridge and the retrieved passages,
  is the bridge's factual content actually supported by them?
- **`check_leak_node`** — local, no API call. Checks whether the gold
  answer's phrasing shows up in the bridge *question* specifically (see
  below for why not the answer/synthesis too).

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

| | n | Result |
|---|---|---|
| Bridges judged grounded in the retrieved source | 10/10 | 100% |
| Bridges that leaked the gold answer in the question | 0/10 | 0% |
| Retrievals that hit the card's actual source chunk | 9/10 | 90% |
| Adversarial checker-validation cases | 3/3 | all passed |

The one retrieval miss (card 10, "how many times does the cycle turn
per glucose") is a defensible near-miss, not a bug: that fact is stated
in both kc-11 and kc-14, and TF-IDF ranked kc-11 higher — a reasonable
call, not a wrong one.

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

**Does not establish:** that bridges are grounded/leak-free across the
full range of topics this session tested live (glycolysis, cell
biology, endocrine, gas laws, neuromuscular) — no curriculum source
exists for those yet. Also doesn't establish this is wired into the
live review flow — it isn't; see the top of this doc for why that's a
deliberate, stated scoping choice, not an oversight.

## Reproducing this

```bash
cd speedrun/tools/socratic-agent
python run_agent.py   # real Claude API calls, ~2-3 min
```
`ANTHROPIC_API_KEY` (or `SPEEDRUN_ANTHROPIC_KEY`) must be set.
