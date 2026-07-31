from pathlib import Path

from anki.collection import Collection

COL_PATH = Path(r"C:\dev\speedrun\core\synctest_data\desktop\collection.anki2")
col = Collection(str(COL_PATH))

cid = 1785450968498  # "[Desktop] Question 0"
stats = col.card_stats_data(cid)
print(f"Card {cid}: interval={stats.interval} reviews={stats.reviews} lapses={stats.lapses}")
print(f"\nRevlog entries ({len(stats.revlog)}):")
for entry in stats.revlog:
    print(f"  time={entry.time} button_chosen={entry.button_chosen} review_kind={entry.review_kind}")

col.close()
