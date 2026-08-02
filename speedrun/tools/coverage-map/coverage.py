#!/usr/bin/env python3
"""Coverage map (PRD §8): every topic on the official AAMC outline, marked
covered or not, with a percentage for the dashboard.

The denominator is the real outline (speedrun/data/mcat_outline.json, 31
content categories across 3 scored science sections), not the topics that
happen to exist in the collection. That distinction is the whole point:
counting only what you already have makes coverage look like 100% no
matter how little you've studied, which is exactly the "content volume
sold as progress" failure the PRD's teardown question asks about.

A content category counts as:
  - "covered"    : at least one card exists under one of its topic tags
                   AND at least one of those cards has a graded review
  - "has_cards"  : cards exist but none have been reviewed yet
  - "uncovered"  : no cards at all

CARS is excluded from the denominator - see the outline file's
`no_outline_reason` for why, and why that exclusion is itself a stated
limitation rather than a convenience.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
OUTLINE_PATH = REPO_ROOT / "speedrun" / "data" / "mcat_outline.json"


@dataclass
class CategoryCoverage:
    category_id: str
    title: str
    section_id: str
    topic_tags: list[str]
    card_count: int = 0
    reviewed_card_count: int = 0

    @property
    def status(self) -> str:
        if self.card_count == 0:
            return "uncovered"
        if self.reviewed_card_count == 0:
            return "has_cards_unreviewed"
        return "covered"


@dataclass
class CoverageReport:
    categories: list[CategoryCoverage] = field(default_factory=list)
    excluded_sections: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.categories)

    @property
    def covered(self) -> int:
        """Categories with at least one *reviewed* card. This is the
        headline number: having made a card is not having studied it."""
        return sum(1 for c in self.categories if c.status == "covered")

    @property
    def with_content(self) -> int:
        """Categories with cards at all, reviewed or not. Reported
        alongside `covered` rather than instead of it - the gap between
        the two is the honest distance between "we built material for
        this" and "this has actually been studied", and collapsing them
        into one number is how a coverage metric gets inflated."""
        return sum(1 for c in self.categories if c.status != "uncovered")

    @property
    def percent(self) -> float:
        return (self.covered / self.total) if self.total else 0.0

    @property
    def content_percent(self) -> float:
        return (self.with_content / self.total) if self.total else 0.0

    def to_dict(self) -> dict:
        return {
            "coverage_percent": round(self.percent * 100, 1),
            "covered_categories": self.covered,
            "content_percent": round(self.content_percent * 100, 1),
            "categories_with_content": self.with_content,
            "total_categories": self.total,
            "excluded_sections": self.excluded_sections,
            "by_status": {
                status: sum(1 for c in self.categories if c.status == status)
                for status in ("covered", "has_cards_unreviewed", "uncovered")
            },
            "categories": [
                {
                    "id": c.category_id,
                    "section": c.section_id,
                    "title": c.title,
                    "status": c.status,
                    "topic_tags": c.topic_tags,
                    "cards": c.card_count,
                    "reviewed_cards": c.reviewed_card_count,
                }
                for c in self.categories
            ],
        }


def load_outline(path: Path = OUTLINE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def outline_categories(outline: dict) -> tuple[list[CategoryCoverage], list[str]]:
    """Flattens the outline into the scored denominator, plus the ids of
    sections deliberately excluded from it."""
    categories: list[CategoryCoverage] = []
    excluded: list[str] = []
    for section in outline["sections"]:
        if not section.get("has_content_outline"):
            excluded.append(section["id"])
            continue
        for concept in section["foundational_concepts"]:
            for cat in concept["content_categories"]:
                categories.append(
                    CategoryCoverage(
                        category_id=cat["id"],
                        title=cat["title"],
                        section_id=section["id"],
                        topic_tags=list(cat["topic_tags"]),
                    )
                )
    return categories, excluded


def compute_coverage(
    tag_card_counts: dict[str, int],
    tag_reviewed_counts: dict[str, int],
    outline: dict | None = None,
) -> CoverageReport:
    """Pure function over per-tag counts, so it is testable without a
    collection and reusable by both this script and the desktop
    dashboard."""
    outline = outline or load_outline()
    categories, excluded = outline_categories(outline)
    for cat in categories:
        for tag in cat.topic_tags:
            cat.card_count += tag_card_counts.get(tag, 0)
            cat.reviewed_card_count += tag_reviewed_counts.get(tag, 0)
    return CoverageReport(categories=categories, excluded_sections=excluded)


def counts_from_collection(col) -> tuple[dict[str, int], dict[str, int]]:
    """Per-`topic::` tag card counts and reviewed-card counts, read from a
    live Anki collection."""
    card_counts: dict[str, int] = {}
    reviewed_counts: dict[str, int] = {}
    for tag in col.tags.all():
        if not tag.startswith("topic::"):
            continue
        card_counts[tag] = len(col.find_cards(f'"tag:{tag}"'))
        reviewed_counts[tag] = len(col.find_cards(f'"tag:{tag}" -is:new'))
    return card_counts, reviewed_counts


def main() -> None:
    sys.path.insert(0, str(REPO_ROOT / "out" / "pylib"))
    from anki.collection import Collection  # noqa: E402

    if len(sys.argv) < 2:
        raise SystemExit(
            "usage: python coverage.py <path/to/collection.anki2>\n"
            "  (e.g. the profile collection, or a fixture from another tool)"
        )
    col_path = sys.argv[1]
    col = Collection(col_path)
    try:
        card_counts, reviewed_counts = counts_from_collection(col)
    finally:
        col.close()

    report = compute_coverage(card_counts, reviewed_counts)
    data = report.to_dict()

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "coverage_report.json").write_text(
        json.dumps({"_collection": col_path, **data}, indent=2), encoding="utf-8"
    )

    print(f"Outline denominator: {data['total_categories']} content categories")
    print(f"  (excluded sections: {', '.join(data['excluded_sections']) or 'none'})")
    print()
    for c in data["categories"]:
        if c["status"] != "uncovered":
            print(
                f"  {c['id']:4} {c['status']:22} cards={c['cards']:3} "
                f"reviewed={c['reviewed_cards']:3}  {c['title'][:55]}"
            )
    print()
    print(f"by status: {data['by_status']}")
    print(f"CONTENT built : {data['content_percent']}% "
          f"({data['categories_with_content']}/{data['total_categories']} categories have cards)")
    print(f"COVERAGE      : {data['coverage_percent']}% "
          f"({data['covered_categories']}/{data['total_categories']} have a *reviewed* card)")
    print(f"\nWrote {out_dir / 'coverage_report.json'}")


if __name__ == "__main__":
    main()
