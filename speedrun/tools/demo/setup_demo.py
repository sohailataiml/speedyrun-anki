"""Builds two throwaway Anki profiles for demoing the v3 thesis.

Neither touches your real collection. Anki reads its base folder from the
ANKI_BASE environment variable, so each profile is just a directory:

    demo-rote     a student who spacebar-reflexed through the deck
                  -> the app REFUSES to score
    demo-honest   a student who mostly thinks, sometimes taps through,
                  and has answered transfer variants
                  -> the app scores, then marks the score down

Usage:
    python setup_demo.py <output-dir>

Then launch each with:
    ANKI_BASE=<output-dir>/demo-rote ./run.bat
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
REPO = TOOLS.parent.parent
sys.path.insert(0, str(REPO / "out" / "pylib"))

from anki.collection import Collection  # noqa: E402

JITTER_JSONL = TOOLS / "ai-jitter" / "output" / "jitter_cards.jsonl"
# Varied and comfortably above a long variant's minimum reading time.
# Identical latencies here would - correctly - make these topics register
# as rote and refuse the whole score, which is not what this profile is
# meant to show.
JITTER_LATENCIES_MS = [7200, 15000, 9500, 22000, 11000, 18000]


def make_profile(base: Path, source: Path) -> Path:
    profile = base / "User 1"
    profile.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, profile / "collection.anki2")
    for stale in ("collection.anki2-wal", "collection.anki2-journal"):
        (profile / stale).unlink(missing_ok=True)
    return base


def add_jitter_attempts(col_path: Path) -> None:
    """Gives the honest profile answered transfer variants, so jitter
    accuracy has something to report."""
    if not JITTER_JSONL.exists():
        print(f"  (no {JITTER_JSONL.name}; skipping jitter cards)")
        return
    records = [
        json.loads(line)
        for line in JITTER_JSONL.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    col = Collection(str(col_path))
    deck = col.decks.id("Speedrun::Jitter")
    basic = col.models.by_name("Basic")
    now = int(time.time() * 1000)
    for i, rec in enumerate(records):
        note = col.new_note(basic)
        note["Front"] = rec["front"]
        note["Back"] = rec["back"]
        note.tags = [f"jitter::src::{rec['source_nid']}"]
        if rec.get("topic"):
            note.tags.append(rec["topic"])
        col.add_note(note, deck)
        cid = col.card_ids_of_note(note.id)[0]
        for k in range(6):
            ease = 1 if (i < 2 and k % 3 == 0) else 3
            col.db.execute(
                "insert into revlog (id,cid,usn,ease,ivl,lastIvl,factor,time,type)"
                " values (?,?,-1,?,1,1,2500,?,1)",
                now + i * 10_000 + k * 100,
                cid,
                ease,
                JITTER_LATENCIES_MS[k],
            )
    col.save()
    col.close()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    gen = TOOLS / "rote-demo" / "make_rote_collection.py"
    tmp = out / "_build"
    tmp.mkdir(exist_ok=True)

    rote_src = tmp / "rote.anki2"
    honest_src = tmp / "honest.anki2"
    subprocess.run([sys.executable, str(gen), str(rote_src)], check=True)
    subprocess.run([sys.executable, str(gen), str(honest_src), "--mixed"], check=True)

    make_profile(out / "demo-rote", rote_src)
    honest_base = make_profile(out / "demo-honest", honest_src)
    add_jitter_attempts(honest_base / "User 1" / "collection.anki2")
    shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("Demo profiles ready. Your real collection is untouched.\n")
    print("  REFUSAL demo (rote pattern detected):")
    print(f'    ANKI_BASE="{out / "demo-rote"}" ./run.bat\n')
    print("  SCORED demo (transfer accuracy + spacebar-reflex markdown):")
    print(f'    ANKI_BASE="{out / "demo-honest"}" ./run.bat\n')
    print("  Then press Ctrl+Shift+D for the Speedrun dashboard.")


if __name__ == "__main__":
    main()
