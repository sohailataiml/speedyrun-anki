# PRD §12 demo video — recording script

A word-for-word script with exact on-screen actions, built from
[demo.md](demo.md)'s shot list plus the two major pieces finished after
that list was written (the §9 ablation/paraphrase-test, and
crash-test/bench). No stated time limit was found in the repo's own
docs — this runs ~7-8 minutes at a natural pace; trim beats 5 and 7 first
if a hard limit applies, they're the most skippable without losing a
required PRD checkbox.

**Before recording:** confirm beat 3's test collection still has 200+
graded reviews on at least one `topic::` (it did as of this session —
Memory 93%, Performance 76%, projected MCAT 508, range 499-517). If it's
been reset, either restore that state or narrate honestly that the gate
is showing a refusal instead of a passing score.

---

## Beat 1 — The spiky POV (15-20s)

**Action:** Talking head or title card, no screen share yet.

**Say:**
> "Speedrun is an MCAT study app forked from Anki. The spiky point of
> view: past a certain amount of flashcard review, more repetitions stop
> helping, because isolated card recall never trains the discrimination
> skill real exam questions require. Everything in this video is real —
> real code, real Rust, real API calls, real numbers, including the
> parts that came back weaker than I expected."

---

## Beat 2 — Ordinary review session, desktop (30-40s)

**Setup:** `cd core && run.bat` (or the packaged installer — see
[desktop-installer.md](desktop-installer.md) if showing the clean-machine
install path instead).

**Action:** Click a due card → Show Answer → grade it (Good).

**Say:**
> "This is a fork of Anki, so ordinary review — unmodified FSRS
> scheduling — works exactly like upstream Anki. Nothing about the
> Speedrun additions changes this path."

---

## Beat 3 — The desktop three-score dashboard (45-60s) — the strongest shot

**Action:** Press `Ctrl+Shift+D` (keyboard-only, no menu item).

