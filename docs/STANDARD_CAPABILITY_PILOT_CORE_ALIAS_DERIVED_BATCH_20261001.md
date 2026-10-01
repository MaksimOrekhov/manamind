# Derived-ID Core alias batch — 2026-10-01

## Scope

Added these fifteen allowlisted Core-to-legacy aliases, each with exact normalized rules-text equality and an existing registered legacy CardDef:

| Core ID | Legacy base | Core ID | Legacy base |
|---|---|---|---|
| `CORE_BT_292` | `BT_292` | `CORE_DRG_256` | `DRG_256` |
| `CORE_EX1_014` | `EX1_014` | `CORE_EX1_189` | `EX1_189` |
| `CORE_EX1_198` | `EX1_198` | `CORE_EX1_310` | `EX1_310` |
| `CORE_KAR_077` | `KAR_077` | `CORE_NEW1_022` | `NEW1_022` |
| `CORE_SCH_713` | `SCH_713` | `CORE_SW_072` | `SW_072` |
| `CORE_SW_429` | `SW_429` | `CORE_TRL_111` | `TRL_111` |
| `CORE_ULD_178` | `ULD_178` | `CORE_UNG_809` | `UNG_809` |
| `CORE_UNG_912` | `UNG_912` |  |  |

These cards have no `countAsCopyOfDbfId`. The generator therefore records `match_basis = DERIVED_CORE_ID_AND_EXACT_RULES_TEXT` only when the ID suffix equals the explicitly allowlisted legacy ID. It still requires a collectible Core root, matching nonempty normalized rules text, an existing base CardDef, available metadata and registered rules sources for fixed dependencies, and unique generated ownership. Cards with random/Discover effects are allowed as registrations but remain blocked by unresolved pool closure.

The 55-card alias manifest is the earlier 40 DBF-linked aliases plus this derived-ID batch. Eleven total alias effects now have unresolved dynamic pools; four of those are in this batch.

## Verification

- Core alias generator validated and emitted all 55 aliases.
- Native CardDef parity: 7 focused cases, 696 assertions passed for all 55 IDs.
- Bridge smoke passed for all 15 new IDs, including Standard deck validation, session creation, opening-hand visibility, and legal-action enumeration.
- Registry suite: 9 tests passed.
- Registry after the batch: 1,185 roots; 167 direct + 77 generated registrations; 151 known non-root nodes; 310 heuristic dynamic-pool signals; 938 text-bearing roots without detected registration; zero complete root closures and zero training-eligible roots.

## Limits

CardDef parity and bridge smoke verify alias ownership and loading, not independent effect correctness. Dynamic Discover/random pools remain unresolved, and all fifteen entries remain `IMPLEMENTED_UNVERIFIED`. No alias is training-eligible from this evidence alone.
