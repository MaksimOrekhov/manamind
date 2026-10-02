# Standard registry report — 2026-10-01

Registry: `standard_registry_20261001_v1`. Full Standard admission: **BLOCKED**.

## Pool and implementation inventory

- Collectible roots: **1185**; metadata present: **1185**.
- Source registration: **167** direct, **179** generated manifest entries, **839** text-bearing without detected registration, **0** textless metadata candidates.
- Current rules verification: **14**; historical scoped evidence marked stale: **5**.
- Route proposals: `{"AUTO": 83, "COMPOSABLE": 187, "CUSTOM": 76, "UNKNOWN": 839}` (heuristic; not correctness status).

## Dependency graph

- Unique edge-target nodes, including Standard roots: **193**; unique known non-root dependency nodes: **191**.
- Static literal/reference candidates: **242**, all requiring review or limited declaration evidence.
- Unresolved dynamic pool candidate signals: **318** across **282** Standard roots and **20** known dependency origins; by kind: `{"discover": 100, "generated_card": 68, "random_card_or_pool": 150}`.
- Detector v2 excludes random board targets and fixed named-token summons; pool candidates remain heuristic, not a confirmed or exhaustive pool inventory.
- Complete root closures: **3**. The known graph is a lower bound; absent edges are not proof of no dependency.

## Admission blockers

- Eligible roots: **0** in `standard_full_20261001_v1`.
- Admission blockers: `["bridge_action:not_audited", "dependency:closure_not_reviewed_complete", "dependency:reachable_rules_not_verified", "dependency:static_edges_unreviewed", "dependency:unresolved_dynamic_pool", "evidence:missing_or_incomplete", "evidence:stale_historical_scope", "rules:IMPLEMENTED_UNVERIFIED", "rules:METADATA_ONLY_CANDIDATE", "rules:UNKNOWN", "rules:scope_not_full_profile", "session_match:not_current"]`.
- This report does not authorize or start pooled training.

## Candidate capability packages

Priority is not inferred from metadata frequency. These are review groupings based on text signals; unlock counts remain unknown until capabilities and dependency closures are verified.

| Signal | Candidate roots | Confidence |
|---|---:|---|
| triggered | 693 (507 without detected rules registration) | LOW |
| resource_cost | 372 (273 without detected rules registration) | LOW |
| damage | 212 (117 without detected rules registration) | LOW |
| summon | 212 (173 without detected rules registration) | LOW |
| discover_choice | 146 (115 without detected rules registration) | LOW |
| draw | 129 (80 without detected rules registration) | LOW |
| transform_copy | 68 (60 without detected rules registration) | LOW |
| destroy | 58 (39 without detected rules registration) | LOW |
| heal | 33 (15 without detected rules registration) | LOW |

## Limits

- Route and action family counts are text/source heuristics, not verified mechanic counts.
- Source registration scanning does not prove the currently loaded RosettaStone binary contains those definitions.
- Dependency closure is incomplete: source literals are unreviewed and heuristic dynamic pool candidates have no exact members or runtime parity evidence; random board targets and fixed named-token summons are excluded by detector v2, but the candidate list is not exhaustive.
- Historical VERIFIED_SCOPED audit entries are retained but marked stale for current admission because reproducible build/source identity is absent.
- No 2026-10-01 meta-frequency dataset is attached, so package order cannot be described as current-meta priority.
- The bridge/action audit and session/match gates are not synthesized from old five-deck pilot claims.
