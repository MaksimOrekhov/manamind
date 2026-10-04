# H6 verification completion

Scope: Phase 4B semantic Policy action cleanup, then architecture/rules stop before card implementation. Baseline 8413065; branch codex/manaengine-first-deck.

| Check | Observed local result |
|---|---|
| Focused Policy/schema | 25 PASS, 3.59s after one legacy-fixture correction |
| Full Python suite | 88 PASS, 11.42s |
| Adapter/pipeline/new semantic tests | 40 PASS, 26.07s |
| Native CTest | 1/1 PASS, 34.07s; unchanged native suite from correctness checkpoint |
| Ruff | PASS, including train_selfplay.py and adapter tests |
| Generic branch guard | PASS, 201 pre-existing reviewed exceptions |
| Regeneration | 36 pinned outputs reproduced on repeat |

There were zero native source edits and zero native rebuilds locally; the existing same-source Debug build was reused. Hosted CI independently rebuilds Release on Windows/Ubuntu. Workflow now includes the new semantic tests, producer path and Phase 4B reports.

Policy feature names are appended, with schema version 2 plus known masks. Legacy migration is tested, not an implicit interpretation of old features. State encoder stays schema 14: no GameState/state-vector change. No Policy/Value training experiment or search was run.

First regeneration correctly reported stale registry/summary after action-encoder changes. Second run reproduced all outputs. Observation fingerprint changes from e195e293e38b45f224d88c680909288f6d8ef9ed7cb1ba5de9b43c0c28873edb to a54cee582bc4da06e8b50d531f5edf4af775f0f542b4a02ac60c5b40c992e5e9. Registry counts, source engine/bridge identity, membership and admission are unchanged. No native evidence or rules status was promoted.

H6 is a shared Python interface repair, not a card package. New root/dependency closures: 0; native capabilities: 0; CUSTOM declarations: 0; training delta: 0. One fixture correction and two focused test runs; one full suite/adapter/native run each. No numerical future throughput forecast is justified.

First recorded timer: 2026-10-04 10:29:17 UTC. The four-hour limit was not exhausted; the earlier exact-rules/core-contract checkpoint was reached. Hosted links and final measured interval will be added after actual acceptance checks. Current local checks pass; hosted acceptance pending at this commit.

Read [STATUS_AND_ARCHITECTURE_CHECKPOINT.md](STATUS_AND_ARCHITECTURE_CHECKPOINT.md) for concrete contradictory aura-timing behavior, alternatives and stop rationale; [RANDOM_DISTINCT_DAMAGE_PROPOSAL.md](RANDOM_DISTINCT_DAMAGE_PROPOSAL.md) records package A. Do not resume B-E automatically. Verdict: ARCHITECTURE_REVIEW_REQUIRED, not DECK_READY.
