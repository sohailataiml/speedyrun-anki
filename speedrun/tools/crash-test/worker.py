#!/usr/bin/env python3
"""Runs continuously, answering cards as fast as possible against the
collection at sys.argv[1], until externally killed. This is the process
crash_test.py hard-kills at a random point - its only job is to be doing
real write work (the same col.sched.answerCard()/getCard() round trip
bench.py times) when that happens.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "out" / "pylib"))

from anki.collection import Collection  # noqa: E402


def main() -> None:
    col_path = sys.argv[1]
    col = Collection(col_path)
    card = col.sched.getCard()
    while card:
        col.sched.answerCard(card, 3)  # Good
        card = col.sched.getCard()
        if card is None:
            # Ran out of due cards before being killed - restart the
            # queue so a slow-to-arrive kill signal still lands mid-write
            # rather than the process just idling.
            col.sched.reset()
            card = col.sched.getCard()


if __name__ == "__main__":
    main()
