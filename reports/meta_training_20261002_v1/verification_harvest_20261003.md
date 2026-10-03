# Verification-harvest audit — Meta Training Profile v1

Date: 2026-10-03
Pinned inputs: `meta_training_20261002_v1`, `standard_full_20261001_v1`, `standard_registry_20261001_v1`, RosettaStone `945d89116e072b7a3be936b8c4e837896b875d86`.

## Scope and filters

Audited all 156 unique pinned profile roots in `reports/meta_training_20261002_v1/card_matrix.json` against the canonical registry and selected 10 deck manifests. The audit starts with 88 roots registered/implemented but not current scoped-verified (including roots with stale evidence), then removes cards with unresolved dynamic pools, CUSTOM-only implementation routes, unresolved session/class mechanics, or source behaviors requiring new event ordering. “No pool detected” in the registry is not treated as proof: source blocks were reviewed for shortlisted roots. CardDef registration and alias text equality remain separate from rules verification.

No deck has complete closure today, so proximity is measured as statically reviewed dependency nodes/root movement, not a claim of deck readiness. Root gains below are scoped-verification estimates; they do not imply training admission.

## Ranked candidates

`ROI` is a planning range of eligible profile roots per elapsed verification hour. Estimates assume focused family scenarios, current bridge build identity, explicit dependency review, and evidence/registry regeneration; actual times will be recorded per package.

| Rank | Candidate semantic family | Reviewed clean profile roots | Current status | Decks advanced | Static closure | Estimated effort / ROI | Correctness risk |
|---:|---|---|---|---:|---|---|---|
| 1 | `core_alias_base_semantics_verification_v1` — each declared Core alias preserves its reviewed base CardDef behavior | `CORE_DRG_107` Violet Spellwing, `CORE_SW_072` Rustrot Viper, `CORE_SW_108` First Flame (**3**); exclude `CORE_DRG_024` Sky Raider because its random Pirate outcome is a dynamic pool absent from the heuristic | 3 unverified; aliases already generated; fixed outcomes `EX1_277`, `SW_108t`; no unresolved pool for these three | 2 (Mage, Demon Hunter) | 2 fixed outcomes plus base-definition edges | 2–3 h; **1.0–1.5 roots/h** | Low–medium: base/task equivalence, deathrattle/weapon legality, First Flame token identity; Sky Raider excluded |
| 2 | Fixed targeted spell damage using existing `DamageTask` | `CORE_CS2_029` Fireball, `CORE_CS2_072` Backstab, `CORE_CS2_024` Frostbolt, `CORE_ICC_055` Drain Soul (**4**) | 4 source-implemented/composed and unverified; no discovered pool or card dependency | 3 (Mage, Rogue, Warlock) | 0 known nodes | 3–5 h; **0.8–1.3 roots/h** | Low–medium: target legality differs; Frostbolt freezes and Drain Soul has Lifesteal |
| 3 | Fixed enemy-board damage spells using existing damage/draw primitives | `CORE_CS2_062` Hellfire, `CORE_EX1_129` Fan of Knives (**2**) | 2 unverified; fixed effects, no generated pool | 2 (Warlock, Rogue) | 0 known nodes | 2–3 h; **0.7–1.0 roots/h** | Medium: Hellfire hits all characters, Fan hits enemy minions then draws |
| 4 | Fixed spell damage plus temporary hero attack | `TIME_218` Static Shock, `END_007` Press the Advantage (**2**) | Both composed; `END_007` evidence stale; shared fixed enchant candidate `BTA_02pe` | 3 (Shaman, Druid, Demon Hunter) | 1 shared enchant candidate | 2–4 h; **0.5–1.0 roots/h** | Medium: enchant expiry and damage/hero ownership |
| 5 | Priest targeted spell enchant plus draw/tag | `CORE_CS2_004` Power Word: Shield, `CAP_801` Haunt (**2**) | Both composed and stale; static dependencies `CS2_004e`, `CS2_009e`; no dynamic pool | 1 (Priest) | 2 fixed enchant nodes | 2–4 h; **0.5–1.0 roots/h** | Medium: exact current rules and combined Reborn/enchantment behavior |
| 6 | Fixed card-cost reductions with existing cost/enchantment primitives | `CORE_EX1_145` Preparation, `CORE_BT_416` Raging Felscreamer (**2**) | Both source-implemented; fixed enchant dependencies `EX1_145o`, `BT_416e`; no pool | 2 (Rogue, Demon Hunter) | 2 fixed enchant nodes | 2–3 h; **0.7–1.0 roots/h** | Medium: next-spell turn expiry vs next-Demon condition and cost reset |
| 7 | Draw-on-event roots using existing draw task and event hooks | `JAIL_872` Spider Rider (**1**) | Existing after-attack draw implementation, no dependency/pool; not yet current scoped evidence | 1 (Druid) | 0 known nodes | 1–1.5 h; **0.7–1.0 roots/h** | Medium: hero attack event boundary and exactly-once draw |
| 8 | End-of-turn fixed damage to enemy targets | `CATA_999` Earthen Drake, `CATA_475` Scalebreaker Bulwark (**2**) | Existing direct/composed triggers and DamageTask; no dependencies or detected pools | 2 (Warlock, Paladin) | 0 known nodes | 2–3 h; **0.7–1.0 roots/h** | Medium: end-turn trigger timing; hero-only vs all enemy targets |
| 9 | Cost discounts from live hand/game-state predicates | `TLC_816` Gravedawn Sunbloom, `JAIL_514` The Unseen Atlas (**2**) | Existing cost manager/composition; no generated outcome pool or card dependencies | 2 (Priest, Warlock) | 0 known nodes | 2–4 h; **0.5–1.0 roots/h** | Medium: Kindred timing and live hand-size cost boundary |
| 10 | Fixed Battlecry Silence on a legal minion target | `CORE_SW_066` Royal Librarian (**1**) | Existing composed Silence task; no dependency or detected pool | 1 (Demon Hunter) | 0 known nodes | 1–1.5 h; **0.7–1.0 roots/h** | Low–medium: target legality, tradeable path and silence reset behavior |

