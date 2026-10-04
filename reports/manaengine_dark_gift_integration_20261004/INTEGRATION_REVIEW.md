# Dark Gift mainline integration review

Target mainline: `codex/manaengine-first-deck` at `097a3a50bdfa18e123136dddbf97f6346865f81a`.
Reference only: `claude/dark-gift-prototype` at `f73cabdad60d6c02b689afd809c7bae455557def`, based on older `31a9df1`.

| Claude component | Current mainline equivalent | Decision | Reason |
|---|---|---|---|
| `PersistentModifier` | `CardInstance` already owns typed identity, cost delta, counters and lifecycle state | PORT, bounded | Store only source option ID, attack/health/cost deltas, Taunt, Lifesteal and Charge. Keep it separate from generated `cost_delta`, spell damage, Prepare, counters and intrinsic definition. |
| `project_modifiers` | Current instance stats are stored and mutated by combat/damage | ADAPT | Recompute intrinsic plus persistent modifiers while preserving damage already taken; never rewrite execution fields. |
| `dark_gift_pool` inline ID list | Phase 4E `PoolManifest` validates versioned pools and source identity | REJECT inline list; ADAPT to typed option manifest | A non-card finite option set is not a spell predicate. Add the smallest typed option-manifest extension and make consumers reference its identity. |
| Offer sampler | ManaEngine has deterministic seeded bounded RNG and Discover continuation | PORT as experimental fixture contract | Uniform over valid injective assignments; sampler remains `UNVERIFIED`, no membership/training promotion, no filtering by engine support and no reroll. |
| Eligibility | Card definitions contain intrinsic stats, mechanics and Battlecry | PORT, independent of execution support | Apply official keyword-overlap, positive-Attack, resulting-Attack and Battlecry constraints to all launch-reviewed options. |
| `apply_dark_gift` | Existing generated-instance creation and hand insertion | ADAPT | Attach one typed modifier to a fresh offered minion; unsupported selected option fails with exact ID. |
| Lifecycle guard | Current `remove_card_from_hand`, `enter_hand`, transform and graveyard paths | PORT guards; preserve existing paths | Hand/board/death/burn/transform are bounded. Copy, Silence, deck/Secret/unreviewed transitions fail closed. |
| `INSTANCE_COPY_V1` | Current bounded Bookkeeper validator | SUPERSEDED, preserve | Do not widen copy semantics. A gifted source remains rejected by the existing copy contract. |
| Observation | ManaEngine `Observation` → adapter → `GameState`; state schema was 15 | ADAPT, bump to 16 | Gift IDs visible in own hand and both public boards; pending gifts only for chooser; no opponent hand, RNG, handles or candidate list. |
| Encoder | Current entity and state encoders | PORT | Ten launch-option identity features with missingness; unknown IDs fail closed. |
| Policy | `dark_gift_1..10` action columns already exist in RosettaStone policy schema | PORT mapping only | Reuse established launch order; do not bump policy schema absent an actual action-feature contract change. |
| Schema version | Mainline observation schema 15 | PORT 15 → 16 | Added entity feature set changes encoder input shape; compatibility must reject/migrate explicitly. |
| `FIR_900` Cremate | No executable Dark Gift handler | ADAPT as scoped experimental consumer | Preserve all reviewed options; runtime membership and sampler remain unresolved, so not globally training-ready. |
| `EDR_488` Avant-Gardening | No executable Dark Gift handler | ADAPT as scoped experimental consumer | Same boundary; deathrattle minion predicate remains distinct. |
| Reborn / Persisting Horror | Current death stabilization has no slot-aware Reborn phase | REJECT / checkpoint | Would change global death ordering and enchantment restoration. |
| Double Battlecry / Rude Awakening | Current Battlecry trigger runs once with a single target/continuation | REJECT / checkpoint | Correct replay contract is unresolved for targets, RNG and nested choices. |
| Phase 4D.1 hand-removal invariant | Shared `remove_card_from_hand` and Shatter-link updates exist | PRESERVE | All normal play and discard flows continue using the shared invariant. |
| Phase 4D.1 Overload guard | Current turn transition rejects impossible debt before mutation | PRESERVE | No changes to Overload semantics. |
| Phase 4E finite pools / generated instances | Typed pool manifests, strict loader, additive generated `cost_delta` | PRESERVE and extend narrowly | Option manifest is a typed sibling; Short Claws cost is independent and combines at effective-cost evaluation. |
| Phase 4E `takes_damage_self_reaction_v1` | Captured occurrence, ownership, activation and descriptor checks | PRESERVE | No changes to damage event processing or pool generation. |

## Evidence boundary

Blizzard's launch article establishes the ten launch-listed effects and the three distinct minion/Gift Discover pairings. Patch 32.2 establishes keyword overlap and Sleepwalker eligibility changes. Runtime membership and assignment distribution remain unverified. This integration does not promote the fixture option set to a canonical runtime pool or training eligibility.
