# Completion record — `manaengine_controlled_prototype_v1`

Status: `COMPLETED_TIMEBOXED_PROTOTYPE`
Branch: `codex/manaengine-prototype`
Elapsed active work: approximately **1 h 30 min**; 12 h hard limit not approached.

| Field | Result |
|---|---|
| Candidate roots | 18 total: 3 Tier A + 15 Tier B; 0 Tier C used for parity |
| Tier A / Tier B | A: `CORE_DRG_107`, `CORE_SW_072`, `CORE_SW_108`. B: `CATA_475`, `CATA_999`, `CORE_BT_416`, `CORE_CS2_024`, `CORE_CS2_029`, `CORE_CS2_062`, `CORE_CS2_072`, `CORE_EX1_129`, `CORE_EX1_145`, `CORE_ICC_055`, `END_007`, `JAIL_327`, `JAIL_516`, `JAIL_872`, `TIME_218` |
| Declaration-only consumers | 18 root mappings are data declarations into typed abilities; no root ID behavior branch in generic C++ dispatch. All 18 receive the same adapter/session boundary. This is prototype mapping reuse, not a production generator package. |
| CUSTOM / deferred outliers | 0 CUSTOM among selected roots. All card behavior is prototype-scoped. Every unselected root and unsupported generated/summoned follow-up remains out of scope. |
| Shared C++ changes | New internal engine header/implementation, pybind binding and native tests: private state, catalog/session, action generation/application, combat/damage/death, FIFO triggers, cost changes, deterministic RNG, typed choice, clone, limited hero power and match termination. JSON data selects typed behaviors. |
| Shared Python changes | One adapter in `src/manamind/integrations/manaengine/` projecting to existing `GameState` and action dictionaries; immutable definition/catalog caching for sessions. |
| Correction cycles | 4: Windows toolchain/import setup; scenario fixtures plus enemy-only Drain Soul targeting; initial hand/Coin/deck order and terminal loop; immutable shared catalog after measured allocation overhead. |
| Final builds | CMake Ninja Debug and Release builds succeeded; final Release CTest 1/1 passed. |
| Native scenarios/assertions | 10 ManaEngine scenario groups / 53 assertions passed. 19 focused Rosetta cases / 150 assertions passed at gitlink `f34da0d3fcb5ad312f7e2acf634d0536b044d29a`. |
| Python/adapter checks | Dedicated adapter pytest 1/1; Ruff passed. Normal main checkout full suite 80/80. Worktree full-suite attempt 77/80; the 3 failures are owner-path checks caused by a temporary junction resolving Rosetta paths outside the worktree. No code was changed for this path issue. |
| Direct bridge parity | Opening and after-Violet states matched in full adapted `GameState` (apart from static `mechanics`, absent from Rosetta bridge) and sorted legal-action sets. |
| Terminal runs | Native card-action/combat fixture reached terminal. Benchmark: 10/10 pass-only fatigue games reached terminal in each backend, average 67 end-turn transitions. |
| Registry delta | 0 canonical registry changes; 0 verification evidence promoted. 18 roots gained prototype-only executable scenarios, not production or training verification. |
| Verified roots gained | 0 canonical/profile evidence promotions. Prototype case coverage is not `VERIFIED_SCOPED` or rules admission. |
| Dependency closures gained | 0; no canonical closure audit/status changed. Runtime deck selectors were tested only on supplied test decks. |
| Training eligibility delta | 0. No training/evaluation was run. |
| Benchmark delta | After immutable catalog sharing, ManaEngine retained-session working-set delta estimate fell from 424,072 B/session to 546 B/session. Current session creation 9.806 ms median; legal actions 0.0325 ms; end-turn apply 0.0382 ms; clone 0.0010 ms. Full backend comparison: `benchmarks.json`. |
| Recommendation | `HYBRID_MIGRATION`; see `FINAL_REPORT.md`. Rosetta remains production authority. |

The prototype crossed its defined success bar without requiring an architecture review: compatible visible state and legal-action projection, typed choice continuation, runtime-derived choice/deck candidates, deterministic branch cloning, focused parity, and complete prototype match termination. The result is deliberately not a production migration proposal.
