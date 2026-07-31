# Sync test results and the conflict rule

Required by PRD §8 ("Sync") and §10's stress-test list ("the same card
reviewed on two devices offline"). Run against a real desktop client and a
real AnkiDroid emulator instance, both talking to a self-hosted
`anki-sync-server` built from this fork (`cargo install --path rslib/sync`).
Desktop was driven via `speedrun/tools/sync-test/desktop_client.py`; Android via the actual
app UI. Full request logs are reproducible by rerunning that script against
a fresh `SYNC_BASE`.

## Test 1 — 10 cards on phone offline, 10 different on desktop, reconnect

**Setup:** both clients started from an empty collection and did an initial
sync against an empty server (establishing shared lineage) before either
added anything.

1. Desktop added 10 cards (`[Desktop] Question 0-9`) offline, then synced —
   server had no cards yet, so this was a `FULL_UPLOAD`.
2. Android logged in and synced *before* adding anything — pulled desktop's
   10 cards via `FULL_DOWNLOAD`. Android now had 10 cards, matching desktop.
3. Android added its own 10 different cards (`AndroidQ0-9`) offline, then
   synced — this was a genuine incremental `NORMAL_SYNC`
   (`/sync/start → applyChanges → chunk → applyChunk → sanityCheck2 → finish`),
   confirmed via the server's request log.
4. Desktop synced again.

**Result: all 20 cards landed on both clients, no duplicates, no loss.**
Verified directly by listing every card id and front text on the desktop
side post-sync.

**One real finding from getting this wrong the first time:** the naive
version of this test — both clients independently adding cards to their own
empty collection *before ever syncing content* — does not exercise
`NORMAL_SYNC` at all. Anki's sync protocol only does incremental delta
merging once both sides share a common synced baseline; if two collections
diverge before that baseline exists, the server reports `FULL_SYNC`
required, and the caller must pick an entire side to win (see below) — nothing
merges automatically. This is why step 2 above (Android downloads before
adding anything) matters: it's not just tidiness, it's what makes the
"20 cards land" outcome possible instead of one side's 10 cards silently
replacing the other's.

## Test 2 — the same card modified on both devices while offline

**Setup:** starting from the synced 20-card baseline above:

1. Desktop reviewed `[Desktop] Question 0` and graded it **Good** (rating 3),
   without syncing.
2. Android reviewed the *same* card and graded it **Again** (rating 1),
   without syncing, and without having pulled desktop's review first.
3. Desktop synced (uploaded its Good review).
4. Android synced. This was still a `NORMAL_SYNC` — no `FULL_SYNC` fallback,
   because both sides shared the lineage from Test 1.
5. Desktop synced once more to pull Android's review back down.

**The conflict rule, empirically confirmed:**

- **The review log is append-only and never drops data.** Querying the
  card's revlog after both syncs shows **both** entries: the Good review
  (earlier timestamp) and the Again review (later timestamp). Neither
  device's review was silently discarded.
- **The card's live scheduling state (interval, queue) reflects whichever
  review has the later timestamp** — Android's Again, submitted after
  desktop's Good, is what the card's current interval/queue reflects on
  *both* clients post-sync (desktop shows `interval=0`, Android shows the
  card moved into the Learning queue — the two clients converged to the
  same state, verified independently on each side).

This matches Anki's general usn/mtime-based conflict handling and confirms
what [ARCHITECTURE.md §5](../../ARCHITECTURE.md#5-sync) predicted before this
test existed: **disjoint changes merge cleanly; the same card touched on
both sides doesn't lose data, but only the temporally-latest review decides
the card's current schedule.** An app built on this fork can recover the
losing review from the log (e.g., to flag "you reviewed this differently on
two devices" to the student) even though it doesn't win scheduling.

## What this doesn't test yet

- Media sync (both tests ran with `sync_media=False`).
- A genuine `FULL_SYNC` (both-sides-diverged) resolution — Test 1's
  narrative above describes what happens if you get the setup wrong, which
  is itself informative, but a deliberate, direction-chosen full-sync
  resolution isn't exercised here.
- Clock skew between devices (PRD §10 also asks about "a phone with a wrong
  clock going offline mid sync") — not attempted.
- More than two clients, or resyncing after an extended offline period.
