# Phase 4 independent rules and contract audit

Date: 2026-10-04. Scope: correctness repairs to a62ff5f, no new profile roots.

## Rules confidence

Executable prototype scenarios establish the stated model contract. They are not an independent Hearthstone oracle. `SUPPORTED` in the experimental catalog is an executable route, not full rules verification or backend training admission. No canonical Rosetta evidence is promoted by ManaEngine tests.

| Question | Evidence and current disposition | Admission limit |
|---|---|---|
| Prepare eligibility/spending | [HearthstoneTeam FAQ](https://www.reddit.com/r/hearthstone/comments/1tux5ya/escape_from_violet_hold_prepare/) explicitly covers once per card, no zero-cost/no-mana Prepare, max useful spend, cost-one special case, same-turn lock and persistent discount. Implemented capped spend, no repeat Prepare, zero-cost play on later turn. | Copy/bounce/shuffle of prepared instances is outside current capabilities. No new copy consumer added. |
| Lifesteal overkill | [Official mechanic introduction](https://hearthstone.blizzard.com/en-gb/news/20944003/arise-knights-of-the-frozen-throne-10-08-2017/) describes healing by damage; pinned Rosetta Character::TakeDamage and [Lifesteal notes](https://hearthstone.wiki.gg/wiki/Lifesteal) corroborate full unprevented damage, including overkill. Native independent 3 damage versus 1 Health expects heal 3; shield/Immune prevent healing. | Hero armor absorbs damage and counts as damage dealt; no unsupported hero protection grant is admitted. |
| Hero attacks minion | Both attack values are snapshotted; defending minion retaliates against the hero. Shield affects its received packet, not retaliation. Weapon consumes durability once. | Narrow supported combat flags only; no claim of all Hearthstone combat mechanics. |
| Ice Barrier | Pinned card text says hero attacked, not hero attacker. All four attacker/target combinations reviewed. | Activates for either hero or minion attacking the defending hero. |
| Explosive Runes + Divine Shield | [Rules notes](https://hearthstone.wiki.gg/wiki/Explosive_Runes) distinguish absorbed minion damage and excess computed from pre-hit Health. A 2-Health shielded minion keeps Health and loses shield; hero receives 4. Both packets use the common typed pipeline. | Focused scenario, not complete Secret-family verification. |
| Flames equal-Health tie | [Card metadata/rules page](https://hearthstone.wiki.gg/wiki/Flames_of_Infinity) carries Random semantics. Seeded choice among living tied maximum-Health targets; no target leaves the Secret armed. [Infinite damage attribute](https://hearthstone.wiki.gg/wiki/Attribute) supports INT_MAX damage rather than destruction; prevention applies. | Tie random selection is prototype executable semantics. Full independent game-log parity still required. |
| Shatter inherited modifiers / merge | [Secondary rules notes](https://hearthstone.wiki.gg/wiki/Shatter) actually describe possible duplicated inherited enchantments and summed merge effects. This contradicts using conservation as an unquestioned Hearthstone rule. No primary trace independently establishes the full contract here. Pre-split cost/Spell Damage/Prepare/counters/enchantments and modified-fragment merge fail closed. Unmodified split/recombine does not invent modifiers. | NEEDS_RULES_VERIFICATION; no full CATA_489 verification. The old +1 -> +2 test is withdrawn. |
| Shatter at hand size 9 / immediate merge | Existing explicit hand-capacity and adjacency scenarios retain prototype behavior. Exact historical game behavior for burn/instant merge is not independently established. | NEEDS_RULES_VERIFICATION before full CATA_489 closure. |
| Oasis after Mystic | Attack window snapshot uses activation ordering and stops on cancellation. Earlier Oasis reaches unsupported Water Elemental and invalidates branch; earlier Mystic cancels and preserves later Secrets. | Exact Hearthstone re-evaluation still NEEDS_RULES_VERIFICATION; Oasis closure blocked by Freeze-on-damage. |
| Tricksy duplicate Secrets | Full pinned membership retained; duplicate-active/full-zone outcomes are attempted, not filtered. Existing activation helper declines duplicates. | Independent exact duplicate cast/history rules NEEDS_RULES_VERIFICATION; JAIL_321 is partial. |
| Tricksy random casts + Counterspell | Prototype invokes spell Secret window for each generated Secret cast; cancellation stops that window. | Auto-cast counterability and history/progress timing NEEDS_RULES_VERIFICATION. No full JAIL_321 verification. |
| Tricksy casts + held progress | Ordinary hand plays advance held per-instance progress; existing random-cast route does not update it. | Not declared correct. NEEDS_RULES_VERIFICATION, including qualifying generated/nested/replayed casts. |
| Counterspelled spell history/progress | Prototype advances hand progress/history before the cancellation window. | NEEDS_RULES_VERIFICATION. Tests describe a prototype choice, not independent truth. |
| Raincaller per-player versus per-instance | Prototype uses active unsilenced source counters, once per turn. Prevention yields no event; Secret spell damage now publishes to its controller. | Entry after earlier player damage, counter ownership and per-step interaction NEEDS_RULES_VERIFICATION. No full CATA_487 verification. |
| Spell Damage snapshot versus per-step | Prototype snapshots board contribution once per spell; per-card bonus is retained until cast. | Multi-step effects/source death/reactions require independent ordering verification. |
| Death phase between Battlecry and after-play | Approved prototype drains FIFO triggers, then removes all dead entities, drains ordered deathrattles, repeats. Full simultaneous-death batches use activation sequence, not owner-zero priority. | Complete Hearthstone event ordering remains unverified. Do not expand event system here. |
| End-turn ordering | Approved prototype merges board reactions/timed effects/Secrets by activation sequence and stabilizes afterward. | Full end-turn/death interleaving NEEDS_RULES_VERIFICATION. |
| Transform | Shared `transform_board` retains entity/owner/controller/zone position and already-attacked state; replaces card identity/base/current stats and resets enchantments/counters/modifiers/freeze/keywords; replacement cannot attack immediately and gets new activation sequence. | Explicit prototype contract, not a claim about all Hearthstone transform ordering/attack-state rules. JAIL_315 remains scoped/partial. |

## Catalog identity / mechanic audit

Before repair, production metadata-only consumers were Water Elemental and a fabricated transform token. Current only admitted vanilla declaration is the real `CS2_tk1` Sheep. Water Elemental `CORE_CS2_033`/`CS2_033` metadata carries Freeze-on-damage and is unsupported. Viper `CORE_SW_072` also carries unimplemented Tradeable and is unsupported. Keyword-only Taunt/Rush/Lifesteal cards can pass coverage when represented explicitly; nonempty text alone does not reject them.

Reviewed generated/transform identities: `EX1_277`, `SW_108t`, `CATA_489t`, `CATA_489t2`, `JAIL_801t`, `JAIL_803t`, `JAIL_805t`, `CS2_tk1`; Mage power `HERO_08bp`. `EX1_100t` and `CORE_SW_108t` were absent in the metadata audit and removed. Finite records and provenance live in `experiments/manaengine/data/dependency_metadata_audit.json`. This Oct-4 capture supplements identity lookup only; it does not redefine pinned Oct-1 scope or certify historical rules. Reconcile historical token metadata before full admission.

Required mechanic representation and exact reviewed rules text are fail-closed authoring guards, not proof of execution correctness. Declaration fields are allowlisted; `TEST_HELD_TRACKER` remains native-test-only, never a production declaration.

## Information and safety audit

- SELF hand: effective cost, Prepare-used/turn lock, held progress, current per-card Spell Damage and Shatter semantic links are visible. Internal link IDs stay private.
- Public board: current stats/flags, Freeze duration and consumed Raincaller-style trigger availability are visible.
- Both players: cast count, active discounts, hero Freeze duration, timed-effect identities/durations and public counts are visible.
- SELF pending Choice: candidate metadata/effective cost reaches GameState and the variable Choice zone used by Value. Policy receives semantic action descriptors. Opponent Choice identities are omitted.
- Hidden hands/deck identities/order, RNG, activation sequence and diagnostic trace are excluded from serialization/encoding. Trace is a debugging channel, not a dataset channel.
- Mage mirror hero power is supported; other class sessions fail closed. Cross-class card fixtures do not certify legal decks.
- Training admission stays false before collection. All reachable outcomes, legal deck/session/action/observation/match gates require backend-specific evidence; no survivor-only filtering.
- Full-state clone is simulation-only. Information-set/determinized state is a hard gate before search/MCTS/search labels and is intentionally not implemented.

## Scheduler test limitation

The second-death-batch regression injects an existing typed end-turn reaction into the mandatory reaction queue through native TestAccess. It verifies scheduler repetition without adding a new damage Deathrattle card/capability. It is explicitly a scheduler control, not independent parity evidence for an unimplemented Hearthstone damage Deathrattle.
