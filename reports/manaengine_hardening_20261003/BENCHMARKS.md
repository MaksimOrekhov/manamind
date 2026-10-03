# Phase 2 performance measurements

Source data: [benchmarks.json](benchmarks.json), Windows 11 Release build, 15 iterations for session/action measurements, 300 clone operations, 10 pass-only complete games. ManaEngine deck is a supported 30-copy test fixture; Rosetta deck is a Rosetta-validated Mage fixture. They have the same length and game loop, but not the same card composition. Cross-backend values are reference context, not an apples-to-apples speed verdict.

## ManaEngine vs prototype checkpoint

The checkpoint data is `reports/manaengine_prototype_20261003/benchmarks.json`. Times are medians unless stated.

| Metric | Prototype checkpoint | Hardening | Delta |
|---|---:|---:|---:|
| Session creation | 9.806 ms | 11.236 ms | +14.6% |
| `legal_actions` | 0.0325 ms | 0.0400 ms | +23.1% |
| `apply_action` (end turn) | 0.0382 ms | 0.0405 ms | +6.0% |
| `clone` | 0.0010 ms | 0.0049 ms | +0.0039 ms absolute; 4.9× relative |
| Working-set delta / session estimate | 546 B | 4,642 B | +4.10 KiB estimated |
| Pass-only transitions/sec | 3,737.9 | 3,302.5 | −11.7% |
| Pass-only complete games/sec | 55.79 | 49.29 | −11.7% |

The fixtures differ: the original used a validated mixed Mage deck, while the hardened ManaEngine run repeats one fully supported minion because no 30-card repeated list can satisfy Rosetta's deck-copy validation. RSS delta is noisy at this scale. The numbers are a warning to retain benchmarks, not evidence that the hardening code alone caused each change.

Clone remains approximately 4.9 microseconds per copy in this run. Full value-copy cloning is still inexpensive for the current small state; no copy-on-write redesign is justified by this measurement.

## Current Rosetta reference run

The newly recorded Rosetta values were session creation 1.135 ms, `legal_actions` 0.0262 ms, end turn 0.2032 ms, estimated working-set delta 223,641 B, and 1,325.2 pass-only transitions/sec. These are not directly compared to ManaEngine because of the fixture difference. Rosetta cloning is not exposed by this benchmark.

## Repeated measurements after held-card progression

Two additional Release runs were recorded in [benchmarks_after_held_progress.json](benchmarks_after_held_progress.json) and [benchmarks_after_held_progress_repeat.json](benchmarks_after_held_progress_repeat.json). Both use the same 30× Violet Spellwing synthetic ManaEngine deck, seed and pass-only workload; each produced 10 fatigue-terminal games. The run medians were:

| Metric | Run 1 | Run 2 |
|---|---:|---:|
| Session creation | 15.53 ms | 14.93 ms |
| `legal_actions` | 0.0408 ms | 0.0436 ms |
| `apply_action` (end turn) | 0.0433 ms | 0.0659 ms |
| `clone` | 0.0058 ms | 0.0055 ms |
| Working-set delta/session estimate | 2,184 B | 25,559 B |
| Pass-only transitions/sec | 2,382.9 | 2,153.1 |
| Pass-only complete games/sec | 35.57 | 32.14 |

The working-set estimate and turn timings vary substantially across these short process-level runs. They are retained as observations, not as a performance verdict or evidence that the held-card hook caused a regression. No numeric performance budget has been defined.

## Limits

- No performance threshold had been defined, so the results do not label the prototype as passing/failing a numeric regression budget.
- Memory is a process working-set delta divided across held sessions, not an exact native object-size calculation.
- No representative action-heavy full games/sec benchmark was added; this remains a future measurement once more than the prototype card set is admitted.

## Phase 3 matched ManaEngine fixture

Measured with the same Windows 11 Release build type, seed 7, `CORE_DRG_107 × 30` deck, pass-only full-game workload, and 25 session/action iterations as `benchmarks_after_held_progress_repeat.json`. The post-Phase-3 run is summarized here; trace remained disabled (the default).

| Metric | Phase 2 repeat | Phase 3 | Change |
|---|---:|---:|---:|
| Session creation median | 14.93 ms | 15.13 ms | +1.4% |
| `legal_actions` median | 0.0436 ms | 0.0401 ms | −8.1% |
| `apply_action` end turn median | 0.0659 ms | 0.0409 ms | −37.9% |
| `clone` median | 0.0055 ms | 0.0056 ms | +1.8% |
| Working-set estimate/session | 25,559 B | 21,135 B | −17.3% |
| Pass-only transitions/sec | 2,153 | 2,715 | +26.1% |
| Pass-only games/sec | 32.14 | 40.52 | +26.1% |

The changes are within the substantial run-to-run variability already observed for working-set and turn timings. None approaches an order-of-magnitude slowdown; these are measurements, not a causal performance claim. The Rosetta side of the same run used a validated Mage fixture with different card composition and remains reference context only.
