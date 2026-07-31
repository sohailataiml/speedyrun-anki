# Speedrun

A desktop + mobile study app for the **MCAT**, forked from [Anki](https://apps.ankiweb.net).
Three separate, honest scores — Memory, Performance, Readiness — instead of
one blended confidence number. Full reasoning in
[speedrun/docs/brainlift.md](speedrun/docs/brainlift.md).

- **Architecture overview:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **The required Rust change** (mastery query + give-up gate + Performance
  model, why they belong in Rust, upstream files touched):
  [speedrun/docs/rust-change-note.md](speedrun/docs/rust-change-note.md)
- **Sync test results** (10+10 disjoint merge, same-card-conflict):
  [speedrun/docs/sync-test-results.md](speedrun/docs/sync-test-results.md)
- **Desktop installer**: [speedrun/docs/desktop-installer.md](speedrun/docs/desktop-installer.md)
- **How to run the demo on both platforms:** [speedrun/docs/demo.md](speedrun/docs/demo.md)

## Build instructions

**Desktop** (this repo). Needs a Rust toolchain and Python on `PATH`:
```bash
just run          # dev build + launch
just wheels        # build the anki/aqt wheels used by the installer
just test-rust      # 3 Rust unit tests for the Rust change
just test-py         # includes the 1 Python test for the Rust change
```
Packaged installer: see [speedrun/docs/desktop-installer.md](speedrun/docs/desktop-installer.md).

**Mobile (Android)** — a separate sibling repo,
[speedyrun-android](https://github.com/sohailataiml/speedyrun-android)
(AnkiDroid, forked) pointed at this repo's Rust backend via
[speedyrun-anki-android-backend](https://github.com/sohailataiml/speedyrun-anki-android-backend)
(Anki-Android-Backend, forked). Full wiring (why two extra repos, the
compatibility fixes required) in
[speedrun/docs/rust-change-note.md](speedrun/docs/rust-change-note.md#shipped-to-android).
Short version:
```bash
# in Anki-Android-Backend/, pointed at this repo's commit
cargo run -p build_rust
# in the AnkiDroid repo, with local.properties containing local_backend=true
./gradlew.bat assemblePlayDebug
```

## What we changed, in one page

This is a fork of upstream Anki (`ankitects/anki`). Everything Speedrun-specific
lives under [`speedrun/`](speedrun/) so it's obvious what's new versus
inherited — see [ARCHITECTURE.md §11](ARCHITECTURE.md#11-repo-layout) for the
exact file list. The Rust engine itself (`rslib`), Python layer (`pylib`),
and Qt frontend (`qt`) are Anki's own code, modified only where noted in
[the Rust change note](speedrun/docs/rust-change-note.md).

## About Anki

Anki is a spaced repetition program; this project builds on it rather than
replacing it. Please see the [Anki website](https://apps.ankiweb.net) and
[upstream development docs](./docs/development.md) to learn about the base
project this fork extends. Anki contributors: [CONTRIBUTORS](./CONTRIBUTORS).

## License

AGPL version 3 or later, same as upstream Anki. See [LICENSE](./LICENSE).
Some parts of Anki use the BSD three-clause license; unchanged from upstream.
