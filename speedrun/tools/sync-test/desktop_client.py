"""Desktop side of the sync test.

Usage:
  python sync_test_desktop.py init        # fresh collection, initial sync (baseline)
  python sync_test_desktop.py add10       # add 10 desktop-only cards (stays local)
  python sync_test_desktop.py sync        # sync with the server
  python sync_test_desktop.py count       # print card count and list
  python sync_test_desktop.py review <n>  # review the nth card (0-indexed) with rating (Again=1..Easy=4)
"""

import sys
from pathlib import Path

from anki.collection import Collection

COL_PATH = Path(r"C:\dev\speedrun\core\synctest_data\desktop\collection.anki2")
ENDPOINT = "http://127.0.0.1:8080/"
USERNAME = "testuser"
PASSWORD = "testpass123"


def get_col() -> Collection:
    COL_PATH.parent.mkdir(parents=True, exist_ok=True)
    return Collection(str(COL_PATH))


def do_sync(col: Collection, full_sync_direction: str | None = None):
    """full_sync_direction: 'upload', 'download', or None (auto: upload wins,
    only used when ChangesRequired.FULL_SYNC leaves it ambiguous)."""
    auth = col.sync_login(USERNAME, PASSWORD, ENDPOINT)
    out = col.sync_collection(auth, sync_media=False)
    required = out.required
    print(f"sync_collection result: required={required}")
    # SyncCollectionResponse.ChangesRequired: 0=NO_CHANGES 1=NORMAL_SYNC
    # 2=FULL_SYNC 3=FULL_DOWNLOAD 4=FULL_UPLOAD
    if required == 3:
        print("Full sync required: local has no cards -> downloading from server")
        col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
    elif required == 4:
        print("Full sync required: server has no cards -> uploading local")
        col.full_upload_or_download(auth=auth, server_usn=None, upload=True)
    elif required == 2:
        direction = full_sync_direction or "upload"
        print(f"Full sync required, both sides have diverged -> {direction}")
        col.full_upload_or_download(auth=auth, server_usn=None, upload=(direction == "upload"))


def cmd_init():
    col = get_col()
    print(f"Collection at {COL_PATH}, initial card count: {col.card_count()}")
    do_sync(col)
    col.close()


def cmd_add10():
    col = get_col()
    for i in range(10):
        note = col.newNote()
        note["Front"] = f"[Desktop] Question {i}"
        note["Back"] = f"[Desktop] Answer {i}"
        col.addNote(note)
    print(f"Added 10 desktop cards. Total now: {col.card_count()}")
    col.close()


def cmd_sync():
    col = get_col()
    print(f"Before sync: {col.card_count()} cards")
    do_sync(col)
    print(f"After sync: {col.card_count()} cards")
    col.close()


def cmd_count():
    col = get_col()
    print(f"Card count: {col.card_count()}")
    for cid in col.find_cards(""):
        card = col.get_card(cid)
        note = card.note()
        print(f"  {cid}: {note['Front']!r}")
    col.close()


def cmd_review(idx: int, rating: int = 3):
    col = get_col()
    cids = col.find_cards("")
    cid = cids[idx]
    card = col.get_card(cid)
    print(f"Reviewing card {cid}: {card.note()['Front']!r} with rating {rating}")
    next_card = col.sched.getCard()
    if next_card is None or next_card.id != cid:
        raise SystemExit(
            f"Expected next queued card to be {cid}, got {next_card.id if next_card else None}. "
            "Scheduler queue order doesn't match card list order - pick a different idx."
        )
    col.sched.answerCard(next_card, rating)
    col.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "count"
    if cmd == "init":
        cmd_init()
    elif cmd == "add10":
        cmd_add10()
    elif cmd == "sync":
        cmd_sync()
    elif cmd == "count":
        cmd_count()
    elif cmd == "review":
        idx = int(sys.argv[2])
        rating = int(sys.argv[3]) if len(sys.argv) > 3 else 3
        cmd_review(idx, rating)
    else:
        print(__doc__)
