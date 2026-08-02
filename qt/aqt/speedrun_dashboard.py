# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Speedrun addition: the three-score dashboard (PRD §5).

Shows Memory (always available, straight from FSRS via mastery_query),
Performance and Readiness (both gated by give_up_gate; refuse rather than
guess when there isn't enough data). See ARCHITECTURE.md §6 for the
Scoring Service this reads from.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import anki.stats_pb2 as stats_pb2
import aqt
import aqt.main
from anki.collection import Collection
from aqt.operations import QueryOp
from aqt.qt import *
from aqt.utils import disable_help_button, restoreGeom, saveGeom, tr

TITLE = "speedrunDashboard"

# Placeholder inputs until a real exam-style question flow exists to
# measure these per attempt. The paraphrase test (speedrun/tools/
# paraphrase-test/) measures accuracy for its own ablation purposes but
# doesn't feed live per-attempt difficulty/timing back into this dashboard.
ASSUMED_DIFFICULTY = 0.5
ASSUMED_TIMING_SECONDS = 70.0


@dataclass
class DashboardData:
    topics: list[str]
    mastery: list[stats_pb2.TopicMastery]
    readiness: stats_pb2.ReadinessQueryResponse | None
    # PRD §8's coverage map: measured against the real AAMC outline, not
    # against the topics that happen to exist in this collection. None if
    # the outline file couldn't be read.
    outline_coverage: dict | None = None


def _fetch_outline_coverage(col: Collection) -> dict | None:
    """Coverage against the official AAMC content outline.

    Deliberately computed here rather than by the Rust `give_up_gate`'s
    `topic_coverage`, which measures a different (and much easier) thing:
    the proportion of the *requested* topics that have a review. That
    number trends to 100% as you study whatever you already have, and
    says nothing about the exam. This one uses the full 31-category
    outline as the denominator, so unstudied sections count against you.
    See speedrun/docs/coverage-map.md for why both still exist.
    """
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "speedrun" / "tools" / "coverage-map"))
        from coverage import compute_coverage, counts_from_collection

        card_counts, reviewed_counts = counts_from_collection(col)
        return compute_coverage(card_counts, reviewed_counts).to_dict()
    except Exception:
        # The dashboard must still render its other two scores if the
        # outline file is missing (e.g. a packaged build that doesn't
        # bundle speedrun/) - same degrade-don't-crash rule as the rest
        # of this project.
        return None


def _fetch_dashboard_data(col: Collection) -> DashboardData:
    tags = [t[len("topic::") :] for t in col.tags.all() if t.startswith("topic::")]
    topics = sorted(set(tags))
    coverage = _fetch_outline_coverage(col)
    if not topics:
        return DashboardData(topics=[], mastery=[], readiness=None, outline_coverage=coverage)
    mastery = list(col.mastery_query(topics))
    # readiness_query runs the give-up gate and Performance model
    # internally, so one call gets us all three scores' worth of data.
    readiness = col.readiness_query(
        topics,
        average_difficulty=ASSUMED_DIFFICULTY,
        average_timing_seconds=ASSUMED_TIMING_SECONDS,
    )
    return DashboardData(
        topics=topics, mastery=mastery, readiness=readiness, outline_coverage=coverage
    )


def _headline_label(text: str) -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setPointSize(font.pointSize() + 3)
    font.setBold(True)
    label.setFont(font)
    return label


def _wrapped_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    return label


def show_speedrun_dashboard(mw: aqt.main.AnkiQt) -> None:
    diag = SpeedrunDashboard(mw)
    diag.show()