**Say (while it's on screen):**
> "This is the three-score dashboard — the core of the project. Three
> separate, honest scores instead of one blended confidence number.
> Memory is straight FSRS retrievability, always available. Performance
> and Readiness are both gated — the app refuses to show a number below
> 200 graded reviews and 50% topic coverage rather than guess. Right now
> this collection clears that gate: Memory 93%, Performance 76%, and a
> projected MCAT score of 508 with a range and a confidence label — not
> a single made-up number."

**Optional add-on, if time allows:** point out the "Method" line under
Readiness — narrate that it states its own simplifying assumption
(population-percentile mapping against AAMC's published score
distribution) rather than hiding it.

---

## Beat 4 — Android: review, dashboard, sync (60-90s)

**Action:** On a real device or emulator: open AnkiDroid, review a due
card, open the deck picker's overflow menu (⋮) → "Speedrun dashboard".

**Say:**
> "The same engine runs on Android — this isn't a second implementation,
> it's the same Rust core compiled for the phone. The dashboard is the
> same three scores, same layout, reachable from the deck picker's
> overflow menu."

**Known gap to narrate honestly, if the populated shot isn't ready:**
> "As of this recording, I've confirmed this screen renders live with no
> crash — the menu item, the screen opening, its correct empty state —
> but I haven't yet gotten a shot of it with real Memory/Performance
> numbers on a real device. That's a demo-recording gap, not a code gap:
> the same tested code path that's showing real numbers on desktop runs
> here too."

**Then, sync round-trip** (`sync-test-results.md`'s script, or manual Sync
button taps on both sides):

**Say:**
> "And it syncs — a card reviewed on the phone lands on desktop, using
> Anki's real sync protocol. This has been verified twice against a
> live sync server: a disjoint-cards merge and a same-card-conflict
> case, both passing."

---

## Beat 5 — The AI subsystem (30-45s, terminal/report, not in-app)

**Action:** Show a terminal running `speedrun/tools/ai-cardgen/eval.py`,
or just display `ai-subsystem.md`'s results table on screen.

**Say:**
> "Speedrun also has an AI card-generation subsystem — real Claude API
> calls turning source material into flashcards, with full provenance
> back to the source chunk, a leakage check, and a gold-set eval graded
> blind. The AI generator beats a keyword-extraction baseline 98% to 0%
> on 'correct and useful.' This is a terminal demo, not a button in the
> app — there's no 'generate cards' UI yet, and I'm narrating that
> plainly rather than dressing it up as a feature that ships."

---

## Beat 6 — The §9 thesis ablation and paraphrase test (90-120s) — the newest, most substantive piece

**Action:** Show `speedrun/docs/paraphrase-test.md`'s results tables on
screen (or the terminal output from `report.py`/`ablation_report.py`).

**Say:**
> "The Brainlift's thesis needed an actual test, not just an
> architecture diagram. I built a second Rust feature — a
> topic-interleaved review mode, a real toggle in the queue builder, not
> a simulation — and ran a genuine three-way ablation: interleaved
> review, blocked review, and unmodified Anki, all producing real review
> queues from the real Rust backend.
>
> To measure it, I generated real reworded exam questions via Claude for
> 30 cards, then renamed every cycle-specific term to something
> fictional, so the model being tested can't just answer from things it
> already knew — a no-study control confirmed that worked: zero out of
> ninety questions answered correctly with nothing studied.
>
> The result: interleaved review beat blocked review by sixteen points
> at a ten-card study budget — but that gap closed entirely by twenty
> cards, once blocked review had caught up on topic coverage anyway.
> That's not the flat 'always interleave' claim I started with — it's a
> front-loaded effect, and I'm reporting the corrected, weaker claim
> instead of the stronger one I would have preferred to find."

**This is the beat to slow down on** — it's the thesis validation and
the most original piece of work in the project; don't rush past the
numbers.

---

## Beat 7 — crash-test and bench (45-60s)

**Action:** Show the terminal output of `crash_test.py` (the 20/20 pass
lines) and `bench.py`'s results table, or `bench-and-crash-test.md`.

**Say:**
> "Two more PRD requirements: a crash test — twenty hard kills of the
> app mid-review, checking for corrupted collections afterward. Twenty
> out of twenty passed. And a benchmark against a fifty-thousand card
> deck, which actually caught a real bug: the dashboard was taking up to
> twenty-eight seconds to load at that scale, because a per-topic search
> wasn't using an index. Fixed it — one combined search instead of
> fifty separate ones — and load time dropped to under three seconds,
> about a ten times improvement. It still doesn't hit the aggressive
> target I set, and I'm showing that failing number on screen rather
> than picking an easier benchmark that would have passed."

---

## Beat 8 — Close (15-20s)

**Say:**
> "Everything shown here is real: real code, real Rust, real API calls
> against real models, and real numbers — including the ones that came
> back weaker, slower, or less complete than I wanted. The full writeup,
> including every stated limitation, is in the repo's docs folder."

---

## Recording notes

- **Screen resolution:** capture at whatever your recording tool
  defaults to; the dashboard dialogs are fixed-size and legible at
  1080p.
- **Cuts are fine** between beats — this doesn't need to be one
  unbroken take. Cutting out dead air (app launch time, emulator boot)
  is expected and normal for a demo video.
- **If Android is unstable when you record:** beats 4 and 6's Android
  portions are the ones most likely to need a retry given this session's
  documented emulator resource-pressure issues (see the "Gotcha" note in
  [rust-change-note.md](rust-change-note.md)). Consider recording desktop
  beats first, then attempting Android fresh with other apps closed.
- **Total runtime target:** ~7-8 minutes as scripted. To cut to ~5
  minutes: drop beat 5 entirely (state in beat 8's close that the AI
  subsystem exists and beats the baseline, point to the doc) and
  shorten beat 7 to just the headline numbers.
