"""Generates jitter variants for real cards and reports how many survive
the quality gates.

Writes JSONL (accepted variants) and a human-readable report. Nothing is
written into a collection — see `import_jitter.py` for that, which is a
separate, deliberate step.

Usage:
    python run_jitter.py <collection.anki2> [--limit N] [--tag topic::x]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "out" / "pylib"))
sys.path.insert(0, str(Path(__file__).parent))

import jitter  # noqa: E402
from anki.collection import Collection  # noqa: E402

OUT_DIR = Path(__file__).parent / "output"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("collection")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--search", default="tag:topic::*")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY not set")

    OUT_DIR.mkdir(exist_ok=True)
    col = Collection(args.collection)

    cards = []
    for cid in col.find_cards(args.search)[: args.limit * 3]:
        card = col.get_card(cid)
        note = card.note()
        front = jitter.grounding.strip_html(note.fields[0])
        back = jitter.grounding.strip_html(note.fields[1]) if len(note.fields) > 1 else ""
        if not front or not back:
            continue
        topic = next(
            (t for t in note.tags if t.startswith("topic::")), None
        )
        cards.append({"nid": note.id, "front": front, "back": back, "topic": topic})
        if len(cards) >= args.limit:
            break
    col.close()

    accepted, rejected = [], []
    for i, card in enumerate(cards, 1):
        print(f"[{i}/{len(cards)}] {card['front'][:60]}")
        try:
            variant = jitter.generate_variant(api_key, card["front"], card["back"])
            verdict = jitter.evaluate_variant(
                api_key, card["front"], card["back"], variant
            )
        except Exception as exc:  # noqa: BLE001
            print(f"    ERROR {type(exc).__name__}: {exc}")
            rejected.append({**card, "error": f"{type(exc).__name__}: {exc}"})
            continue

        record = {
            "source_nid": card["nid"],
            "topic": card["topic"],
            "original_front": card["front"],
            "original_back": card["back"],
            "front": variant["front"],
            "back": variant["back"],
            "shifted": variant.get("shifted", ""),
            "term_reuse": round(verdict.term_reuse, 3),
            "same_principle": verdict.same_principle,
            "new_situation": verdict.new_situation,
            "grounded": verdict.grounded,
            "judge_reasoning": verdict.judge_reasoning,
            "method": "ai_jitter",
            "model": jitter.MODEL,
        }
        if verdict.accepted:
            accepted.append(record)
            print(f"    ACCEPTED  reuse={verdict.term_reuse:.0%}  "
                  f"shifted: {variant.get('shifted','')}")
        else:
            record["rejections"] = verdict.rejections
            rejected.append(record)
            print(f"    REJECTED  {'; '.join(verdict.rejections)}")

    (OUT_DIR / "jitter_cards.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in accepted) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "jitter_rejected.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rejected) + "\n",
        encoding="utf-8",
    )

    total = len(accepted) + len(rejected)
    print(f"\n{'='*66}")
    print(f"accepted {len(accepted)}/{total}   rejected {len(rejected)}/{total}")
    reasons: dict[str, int] = {}
    for r in rejected:
        for reason in r.get("rejections", [r.get("error", "unknown")]):
            key = reason.split(":")[0]
            reasons[key] = reasons.get(key, 0) + 1
    if reasons:
        print("rejection reasons:")
        for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"  {v:>3}  {k}")
    print(f"\nwrote {OUT_DIR / 'jitter_cards.jsonl'}")


if __name__ == "__main__":
    main()
