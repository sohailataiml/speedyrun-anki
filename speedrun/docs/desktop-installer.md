# Desktop installer

Required by the PRD's early-submission bar: "Desktop installer that runs on
a clean machine." This is a real Windows `.msi`, not a placeholder — it
bundles the actual `anki`/`aqt` wheels built from this fork, which include
the mastery-query Rust change ([rust-change-note.md](rust-change-note.md)).

## For the grader: running it

1. Get `anki-0.0.1-win-x64.msi` (built from `out/installer/dist/` inside
   this repo's `core/` root — see below if it needs rebuilding; it isn't
   checked into git because it's ~600MB).
2. Double-click it, or `msiexec /i anki-0.0.1-win-x64.msi` from a terminal.
3. **Expect a SmartScreen warning ("Windows protected your PC").** This
   build is unsigned — the upstream Anki CI pipeline signs installers via
   Azure Trusted Signing, which isn't available outside that pipeline.
   Click "More info" → "Run anyway" to proceed. This is the one thing that
   won't match a production Anki release.
4. Finish the install wizard. Anki launches from the Start Menu afterward
   with no separate runtime to install — Python, PyQt6/WebEngine, and this
   fork's Rust backend are all bundled inside the MSI.

## How it was built (to reproduce)

From this repo's `core/` root, with a Rust toolchain and Python on `PATH`:

```bash
# 1. Build the anki/aqt wheels for this fork (includes mastery_query)
just wheels
# produces out/wheels/anki-26.5-*.whl and out/wheels/aqt-26.5-*.whl

# 2. Build the app bundle from those wheels
PYTHONPATH="out/pylib;pylib;out/qt;qt" ./out/pyenv/Scripts/python.exe -m tools.build_installer \
  --version "0.0.1" build \
  --aqt_wheel "out/wheels/aqt-26.5-py3-none-any.whl" \
  --anki_wheel "out/wheels/anki-26.5-cp310-abi3-win_amd64.whl" \
  --skip_fcitx

# 3. Package the bundle into an MSI
PYTHONPATH="out/pylib;pylib;out/qt;qt" ./out/pyenv/Scripts/python.exe -m tools.build_installer \
  --version "0.0.1" package
```

Output lands at `out/installer/dist/anki-0.0.1-win-x64.msi`.

(Upstream CI, `.github/workflows/release.yml`, does the equivalent via
`tools\ninja installer:build` then invokes `build_installer.py ... package`
directly to avoid re-triggering a submodule clone that would wipe a
just-applied code signature — irrelevant here since this build is
unsigned, but noted in case the ninja target is used instead.)

Packaging is driven by [Briefcase](https://briefcase.readthedocs.io/); it
downloads and caches its own copies of the embeddable Python runtime, a
stub binary, and the WiX Toolset (used for MSI generation) on first run —
expect a few hundred MB of one-time downloads and an internet connection
for that first build.

## What's verified vs. what isn't

- **Verified:** the build pipeline itself was broken before this work — two
  `qt/installer/{windows,mac}-template` git submodules were never
  initialized in this fork's clone, which made `briefcase build` fail with
  "Unable to clone application template." Fixing that (`git submodule
  update --init qt/installer/windows-template qt/installer/mac-template`)
  brought `qt/tests/test_installer.py` from 2 failing to 27/27 passing, and
  a full manual `build` + `package` run (documented above) produced a real,
  correctly-sized MSI containing the actual fork wheels (confirmed by
  checking the installed packages list in the build log — `anki-26.5`,
  `aqt-26.5`, `PyQt6-6.11.0`, etc., not a stand-in dummy package).
- **Not verified:** an install on a genuinely separate clean machine or VM
  (none was available in this environment). Running the steps above on the
  grader's own machine, which has never had this dev toolchain on it, is
  the actual clean-machine test.
