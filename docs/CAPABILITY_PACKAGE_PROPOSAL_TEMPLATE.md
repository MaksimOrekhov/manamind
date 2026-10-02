# CAPABILITY PACKAGE PROPOSAL

Create one proposal per semantic package before engine/generic-generator changes for new card support. Fill each field; use UNKNOWN with its blocking question where evidence is missing. This template selects no cards and authorizes no new implementation wave.

## package_id

Stable package identity, proposal revision/date, pinned Standard profile and registry inputs.

## semantic capability

Contract name/version and proposed GENERIC / REUSABLE_CAPABILITY / CUSTOM classification. Describe timing, actor/controller, targeting, zones, sequencing, state/history, randomness and supported combinations. State why another matching card can be added by declaration alone.

## existing RosettaStone primitives

Reviewed Tasks, Triggers, Auras, Conditions and engine contracts, with source references and limitations. File presence alone is not capability evidence.

## candidate cards using the same semantics

| Root ID | Rules/source fingerprint | Contract parameters | Existing/new support | Review status |
|---|---|---|---|---|
| <reviewed ID> | <pinned reference> | <declaration fields> | <status> | <reviewed/unknown> |

Separate confirmed in-scope candidates, provisional candidates and regression/control cases. Similar text alone does not establish membership.

## dependencies

Literal tokens/enchantments/options and transitive outcomes; exact dynamic-pool predicates and versioned membership where known. List missing/unknown rules, action support, state-dependent pools and closure blockers.

## required engine/generator changes

Shared implementation/entrypoints, strict parameter schema, declaration ownership, contract version changes and evidence invalidation. Explicitly answer whether any new card-ID behavior branch is required. If yes, classify that behavior CUSTOM and isolate it. For a single-consumer generic operation, provide a second independent declaration/control variation requiring no generator-code change.

## expected unlock count

Unique reviewed root IDs becoming registerable: <count and IDs>.

Known dependency/outcome IDs: <separate count and IDs>.

Potential verified closures/admission benefit: <evidence-based estimate or UNKNOWN, assumptions and gates>. Registration count is not training eligibility. Record estimated authoring, review, debug and incremental build effort for package ranking.

## test strategy

Independent family expectations, parameter variations, edge/negative cases, relevant interactions and pool membership checks. Define scoped native/bridge checks, ownership/regeneration checks, affected-consumer rebuild requirements and how evidence/registry will be updated. Do not derive all expected results from the implementation declaration.

## custom outliers

IDs, semantic differences, explicit custom owners and reasons for exclusion/deferment. Do not add special generic branches to fit these cards. Record follow-up packages/gaps without opportunistic implementation.

## Completion record

Actual shared changes, all delivered/deferred declarations, family evidence, registry/closure delta, correction cycles and measured effort. Compare expected and actual unlocks without conflating registration with verified behavior or training readiness.

| Measurement | Before/forecast | Actual after package |
|---|---|---|
| Unique registered roots / verified closures / eligible roots | <separate counts> | <separate counts> |
| Declaration-only consumers / consumers requiring custom changes | <reviewed candidates> | <IDs and counts> |
| Shared contract/renderer/native changes | <planned changes> | <actual changes> |
| Authoring / review / debugging / build effort | <estimate or UNKNOWN> | <measured time; measurement limits> |
| Correction cycles and check/build runs | <plan> | <actual counts> |

Record an independent declaration/control variation demonstrating reuse without generator changes. If the package reuses an existing contract with zero shared changes, report zero; do not invent a ratio with a zero denominator. Deferred dependency gates remain blockers even when every declaration is delivered.
