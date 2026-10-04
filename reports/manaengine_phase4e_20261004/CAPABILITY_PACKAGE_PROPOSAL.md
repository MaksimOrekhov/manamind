# Capability package proposal — Phase 4E

## `finite_pool_generated_instance_v1`

- **Semantic contract:** sample one canonical identity uniformly from an immutable, versioned finite pool; invalidate if the selected outcome is unavailable/unsupported; create a fresh generated `CardInstance`; apply only the reviewed additive `cost_delta`; send it through the existing `enter_hand` path.
- **Existing primitives:** pinned metadata snapshots and candidate pool audits; `std::mt19937_64` bounded sampling; fresh entity IDs/provenance; `enter_hand`, Shatter guards, current-cost calculation, clone-by-copy, and SELF hand observation.
- **Candidates:** Fire spell candidates for future Vulcanos appendages (33 metadata candidates); Whelp 1-cost spell candidates (77 raw; 63 current provisional non-Quest class spells). Neither exact runtime membership is admitted by this package.
- **Dependencies:** standard profile ID/date and exact source-snapshot hash; canonical IDs; independent generation-eligibility evidence; a matching full `CardCatalog` entry for any runtime outcome.
- **Required changes:** typed immutable `PoolManifest`; strict version/status/predicate/metadata/membership validation; deterministic membership and rules fingerprints; `ReviewedPoolRef`; `GeneratedInstanceModifiers{additive_cost_delta}` with a manifest-backed pool identity; one generic generation operation and an explicit full-hand preflight.
- **Expected unlock:** reusable finite random generation infrastructure. **0 production roots** and **0 training-eligible outcomes** are claimed.
- **Test strategy:** synthetic reviewed pool with supported and unsupported identities; prove sampling is over full membership; unsupported chosen identity invalidates without reroll; duplicate outcomes make independent instances; modifier is stored while effective cost clamps; clone RNG equivalence/independence; full-hand refusal before RNG; hand-entry/Shatter behavior; strict loader rejection cases.
- **Outliers:** Fire and Whelp exact runtime membership; Fire/Whelp consumers; any selected outcome whose metadata/behavior is missing; generated Shatter card with unsupported modifier inheritance; any hand-full ordering requiring client evidence.

## `takes_damage_self_reaction_v1`

- **Semantic contract:** a positive, unprevented packet to a minion captures a typed reaction descriptor at occurrence; at a bounded local packet checkpoint, a surviving same-entity, same-controller, unsilenced consumer may generate one card to its controller's hand. This package does not require survival as Hearthstone's universal rule; it fails closed for lethal state under this v1 admission boundary.
- **Existing primitives:** `deal_damage` is the shared protection/health path; it already distinguishes Shield/Immune and records spell damage; clone copies all internal state; generated-card creation reuses the first package.
- **Candidates:** synthetic fixtures only. Vulcanos appendages remain unconfigured because Fire membership is unresolved. No production card is added.
- **Dependencies:** reviewed local packet checkpoint; generation manifest/ref; stable entity/controller/silence checks; current batch death processing remains after action/group resolution.
- **Required changes:** typed `DamageOccurrence`, packet-local checkpoint sequence, captured consumer descriptor, exact packet amount and actual health delta, and fail-closed preconditions. No universal event bus or per-card callback.
- **Expected unlock:** reusable bounded damage-trigger infrastructure, with **0 production roots** admitted.
- **Test strategy:** positive/zero/prevented, each damage kind, both controllers, two consumers, separate packets, clone determinism, silence, source removal/lethal/control-change invalidation, and full-hand-before-RNG behavior.
- **Outliers:** multi-event phase ordering, lethal reactions, nested damage reactions, delayed resolution after silence/removal, control-change lifetime, hero consumers, and area-damage ordering beyond the local packet contract.

## Rules and pool disposition before implementation

- Fire candidate membership is **33** IDs, hash `480f5971bdf90a339f08142a9f2e47c7650be1ddd6973241960885b20b3e0e87`. Pinned metadata/card text cover Standard, collectible, spell, Fire school, class/Neutral, set, alias, ban, rune, and Quest candidate checks. Full patch-specific non-generatable exception inventory/client result is unavailable, so the runtime status remains candidate.
- Whelp has **77** raw collectible base-cost-1 Spell candidates; **12** Quest candidates; **65** after working Quest exclusion including Neutral; **63** non-Quest class candidates. The two Neutral candidates keep “from any class” unresolved. These remain candidate variants, not a reviewed runtime set.
- The official Blizzard 32.0 patch note confirms damage effects still function on functionally dead minions with damage-trigger effects. It does not settle all checkpoints. V1 therefore uses a local synchronous packet checkpoint and explicitly rejects lethal/self-removal and delayed/nested states; it does not claim full Hearthstone ordering.
- Fire membership is not sufficiently reviewed for runtime use. No Vulcanos appendage wiring is in scope. Whelp consumer is explicitly deferred.

## Changes intentionally excluded

No canonical registry/evidence promotion, no observation schema change, no production card implementation, no root consumer, no training eligibility, no Whelp, Vulcanos, Colossal, Dark Gift, or search changes.
