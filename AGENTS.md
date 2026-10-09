# ManaMind — working rules

## Authority and reading order

Latest explicit user instructions take precedence over repository guidance. This file defines durable working rules. Current priorities live only in [docs/MODEL_FIRST_ROADMAP.md](docs/MODEL_FIRST_ROADMAP.md). [README.md](README.md) holds the product brief, architecture and runnable entry points. Do not add a second roadmap, card queue or session diary here.

Read on demand: [docs/REAL_MATCH_DATA.md](docs/REAL_MATCH_DATA.md) (Power.log and datasets), [docs/LIVE_BRIDGE.md](docs/LIVE_BRIDGE.md) (live pipeline), [docs/POLICY_REPRESENTATION.md](docs/POLICY_REPRESENTATION.md) (Policy v1/v2 contracts). ManaEngine and card-support documents ([experiments/manaengine/README.md](experiments/manaengine/README.md), [docs/MANAENGINE_ADMISSION.md](docs/MANAENGINE_ADMISSION.md), [docs/PARTIAL_SIMULATOR_ARCHITECTURE.md](docs/PARTIAL_SIMULATOR_ARCHITECTURE.md), [docs/STANDARD_REGISTRY.md](docs/STANDARD_REGISTRY.md), [docs/CAPABILITY_PACKAGE_PROCESS.md](docs/CAPABILITY_PACKAGE_PROCESS.md)) describe a **frozen optional component**; read them only for a task that explicitly concerns ManaEngine. Everything under `docs/history/`, dated `reports/` and old experiment results is evidence only: its old priorities, resume steps and permissions are inactive and cannot authorize training or choose the next task.

Answer in Russian by default. Explain Python/ML concepts plainly; the user is a frontend developer learning this stack.

## Strategy: Model-first

ManaMind is a desktop Hearthstone adviser built around **its own local neural network** that scores the currently legal actions from the player-visible state, card metadata and card text, accumulated experience and observed action outcomes. It does not automate gameplay: no mouse movement, clicks or game actions.

The main practical scenario is 1–2 user decks in current Standard against varied opponents and states.

Priorities, in order:

1. Short ML experiments with a measurable result.
2. Better Policy decision quality.
3. Generalization to new cards and situations.
4. Use of card texts.
5. Learning from reliable game consequences.
6. Verification on independent game situations.
7. Live integration of a model that has proved useful.

## Experiment rules

- Every experiment states a concrete hypothesis and a baseline before it runs.
- Start with the smallest training that can answer the question; evaluate quickly. Avoid large trainings without a prior positive small result.
- Compare models on identical data and honest splits. Split whole matches by `game_id`, never individual positions.
- Report game quality, imitation accuracy and technical correctness separately; do not merge them into one claim.
- Synthetic training is allowed for controlled skills but does not prove playing strength. Weak-simulator or synthetic results verify plumbing only.
- Keep independent real control data that training never touches.
- Do not change the architecture without a measured need.
- Do not start self-play, mass card implementation or training/evaluation as a side effect of maintenance or on own initiative; a pilot needs explicit user authorization and recorded limits.
- Do not expand ManaEngine without a separate task and a justified benefit for Model-first.
- Do not use or reintroduce RosettaStone. Do not build a second approximate Hearthstone rules engine.

## Information and data contracts

- Model inputs contain player-visible information only: SELF hand, public entities and explicitly revealed opponent cards. Never hidden opponent hand identities, deck order, future draws or RNG outcomes. Entity IDs are action handles, not policy inputs.
- Never substitute invented values for unknown ones: keep missing-value masks and unknown booleans. Preserve unknown/new-card support, ordered SELF hand, shared minion/Location board positions and variable-size zones.
- Keep base card metadata separate from current instance cost/stats/durability; gameplay consumers use effective current values.
- Value targets are for SELF: win 1.0, loss 0.0, draw 0.5. Estimate positions, not context-free card strength.
- Keep data schemas explicit and checkpoints compatible. A checkpoint owns its model config/weights, vocabulary, catalog, feature names, normalization and encoder schema. Reject incompatible schemas; never reinterpret old features. External metadata may supplement unknown IDs but must not change trained vocabulary indices.
- Experiments must be reproducible: pinned inputs, recorded seeds, deterministic outputs where practicable.
- Preserve all checkpoints, datasets, raw logs and historical results. Write to new output paths and temporary smoke directories; never overwrite old results, and do not edit old research results to match new architecture.
- Keep raw logs and imports in ignored `data/raw/` and `data/processed_real/`. Do not expose player names or hidden opponent information. The single-match Power.log limitation remains until mode metadata can be associated safely per game.
- The pinned Standard catalog `data/cards/standard_current_enUS.json` is rebuilt from the pinned HearthstoneJSON snapshot by `scripts/check_generated_artifacts.py`. Do not download or swap a snapshot, or change the Standard composition or model catalog, as a side effect.

## ManaEngine (frozen, optional)

ManaEngine is an independent optional simulator for bounded tactical verification. It is not a prerequisite for training or for live inference on real legal actions, and full Standard coverage is not a requirement. Its development is frozen; extend it only for a separate task with a written Model-first benefit. Its strict rules remain in force: deterministic, fail closed on unsafe or unsupported transitions, never fabricate a plausible transition, never leak full-information cloning into live-game search. Engineering rules for the engine (evidence, admission, native build) live in [experiments/manaengine/README.md](experiments/manaengine/README.md) and [docs/MANAENGINE_ADMISSION.md](docs/MANAENGINE_ADMISSION.md).

## Implementation and verification

- Inspect relevant source and existing tests before editing. Keep modules small; add no dependency or abstraction without a concrete need. Preserve unrelated work.
- The project clones and checks without Git submodules or any native toolchain for Python work.
- Source CI: ruff, offline regeneration of the pinned Standard catalog with a clean `git diff`, full pytest. ManaEngine has its own CMake/CTest/adapter workflow. CI does not train models.
- Update the authoritative document when a requirement changes. Keep experimental results in `reports/`.
