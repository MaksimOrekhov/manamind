# Per-deck reachable-closure audit (registry lower bound)

Candidate edges and pool hypotheses are not reviewed closure. Counts below describe only known registry candidates reachable from pinned collectible roots; they do not include unresolved Fabled seeds.

| Deck | Class | Listed slots | Pinned roots | Current verified | Registered, unverified | Unregistered | Known candidate nodes | Candidate edges | Unresolved pools |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cannoneer_dragon_warrior | Warrior | 30 | 16 | 0 | 15 | 1 | 5 | 6 | 5 |
| fire_pirate_warrior | Warrior | 30 | 17 | 0 | 12 | 5 | 5 | 5 | 3 |
| wanted_mug_shaman | Shaman | 30 | 16 | 1 | 4 | 12 | 2 | 3 | 5 |
| elise_attack_druid | Druid | 30 | 20 | 1 | 17 | 3 | 15 | 15 | 5 |
| reborn_quest_priest | Priest | 30 | 17 | 0 | 13 | 4 | 3 | 3 | 9 |
| ashamane_ayaya_rogue | Rogue | 30 | 17 | 1 | 4 | 13 | 1 | 1 | 6 |
| mother_drake_warlock | Warlock | 30 | 19 | 1 | 19 | 0 | 3 | 3 | 2 |
| tricky_burn_mage | Mage | 30 | 17 | 4 | 6 | 9 | 5 | 5 | 2 |
| beatrix_pure_paladin | Paladin | 30 | 16 | 2 | 5 | 11 | 0 | 0 | 5 |
| galaxy_brain_raza_demon_hunter | Demon Hunter | 30 | 15 | 2 | 4 | 10 | 3 | 2 | 1 |

## Pool IDs

- `cannoneer_dragon_warrior`: `POOL:CAP_105:discover`, `POOL:CATA_556:random_card_or_pool`, `POOL:EDR_456:discover`, `POOL:FIR_939:discover`, `POOL:TIME_034:random_card_or_pool`
- `fire_pirate_warrior`: `POOL:CAP_105:discover`, `POOL:END_020:random_card_or_pool`, `POOL:FIR_939:discover`
- `wanted_mug_shaman`: `POOL:CAP_407:discover`, `POOL:CORE_GIL_836:discover`, `POOL:JAIL_987:random_card_or_pool`, `POOL:TIME_EVENT_999:discover`, `POOL:TLC_464:discover`
- `elise_attack_druid`: `POOL:CATA_140:random_card_or_pool`, `POOL:JAIL_200:random_card_or_pool`, `POOL:JAIL_201:random_card_or_pool`, `POOL:JAIL_875:discover`, `POOL:TIME_701:discover`
- `reborn_quest_priest`: `POOL:CAP_804:generated_card`, `POOL:CAP_806:generated_card`, `POOL:CORE_BAR_311:random_card_or_pool`, `POOL:DINO_426:discover`, `POOL:DINO_426:generated_card`, `POOL:EDR_463:random_card_or_pool`, `POOL:EDR_856:discover`, `POOL:JAIL_912:random_card_or_pool`, `POOL:JAIL_940:generated_card`
- `ashamane_ayaya_rogue`: `POOL:CORE_RLK_567:generated_card`, `POOL:EDR_528:discover`, `POOL:EDR_528:generated_card`, `POOL:TIME_039:discover`, `POOL:TIME_039:generated_card`, `POOL:TLC_515:discover`
- `mother_drake_warlock`: `POOL:JAIL_515:random_card_or_pool`, `POOL:TLC_451:discover`
- `tricky_burn_mage`: `POOL:CATA_484:discover`, `POOL:TLC_226:generated_card`
- `beatrix_pure_paladin`: `POOL:CATA_474:random_card_or_pool`, `POOL:JAIL_327:generated_card`, `POOL:JAIL_516:generated_card`, `POOL:TIME_009:generated_card`, `POOL:TLC_438:random_card_or_pool`
- `galaxy_brain_raza_demon_hunter`: `POOL:CORE_YOP_001:discover`

No row is complete or training-eligible. Full root tests, reviewed static edges, exact dynamic memberships/outcome rules, bridge/action checks, and class/session/match evidence remain required.
