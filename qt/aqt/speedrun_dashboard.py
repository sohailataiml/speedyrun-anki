# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Speedrun addition: the three-score dashboard (PRD §5).

Shows Memory (always available, straight from FSRS via mastery_query),
Performance (gated by give_up_gate; refuses rather than guesses), and
Readiness (not yet implemented - the Readiness mapper doesn't exist, so
this is stated plainly rather than faked). See ARCHITECTURE.md §6 for the
Scoring Service this reads from.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import anki.stats_pb2 as stats_pb2
import aqt
import aqt.main
from anki.collection import Collection
from aqt.operations import QueryOp
from aqt.qt import *
from aqt.utils import disable_help_button, restoreGeom, saveGeom, tr

TITLE = "speedrunDashboard"

# Placeholder inputs until a real exam-style question flow exists to
# measure these per attempt (PRD §8's paraphrase test, not yet built).
ASSUMED_DIFFICULTY = 0.5
ASSUMED_TIMING_SECONDS = 70.0


@dataclass
class DashboardData:
    topics: list[str]
    mastery: list[stats_pb2.TopicMastery]
    performance: stats_pb2.PerformanceQueryResponse | None


def _fetch_dashboard_data(col: Collection) -> DashboardData:
    tags = [t[len("topic::") :] for t in col.tags.all() if t.startswith("topic::")]
    topics = sorted(set(tags))
    if not topics:
        return DashboardData(topics=[], mastery=[], performance=None)
    mastery = list(col.mastery_query(topics))
    performance = col.performance_query(
        topics,
        average_difficulty=ASSUMED_DIFFICULTY,
        average_timing_seconds=ASSUMED_TIMING_SECONDS,
    )
    return DashboardData(topics=topics, mastery=mastery, performance=performance)


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
        self._layout.addWidget(self._performance_group(data.performance))
        self._layout.addWidget(self._readiness_group())
        self._add_close_row()

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
        self, performance: stats_pb2.PerformanceQueryResponse | None
    ) -> QGroupBox:
        box = QGroupBox("Performance (DOK 2/3 — held-back exam-style questions)")
        layout = QVBoxLayout()

        which = performance.WhichOneof("result") if performance else None
        if which == "data":
            data = performance.data
            layout.addWidget(
                _headline_label(f"Performance: {data.predicted_accuracy:.0%}")
            )
            layout.addWidget(
                _wrapped_label(
                    "Point estimate only — no range yet (needs the Readiness "
                    "mapper below). Assumes an average-difficulty, "
                    f"~{ASSUMED_TIMING_SECONDS:.0f}s question; not yet measured "
                    "from a real exam-style question attempt."
                )
            )
            reasons = self._top_weak_topics(data.inputs.topics)
            if reasons:
                layout.addWidget(QLabel(f"Weakest topics: {reasons}"))
            layout.addWidget(
                self._give_up_status_label(
                    data.inputs.total_graded_reviews,
                    data.inputs.topic_coverage,
                    passed=True,
                )
            )
        elif which == "insufficient":
            insufficient = performance.insufficient
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

    def _readiness_group(self) -> QGroupBox:
        box = QGroupBox("Readiness (DOK 4 — projected exam score)")
        layout = QVBoxLayout()
        layout.addWidget(
            _wrapped_label(
                "Not yet available — the Readiness mapper (Performance → MCAT "
                "scale, with a range) hasn't been built yet. This is stated "
                "plainly rather than showing a number that isn't real; see "
                "ARCHITECTURE.md §6."
            )
        )
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
