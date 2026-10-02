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

Implement shared dynamic pools when a reviewed package or profile actually needs them. Do not build every possible pool before that demand exists. Preserve the distinction between heuristic/source candidate edges, reviewed rule edges and runtime parity evidence; candidate graph growth does not itself close a dependency.

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

### Proposed bounded training profile

A separately pinned, fully verified training profile can precede full Standard completion. This is a strategy proposal, not an existing dedicated profile or authorization to select decks/start training. The full Standard target remains active. If the user approves this direction, define a finite deck/root scope, legality snapshot and sampling purpose, then include **all actually reachable outcomes** transitively. Prefer a scope with manageable dependencies; do not alter real card rules or silently narrow random/Discover pools. A bounded deck scope with exact rules differs from an approximate restricted-outcome pilot, which must be labelled separately.

Apply the same rules, closure, action/observation and session/match gates to the entire selected profile. Record class/hero/hero-power initialization, legal action progression, turn transitions and termination/results, relevant interactions, hidden-information checks, loaded build/bridge identity, profile fingerprints, run/seed coverage and incomplete/invalid episode rates. Successful games alone do not prove all required rules. Evidence producers and profile tooling must support that explicit scope before it can be admitted; an old full-Standard report or a manually selected deck list is insufficient.

Choose the first scope from reviewed capability coverage and dependency cost, not a fixed number of decks/cards. Measure package and match-gate work before estimating a date. Existing Value/Policy plumbing can then be assessed on valid data and held-out matches; this proposal does not require a new model architecture or authorize evaluation now.

## Rebuild and update

The `minion_set_enchant.v1.json` declaration installs a bounded validated schema
for its package/contract identity, implementation kind, finite effects and two
existing fixed-enchantment owners. Its generated manifest is recognized by the
canonical registry. Matching explicit execution evidence controls contract
review, scoped rules/actions and reviewed closure; the manifest alone does not
upgrade those gates. This is not a migration of legacy generator schemas.

```powershell
.\.venv\Scripts\python.exe scripts/generate_minion_set_enchant.py
.\.venv\Scripts\python.exe scripts/build_native_identity.py
.\.venv\Scripts\python.exe scripts/verify_minion_set_enchant.py
```

Configure the existing native build first when adding its new source/test files.
The verifier's approved card/dependency scope is fixed independently of renderer
reuse. Additional declarations require new reviewed expectations/evidence; they
are never automatically verified by an existing producer. Its controlled
fixtures and Druid/Priest opening checks do not close full session/match gates.

For unchanged pinned inputs:

```powershell
.\.venv\Scripts\python.exe scripts/build_standard_profile.py
# Run the applicable declaration generators after changing their reviewed inputs.
.\.venv\Scripts\python.exe scripts/build_standard_registry.py
.\.venv\Scripts\python.exe scripts/check_generated_artifacts.py
```

The last command verifies reproduction against the saved outputs, so expected changes must first be generated/reviewed. Tools accept `--profile PATH`; generators also accept `MANAMIND_STANDARD_PROFILE`. Do not use the older latest-feed catalog/overlay scripts to overwrite the selected pinned profile independently.

A patch/rotation creates new versioned scope/archive/bans/profile and a diff: added/removed roots, rules/stat changes, Core reissues and affected pool memberships. Review the impacted capabilities/dependencies, regenerate outputs and reassess evidence. Use unchanged evidence only under its documented matching-fingerprint policy. Publish the new profile only after its inputs are reviewed; changing a profile does not automatically admit training.