## First package selection

Proceed with rank 1, limited to `CORE_DRG_107`, `CORE_SW_072`, and `CORE_SW_108`. It reuses the existing Core alias generator and existing engine CardDefs; work is verification/evidence, not a new generic operation or rules renderer. The family contract is only “the declared Core definition preserves the reviewed base behavior”; tests must still be independently specific for each card. `CORE_DRG_024` is explicitly out because its random Pirate outcome pool is not represented in the current detected-pool fields.

No selected root becomes training-eligible from this work. Current Meta Profile report remains zero fully closed decks; alias checks can add roots and static dependency confidence but cannot clear unrelated deck roots, dynamic pools, external Fabled seeds, action/session, or match-evidence gates.

## Execution results — first two candidates (intermediate checkpoint)

The first three ranked candidates were completed as verification-only packages:

| Package | Roots scoped-verified | Native | Bridge | Production engine changes | Closure gained | Training eligibility gained |
|---|---:|---|---|---:|---:|---:|
| `core_alias_base_semantics_verification_v1` | 3 | 4 cases / 789 assertions including structural alias parity | 3 sessions passed | 0 | 0 | 0 |
| `profile_single_target_spell_damage_verification_v1` | 4 | 4 cases / 16 assertions | 4 sessions passed | 0 | 0 | 0 |

At this intermediate checkpoint: **7 roots** use pre-existing declarations/aliases; CUSTOM and deferred outliers among those seven: **0**. No new shared engine capability and no engine fix were required. The two packages averaged 3.5 roots each; elapsed time was not captured and is therefore not converted into an observed throughput figure. The targeted spell family advances four roots across three classes; it does not close a deck or its full dependency graph. Canonical Standard evidence remains separate from Meta-scoped evidence.

Best observed return in root count was the four-root targeted spell package. The Core alias family remains the lightest verification candidate by implementation surface. The original effort/ROI ranges above are estimates, not measured elapsed times.

## Corrected independent evidence and outstanding blockers

The complete configured native UnitTests run against RosettaStone `945d89116e072b7a3be936b8c4e837896b875d86` is preserved at `reports/meta_training_20261002_v1/native_full_suite_945d891.txt`: **266/267 cases passed; the sole failure is the established `CORE_OG_044 : Fandral Staghelmh` baseline** (two assertions and the existing SIGSEGV). No new failure is designated baseline.

`shaman_spell_threshold_hand_transform_v1` remains `BLOCKED_DESIGN_REVIEW`; its short audit found no complete canonical event boundary covering normal, generated, replayed, auto-cast and nested spell resolutions without crossing global event-order semantics. No Shaman production code was changed.

At this intermediate checkpoint the Meta Profile audit reports 11 current scoped-verified roots, 85 registered but not currently scoped-verified roots, and 68 roots without detected registration. It still reports zero fully closed decks and zero roots admitted for full-profile training. Continue verification harvest while exact per-deck dependency/session blockers remain unresolved.
