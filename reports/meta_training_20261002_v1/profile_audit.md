# Meta Training Profile v1 audit draft — meta_training_20261002_v1

Pinned source: `standard_full_20261001_v1` / `standard_registry_20261001_v1` (Standard snapshot 2026-10-01).

## Resolution checkpoint

- Frozen decklists and quantities: 10 lists, 300 slots parsed.
- Distinct decklist names: 162; pinned collectible canonical roots: 156.
- Noncollectible Fabled deck entries: 6 distinct candidates; their IDs are external candidates and are absent from the pinned registry.
- Current scoped-verified roots in this profile: 11; current under canonical Standard registry evidence: 3; stale historical evidence: 5.
- Registered but not current-verified roots: 85; roots with no detected registration: 68.
- Distinct classes in the frozen lists: 9 (Demon Hunter, Druid, Mage, Paladin, Priest, Rogue, Shaman, Warlock, Warrior).

The six Fabled entries remain visible in the slot list because the frozen source lists them. They are not collectible Standard roots. The profile keeps their externally matched IDs as candidates only; they require explicit dependency metadata and runtime verification. `Scarlet Bruiser` remains a separate Beatrix dependency with unresolved ID.

## Closure and admission

The Standard registry reports 0 Standard roots with complete closure and 0 roots training-eligible in its full-profile scope. Meta-scoped closures are therefore not inferred from these global figures.
The profile roots reach 42 known source-candidate dependency-node occurrences across decks and 41 unique unresolved pool definitions. Candidate edges are not reviewed closure; source metadata may omit real outcomes.

No deck currently has a complete meta closure or current profile session/match evidence. `configs/standard_profile.json` has no `session_match_evidence`. Meta-profile scoped evidence is checked separately against the pinned Standard execution identity and manifest hash `44d5f33b41562656e7b9c831063bc8c96b274a00cab71ec45ea2871b1087bd4a`; it does not make a root training-eligible in the canonical Standard registry. The current registry also marks all six candidate seed IDs absent from its pinned root/dependency inventory.

## Stop/continue assessment

The chosen classes and archetypes are structurally useful, and the user-approved reserve deck can cover one disproportionate blocker. The profile is not yet implementation-ready as an exact simulator manifest: six listed Fabled entries and the extra Scarlet Bruiser lack pinned dependency records, and no complete root/dependency closure exists. Do not silently treat these as Standard collectible roots or shrink their outcomes. Initial package work can proceed only on exact pinned collectible roots whose contract and dependencies are independently reviewed; Fabled/session work remains a separate explicit blocker.
