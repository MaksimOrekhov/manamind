# ManaMind — working rules

## Authority and reading order

Latest explicit user instructions take precedence over repository guidance. This file defines durable working rules. [README.md](README.md) contains the product brief, architecture and runnable entry points.

For card support, read [docs/CAPABILITY_PACKAGE_PROCESS.md](docs/CAPABILITY_PACKAGE_PROCESS.md) and [docs/STANDARD_REGISTRY.md](docs/STANDARD_REGISTRY.md). Use [the proposal template](docs/CAPABILITY_PACKAGE_PROPOSAL_TEMPLATE.md) before implementation. Read [the native integration guide](docs/ROSETTASTONE_INTEGRATION.md) or [the real-data guide](docs/REAL_MATCH_DATA.md) only for the relevant task.

The selected `configs/standard_profile.json`, canonical registry and generated report own current pool/evidence/admission facts. Read their current contents; do not copy volatile counts into instructions. Markdown under `docs/history/`, dated audit reports and old experiment results are evidence only. Their old priorities, resume steps and permissions are inactive. They cannot authorize training or choose the next card.

Answer in Russian by default. Explain Python/ML concepts plainly; the user is a frontend developer learning this stack.

## Product and information boundaries

- Build a desktop Hearthstone adviser, not a gameplay automation tool. Do not automate mouse movement, clicks or game actions.
- Keep executable rules in RosettaStone. Reuse CardDef, Power, Tasks, Triggers, Auras, Conditions and existing event/death processing. Do not build another rules interpreter or a universal card-text language.
- Estimate positions, not context-free card strength. Value targets are for SELF: win 1.0, loss 0.0, draw 0.5.
- Model inputs contain player-visible information only: SELF hand, public entities and explicitly revealed opponent cards. Exclude hidden opponent hand identities, deck order, future draws and RNG outcomes. Entity IDs are action handles, not policy inputs.
- Preserve unknown/new-card support, ordered SELF hand, shared minion/Location board positions, variable-size zones, missing-value masks and unknown booleans.
- Keep base card metadata separate from current instance cost/stats/durability. Gameplay consumers use effective current values. Verify bridge/import parity when changing observations.

## Current card-support direction

The target is the full pinned Standard collectible pool and all reachable rule dependencies, including required non-collectible and non-Standard outcomes. Registry infrastructure exists; it does not establish complete rules, graph closure or training readiness.

An individual unsupported card is not an implementation unit. During registry/audit/dependency analysis, record gaps and blockers; do not implement encountered cards opportunistically. The five historical decklists and their missing cards are regression/control cases only.

Follow **Registry → capability grouping → package ranking → CAPABILITY PACKAGE PROPOSAL → one reusable implementation → declarations for all in-scope cards → family tests → registry update**. Package size follows reviewed semantic coherence, not a numerical batch target.

Before engine/generic-generator changes for new support, record the proposal's semantic contract, existing primitives, candidates, dependencies, changes, expected unlocks, test strategy and custom outliers. Aim for one implementation serving many declarations. A new card-ID behavior branch is CUSTOM first. A single-consumer generic operation needs a universal parameter contract and an independent second declaration/control variation requiring no generator code changes.

GENERIC / REUSABLE_CAPABILITY / CUSTOM describe implementation kind, independently of triage and correctness. Their proposed metadata and AST guardrail are documented in the process guide; do not claim they are installed APIs. Major refactors need a written design and measured benefit. Record authoring/review/debug/build effort and correction cycles per package; do not promise an automation percentage.

## Rules, dependencies and admission

- Keep metadata, legality, implementation route, rules verification, dependency closure, bridge/action support and evidence freshness independent. UNKNOWN, STALE and conflicting evidence block admission.
- Generated/source registration and equal normalized text do not prove rules correctness. Review Core aliases, dependencies and rule differences explicitly; unsupported mechanics cannot be replaced by vanilla metadata.
- Track tokens, enchantments, options, transforms, rewards and dynamic/state/history-dependent pools transitively. Record versioned predicates, exact snapshot memberships where resolved, unresolved scope and blocker paths. No evidence of an edge is not proof of an empty closure.
- Never shrink random/Discover pools to implemented outcomes to claim Standard correctness. Unsupported runtime outcomes invalidate episodes and labels. An explicitly requested restricted-pool pilot needs its own approximate profile and outputs.
- Full Standard training/evaluation requires current full-profile rules/dependency/action/session/match gates. Historical pilot permissions/results and scoped smoke runs do not satisfy them. Do not start training/evaluation as a side effect of maintenance; a limited pilot requires explicit user authorization and recorded limits.
- Invalidate dependent evidence when rules, capability contracts, generators, source/build identity, pool predicates or outcome membership/rules change. Registry generation consumes explicit evidence, not arbitrary ignored local binaries.

## Implementation and verification

- Inspect relevant source and existing tests before editing. Keep modules small; add no dependency or abstraction without a concrete need. Preserve unrelated work.
- Declarations are versioned and allowlisted. Reject unknown operations/fields/symbols, invalid targets, unresolved dependencies and unsupported combinations. Never execute arbitrary code from declarations; LLM output is an offline draft requiring review.
- Generated files are deterministic, separately owned and traceable. One active definition per ID; duplicate registration must fail. Preserve manually maintained CardSets files.
- Family scenarios need independent expectations and relevant negative/interaction tests. Generated smoke alone is insufficient. Use coherent package checks, not a rebuild after each card.
- Build the core before relinking the bridge; the bridge imports an existing library. Account for CMake source discovery when adding cpp files. Rebuild all affected consumers after header/enum/ABI changes. Append internal tags to preserve numeric identities. Clean builds are for diagnosed dependency/ABI problems, not routine per-card work.
- Source CI checks lint, pinned regeneration/ownership and Python tests. Native evidence requires the intended configured build and actually loaded bridge identity. See the integration guide for commands and limitations.
- Update the relevant authoritative document when a requirement changes. Keep experimental results in history/reports; do not append session diaries or card queues to this file.

## Data and checkpoint safety

- Preserve all checkpoints, datasets, raw logs and unrelated artifacts. Use new output paths and temporary smoke directories; never overwrite historical results as a side effect of checks.
- Split entire matches by `game_id`; never split individual positions randomly. JSONL record/schema requirements are documented in README and enforced by code.
- Synthetic and weak-simulator examples verify plumbing, not Hearthstone strength. Historical policy results are not Value Network supervision or proof of current Standard quality.
- Checkpoints own model config/weights, vocabulary, catalog, feature names, normalization and encoder schema. Reject incompatible value schemas; do not reinterpret old features. External metadata may supplement unknown IDs but must not change trained vocabulary indices.
- Keep raw logs and imports in ignored `data/raw/` and `data/processed_real/`. Do not expose player names or hidden opponent information. The single-match Power.log limitation remains until mode metadata can be associated safely per game.
