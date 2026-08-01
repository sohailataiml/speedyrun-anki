# Speedrun — Architecture

Status: Brainlift v1 complete, both decisions locked (§9 — exam: MCAT, Rust feature: mastery query). Core Engine, Android build, sync, and desktop installer are implemented and verified (see status notes in §3, §4, §5, §10). The full Scoring Service — give-up gate, Performance model, and Readiness mapper — is implemented (§6, Performance's training data is synthetic), both the desktop and Android three-score dashboards show all three scores live, and the AI Subsystem (§7) is implemented and run for real — generation, provenance, leakage check, and gold-set eval all verified, AI beats its baseline 98% to 0%. The §9 thesis ablation and paraphrase test are implemented and run for real: a second Rust feature (`speedrunTopicOrder`, a real queue-order toggle) drives a genuine three-way comparison, and both the item-side sufficiency test and the ablation produced real, non-fabricated results — see [speedrun/docs/paraphrase-test.md](speedrun/docs/paraphrase-test.md) and Brainlift §7. `crash-test` (20/20 kill-mid-review, zero corrupted collections) and `bench` (real p50/p95/worst-case timings against a 50k-card fixture) are both implemented and run for real — bench caught and fixed a real O(topics × collection_size) scaling bug in `mastery_query` along the way (dashboard load: 13-28s → 1.7-2.6s), though the aggressive dashboard-load targets still aren't met at 50k cards. See [speedrun/docs/bench-and-crash-test.md](speedrun/docs/bench-and-crash-test.md). Still not built: real held-back training data for the Performance model.

## 1. Mission → system shape

The PRD asks for three separate, honest scores, not one blended confidence number:

| Score | DOK level | What it answers | Source of truth |
|---|---|---|---|
| Memory | DOK 1 | Can you recall this fact right now? | FSRS (unmodified, from Anki core) |
| Performance | DOK 2/3 | Can you answer a *novel* exam-style question using it? | A trained model, held out of Rust, evaluated against data held back |
| Readiness | DOK 4 | What would you score today, and how sure are we? | A score-mapping function over Performance, with a range and a give-up rule |

That table drives the whole architecture: Memory lives entirely inside the forked Anki engine (don't touch FSRS). Performance and Readiness are new, sit outside the core engine, are individually falsifiable, and must be able to say "I don't know."

## 2. Component diagram

```mermaid
flowchart TB
    subgraph Clients
        Desktop["Desktop App\n(Anki Qt fork)"]
        Android["Android App\n(AnkiDroid fork)\nthe phone companion"]
    end

    subgraph CoreEngine["Core Engine (forked Anki, Rust)"]
        Rslib["rslib\nFSRS scheduler + collection storage"]
        MasteryMod["speedrun mastery module\n(new Rust code, Section 8 requirement)"]
        Proto["backend.proto\n(+ new messages/RPCs)"]
    end

    subgraph Sync["Sync"]
        SyncServer["Sync server\n(Anki sync protocol, self-hosted)"]
    end

    subgraph Scoring["Scoring Service (outside Rust)"]
        PerfModel["Performance model\n(held-back eval)"]
        ReadinessMap["Readiness mapper\n(range + give-up rule)"]
        Calibration["Calibration tracker\n(Brier/log loss)"]
    end

    subgraph AI["AI Subsystem (optional, degrades cleanly)"]
        CardGen["Card generator\n(source → cards)"]
        Eval["Gold-set eval + leakage check"]
    end

    Desktop --> Rslib
    Android --> Rslib
    Rslib --> MasteryMod
    MasteryMod --> Proto

    Desktop <--> SyncServer
    Android <--> SyncServer

    Desktop --> PerfModel
    Android --> PerfModel
    PerfModel --> ReadinessMap
    ReadinessMap --> Calibration

    Desktop -.optional.-> CardGen
    CardGen --> Eval
```

Key constraint from the non-negotiables: **both apps must run fully with AI switched off.** That's why `AI` is drawn as a separate optional subsystem feeding cards into the collection, not something the review loop or the Scoring Service depends on at runtime.

## 3. Core Engine — the forked Anki Rust backend

Fork Anki at the `rslib` / `pylib` / `qt` boundary it already has. Do not reimplement the scheduler.

**What's untouched:** FSRS, card scheduling math, undo, collection storage format (SQLite + protobuf transaction log).

**What's new — the Rust change required by Section 8.** Pick one, sized to the same shape:

| Option | What it does | Risk |
|---|---|---|
| Mastery query | New read-only query: per-topic mastery + average recall, fast on 50k cards, for the dashboard/coverage map | Lowest risk — additive, no scheduling changes |
| Topic-aware scheduling | Reweights due-card order by topic weight × weakness, keeps FSRS intervals/undo valid | Medium — touches the scheduling hot path |
| Points-at-stake queue | New queue ordering + new protobuf message | Medium — new wire format, needs client updates everywhere |

**Recommendation:** mastery query. The dashboard, coverage map, and all three scores need per-topic mastery regardless of which option is picked, it's additive (touches nothing FSRS owns), and it's the one most directly testable with the 3 Rust unit tests + 1 Python test the PRD requires. Confirm against the actual Spiky POV once Brainlift v1 exists — if the thesis is about *scheduling order* rather than *measurement*, topic-aware scheduling is the honest pick instead, and the traceability table should say so.

**Status: implemented.** Lives at `rslib/src/stats/mastery.rs` (not a new top-level `rslib/src/mastery/` as originally sketched — placed alongside `rslib/src/stats/card.rs` and `graphs/` since that's where this codebase's existing query-and-return-a-response-message pattern already lives, and following it turned out to matter more for "how well it fits Anki" than a clean-slate directory would have). Wired through `StatsService.MasteryQuery` in `proto/anki/stats.proto`. Full rationale, the exact files touched, and the undo-safety argument are in [speedrun/docs/rust-change-note.md](speedrun/docs/rust-change-note.md) — that doc is the required one-page note.

- Topic metadata on cards: reuse Anki's existing tag/tagging system rather than a new schema — a `topic::<name>` tag namespace avoids a schema migration and keeps the change small. Confirmed in the implementation: no schema change, just a `tag:topic::<name>` search.
- Confirmed via implementation: Python (pylib) and Kotlin (AnkiDroid) both picked up the generated binding — `GeneratedBackend.kt` exposes `fun masteryQuery(topics: Iterable<String>): List<anki.stats.TopicMastery>`. Reaching Kotlin required building AnkiDroid against a locally-built backend AAR rather than the published one — see §4's build detail and [speedrun/docs/rust-change-note.md](speedrun/docs/rust-change-note.md) for exactly how. The "ships to the phone too" requirement is satisfied.

## 4. Two apps, one engine

- **Desktop** — Anki's existing Qt frontend, extended with the three-score dashboard. Main tool per the PRD. **Status: implemented.** `qt/aqt/speedrun_dashboard.py`, opened with `Ctrl+Shift+D`. Shows Memory (always available, straight from `mastery_query`), Performance (gated by `give_up_gate` — shows the exact review/coverage shortfall when it refuses, a real number when it doesn't), and Readiness (a projected MCAT score with a range and confidence label — same gate, plus the mapper's own stated method/limitation shown inline). Built as a native PyQt dialog (`QueryOp` for the background backend call), not a new Svelte page.
- **Android** — fork AnkiDroid, which already embeds the Rust backend over JNI. Add the same dashboard. This is the phone companion. **Status: implemented and confirmed live on an emulator.** `AnkiDroid/src/main/java/com/ichi2/anki/speedrun/ScoreDashboard.kt`, reachable from the deck picker's overflow menu ("Speedrun dashboard"). Mirrors the desktop dashboard's Memory/Performance/Readiness layout, built the way AnkiDroid actually builds screens — a classic View/Fragment `AnkiActivity` with ViewBinding and an MVVM `ViewModel`/`StateFlow` (not Compose, which the app depends on but doesn't use for real screens). `libanki/.../Speedrun.kt` wraps the four backend RPCs as `Collection` extension functions, mirroring pylib's own wrapper. Built clean (`BUILD SUCCESSFUL`), calls the same RPCs confirmed live in `GeneratedBackend.kt` (§3), and — as of this session — was driven live via `adb` on a fresh emulator: menu item confirmed present, the screen opens and renders its correct empty state ("No topics tagged yet"), and a `topic::`-tagged note was added and saved through the real note editor and tag picker with no crash at any point (`logcat` clean throughout). A screenshot of the dashboard populated with real Memory/Performance/Readiness numbers (the equivalent of the desktop shot) is still outstanding — the same session's emulator became too resource-starved (host down to ~1.7GB free RAM) to reliably complete a review pass afterward; retry once the host has more headroom.
  - **Important build detail, confirmed by getting it building:** AnkiDroid does not compile the Rust backend from source by default — `gradle/libs.versions.toml` pulls it as a prebuilt Maven artifact (`io.github.david-allison:anki-android-backend`). **Resolved:** `apps/Anki-Android-Backend` is cloned as a sibling to `apps/android` (its own documented local-dev layout), its `anki` submodule points at this fork instead of upstream, and it's built locally via `cargo run -p build_rust` (NDK cross-compile of `rsdroid` to `x86_64-linux-android` via `cargo-ndk`) to produce `rsdroid-release.aar`. `apps/android/local.properties` sets `local_backend=true` so AnkiDroid's Gradle build links that local AAR instead of the Maven one. Full detail, including two small compatibility fixes this required, in [speedrun/docs/rust-change-note.md](speedrun/docs/rust-change-note.md).
- **iOS — explicitly descoped.** No Mac (or cloud Mac CI) is available for this project, and iOS development has no supported path on Windows (no Xcode, no simulator, no on-device signing). The PRD's phone-companion requirement is written in the singular ("the phone") and the grading hard limit ("no phone companion sharing the engine and syncing: 70% maximum") is about having *a* working phone client, not both platforms — so Android alone satisfies it. This gap is stated here and in the Brainlift rather than silently dropped, per the project's own honesty rule.

Both clients talk to the same collection format and the same sync protocol. No client owns its own copy of scheduling logic.

## 5. Sync

Extend Anki's existing sync protocol rather than inventing a new one — it already solves the hard part (usn-based incremental sync of a SQLite collection).

**What syncs:** review log entries (additive, append-only) and topic tags. Mastery is *derived*, not synced — every client recomputes it locally from the review log it already has. This sidesteps a whole class of merge conflicts: you only need a conflict rule for raw review data, never for the derived mastery numbers.

**Conflict rule (must be written down per Section 8) — status: verified against a real desktop client + real AnkiDroid emulator + self-hosted sync server, not just theorized. Full test log and setup in [speedrun/docs/sync-test-results.md](speedrun/docs/sync-test-results.md).**
- Disjoint reviews (10 cards phone-offline, 10 different desktop-offline) → both sets land, nothing is dropped, because review log entries are append-only and keyed by (card, timestamp, device). Confirmed: all 20 cards landed on both clients.
- Same card reviewed on both devices while offline → both review log entries are kept (nothing is silently discarded — that would be an "invented number" by omission), but the card's *next-due* scheduling state is resolved by latest-timestamp-wins, matching Anki's existing usn/mtime conflict handling. Confirmed: both revlog entries survived on both clients; both clients converged to the state dictated by the later-timestamped review.
- Real finding from the test: this only works because both clients shared a synced baseline *before* diverging. If two collections add content independently before ever syncing, the server requires a `FULL_SYNC` (pick one side to win entirely) rather than merging — worth knowing before assuming "just sync" always merges cleanly.

## 6. Scoring Service (outside the Rust core, by design)

Lives outside Rust because it's statistical, needs retraining, and needs to be evaluated on held-back data — none of which belongs in the scheduler.

- **Input:** topic mastery + average recall (from the Core Engine's mastery query), question difficulty, timing, coverage %.
- **Performance model:** predicts accuracy on held-back exam-style questions from those inputs. Calibrated and evaluated with a stated train/test cutoff someone else can rerun. **Status: apply-side implemented, training data is a placeholder.** Split train/apply, same reasoning as the give-up gate: `speedrun/tools/scoring-train/train_performance_model.py` trains a small logistic regression in Python (mastery, difficulty, timing, coverage → predicted accuracy) and serializes the weights; `rslib/src/stats/performance_model.rs` embeds that weights file at compile time and applies it identically on desktop and Android, exposed as `StatsService.PerformanceQuery` — same "one engine" guarantee as `mastery_query`, and it runs the give-up gate first, so nothing here executes for a caller the gate would refuse. **The training data is synthetic** (generated from a fixed seed, clearly labeled in the script) because no real held-back exam-question bank exists yet (§8's "Held-back sets" — not built) — the pipeline is proven rerunnable and beats a majority-class baseline (69% vs 59% on the synthetic eval split), but the resulting weights must not be presented to a real student as a genuine score until retrained on real held-back questions. 4 Rust unit tests + 1 Python test.
- **Readiness mapper:** maps performance distribution → the real exam scale (MCAT, 472-528, see §9) with a range, never a single number. **Status: implemented.** `StatsService.ReadinessQuery` in `rslib/src/stats/readiness_mapper.rs` — runs `performance_query` first, then maps predicted accuracy onto AAMC's published MCAT score distribution (mean 500.5, SD ~10.6) by treating accuracy as an approximate population percentile via the inverse normal CDF (a hand-implemented, numerically-verified rational approximation — no new crate dependency). Range width and a Low/Medium/High confidence label are both derived from graded-review count and topic coverage (more data → narrower range). **Stated limitation, not hidden:** treating predicted accuracy as a population percentile is a real simplifying assumption, not validated against actual MCAT takers with real study history and score outcomes — that validation is PRD §10's bonus tier. 5 Rust unit tests (including exact z-value checks against known values) + 1 Python test.
- **Give-up rule:** enforced here, not in the UI — the service itself refuses to emit a score below the stated thresholds (<200 graded reviews or <50% topic coverage), so no client can accidentally bypass it. **Status: implemented.** `StatsService.GiveUpGate` in `rslib/src/stats/give_up_gate.rs` — calls `mastery_query` internally, computes collection-wide graded-review count and topic coverage, and returns a protobuf `oneof` (`data` vs `insufficient`) so there's no code path where a caller can read a score without either passing the gate or being told why not. 3 Rust unit tests + 1 Python test, same pattern as the mastery query. `performance_query` and `readiness_query` both cascade through this same gate before doing any further work.
- **Calibration tracking:** Brier score / log loss against held-back reviews, surfaced on the dashboard alongside every score, per the honesty rule.

This service can run as a local process embedded in the desktop/mobile app (no network dependency for the *required* scores) — only the optional AI subsystem needs a network call, keeping "both apps run with AI off" true by construction.

## 7. AI Subsystem (optional, must degrade cleanly)

- Card generation: source → chunking → generation → gold-set eval (50 QA pairs, cutoff set before looking) → leakage check, before anything reaches a student. **Status: implemented and run for real**, full writeup in [speedrun/docs/ai-subsystem.md](speedrun/docs/ai-subsystem.md). `speedrun/ai/source_material.md` (14 chunks, original content) → `speedrun/tools/ai-cardgen/generate.py` (real Claude API calls, one per chunk) → 50 traced cards. Paraphrase test not yet built (separate PRD §8 item, tracked in §10's table below).
- Every AI output must trace to a named source (Section 3 non-negotiable) — store provenance alongside generated cards, not just the card text. **Status: implemented.** Every generated card carries `source_chunk`/`source_title`; this is checked by the generator's own output schema, not just convention.
- Must beat a simpler baseline (keyword or vector search) on the held-out eval, or it doesn't ship. **Status: verified — it beats the baseline by a wide, honest margin.** `speedrun/tools/ai-cardgen/baseline.py` (regex/keyword extraction, no LLM) vs the real generator, graded by `eval.py` against the same gold set with the same rubric: **98% correct-and-useful (AI) vs 0% (baseline)**. Full numbers, the one AI card that graded `wrong`, and a sample baseline failure in the doc above.
- Leakage check. **Status: implemented, and it caught a real bug in itself first.** `speedrun/tools/leakage-check/check.py` verifies gold-set-specific content never reached the generation prompt (not just that the code doesn't read `gold_set.json` — checked empirically against the actual logged prompts). An earlier version of the check produced 19 false positives before being fixed to account for expected source-material overlap; see the doc for why.
- Failure mode: if the AI service is offline or returns garbage, the app keeps working and keeps scoring — this is why AI is drawn as a side-branch in §2, not on the path from review → score. True by construction: none of `mastery_query`/`give_up_gate`/`performance_query`/`readiness_query` or the desktop dashboard touches `speedrun/tools/ai-cardgen/` at all.

## 8. Data model additions (on top of Anki's existing schema)

- `topic` tag namespace on cards (see §3) — no new table needed for basic tagging.
- Exam outline mapping: a data file (versioned in-repo) mapping the official exam outline → topic tags, used for the coverage map and the "abstain below your line" rule.
- Held-back sets: exam-style question bank split into train/eval with a stated, timestamped cutoff — kept out of any AI training/generation context (this is what the leakage checker verifies).
- Gold set: 50 QA pairs for the AI card-quality eval, graded correct-and-useful / wrong / correct-but-bad-teaching.

| Entity | Purpose | Status |
|---|---|---|
| `topic::<name>` tag | Links cards to outline topics | Done — reuses Anki's tag table |
| Exam outline mapping file | Official outline → topic tags, for coverage map | Not built |
| Held-back question bank (train/eval split) | Performance model training + input to leakage check | Not built |
| Gold set (50 QA pairs) | AI card-quality eval | **Done** — `speedrun/ai/gold_set.json`, cutoff-committed before generation, used by `speedrun/tools/ai-cardgen/eval.py`. See [ai-subsystem.md](speedrun/docs/ai-subsystem.md). |
| Performance history | Per-topic accuracy on held-back exam-style questions, feeds the Performance model | Not built |
| Readiness prediction log | Each estimate + range + inputs, for the calibration chart (§10.1) | Not built |
| Calibration log | Predicted-vs-actual outcomes, source of Brier/log-loss numbers (§6, §10) | Not built |

## 9. Decisions locked by Brainlift v1

See [speedrun/docs/brainlift.md](speedrun/docs/brainlift.md) for the full research and reasoning behind these.

- **Target exam: MCAT.** Readiness is a scaled score (472–528) with a range, not a pass probability — the branch this would have taken for USMLE doesn't apply. The exam outline mapping (§8) is AAMC's official four-section content list.
- **Rust feature: mastery query** (§3), confirmed rather than overridden — the Brainlift's thesis (POV 1, below) is about *measuring* the recall/transfer gap, not primarily about reordering the review queue, so the lowest-risk, additive option is also the one the thesis actually needs as its *required* PRD Rust feature. A second, smaller Rust feature was still needed to actually run the ablation (below) — the PRD's one required feature and the ablation's own feature flag turned out not to be the same thing, and both got built.
- **Thesis feature for Section 9's ablation — implemented and run.** POV 1: "past a range of card-retention levels, further gains come from transfer training, not more review reps, because isolated flashcard review never trains the discrimination skill exam items require." The three-way build: (1) full app with a topic-interleaved review mode, (2) same app with that mode off (plain topic-blocked review), (3) unmodified Anki. **Status: all three builds exist and were run for real**, via `speedrunTopicOrder` (`rslib/src/scheduler/queue/builder/topic_order.rs` — see [rust-change-note.md](speedrun/docs/rust-change-note.md)), a config-key toggle rather than a new RPC (no proto regen, no Android AAR rebuild needed). The paraphrase test (30 cards × 2 rewordings) is the shared measurement across all three — see [speedrun/docs/paraphrase-test.md](speedrun/docs/paraphrase-test.md) for the full results: a real 16-point interleaved-vs-blocked gap at a 10-card study budget, closing by a 20-card budget as topic coverage converges. Brainlift §7 has the summary and verdict on POV 1.
- **Feature flags this implied:** the Core Engine needed the interleaving/blocking toggle on the review queue (built — see above); the Scoring Service keeping the Performance model computable identically regardless of which build produced the review history was addressed by having the ablation drive real review history through the same `Collection`/RPC surface for all three builds, rather than a separate code path per build.

## 10. Testing & benchmark surface (Section 8/10 requirements → where they live)

### Performance targets (PRD §10, verbatim numbers)

Every row must be reported as p50 / p95 / worst-case on the shared 50k-card deck — a single self-picked number does not satisfy this ("One number you picked yourself does not count."). `speedrun/tools/bench` — **implemented and run for real**; see [speedrun/docs/bench-and-crash-test.md](speedrun/docs/bench-and-crash-test.md) for full numbers and methodology.

| Metric | Target | Result |
|---|---|---|
| Button press acknowledged | p95 < 50ms | Not measured — requires driving the real GUI, not scriptable headlessly |
| Next card after grading | p95 < 100ms | **PASS** — p50 4ms, p95 6ms, worst 33ms |
| Dashboard first load | < 1s | **FAIL** — p50 1.76s, p95 2.15s (down from 13-28s pre-fix — see below) |
| Dashboard refresh | < 500ms | **FAIL** — p50 1.88s, p95 2.58s |
| Normal session sync | < 5s | Not run in bench.py — see `speedrun/tools/sync-test/`'s own timing |
| Memory at 50,000 cards | Under a limit we state | 6.5MB RSS delta (harness process; not Qt/Android's own footprint) |
| Cold start | < 5s desktop, < 4s phone | **PASS** (lower bound) — p50 8ms, p95 9ms (backend collection-open only, not full app launch) |
| Crash test | Zero corrupted collections | **PASS** — 20/20, all kills landed on a live process |

| Requirement | Lives in |
|---|---|
| 3 Rust unit tests + 1 Python test for the Rust change | `core/rslib/src/<module>/tests.rs`, `core/pylib/tests/` — satisfied twice over: `mastery.rs`/`give_up_gate.rs`/etc. for the primary Rust change, and `topic_order.rs` (4 unit tests + 1 integration test) + `test_speedrun_topic_order.py` for the ablation's queue-order toggle |
| Sync test (20 cards, offline/reconnect, conflict rule) | `speedrun/tools/sync-test/` driving two headless client instances against the sync server |
| Coverage map | Derived at runtime from §8's outline mapping; surfaced on dashboard |
| Paraphrase test | `speedrun/tools/paraphrase-test/` — **implemented and run for real.** Item-side sufficiency (93% near-transfer vs. 73% discrimination, real Claude API calls) plus the full three-way ablation (real Rust queue output, counterfactual-content student simulation, 0% no-study control confirming no contamination). See [speedrun/docs/paraphrase-test.md](speedrun/docs/paraphrase-test.md). |
| Leakage check | `speedrun/tools/leakage-check/` — implemented, passes. See [speedrun/docs/ai-subsystem.md](speedrun/docs/ai-subsystem.md) |
| AI card check (gold set) | `speedrun/tools/ai-cardgen/eval.py` — implemented, run for real. AI 98% correct-and-useful vs baseline 0%. See [speedrun/docs/ai-subsystem.md](speedrun/docs/ai-subsystem.md) |
| Crash/offline test (20x kill mid-review) | `speedrun/tools/crash-test/` — **implemented and run for real: 20/20 pass, zero corrupted collections.** Desktop only — Android scoped out this session (emulator resource constraints). See [speedrun/docs/bench-and-crash-test.md](speedrun/docs/bench-and-crash-test.md). |
| Benchmark (`make bench`) | `speedrun/tools/bench/` — **implemented and run for real** against the 50k-card fixture. Found and fixed a real scaling bug in `mastery_query` along the way (see [rust-change-note.md](speedrun/docs/rust-change-note.md)); dashboard-load targets still not met post-fix. See [speedrun/docs/bench-and-crash-test.md](speedrun/docs/bench-and-crash-test.md). |
| Desktop installer (clean-machine run) | `speedrun/docs/desktop-installer.md` — real `.msi` built from this fork's wheels via Briefcase; build verified, install-on-genuinely-separate-machine left to the grader (see doc for what's checked vs. not) |

## 11. Repo layout

This is the actual current layout, not an aspirational sketch. **`core/` (this repo) is the primary submission** — Anki's fork with `rslib`/`pylib`/`qt` mostly untouched, plus everything Speedrun-specific added under `speedrun/` so it's obvious what we added versus what's inherited from upstream Anki:

```
core/                             # this repo — the public Anki fork
├── ARCHITECTURE.md               # this file
├── rslib/src/stats/
│   ├── mastery.rs                # the required Rust change (implemented)
│   ├── give_up_gate.rs           # give-up rule gate (implemented)
│   ├── performance_model.rs      # Performance model, apply side (implemented, synthetic training data)
│   └── readiness_mapper.rs       # Readiness mapper (implemented)
├── proto/anki/stats.proto        # new RPCs/messages for all of the above
├── pylib/anki/collection.py      # thin Python wrappers over the same RPCs
├── qt/aqt/speedrun_dashboard.py  # desktop three-score dashboard (Ctrl+Shift+D)
├── qt/installer/                 # desktop installer packaging (Briefcase)
└── speedrun/
    ├── ai/
    │   ├── source_material.md    # original content the AI generator runs on
    │   └── gold_set.json         # 50 QA pairs, cutoff committed before generation ran
    ├── docs/
    │   ├── brainlift.md
    │   ├── rust-change-note.md
    │   ├── sync-test-results.md
    │   ├── desktop-installer.md
    │   ├── ai-subsystem.md       # generation, leakage check, eval results
    │   └── demo.md                # how to run the demo on both platforms today
    └── tools/
        ├── sync-test/             # drives real desktop + Android clients against the sync server
        ├── scoring-train/         # Performance model training script + versioned weights
        ├── ai-cardgen/            # baseline.py, generate.py, eval.py
        └── leakage-check/
```

The phone companion is **not** inside this repo — it's two separate public forks:
[speedyrun-android](https://github.com/sohailataiml/speedyrun-android) (AnkiDroid) and
[speedyrun-anki-android-backend](https://github.com/sohailataiml/speedyrun-anki-android-backend)
(the JNI bridge that builds this fork's Rust backend for Android — its `anki` submodule
points at this repo, not upstream Anki). `speedrun/docs/rust-change-note.md` documents
exactly how they're wired together.

Not yet built, so not yet a real directory: the Performance model's train-time consumer of real held-back questions (currently synthetic — see `speedrun/tools/scoring-train/`). `paraphrase-test`, `crash-test`, and `bench` are all now real — see above.

## 12. Non-negotiables → architecture mapping

| Non-negotiable (PRD §3) | Where it's enforced |
|---|---|
| Real change inside Anki's Rust code | §3, new module under `core/rslib` |
| Two apps sharing one engine, syncing both ways | §4, §5 |
| Three separate scores, each with a range | §6 — Scoring Service returns a range, never a scalar |
| Models tested on held-back data, rerunnable | §8, §10 — stated cutoffs, `speedrun/tools/` scripts anyone can run |
| Thesis feature testable on/off | §9 — feature-flagged in Core Engine and/or Scoring Service |
| Refuses to score without data | §6 — give-up rule lives in the Scoring Service, not the UI |
| Both apps run with AI off | §7 — AI is a side-branch, never on the score-computation path |
| AGPL v3+, credit to Anki | License file at repo root; retain Anki's existing license headers where forked code is unmodified |
