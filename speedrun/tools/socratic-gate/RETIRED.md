# Retired with Brainlift v2 — kept as evidence, not as a live tool

The Socratic bridge feature these harnesses were built to validate was
removed in the v3 Latency-Volatility pivot. Brainlift v3 §1 puts
"general-purpose Socratic tutoring (avoiding 'hint dependency')" out of
scope, and POV 3 argues AI hints create a dependency loop.

**These directories are deliberately not deleted.** They produced the
n=90 ablation that is now the strongest empirical result the project
owns — and it points the *same way* as the new thesis: bridges measurably
hurt verbatim recall (97% → 83%) and were a wash on transfer and
discrimination (63–70% either way). Written as a limitation of v2, that
finding reads as direct support for v3's POV 3. Deleting the tool that
produced it would leave the claim uncheckable.

**Their code comments reference files that no longer exist**
(`qt/aqt/speedrun_socratic_gate.py`, `SocraticGate.kt`,
`rslib/src/stats/socratic_gate.rs`). Those pointers are left as-is rather
than rewritten, because they describe what was true when the experiment
ran. Rewriting them would make the record of the experiment disagree with
the experiment.

What actually survived the cut, and where it went:

| v2 code | v3 home |
|---|---|
| grounding + leak checks (desktop) | `qt/aqt/speedrun_grounding.py` |
| grounding + leak checks (Android) | `CurriculumGrounding.kt` (generalised) |
| latency fast/slow threshold | `rslib/src/stats/latency_monitor.rs` |
| bridge generation, gating UI, dialogs | removed |

See `speedrun/docs/pivot-plan-latency-volatility.md`.
