# Standard registry: scope, dependencies and admission

This is the current technical contract. Card-support execution follows the [capability-package process](CAPABILITY_PACKAGE_PROCESS.md). Historical plans and dated reports are not implementation queues.

## Source of current facts

`configs/standard_profile.json` selects the dated scope, metadata archive, collectible roots, bans, catalog, engine overlay, canonical registry, reports and evidence inputs. Read the selected generated summary for current counts and admission; this document does not copy them.

The initial full-Standard registry milestones (snapshot, registry, classifier proposals, graph, computed blockers/admission and reports) have been implemented. Their existence does not prove complete rules or dependency coverage. Next card work begins with grouping/ranking and a package proposal, not a missing-card list.

## Pool and metadata contract

- Target all collectible roots of the pinned Standard snapshot and every recursively reachable rule dependency. Required outcomes may be non-collectible or outside Standard; they do not thereby become legal deck cards.
- Distinguish metadata membership, deck legality and availability through generation. Apply bans according to their actual scope; do not automatically remove banned deck cards from random/Discover outcomes.
- Keep Preview/unreleased data separate. Approved early-access exceptions are explicit IDs in the pinned scope, not permission to add an entire future set. Do not infer current legality from a legacy CORE label or a Core/legacy text match.
- HearthstoneJSON is versioned metadata, not executable rules. Record archive/source identity, capture date, reviewed scope/bans and fingerprints. Never silently fetch a new feed into an existing profile.
- Roots, generator catalog and engine overlay must describe the same approved membership. Metadata presence and a vocabulary entry do not implement effects or create useful training labels.

## Registry ownership and axes

The registry consolidates provenance/statuses; declarations and native definitions own executable rules. Do not create a second editable rules source in the registry.

Keep separate axes for metadata/version, deck legality, implementation route, rules verification, dependency verification, bridge/action support and evidence freshness. Classifier AUTO/COMPOSABLE/MISSING_PRIMITIVE/CUSTOM/UNKNOWN routes are proposals, not registrations or correctness. GENERIC/REUSABLE_CAPABILITY/CUSTOM implementation-kind metadata is proposed in the process guide and is not yet a replacement registry API.

Rules statuses and scoped evidence must state what was actually verified. UNKNOWN, PARTIAL, STALE and conflicting inputs do not become PASS. Source registration scans and generated manifests do not certify a loaded binary. When runtime inventory is unavailable, retain that limitation.

Generated reports/queues derive from a registry version. Historical manual analyses explain decisions but cannot override current computed facts. Do not describe a fixed five-deck control sample as current-meta frequency; dated frequency data is required for that claim.

## Dependency graph

Audit tokens, enchantments, choice options, appendages, transforms, rewards, generated spells/weapons/hero powers and random/Discover outcomes transitively. Source literals are candidate edges requiring review. Random board targeting does not create a card pool.

Dynamic pools need a versioned predicate, source-rules identity, snapshot membership/hash and parity evidence. Reuse pool definitions across consumers. For state/history-dependent pools, record an exact filter and a reviewed upper bound where possible; an upper bound alone does not prove runtime selection correctness. Missing membership/filter/recursive coverage stays unresolved.

Handle cycles with a fixed-point/SCC or equivalent deduplicated traversal. A cycle is not automatically invalid; every required node and outgoing outcome must be supported. Resource/depth limits produce INCOMPLETE, not a successful closure.

Report unique-root closure coverage, unique dependency counts, unresolved graph scope and blocker paths. Edge percentages alone can be misleading for shared pools. The known graph is a lower bound until reviewed completeness is established.

Never shrink a random/Discover pool to implemented cards to make a full Standard claim. Unsupported outcomes invalidate the affected episode/labels. Restricted-pool experiments require explicit user authorization, a distinct approximate profile and separate outputs.

## Evidence and training admission

Canonical generation consumes explicit evidence and source/profile fingerprints; it does not inspect whichever ignored native binaries happen to exist locally. Native producers check the configured build identity and the bridge actually loaded before recording successful execution.

Full-profile admission requires all of:

1. Correct pinned metadata/legality for the applicable deck roots and outcome rules for generated dependencies.
2. Current rules evidence covering the full required profile, rather than only a limited package scenario.
3. Explicitly reviewed complete reachable closures, current full-scope reachable rules, and no unresolved dynamic outcomes.
4. Reviewed bridge/action and observation contracts without hidden-information leakage.
5. Current profile session/match gates, including class setup and relevant interactions.

An empty profile cannot pass. Registration, scenario success, closure, match completion and training eligibility are distinct gates. Deck/root/admission counts are computed, not manual flags. Historical pilots cannot satisfy stricter current gates.

Changes to rules/metadata, capabilities, declarations/output, native/bridge/actions, scenario expectations or pool predicates/membership/outcome rules invalidate affected evidence. Equal pool membership does not preserve evidence if its predicate or outcome rules changed. If the impact scope is unknown, invalidate conservatively. Retain earlier evidence as dated history; CURRENT means matching applicable inputs, not merely an old PASS statement.

Training data quality remains a separate requirement: valid complete episodes, reviewed sampling/deck distribution, diverse states, match-level splits and held-out evaluation. Scoped correctness or a weak baseline win rate is not established game strength.

## Rebuild and update

For unchanged pinned inputs:

```powershell
.\.venv\Scripts\python.exe scripts/build_standard_profile.py
# Run the applicable declaration generators after changing their reviewed inputs.
.\.venv\Scripts\python.exe scripts/build_standard_registry.py
.\.venv\Scripts\python.exe scripts/check_generated_artifacts.py
```

The last command verifies reproduction against the saved outputs, so expected changes must first be generated/reviewed. Tools accept `--profile PATH`; generators also accept `MANAMIND_STANDARD_PROFILE`. Do not use the older latest-feed catalog/overlay scripts to overwrite the selected pinned profile independently.

A patch/rotation creates new versioned scope/archive/bans/profile and a diff: added/removed roots, rules/stat changes, Core reissues and affected pool memberships. Review the impacted capabilities/dependencies, regenerate outputs and reassess evidence. Use unchanged evidence only under its documented matching-fingerprint policy. Publish the new profile only after its inputs are reviewed; changing a profile does not automatically admit training.
