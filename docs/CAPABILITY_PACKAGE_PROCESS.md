# Capability-package card-support process

Effective 2026-10-01. These rules replace card-by-card implementation queues. The implementation unit is a capability package; audit work records gaps without implementing discovered cards.

## Workflow

1. Read the pinned registry/profile and collect gaps and blockers.
2. Group candidates by reviewed semantic contracts: event timing, controller/actor, target rules, zones, sequencing, state/history, randomness and generated outcomes. Similar text is only a discovery hint.
3. Rank packages by reviewed candidate coverage, reachable dependency cost, correctness risk and estimated authoring/review/debug effort. Historical decklists supply regression controls. Missing cards in those lists do not determine the queue.
4. Write a [CAPABILITY PACKAGE PROPOSAL](CAPABILITY_PACKAGE_PROPOSAL_TEMPLATE.md) before engine/generator changes for new card support. Record unknown rules or primitive contracts explicitly and narrow the package until its implementation scope is clear.
5. Implement or reuse one parameterized contract. Express all reviewed in-scope candidates as declarations. Record deferred candidates and custom outliers with reasons; do not silently drop them or add special ID branches to fit them.
6. Use independent family expectations and interaction/negative scenarios. Cover parameter variations, event ownership/timing, invalid targets, relevant silence/copy/death ordering, and exact generated-pool membership where applicable. A smoke test derived from the same declaration is insufficient rules evidence.
7. Update registration ownership, dependency graph, scoped evidence and registry reports. Capture actual effort and correction cycles. Separate registrations unlocked, verified root closures, and training eligibility.

The proposal is a required design record, not a new mandatory user-confirmation step. Existing authorization for reversible work remains subject to the latest task scope. This documentation change starts no card implementation package.

## Technical classification

The following is a proposed metadata design, not a migration of today's registry or an existing API.

| `implementation_kind` | Contract | Implementation boundary | Extension criterion |
|---|---|---|---|
| `GENERIC` | A parameterized primitive/composition operation, e.g. damage by amount and target | Shared operation renderer and strict parameter validation; no card-specific behavioral dispatch | A new matching card changes declarations only |
| `REUSABLE_CAPABILITY` | A versioned family contract involving events, conditions, history or multiple primitives | Named reusable handler/helper plus declarative parameters; no card-specific behavioral dispatch | All reviewed family candidates use the same handler; another matching card changes declarations only |
| `CUSTOM` | Exceptional behavior or semantics that cannot yet be expressed by a reviewed shared contract | Explicit custom/native handler or custom emitter with declared card ownership | Additional code may be needed; count it as custom effort until a reusable contract is established |

`GENERIC` and `REUSABLE_CAPABILITY` describe different abstraction levels. Neither is synonymous with VERIFIED_SCOPED or training eligibility. They also do not replace existing AUTO/COMPOSABLE/MISSING_PRIMITIVE/CUSTOM/UNKNOWN triage routes. A card combining generic and family operations should reference both contracts; any custom behavioral component makes the card's implementation kind CUSTOM.

Suggested contract metadata:

```yaml
contract_id: <stable semantic name>
contract_version: 1
implementation_kind: GENERIC | REUSABLE_CAPABILITY | CUSTOM
package_id: <proposal identity>
parameters: <strict fields, types, bounds, allowed combinations>
semantics: <timing, actor/controller, targets, zones, order, outcomes>
entrypoints: <Python function and/or C++ handler references>
consumer_declarations: <reviewed declaration references>
test_evidence: <independent family expectations and their scope>
limitations: <unsupported interactions and dependencies>
```

For CUSTOM also record explicit `custom_card_ids` and the reason for the exception. Declarations and generated manifests should carry the contract identity/version and implementation kind so classification is traceable. Do not infer these new fields by blindly renaming current COMPOSABLE routes; existing consumers need a contract review.

### One current consumer

A generic contract can have one currently reviewed card. Consumer count alone does not prove or disprove reuse. To justify GENERIC, specify its universal parameters and demonstrate a second independent declaration/control variation that uses the identical renderer without code changes. A hypothetical example is design evidence only, not an additional supported Standard card. A contract containing a special rule for that first ID remains CUSTOM.

Likewise, multiple cards sharing a Python branch do not establish REUSABLE_CAPABILITY if the handler dispatches different behavior by card ID. Validate semantic equivalence, not just the number of consumers.

## Proposed automated guardrail

Add a small source-only `scripts/check_generic_card_branches.py` check before generation in the existing Linux/Windows CI workflow. This checker is proposed here; it is not installed by this documentation change.

### Initial scope

- Inspect Python ASTs under `scripts/generate_*.py` and `scripts/card_rules/`, with explicit entrypoint ownership for generic rendering, shared capability handlers, metadata validation, custom routing and custom emitters.
- Do not exempt an entire generator or validator file: those files can mix metadata validation with behavioral emission. Track the function/block's role.
- Inspect `if`, conditional expressions, `match`, membership tests and literal dictionary dispatch for comparisons/lookups involving `card_id`, `card['card_id']`, `card['id']` or recognized local aliases. Detect literal card IDs and ID allowlist dispatch, not just the spelling `card_id == "X"`.
- Report filename, line, enclosing function, detected IDs and classification. Reject new unclassified identity-based behavior in GENERIC/REUSABLE_CAPABILITY entrypoints.

### Allowed outcomes

1. Replace the identity branch with semantic parameters under a reviewed contract.
2. Move behavior into an explicitly owned CUSTOM handler/emitter and classify all affected declarations/manifests CUSTOM. Check that those IDs cannot be emitted as generic/family behavior; the current `implementation_route` custom boundary can be an initial integration point.
3. For metadata validation/allowlists, require a narrow documented validation role. Checking source fingerprints or permitted declaration IDs can be valid; choosing different effects by ID cannot be exempted as validation.

Start with a reviewed baseline of the existing validator/custom branches. Baseline entries should identify AST structure/function, IDs and reason rather than line numbers alone. CI should detect new or changed branches; enlarging the baseline is a reviewed exception, not an automatic bypass. Existing custom behavior must remain honestly classified, and old metadata guards need not be rewritten just to introduce this check.

### Guardrail fixtures and limits

When implementing the checker, add fixtures for equality with reversed operands, set membership, conditional expressions, match cases, dictionary dispatch, a simple ID-variable alias, an allowed source-fingerprint guard, and a correctly classified CUSTOM emitter. Include a failure fixture where a custom ID is labelled GENERIC in the manifest.

AST scanning is a practical regression detector, not proof of reusable semantics. Indirect dispatch, computed IDs, helper calls and embedded C++ can evade simple analysis. Extend recognized cases when encountered and retain source review. Native shared handlers still require contract review; a Python check does not certify their C++ semantics.

## Unlock accounting

`expected unlock count` must list unique reviewed Standard root IDs, dependency/outcome IDs separately, and unresolved candidates with assumptions. Distinguish newly registerable roots from roots whose full closure and action/scenario gates could become verified. Do not claim that registering N cards creates N training-eligible cards. If a dependency pool is unresolved, state the uncertainty instead of inventing a precise closure benefit.
