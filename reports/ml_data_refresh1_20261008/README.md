# ML-DATA-REFRESH-1 — Canonical real-policy dataset rebuild

Result: `COMPLETE`

The Policy corpus was rebuilt from the current local Power.log collection using the existing segmented ML-1B importer. This is a data refresh only: no model training, evaluation, encoder/schema changes, or changes to live/ManaEngine behavior were made.

## Provenance and reproducibility

- Exact base: `3c0cb5db76a306fc3c7bb86ed32d3e99af17e377` (`origin/main` at task start).
- Branch: `codex/ml-data-refresh-1`; workflow source revision: `f90e8a39ab7bb590fe8270e6cf8f46a948dc4fc9`.
- Raw inputs: 36 `.log` files, 148,951,694 bytes. Four reset/incomplete matches were rejected as `GAME_RESET`; 32 matches were admitted.
- Two independent imports produced the same canonical content identity: `730303e1f9d89af7609e48ceab57ac3b2265ca8672e282cf957541f9c3f367dd`.
- Admitted dataset: 32 matches / 1,227 decisions; dataset identity `60351703209b5cda69caa84364994e7763c43b6baba3d8a6d65181e3c7e96cb9`.
- Catalog identity: `3dfae0cb5fe312af22c2a16e01eba1286c073f89ea020808fbbf1778067870d9`.
- Existing contracts retained: real-policy dataset schema 1, state encoding 16, policy action 4, semantic action 1. The checkpoint loader successfully validated the existing v1 and v2 checkpoint provenance; their exact SHA-256 values are stored in the ignored local usage registry.
- Comparison with the previous 32-match / 1,227-decision corpus found no decision, action label, legal-menu, outcome, or non-schema state differences. All 1,227 serialized states now explicitly include the current `healing_bonus: null` field; this is a serialization compatibility repair through the canonical importer, not a change in observation meaning.

The corpus and per-match registries remain under `data/processed_policy_real/refresh_20261008` and are Git-ignored. The two determinism outputs are also ignored. No raw log excerpt, player identity, or per-match identifier is included in this report.

## Experiment-use registry and split safety

The local registry records the frozen v1/v2 match-level split provenance (17 train / 2 validation / 2 test matches; 591 / 85 / 60 decisions) and the 12-match / 515-decision ML-EVAL-0 inference cohort. The ML-1C/ML-2A historical corpus identity remains `2b20c3b0fd48c34031dfbb8cf516cda9679ce53fee21843e0fc8613609f0b598` (21 matches / 736 decisions). The prior ML-EVAL-0 corpus identity remains `bc5d9c8667bcd5dbf2a6f26297a843c22d8cfdfe73b3a6dafafc825821f54b18` (32 matches / 1,227 decisions).

All 32 currently admitted matches are already assigned to prior training, validation, test, or ML-EVAL-0 inference use. The four rejected reset matches contribute no admitted decisions. Therefore the refresh proposes no clean three-way split (0 eligible matches / 0 decisions). No fresh holdout was created, and no historical split or test result was changed or reused as a new evaluation.

## Data quality observations

- Outcomes: 18 wins, 14 losses, 0 draws. SELF class is concentrated: 29 Priest matches and 3 Warrior matches.
- 335 decisions were skipped by existing admission rules: 254 `AMBIGUOUS_SELECTION`, 79 `OPTIONS_SUPERSEDED`, and 2 `CHOICE_UNRESOLVED`.
- 299/1,227 admitted decisions are targeted; legal-menu sizes range from 1 to 69 actions.
- The unknown public-card identity ratio is 26.31% under the existing audit definition.
- `healing_bonus` remains unknown in the available observations. Turn number is also unavailable in these imported decisions. No deck identity is inferred from partial visible-hand snapshots.

These are observable limitations of this corpus, not evidence of model quality or playing strength. No model was trained and no new predictive metrics are claimed.

## Validation

- New refresh tests plus existing real-policy dataset tests: **36 passed**.
- Ruff across the repository: **passed**.
- `git diff --check`: **passed**.
- Full pytest: **490 passed, 1 skipped, 26 errors and 3 failed**. All 29 failures stem from the isolated worktree lacking the initialized `vendor/RosettaStone/Resources/cards.json` pinned submodule needed by those existing tests. The pinned submodule revision is present in the main checkout; the worktree was left unmodified rather than linking/copying that unrelated private checkout into it.
- Rebuilt corpus and determinism directories were verified Git-ignored; no private data is staged or committed.

## Recommended next task

Collect at least three new, complete, admitted matches with match-level identities disjoint from every registered v1/v2 and ML-EVAL-0 cohort. Then freeze a new whole-game split before any training or tuning. Expand class/deck and unknown-card coverage where possible; keep prior held-out matches out of model selection.

ML-DATA-REFRESH-1 = COMPLETE

