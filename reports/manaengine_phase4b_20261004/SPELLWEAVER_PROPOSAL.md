# CAPABILITY PACKAGE PROPOSAL

package_id: direct_spell_damage_turn_cost_fixed_summon_v1
implementation_kind: REUSABLE_CAPABILITY
contract_version: 1
baseline: ManaMind 28baac6fe21bd1715e1c2c670f01502572474f14; RosettaStone f34da0d3fcb5ad312f7e2acf634d0536b044d29a
pinned_profile: standard_full_20261001_v1; frozen tricky_burn_mage

## Semantic contract

Accumulate full successful packet amounts attributed explicitly to DirectSpell, separately from DamageKind. Shield/Immune prevention contributes zero; armor absorption still counts; overkill counts full unprevented damage as explicitly reviewed by the user. Combat, hero power, fatigue, minion effects and ExternalSpellEffect do not contribute. DamageKind::Spell alone grants no attribution. Existing Raincaller event semantics stay independent and unchanged.

Ordinary spell damage, composed spell Damage steps and missile unit packets are reviewed DirectSpell consumers. Explosive Runes' actual damage packets are direct Secret spell damage. Flames of Infinity's existing destroy-via-damage placeholder is NOT reviewed direct damage and does not contribute; its legacy rules limitations remain recorded, not silently closed.

The per-player counter belongs to the current GLOBAL turn. End-turn reactions run in the ending turn; reset BOTH counters when the engine actually rotates to the next turn, before its draw. Opponent-turn Secret damage is credited to the Secret controller in that global turn, then discarded at rotation. No history/event-order subsystem or scheduler rewrite is required.

Dynamic cost is a declarative nonnegative per-damage coefficient on spells, composed with existing instance/next-spell modifiers through effective_cost and clamped at zero. Base metadata is immutable. CATA_452 uses coefficient 1 and base cost 10. Existing hand current_cost and semantic action card_cost carry the effective value; no new GameState/Policy field is needed in this package. The internal counter is cloned with full engine state.

SUMMON_FIXED is a typed EffectStep with SELF target, positive count and an exact declared dependency. Validate supported minion dependency and fields before execution. Append to board with correct owner, instance/position/activation and normal summoning sickness; no Battlecry-from-summon. At seven minions, the SPELL can still be played and consumed; the failed summon creates no entity/hand/graveyard token or death event. This follows the user's casting requirement and the archived Blizzard clarification that an extra minion is not summoned at all when no slot remains (https://www.hearthpwn.com/news/82-blue-post-recap-arena-card-clarifications, Summoning Minions On a Full Board). Do not invent burned-token behavior.

## Candidates and dependencies

CATA_452: pinned 10-cost Mage Arcane spell, exact reviewed text: Summon a 6/6 Dragon. Costs (1) less for each damage you dealt with spells this turn.

CATA_452t: Azure Warden, dbfId 122455, MINION/DRAGON, 6 cost, 6 attack, 6 health, noncollectible (no collectible flag), no text or mechanics. Full HearthstoneJSON response captured 2026-10-04 has SHA-256 e8ea569a7ca1790c2258ed57c60798d808ffb057acb7bb73663c00ea174dae65, matching the previous finite dependency audit's complete-feed identity. Root metadata is identical to the pinned Oct1 row. Save a NEW finite dependency archive; preserve the older archive and Standard membership.

Independent native control declaration varies coefficient (2), summon count (2) and fixed supported minion ID without shared code changes. It is a fixture, not another delivered Standard root.

## Existing primitives and required shared changes

Reuse ManaEngine deal_damage, prevention/armor/overkill, damage-boundary v1, current instance cost path, typed effects, make_instance, activation/zone helpers, clone and existing turn rotation. RosettaStone SummonTask and mana-condition/history primitives are reference implementations, not an independent oracle or evidence promotion.

Add explicit damage attribution, saturating 64-bit turn accounting, positive spell cost coefficient and SUMMON_FIXED fields/validation/renderer/bindings. Strict allowlists reject unsupported combinations/dependencies. No card-ID behavior branches. Do not implement Skeleton Key, TIME_855, Bookkeeper, Vulcanos or Whelp.

## Expected unlocks and verification

One declaration-only experimental root plus one exact fixed token dependency. Full canonical RosettaStone verification delta remains zero; frozen deck remains incomplete and training blocked. Existing unreviewed Secret/death/dynamic-pool routes cannot be certified by this package.

Independent native expectations: cost 10/9/4/0; two spells and multi-packet totals; Missiles; Sleet; Shield/Immune; overkill; armor; Counterspell; typed external attribution negative case; non-spell negatives; both-player global resets and off-turn Secrets; cloned counter divergence; parameter reuse; exact Dragon stats/instance/position; board-full no token/death; static dependency and invalid declaration rejection. Real adapter actions assert current cost/base cost, Policy encoding, exact summon and clone/turn changes.

Rebuild affected C++ consumers together. Run full native suite, adapter/policy suite, full pytest, lint, generic guard and canonical regeneration. Push and require Windows/Ubuntu Source and experimental CI with actual pytest log evidence. Record measured elapsed/correction cycles, scoped results and remaining missing roots, then STOP.
