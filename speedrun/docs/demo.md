# Running the demo (desktop + mobile)

How to actually run this project end to end, on both platforms, right now.
Written for whoever is recording the PRD §12 demo video, or a grader who
wants to reproduce what's claimed elsewhere in `speedrun/docs/`.

## Honest scope check first

What you can actually demo today:

- ✅ A real review session on both platforms, backed by the same Rust engine.
- ✅ All three scores, live, on a real screen: `Ctrl+Shift+D` on desktop
  opens the three-score dashboard — Memory, Performance, and a projected
  MCAT score with a range and confidence label for Readiness. Also
  reachable via each platform's debug console if you want the raw protobuf
  output instead.
- ✅ Sync, both directions, including the same-card-conflict case
  ([sync-test-results.md](sync-test-results.md)).
- ❌ **No dashboard on Android yet.** Desktop's dashboard is a native PyQt
  screen that doesn't port to AnkiDroid's Kotlin/Compose UI automatically —
  Android still needs its own dashboard screen, or its scores shown via the
  console pattern in the Android section below.
- ✅ **The AI subsystem is real and run, but it's a terminal demo, not a
  screen.** `speedrun/tools/ai-cardgen/` generates real cards from a
  source document via Claude, traces each to its source chunk, and beats
  a keyword-extraction baseline 98% to 0% on the gold-set eval — see
  [ai-subsystem.md](ai-subsystem.md) for the full numbers. It isn't wired
  into the desktop app UI (no "generate cards" button exists), so
  demoing it means running the scripts and showing the output, not
  clicking through the app.

If you're recording the actual submission video, an Android dashboard is
the main piece still worth finishing — or the video should honestly
narrate what's console/terminal-only vs on-screen, matching the project's
own honesty rule rather than hiding the gap.

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

**Show the three-score dashboard:** `Ctrl+Shift+D` (no menu item —
keyboard shortcut only, same as the Debug Console below). Shows Memory,
Performance, and Readiness (projected MCAT score, range, confidence label,
and the mapper's stated method) for every `topic::<name>` tag in the
collection, computed live. This is the better shot for a demo video than
the console dump below — it's an actual screen.

**Show the Rust change via console** (for the raw protobuf output instead
of the dashboard's formatted view): `Ctrl+Shift+;` opens the Debug Console
(no menu item — keyboard shortcut only). Paste:

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
3. `Ctrl+Shift+D` — the three-score dashboard, ideally after the 200-review
   loop so it shows a real passing gate, a real Performance number, and a
   real projected MCAT score with a range, not just a refusal. This is the
   strongest shot in the whole demo: it's a real screen, not console output.
4. A review on Android, then a sync round-trip showing the card landing on
   desktop (`sync-test-results.md`'s script, or manual Sync button taps on
   both sides).
5. Run `speedrun/tools/ai-cardgen/eval.py`'s output (or just show
   `ai-subsystem.md`'s results table) — real generated cards with source
   provenance, beating the baseline 98% to 0%. Narrate that this is a
   terminal/report demo, not an in-app button, since there's no
   "generate cards" UI yet.
6. **Not yet available:** an Android dashboard. State this plainly rather
   than hiding it.
