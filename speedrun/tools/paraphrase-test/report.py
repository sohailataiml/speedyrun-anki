#!/usr/bin/env python3
"""Renders sufficiency_results.json (and, if present, ablation_results.json)
into the markdown table pasted into speedrun/docs/paraphrase-test.md and
speedrun/docs/brainlift.md §7.
"""

from __future__ import annotations

import json
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"
SUFFICIENCY_PATH = OUTPUT_DIR / "sufficiency_results.json"
REPORT_PATH = OUTPUT_DIR / "paraphrase_results.md"


def pct(x: float) -> str:
    return f"{x:.0%}"


def main() -> None:
    data = json.loads(SUFFICIENCY_PATH.read_text(encoding="utf-8"))
    summary = data["summary"]
    overall, near, disc = summary["overall"], summary["near_transfer"], summary["discrimination"]

    gap = near["rate"] - disc["rate"]
    lines = [
        "# Paraphrase test — Tier 0 results (item-side card-sufficiency)",
        "",
        "**Method:** for each of 30 cards, 2 reworded exam-style questions "
        "(1 near-transfer, 1 discrimination) were generated via real Claude "
        "API calls, then a blind grader judged whether each rewording is "
        "answerable using only that card's front+back. Grading model: "
        f"`{data['grading_model']}`. No simulated student population — a "
        "direct per-item measurement of transfer distance.",
        "",
        "| Condition | n | Sufficient | Rate | 95% CI |",
        "|---|---|---|---|---|",
        f"| Overall | {overall['n']} | {overall['sufficient']} | {pct(overall['rate'])} | "
        f"{pct(overall['ci_95_low'])}–{pct(overall['ci_95_high'])} |",
        f"| Near-transfer | {near['n']} | {near['sufficient']} | {pct(near['rate'])} | "
        f"{pct(near['ci_95_low'])}–{pct(near['ci_95_high'])} |",
        f"| Discrimination | {disc['n']} | {disc['sufficient']} | {pct(disc['rate'])} | "
        f"{pct(disc['ci_95_low'])}–{pct(disc['ci_95_high'])} |",
        "",
        f"**Near-vs-discrimination gap: {pct(gap)}.**",
        "",
    ]
    if gap > 0.15:
        lines.append(
            "This is a real, non-ceiling gap: single-card recall mostly "
            "carries to differently-worded questions testing the same "
            "fact (near-transfer), but degrades meaningfully once the "
            "question requires ruling out a plausible neighboring fact "
            "(discrimination) — directionally consistent with POV 1's "
            "claim that isolated card recall and discrimination are "
            "separable skills. **This does not by itself validate the "
            "topic-interleaved review mechanism** — it measures a static "
            "property of card-vs-question distance, not what training "
            "(interleaved practice) closes the gap. See the three-way "
            "ablation (if run) for that test."
        )
    else:
        lines.append(
            "Gap is small — near-transfer and discrimination items are "
            "answered from card knowledge at similar rates. This would "
            "weigh against POV 1's premise that discrimination is a "
            "meaningfully harder, separable skill from recall."
        )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n-> {REPORT_PATH}")


if __name__ == "__main__":
    main()