class SpeedrunDashboard(QDialog):
    silentlyClose = True

    def __init__(self, mw: aqt.main.AnkiQt) -> None:
        super().__init__(mw, Qt.WindowType.Window)
        self.mw = mw
        self.mw.garbage_collect_on_dialog_finish(self)
        self.setWindowTitle("Speedrun — three scores")
        self.setMinimumSize(640, 480)
        disable_help_button(self)
        restoreGeom(self, TITLE)

        self._layout = QVBoxLayout()
        self._layout.addWidget(QLabel("Loading…"))
        self.setLayout(self._layout)

        self._refresh()

    def _refresh(self) -> None:
        QueryOp(
            parent=self,
            op=_fetch_dashboard_data,
            success=self._render,
        ).run_in_background()

    def _clear_layout(self) -> None:
        while (item := self._layout.takeAt(0)) is not None:
            if widget := item.widget():
                widget.deleteLater()

    def _render(self, data: DashboardData) -> None:
        self._clear_layout()

        if not data.topics:
            self._layout.addWidget(
                _wrapped_label(
                    "No topics tagged yet. Add a topic::<name> tag to a card's "
                    "note to see scores here."
                )
            )
            self._add_close_row()
            return

        self._layout.addWidget(self._memory_group(data.mastery))
        self._layout.addWidget(self._performance_group(data.readiness))
        self._layout.addWidget(
            self._readiness_group(data.readiness, data.outline_coverage)
        )
        self._layout.addWidget(self._coverage_group(data.outline_coverage))
        self._add_close_row()

    def _coverage_group(self, coverage: dict | None) -> QGroupBox:
        """PRD §8's coverage map, measured against the real AAMC outline.

        Shown as its own panel rather than folded into Readiness because
        it answers a different question: not "how ready are you on what
        you've studied" but "how much of the exam have you touched at
        all". A high Memory score on 10% coverage is exactly the
        "content volume sold as progress" failure the Brainlift's
        teardown calls out, and burying this number would reproduce it.
        """
        box = QGroupBox("Coverage map (AAMC content outline)")
        layout = QVBoxLayout()
        if not coverage:
            layout.addWidget(
                _wrapped_label(
                    "Coverage unavailable — speedrun/data/mcat_outline.json "
                    "could not be read. The other scores are unaffected."
                )
            )
            box.setLayout(layout)
            return box

        pct = coverage["coverage_percent"]
        covered = coverage["covered_categories"]
        total = coverage["total_categories"]
        by_status = coverage["by_status"]
        layout.addWidget(_headline_label(f"Coverage: {pct}%"))
        layout.addWidget(
            _wrapped_label(
                f"{covered} of {total} content categories have at least one "
                f"reviewed card. {by_status['has_cards_unreviewed']} more have "
                f"cards but no reviews yet; {by_status['uncovered']} have no "
                "cards at all."
            )
        )
        studied = [
            c for c in coverage["categories"] if c["status"] != "uncovered"
        ]
        if studied:
            lines = "\n".join(
                f"  {c['id']} — {c['title'][:60]} "
                f"({c['cards']} cards, {c['reviewed_cards']} reviewed)"
                for c in studied
            )
            layout.addWidget(_wrapped_label(f"Touched so far:\n{lines}"))
        layout.addWidget(
            _wrapped_label(
                "Denominator is the official outline, not the tags in this "
                "collection — unstudied sections count against you. CARS is "
                "excluded: it has no memorizable content outline, so a "
                "flashcard deck structurally can't cover it. That means even "
                "100% here would leave a quarter of the exam unmeasured."
            )
        )
        box.setLayout(layout)
        return box

    def _memory_group(self, mastery: list[stats_pb2.TopicMastery]) -> QGroupBox:
        with_reviews = [t for t in mastery if t.cards_with_reviews > 0]
        overall = (
            sum(t.mastery for t in with_reviews) / len(with_reviews)
            if with_reviews
            else None
        )
        headline = (
            f"Memory: {overall:.0%}"
            if overall is not None
            else "Memory: no reviewed cards yet"
        )

        box = QGroupBox("Memory (DOK 1 — FSRS recall probability)")
        layout = QVBoxLayout()
        layout.addWidget(_headline_label(headline))

        table = QTableWidget(len(mastery), 4)
        table.setHorizontalHeaderLabels(
            ["Topic", "Mastery", "Avg recall", "Reviewed / total"]
        )
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for row, topic in enumerate(mastery):
            table.setItem(row, 0, QTableWidgetItem(topic.topic))
            mastery_text = (
                f"{topic.mastery:.0%}" if topic.cards_with_reviews else "—"
            )
            table.setItem(row, 1, QTableWidgetItem(mastery_text))
            recall_text = (
                f"{topic.average_recall:.0%}" if topic.cards_with_reviews else "—"
            )
            table.setItem(row, 2, QTableWidgetItem(recall_text))
            table.setItem(
                row,
                3,
                QTableWidgetItem(f"{topic.cards_with_reviews} / {topic.cards_total}"),
            )
        table.horizontalHeader().setStretchLastSection(True)
        table.resizeColumnsToContents()
        layout.addWidget(table)
        box.setLayout(layout)
        return box

    def _performance_group(
        self, readiness: stats_pb2.ReadinessQueryResponse | None
    ) -> QGroupBox:
        box = QGroupBox("Performance (DOK 2/3 — held-back exam-style questions)")
        layout = QVBoxLayout()

        which = readiness.WhichOneof("result") if readiness else None
        if which == "data":
            performance = readiness.data.inputs
            layout.addWidget(
                _headline_label(f"Performance: {performance.predicted_accuracy:.0%}")
            )
            layout.addWidget(
                _wrapped_label(
                    "Point estimate feeding the Readiness score below. Assumes "
                    "an average-difficulty, "
                    f"~{ASSUMED_TIMING_SECONDS:.0f}s question; not yet measured "
                    "from a real exam-style question attempt."
                )
            )
            reasons = self._top_weak_topics(performance.inputs.topics)
            if reasons:
                layout.addWidget(QLabel(f"Weakest topics: {reasons}"))
            layout.addWidget(
                self._give_up_status_label(
                    performance.inputs.total_graded_reviews,
                    performance.inputs.topic_coverage,
                    passed=True,
                )
            )
        elif which == "insufficient":
            insufficient = readiness.insufficient
            layout.addWidget(
                _headline_label("Performance: refusing to score — not enough data")
            )
            layout.addWidget(
                self._give_up_status_label(
                    insufficient.total_graded_reviews,
                    insufficient.topic_coverage,
                    passed=False,
                    reviews_required=insufficient.reviews_required,
                    coverage_required=insufficient.coverage_required,
                )
            )
        else:
            layout.addWidget(QLabel("Performance: unavailable"))

        box.setLayout(layout)
        return box

    def _outline_coverage_caveat(self, coverage: dict | None) -> QLabel | None:
        """Warn when the give-up gate passed on its easier measure while
        real outline coverage is far lower.

        This is not decoration. The gate's `topic_coverage` counts the
        proportion of *requested* topics with a review, which on this
        collection reads ~67% while genuine coverage of the AAMC outline
        is under 10%. Emitting a projected score on that basis without
        saying so is close to the PRD's automatic-fail line ("dressing a
        guess as a measurement"), so the gap is stated on the same panel
        as the number it undercuts. Fixing the gate itself needs the
        outline in Rust — see speedrun/docs/coverage-map.md.
        """
        if not coverage:
            return None
        pct = coverage["coverage_percent"]
        if pct >= 50.0:
            return None
        label = _wrapped_label(
            f"⚠ Read this number with the coverage map: only {pct}% of the "
            f"official AAMC outline "
            f"({coverage['covered_categories']}/{coverage['total_categories']} "
            "content categories) has any reviewed card. The give-up rule "
            "above passed on a different, easier measure — the share of "
            "the topics you already have cards for — which says nothing "
            "about the rest of the exam. Treat this projection as an "
            "estimate over a small slice, not a whole-exam prediction."
        )
        label.setStyleSheet("color: darkorange;")
        return label

    def _readiness_group(
        self,
        readiness: stats_pb2.ReadinessQueryResponse | None,
        outline_coverage: dict | None = None,
    ) -> QGroupBox:
        box = QGroupBox("Readiness (DOK 4 — projected exam score)")
        layout = QVBoxLayout()

        which = readiness.WhichOneof("result") if readiness else None
        if which == "data":
            data = readiness.data
            confidence_name = stats_pb2.ReadinessData.Confidence.Name(
                data.confidence
            ).capitalize()
            layout.addWidget(
                _headline_label(f"Projected MCAT: {data.projected_score}")
            )
            layout.addWidget(
                _wrapped_label(
                    f"Likely range {data.range_low} to {data.range_high}. "
                    f"Confidence: {confidence_name}, based on graded-review "
                    "count and topic coverage."
                )
            )
            layout.addWidget(
                _wrapped_label(
                    "Method: treats predicted accuracy as an approximate "
                    "population percentile against AAMC's published MCAT "
                    "score distribution (mean 500.5, SD ~10.6) — a stated "
                    "simplifying assumption, not validated against real "
                    "student outcomes. See rslib/src/stats/readiness_mapper.rs."
                )
            )
            caveat = self._outline_coverage_caveat(outline_coverage)
            if caveat is not None:
                layout.addWidget(caveat)
        elif which == "insufficient":
            layout.addWidget(
                _headline_label("Readiness: refusing to score — not enough data")
            )
        else:
            layout.addWidget(QLabel("Readiness: unavailable"))

        box.setLayout(layout)
        return box

    def _top_weak_topics(
        self, topics: list[stats_pb2.TopicMastery], limit: int = 2
    ) -> str:
        reviewed = [t for t in topics if t.cards_with_reviews > 0]
        weakest = sorted(reviewed, key=lambda t: t.mastery)[:limit]
        return ", ".join(f"{t.topic} ({t.mastery:.0%})" for t in weakest)

    def _give_up_status_label(
        self,
        total_graded_reviews: int,
        topic_coverage: float,
        passed: bool,
        reviews_required: int = 200,
        coverage_required: float = 0.5,
    ) -> QLabel:
        mark = "✓" if passed else "✗"
        text = (
            f"{mark} Give-up rule: {total_graded_reviews} / {reviews_required} "
            f"graded reviews · {topic_coverage:.0%} / {coverage_required:.0%} "
            "topic coverage"
        )
        label = QLabel(text)
        label.setStyleSheet("color: green;" if passed else "color: darkorange;")
        return label

    def _add_close_row(self) -> None:
        row = QHBoxLayout()
        refresh = QPushButton("Refresh")
        qconnect(refresh.clicked, self._refresh)
        row.addWidget(refresh)
        row.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        qconnect(buttons.rejected, self.close)
        row.addWidget(buttons)

        footer = QLabel(f"Last updated {datetime.now().strftime('%H:%M:%S')}")
        footer.setStyleSheet("color: gray;")
        self._layout.addWidget(footer)
        self._layout.addLayout(row)

    def closeEvent(self, event: QCloseEvent | None) -> None:  # noqa: N802
        saveGeom(self, TITLE)
        super().closeEvent(event)
