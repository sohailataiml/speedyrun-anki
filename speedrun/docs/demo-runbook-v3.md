# Quick demo runbook (Brainlift v3)

Five minutes, four beats, neither of which touches your real collection.

## One-time setup

```bash
cd C:/dev/speedrun/core
out/pyenv/Scripts/python speedrun/tools/demo/setup_demo.py C:/dev/speedrun/demo
```

Builds two throwaway profiles. Anki takes its base folder from
`ANKI_BASE`, so your real collection is never opened, never migrated,
never written to. Verified: launching a demo profile leaves the real
`collection.anki2` mtime unchanged.

| Profile | The student it represents |
|---|---|
| `demo-rote` | spacebar-reflexed through everything |
| `demo-honest` | mostly thinks, sometimes taps through, has answered transfer variants |

---

## Beat 1 — "Anki says you're doing great"

```bash
ANKI_BASE="C:/dev/speedrun/demo/demo-rote" ./run.bat
```

Before opening the dashboard, point at the bottom of the deck screen:

> **Studied 240 cards in 8.94 minutes today (2.23s/card)**

That is what every other SRS app would call a good session. 240 reviews,
100% pass rate.

## Beat 2 — the refusal (`Ctrl+Shift+D`)

> **Performance: refusing to score — rote pattern detected**
> ✗ Rote pattern detected — 67% of measurable topics show near-identical
> response times (volatility below 0.20); at most 40% is allowed.
> *This is not a data-volume problem…*

The line to say out loud: **both of the old give-up conditions passed.**
240 graded reviews against a 200 floor, 100% topic coverage against a 50%
floor. By every metric AnKing or UWorld reports, this student did the
work. The app refuses anyway — because of *how* the work was done.

Scroll up to the **Latency volatility** panel for the evidence:
four topics at volatility 0.00, each with 40 reviews answered *faster
than the card can be read*.

## Beat 3 — scoring, but marked down

```bash
ANKI_BASE="C:/dev/speedrun/demo/demo-honest" ./run.bat
```

`Ctrl+Shift+D`. This student is not pattern-matching, so the app does
score them — and then discounts it:

> **Projected MCAT: 497** (range 488–506)
> ⚠ Score reduced to 83% of the model's estimate: 96 review(s) were
> answered faster than the card could be read.

Plus, in the Performance panel:

> **Transfer (jitter) accuracy: 92% over 48 context-shifted variant(s)** —
> the same principle asked in a situation you haven't seen.

The contrast with Beat 2 is the whole product: **refuse when the data is
untrustworthy, discount when it is merely imperfect, and say which.**

## Beat 4 — two apps, one engine

```bash
C:/Android/sdk/emulator/emulator.exe -avd speedrun_test -no-snapshot-load
```

```bash
adb push "C:/dev/speedrun/demo/demo-honest/User 1/collection.anki2" \
  /storage/emulated/0/Android/data/com.ichi2.anki.debug/files/AnkiDroid/collection.anki2
```

Launch AnkiDroid → overflow menu (⋮) → **Speedrun dashboard**.

Same volatility table, same 92% transfer accuracy, same 83% markdown,
same projected 497 — computed by the same Rust core, not a
reimplementation. Swap in `demo-rote` and the phone refuses identically.

---

## If something looks wrong

**Dashboard says "No topics tagged yet"** — the profile didn't load. Check
`ANKI_BASE` points at the folder *containing* `User 1`, not at `User 1`
itself.

**Android shows different numbers from desktop** — the AAR is stale.
That has bitten this project once already (the phone scored a deck 499
that desktop refused). The AAR prints `Anki commit: <sha>` when built;
it must match `git rev-parse HEAD` in the core repo. Rebuild:

```bash
cd C:/dev/speedrun/apps/Anki-Android-Backend && ALL_ARCHS=1 cargo run -p build_rust
```

(The Robolectric step panics with "Must be on macOS" — expected, and
harmless. The Android `.so`s are built and copied before it. Then
`./gradlew.bat :rsdroid:assembleRelease -x :rsdroid:buildRust`.)

**Emulator ANRs or dies** — it needs headroom. Stop the Gradle daemons
first: `./gradlew.bat --stop`.

---

## What is synthetic, and say so on camera

The two demo decks are **generated fixtures, not real study**. Both are
built by `speedrun/tools/rote-demo/make_rote_collection.py` into a temp
profile.

This is worth stating plainly during the demo rather than hoping nobody
asks, and the reason it is defensible is the direction it pushes: the
rote fixture manufactures *bad* behaviour so the detector can be seen
catching it. It can only ever make the product look **worse**. (An
earlier feature that would have fabricated reviews to make coverage look
*better* was cut for exactly that asymmetry — see
[coverage-map.md](coverage-map.md).)

The honest profile's transfer-variant attempts are likewise synthetic.
The **jitter variants themselves are real** — genuine model output, 8 of
14 accepted through the quality gates, with the 6 rejections and their
reasons committed at `speedrun/tools/ai-jitter/output/`.

If you want a beat with zero synthetic data, open your **real**
collection: it shows Memory 68%, honest per-topic volatility of
0.60–1.06, and a refusal on *"Not enough topic coverage: 36% of 50%"* —
the app declining to score its own author.
