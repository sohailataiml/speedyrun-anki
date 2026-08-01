#!/usr/bin/env python3
"""Renders output/ablation_results.json (produced by run.py) plus
output/study_orders.json's topic-coverage numbers into the three-way
comparison table for speedrun/docs/brainlift.md §7 and
speedrun/docs/paraphrase-test.md.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"
STUDY_ORDERS_PATH = OUTPUT_DIR / "study_orders.json"
ABLATION_RESULTS_PATH = OUTPUT_DIR / "ablation_results.json"
REPORT_PATH = OUTPUT_DIR / "ablation_report.md"


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def pct(x: float) -> str:
    return f"{x:.0%}"


def condition_rate(items: list[dict]) -> dict:
    correct = sum(1 for i in items if i["verdict"] == "correct")
    lo, hi = wilson_interval(correct, len(items))
    return {"n": len(items), "correct": correct, "rate": correct / len(items), "ci_lo": lo, "ci_hi": hi}


def main() -> None:
    study_orders = json.loads(STUDY_ORDERS_PATH.read_text(encoding="utf-8"))
    ablation = json.loads(ABLATION_RESULTS_PATH.read_text(encoding="utf-8"))

    control = condition_rate(ablation["no_study_control"])

    build_names = [b for b in study_orders["builds"] if b != "no_study_control"]
    budgets = sorted({int(cond.split("@")[1]) for cond in ablation if "@" in cond})

    lines = [
        "# §9 ablation results",
        "",
        "**Method:** 3 builds (interleaved / blocked / unmodified Anki) x study "
        "budget, using the REAL Rust queue order per build (study_orders.json) "
        "against 30 counterfactual-renamed cards (fictional terms, so the "
        "model can't answer from real biochemistry knowledge - see "
        "counterfactualize.py). A 'student' (Claude, given only the studied "
        "cards) answers each card's verbatim front + 2 rewordings; a blind "
        "grader scores correct/partial/incorrect.",
        "",
        f"**No-study control: {control['correct']}/{control['n']} correct "
        f"({pct(control['rate'])}, 95% CI {pct(control['ci_lo'])}-"
        f"{pct(control['ci_hi'])}).** This is the contamination check: with "
        "nothing studied, the model should score at floor. "
        + ("It does - the counterfactual renaming eliminated prior-knowledge "
           "leakage." if control['rate'] < 0.10 else
           "It does NOT - some residual prior-knowledge leakage remains; "
           "treat all rates below as upper bounds, not clean measurements."),
        "",
    ]

    for budget in budgets:
        lines.append(f"## Budget = {budget} cards")
        lines.append("")
        lines.append("| Build | Topics covered | n | Correct | Rate | 95% CI |")
        lines.append("|---|---|---|---|---|---|")
        rates = {}
        for build in build_names:
            cond = f"{build}@{budget}"
            if cond not in ablation:
                continue
            items = ablation[cond]
            r = condition_rate(items)
            rates[build] = r
            topics = study_orders["builds"][build]["topics_covered_at_budget"][str(budget)]
            lines.append(
                f"| {build} | {topics} | {r['n']} | {r['correct']} | {pct(r['rate'])} | "
                f"{pct(r['ci_lo'])}-{pct(r['ci_hi'])} |"
            )
        lines.append("")
        if "interleaved" in rates and "blocked" in rates:
            gap = rates["interleaved"]["rate"] - rates["blocked"]["rate"]
            ci_overlap = rates["interleaved"]["ci_lo"] < rates["blocked"]["ci_hi"]
            lines.append(
                f"**Interleaved vs. blocked gap at budget {budget}: {pct(gap)}.** "
                + ("The 95% CIs overlap - underpowered to confidently distinguish "
                   "these conditions at this n." if ci_overlap else
                   "The 95% CIs do not overlap - a statistically distinguishable gap.")
            )
        lines.append("")

    lines.append(
        "**Limitation, stated per the project's honesty rule:** this ablation "
        "measures the effect of topic-coverage *breadth* at a fixed card "
        "budget, which is mechanically produced by the real Rust queue order "
        "- it does not measure Rohrer & Taylor's discrimination-training "
        "mechanism directly, since that operates on a human learner across "
        "repeated practice, not an LLM reading cards from a context window "
        "once. See speedrun/docs/paraphrase-test.md for the full discussion."
    )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n-> {REPORT_PATH}")


if __name__ == "__main__":
    main()
