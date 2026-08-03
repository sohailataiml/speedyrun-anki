"""The AI Jitter Engine (Brainlift v3, POV 3).

> *"AI should only be used to Jitter (Re-contextualise) the card to prove
> the logic holds in a new scenario."*

A jitter variant takes a card and moves the *same underlying principle*
into a *different concrete situation* — new patient, new organism, new
units, new experimental setup. The point is Tulving's encoding
specificity: a fact welded to one card's phrasing may not survive
transfer to an MCAT passage, and the only way to find out is to ask it
somewhere else.

## The two-sided quality problem

A variant can fail in opposite directions, and catching only one of them
is worse than useless:

- **Too similar** → it's a paraphrase. Answering it proves nothing the
  original didn't already prove, but it *looks* like transfer evidence,
  so it would inflate the Performance score with recall dressed up as
  reasoning. This is the failure the brainlift's POV 3 is actually about.
- **Too different** → it tests some other fact entirely. Accuracy on it
  says nothing about whether the student knows the original, so feeding
  it into a per-topic score is just noise.

Both bounds are enforced, but by **different kinds of check**, and that
split was learned the hard way (see `MAX_TERM_REUSE`):

- *Too similar* is a question about **vocabulary**, so a cheap
  deterministic measure answers it — and answers it before any judge call
  is spent.
- *Too different* is a question about **meaning**, which no lexical
  measure can answer. It belongs to the LLM judge's `SAME_PRINCIPLE`
  check. An early lexical floor here rejected four good variants out of
  ten before being removed.

Plus the two checks inherited from the retired Socratic work: curriculum
grounding, and answer leakage.

Nothing here writes to a collection. It emits JSONL for review, exactly
like `ai-cardgen/generate.py`, because a generator that silently injects
cards into a study deck is not something you can audit after the fact.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "qt" / "aqt"))

import speedrun_grounding as grounding  # noqa: E402

MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"

# Above this, the variant reuses so much of the original's wording that
# it cannot be testing anything new.
#
# There is deliberately NO lower bound. The first version had one, and it
# was wrong in a way worth recording: it used symmetric Jaccard, which is
# length-sensitive, so a four-word original ("Cell organelle responsible
# for protein synthesis") against a rich clinical vignette scored 0.06
# and was rejected as "unrelated" - even though the judge marked it both
# same-principle and new-situation. Four of ten variants were thrown away
# that way, and every one of them was good. Symmetric similarity punishes
# exactly the asymmetry jitter is *supposed* to produce: short prompt in,
# rich scenario out. (The same mistake, in the same shape, as the cosine
# similarity that once broke curriculum retrieval in this project.)
#
# Two fixes, both load-bearing:
#   1. The measure is now asymmetric - what fraction of the ORIGINAL's
#      terms the variant reuses - so variant length cannot drag it down.
#   2. The floor is gone entirely. "Too different" is a question about
#      meaning, not vocabulary, and the judge's SAME_PRINCIPLE check
#      already answers it properly. A lexical floor was a worse proxy for
#      a question something else was already answering correctly.
MAX_TERM_REUSE = 0.60

JITTER_SYSTEM_PROMPT = (
    "You re-contextualise MCAT flashcards for a study app. Given one "
    "card (front/back), write ONE variant that tests the SAME underlying "
    "principle in a DIFFERENT concrete situation.\n\n"
    "Rules:\n"
    "1. Change the scenario: different organism, tissue, patient, "
    "experimental setup, or numbers. The surface story must be new.\n"
    "2. Keep the principle identical. A student who understands the "
    "original should be able to reason to your variant's answer; a "
    "student who only memorised the original's wording should not.\n"
    "3. Do NOT simply reword the original question. If your variant "
    "could be answered by pattern-matching the original's phrasing, it "
    "is wrong.\n"
    "4. Do NOT introduce facts beyond the original card's principle and "
    "standard background knowledge.\n"
    "5. The variant's question must not contain its own answer.\n\n"
    "Respond with a JSON object and nothing else:\n"
    '{"front": "...", "back": "...", "shifted": "<one phrase naming what '
    'you changed about the scenario>"}'
)

JUDGE_SYSTEM_PROMPT = (
    "You audit re-contextualised MCAT flashcards. You will see an "
    "ORIGINAL card and a VARIANT. Decide two things independently.\n\n"
    "SAME_PRINCIPLE: does answering the variant correctly require the "
    "same underlying principle as the original? Answer no if the variant "
    "tests a different fact, even a related one.\n\n"
    "NEW_SITUATION: is the variant set in a genuinely different concrete "
    "situation, such that a student who had memorised the original's "
    "wording without understanding it would NOT be able to answer? "
    "Answer no if the variant is the original reworded, or merely has "
    "synonyms swapped in.\n\n"
    "Respond in exactly this format, nothing else:\n"
    "SAME_PRINCIPLE: <yes or no>\n"
    "NEW_SITUATION: <yes or no>\n"
    "REASONING: <one or two sentences>"
)

JUDGE_RE = re.compile(
    r"SAME_PRINCIPLE:\s*(yes|no)\s*\nNEW_SITUATION:\s*(yes|no)\s*\nREASONING:\s*(.+)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class JitterVerdict:
    """Why a variant was accepted or rejected. Every gate's result is
    recorded even when an earlier one already failed, so a rejection can
    be read back without re-running the generator."""

    accepted: bool
    rejections: list[str] = field(default_factory=list)
    term_reuse: float = 0.0
    same_principle: bool | None = None
    new_situation: bool | None = None
    grounded: bool | None = None
    leaked: bool = False
    judge_reasoning: str = ""


def _call(api_key: str, system: str, user: str, max_tokens: int = 800) -> str:
    payload = json.dumps(
        {
            "model": MODEL,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "temperature": 0.7,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = json.loads(response.read())
    text = body["content"][0]["text"].strip()
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text)


def term_reuse(original_front: str, variant_front: str) -> float:
    """What fraction of the ORIGINAL question's content terms the variant
    reuses. 1.0 means the variant kept every distinctive word.

    Asymmetric on purpose: the denominator is the original alone, so a
    long, scenario-rich variant is not penalised for being long. That is
    the whole point of the rewrite described at MAX_TERM_REUSE.

    Measured on the *questions only*. Two cards testing one principle
    should converge on a similar answer - that is a jitter variant
    working, not evidence of laziness. It is the question's scenario that
    has to move.
    """
    a = grounding.content_terms(original_front)
    b = grounding.content_terms(variant_front)
    if not a:
        return 0.0
    return len(a & b) / len(a)


def generate_variant(api_key: str, front: str, back: str) -> dict:
    user = f"Original card front: {front}\nOriginal card back: {back}"
    return json.loads(_call(api_key, JITTER_SYSTEM_PROMPT, user))


def judge_variant(
    api_key: str, front: str, back: str, v_front: str, v_back: str
) -> tuple[bool, bool, str]:
    user = (
        f"ORIGINAL\nfront: {front}\nback: {back}\n\n"
        f"VARIANT\nfront: {v_front}\nback: {v_back}"
    )
    text = _call(api_key, JUDGE_SYSTEM_PROMPT, user, max_tokens=300)
    match = JUDGE_RE.search(text)
    if not match:
        raise ValueError(f"unparseable judge response: {text!r}")
    return (
        match.group(1).lower() == "yes",
        match.group(2).lower() == "yes",
        match.group(3).strip(),
    )


def evaluate_variant(
    api_key: str, front: str, back: str, variant: dict
) -> JitterVerdict:
    """Runs all four gates. Cheap, deterministic checks first so an
    obvious paraphrase costs one API call rather than two."""
    v_front = variant["front"]
    v_back = variant["back"]
    verdict = JitterVerdict(accepted=True)

    verdict.term_reuse = term_reuse(front, v_front)
    if verdict.term_reuse > MAX_TERM_REUSE:
        verdict.rejections.append(
            f"paraphrase: reuses {verdict.term_reuse:.0%} of the original's "
            f"terms (max {MAX_TERM_REUSE:.0%})"
        )

    # The variant's question must not hand over its own answer. Reuses
    # the leak checker written for the retired Socratic bridge - same
    # failure, different feature.
    verdict.leaked = grounding.leaks_answer(v_front, v_back)
    if verdict.leaked:
        verdict.rejections.append("variant question contains its own answer")

    same, new, reasoning = judge_variant(api_key, front, back, v_front, v_back)
    verdict.same_principle = same
    verdict.new_situation = new
    verdict.judge_reasoning = reasoning
    if not same:
        verdict.rejections.append("judge: tests a different principle")
    if not new:
        verdict.rejections.append("judge: not a genuinely new situation")

    # Grounding is reported, never enforced: the corpus covers six topics,
    # so making it a hard gate would silently kill variants on every
    # other topic. Same soft-signal discipline as the retired bridge.
    g = grounding.verify_grounding(api_key, v_front, v_back, f"{v_front} {v_back}")
    verdict.grounded = g.grounded
    if g.grounded is False:
        verdict.rejections.append("not grounded in the curriculum corpus")

    verdict.accepted = not verdict.rejections
    return verdict
