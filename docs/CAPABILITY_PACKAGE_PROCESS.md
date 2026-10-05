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

## Rules uncertainty disposition

For each capability whose Hearthstone semantics are not fully established,
classify the uncertainty before implementation:

1. **REVIEWED / sufficiently established.** Implement the reviewed contract
   with strict semantics and ordinary family verification.
2. **FINITE BOUNDED UNCERTAINTY.** Runtime may use `REVIEWED_INFERRED` only
   when the assumption and scope are explicit, the behavior/outcome set is
   finite and deterministically representable, the project has approved the
   assumption, and a concrete invalidation condition is recorded. Keep
   evidence debt attached. This status is not rules verification or canonical
   training permission.
3. **UNSAFE / UNBOUNDED UNCERTAINTY.** If uncertainty changes legality,
   hidden-information boundaries, target topology, unbounded state mutation,
   passive/held behavior, or otherwise cannot be bounded safely, fail closed
   and defer the capability pending rules evidence or design review.

`REVIEWED_INFERRED` is not permission to guess arbitrary rules. Any package
using inferred behavior records the assumption, scope, provenance,
client/build/version, invalidation condition and canonical-training impact.
Keep runtime execution, rules/evidence basis, dependency closure and training
eligibility as separate axes. See [Partial Simulator Architecture](PARTIAL_SIMULATOR_ARCHITECTURE.md)
for the project-wide status model.

## Technical classification

The table defines the classification design; it is not a migration of all legacy
generators. The first bounded implementation, `minion_set_enchant_v1`, validates
contract/package/version/kind fields and exposes them through its generated
manifest and canonical registry consumer. Other schemas remain unchanged.

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

For CUSTOM also record explicit `custom_card_ids` and the reason for the exception. New-package schemas should introduce contract identity/version, package identity and implementation kind together with their validation and consumer support. These fields are not installed in all current declarations/manifests. Do not infer them by blindly renaming current COMPOSABLE routes or migrate every historical manifest as a prerequisite. Existing consumers need a contract review; the current CUSTOM route/list remains the operational boundary until a separate migration is justified.

### One current consumer

A generic contract can have one currently reviewed card. Consumer count alone does not prove or disprove reuse. To justify GENERIC, specify its universal parameters and demonstrate a second independent declaration/control variation that uses the identical renderer without code changes. A hypothetical example is design evidence only, not an additional supported Standard card. A contract containing a special rule for that first ID remains CUSTOM.

Likewise, multiple cards sharing a Python branch do not establish REUSABLE_CAPABILITY if the handler dispatches different behavior by card ID. Validate semantic equivalence, not just the number of consumers.

## Automated source guardrail

`scripts/check_generic_card_branches.py` runs before generation in the Linux/Windows source CI workflow. It parses source ASTs without importing generators or executing declarations. Run it locally with:

```powershell
.\.venv\Scripts\python.exe scripts/check_generic_card_branches.py
```

### Initial scope

- Inspect Python ASTs under `scripts/generate_*.py` and `scripts/card_rules/`. New detected identity logic fails by default, including in custom files; no whole-file exemption exists.
- Inspect `if`, conditional expressions, `match`, comparisons (also in assertions/comprehensions), ID-indexed lookups and `.get(ID)`. Recognize conventional ID variables, simple assignment aliases, ID fields and literal ID allowlists.
- Report filename, line, enclosing function and detected IDs. Existing exceptions in `configs/generator_branch_policy.json` pin the function, AST hash, IDs and occurrence count, with a reviewed role and reason. Adding an identical branch also changes its count and fails.
- Exception roles are `METADATA_VALIDATION`, `CUSTOM_ROUTING` and `CUSTOM`. They describe a narrow source exception, not rules-verification status or a new registry API. No GENERIC/REUSABLE_CAPABILITY behavior exemption is provided.

### Allowed outcomes

1. Replace the identity branch with semantic parameters under a reviewed contract.
2. Move behavior into an explicitly owned CUSTOM handler/emitter and classify all affected declarations/manifests CUSTOM. Check that those IDs cannot be emitted as generic/family behavior; the current `implementation_route` custom boundary can be an initial integration point.
3. For metadata validation/allowlists, require a narrow documented validation role. Checking source fingerprints or permitted declaration IDs can be valid; choosing different effects by ID cannot be exempted as validation.

The baseline preserves existing metadata restrictions and exceptional emitters. Changing it requires source/semantic review; do not regenerate it automatically to make CI green. CUSTOM exceptions list owning generated cards. The checker requires unique generated owners and current `implementation_route: CUSTOM` (and CUSTOM implementation kind when present) for those owners and the existing `CUSTOM_EMITTER_CARD_IDS` list. Dependency IDs such as enchantments can differ from their owning root IDs. This ownership check does not establish correctness or inspect every native definition.

### Limits and future verification

The checker has been run on current repository sources; dedicated regression fixtures remain follow-up work. Cover reversed equality, membership, conditional expressions, match cases, dictionary dispatch, simple aliases, duplicate occurrences, permitted metadata checks and CUSTOM ownership rejection when verification work is requested.

AST scanning is a practical regression detector, not proof of reusable semantics. Computed IDs, interprocedural dataflow, aliases hidden in annotated/walrus assignments, function defaults/decorators and embedded C++ are not comprehensively tracked. Extend recognized cases when encountered and retain source review. Native shared handlers still require contract review; a Python check does not certify their C++ semantics.

## Unlock accounting

`expected unlock count` must list unique reviewed Standard root IDs, dependency/outcome IDs separately, and unresolved candidates with assumptions. Distinguish newly registerable roots from roots whose full closure and action/scenario gates could become verified. Do not claim that registering N cards creates N training-eligible cards. If a dependency pool is unresolved, state the uncertainty instead of inventing a precise closure benefit.

For each completed package, record declarations delivered without card-specific generator/native changes, cards requiring custom code, shared contract changes, correction cycles and authoring/review/debug/build effort. Compare before/after closure and admission as well as registration. Prove reuse with a matching declaration requiring no shared code change; shared file placement alone is insufficient. A declaration-only package using an existing contract can have zero new shared changes; report that directly rather than an undefined automation ratio. Measure the first real package before promising throughput or completion dates.
