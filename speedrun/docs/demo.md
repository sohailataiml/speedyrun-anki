# Running the demo (desktop + mobile)

How to actually run this project end to end, on both platforms, right now.
Written for whoever is recording the PRD §12 demo video, or a grader who
wants to reproduce what's claimed elsewhere in `speedrun/docs/`.

## Honest scope check first

What you can actually demo today:

- ✅ A real review session on both platforms, backed by the same Rust engine.
- ✅ The Rust change (`mastery_query`), the give-up gate, and the Performance
  model — live, via each platform's debug console (see below). No dashboard
  UI renders these yet.
- ✅ Sync, both directions, including the same-card-conflict case
  ([sync-test-results.md](sync-test-results.md)).
- ❌ **No three-score dashboard UI exists yet.** The scores are real and
  computable (see below) but nothing in the Qt or Android UI displays them —
  today's demo has to show them via each platform's console, not a screen.
- ❌ **No AI subsystem exists yet.** There is nothing to demo here.

If you're recording the actual submission video, the three-score dashboard
and AI subsystem need to exist first, or the video should honestly narrate
"scores computed here in the console; the dashboard is still open work" —
matching the project's own honesty rule rather than hiding the gap.

## Desktop

**Launch (dev mode — fastest, what to use for a demo):**
```bash
cd core
./run.bat
```
First launch after a fresh pull rebuilds the Rust backend and TS/Svelte
frontend and takes a few minutes; subsequent launches are fast.

**Or launch the packaged installer** ([desktop-installer.md](desktop-installer.md))
if you specifically want to show the clean-machine install path.

**Show a review session:** click a due card, grade it. Ordinary Anki
behavior — this is the unmodified FSRS path.

**Show the Rust change live:** `Ctrl+Shift+;` opens the Debug Console (no
menu item — keyboard shortcut only). Paste:

```python
mw.col.set_config("fsrs", True)  # memory_state only populates with FSRS on
note = mw.col.new_note(mw.col.models.by_name("Basic"))
note["Front"] = "Krebs cycle"
mw.col.add_note(note, 1)
note.tags = ["topic::krebs_cycle"]
mw.col.update_note(note)

print(mw.col.mastery_query(["krebs_cycle"]))
print(mw.col.give_up_gate(["krebs_cycle"]))
print(mw.col.performance_query(["krebs_cycle"], average_difficulty=0.5, average_timing_seconds=70.0))
```
With only one review, `give_up_gate` and `performance_query` both correctly
return `insufficient` — this is the give-up rule refusing to guess, which is
worth narrating explicitly since it's a PRD non-negotiable, not a bug.

**To show a passing gate with a real predicted score**, the collection needs
200 real graded reviews. `Ctrl+Enter` runs the current script; run this
after the block above (raises the deck's default 20/day new-card cap first,
otherwise `getCard()` returns `None` partway through):
```python
conf = mw.col.decks.config_dict_for_deck_id(1)
conf["new"]["perDay"] = 9999
mw.col.decks.save(conf)
cid = mw.col.find_cards("")[0]
while mw.col.give_up_gate(["krebs_cycle"]).WhichOneof("result") == "insufficient":
    mw.col.sched.forgetCards([cid])
    card = mw.col.sched.getCard()
    if card is None:
        break
    mw.col.sched.answerCard(card, 3)
resp = mw.col.give_up_gate(["krebs_cycle"])
print(resp)
print(mw.col.performance_query(["krebs_cycle"], average_difficulty=0.5, average_timing_seconds=70.0))
```
This lands on `give_up_gate` returning `data` (mastery ≈1.0, coverage 1.0)
and `performance_query` returning a real `predicted_accuracy` — verified to
land around 0.78 with these inputs, since higher mastery and coverage push
the model up and difficulty=0.5 is a middling input.

## Mobile (Android)

AnkiDroid, built against this fork's Rust backend
(`apps/Anki-Android-Backend`, see [rust-change-note.md](rust-change-note.md)
for the full wiring). A debug APK linked to this fork is already built at
`apps/android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-x86_64-debug.apk`.

**Start the emulator** (an AVD named `speedrun_test` already exists):
```bash
"C:/Android/sdk/emulator/emulator.exe" -avd speedrun_test
```

**Rebuild after a Rust change** (skip this if the APK above is already current):
```bash
cd apps/Anki-Android-Backend
cargo run -p build_rust     # cross-compiles rsdroid, rebuilds the AAR
cd ../android
./gradlew.bat assemblePlayDebug
```

**Install and launch:**
```bash
adb install -r apps/android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-x86_64-debug.apk
adb shell am start -n com.ichi2.anki.debug/com.ichi2.anki.IntentHandler
```

**Show a review session:** same as desktop — tap a due card, grade it.

**Show the Rust change live:** AnkiDroid doesn't ship an equivalent of
Anki desktop's Debug Console. The practical option for a demo is `adb shell`
into the app's data and drive it the same way the sync test does — see
[sync-test-results.md](sync-test-results.md) and
`speedrun/tools/sync-test/` for the actual pattern used to exercise this
fork's Rust calls against a live AnkiDroid instance. There is currently no
on-device UI surfacing `mastery_query`/`give_up_gate`/`performance_query`
results directly (same dashboard gap as desktop).

## Cross-app sync

Fully scripted and already verified twice (disjoint-cards merge,
same-card-conflict) — don't re-derive this by hand, follow
[sync-test-results.md](sync-test-results.md) and run
`speedrun/tools/sync-test/desktop_client.py` against a self-hosted
`anki-sync-server` (`cargo install --path rslib/sync`), with the Android
side driven through the app's own Sync button. That doc has the exact
sequencing gotcha (Android must download the shared baseline before
diverging) spelled out.

## Suggested demo video shot list

Mapped to what PRD §12 actually asks for, against what exists today:

1. Spiky POV, one sentence (from [brainlift.md](brainlift.md)).
2. A review session on desktop (ordinary FSRS, unmodified).
3. The Rust change live in the Debug Console — `mastery_query` →
   `give_up_gate` refusing, then passing after 200 reviews →
   `performance_query` returning a real number. Narrate that this proves the
   backend, not that it's a finished UI.
4. A review on Android, then a sync round-trip showing the card landing on
   desktop (`sync-test-results.md`'s script, or manual Sync button taps on
   both sides).
5. **Not yet available:** the three scores on an actual dashboard screen, and
   any AI feature. State this plainly rather than only showing the console.
