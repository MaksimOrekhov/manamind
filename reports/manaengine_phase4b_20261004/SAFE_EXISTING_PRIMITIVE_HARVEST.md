# Safe existing-primitive harvest ledger

Profile `standard_full_20261001_v1`; 105 unique audit candidates. Support count means a ManaEngine declaration exists, not runtime-pool admission or training eligibility.

| Measure | Count |
|---|---:|
| IMPLEMENTED_SCOPED_VERIFIED | 4 |
| IMPLEMENTED_BUT_RULES_BLOCKED | 8 |
| DEFERRED_NEW_CAPABILITY | 0 |
| DEFERRED_DYNAMIC_DEPENDENCY | 9 |
| DEFERRED_RULES_EVIDENCE | 31 |
| DEFERRED_ARCHITECTURE | 53 |

## Coverage changes

- Completion verification: native binary 34 scenario groups / 665 assertions PASS; adapter/policy CI selection 46 PASS; full Python suite 90 PASS; Ruff PASS; generic branch guard PASS; generated artifact check PASS (36 outputs); `git diff --check` PASS.
- Existing supported ManaEngine declarations in this universe: 8 roots; prior source state is preserved and not reverified here.
- New focused ManaEngine root scenarios: 4 roots — CORE_BAR_801, CORE_CS1_130, CORE_CS2_032, CORE_DS1_185.
- Fire declaration coverage: 8/33; working-class Whelp declaration coverage: 6/63. Neither pool is runtime-admitted.
- Exact fixed dependency: `BAR_035t` Swift Hyena, 1/1 Beast with Rush; separately declared `VERIFIED_VANILLA`.
- New engine primitives: 0; card-ID behavior branches: 0; native scenario groups added: 1; bridge parity runs: 0.
- Canonical rules evidence promotions: 0. New scoped test results do not change registry or training eligibility.

## Candidate ledger

| ID | Family | F | W raw/work | Prior declaration | This task | Status | Blocker |
|---|---|---:|---:|---|---|---|---|
| CAP_002 | temporary_inherited_effect | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| CAP_006 | held_history_damage | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| CAP_101 | temporary_inherited_effect | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| CAP_402 | temporary_inherited_effect | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| CATA_136 | random_deck_generation | no | yes / yes | no | no | DEFERRED_DYNAMIC_DEPENDENCY | Reachable runtime pool/state selector is unresolved: MINION_BASE_COST_AT_LEAST_8_ANY_CLASS |
| CATA_302 | healing_draw | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Independent family/action scenarios required before rules verification. |
| CATA_303 | damage_outcome_followup | yes | no / no | no | no | DEFERRED_RULES_EVIDENCE | Independent family/action scenarios required before rules verification. |
| CATA_485 | sequential_damage | no | yes / yes | yes | no | IMPLEMENTED_BUT_RULES_BLOCKED | Existing ManaEngine declaration is preserved.; Canonical rules status: IMPLEMENTED_UNVERIFIED.; No new focused verification or evidence promotion in this harvest. |
| CATA_528 | delayed_fixed_summon | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Start-of-next-turn scheduler is not the existing timed end-turn recruit; exact phase review required. |
| CATA_554 | stat_set_retarget | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Second 'pick another' continuation and excluding first target; no universal Choice redesign assumed. |
| CATA_581 | state_scaled_damage | yes | no / no | no | no | DEFERRED_RULES_EVIDENCE | Review improved amount, when battlefield size is snapshotted, and damage group semantics. |
| CATA_582 | area_damage_hero_attack | yes | no / no | no | no | DEFERRED_RULES_EVIDENCE | Independent family/action scenarios required before rules verification. |
| CATA_585 | excess_damage_return_outlier | yes | yes / yes | no | no | DEFERRED_DYNAMIC_DEPENDENCY | Reachable runtime pool/state selector is unresolved: SELF_VARIANT:CATA_585 |
| CATA_621 | random_persistent_aura | no | yes / yes | no | no | DEFERRED_DYNAMIC_DEPENDENCY | Reachable runtime pool/state selector is unresolved: PALADIN_AURA_SPELLS |
| CORE_AT_037 | choose_one_composition | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Independent family/action scenarios required before rules verification. |
| CORE_AT_055 | healing_draw | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Independent family/action scenarios required before rules verification. |
| CORE_BAR_801 | fixed_summon_composition | no | yes / yes | no | yes | IMPLEMENTED_SCOPED_VERIFIED | Task-local native family scenario and adapter/policy test passed.; Canonical registry remains IMPLEMENTED_UNVERIFIED; no Rosetta bridge parity or registry evidence promotion in this task.; Dynamic generation pool admission and full dependency closure remain outside this package. |
| CORE_BOT_222 | fixed_damage | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Independent family/action scenarios required before rules verification. |
| CORE_BOT_451 | overload_composition | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Independent family/action scenarios required before rules verification. |
| CORE_CS1_130 | fixed_damage | no | yes / yes | no | yes | IMPLEMENTED_SCOPED_VERIFIED | Task-local native family scenario and adapter/policy test passed.; Canonical registry remains IMPLEMENTED_UNVERIFIED; no Rosetta bridge parity or registry evidence promotion in this task.; Dynamic generation pool admission and full dependency closure remain outside this package. |
| CORE_CS2_004 | stat_keyword_enchant | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| CORE_CS2_029 | fixed_damage | yes | no / no | yes | no | IMPLEMENTED_BUT_RULES_BLOCKED | Existing ManaEngine declaration is preserved.; Canonical rules status: IMPLEMENTED_UNVERIFIED.; No new focused verification or evidence promotion in this harvest. |
| CORE_CS2_032 | fixed_damage | yes | no / no | no | yes | IMPLEMENTED_SCOPED_VERIFIED | Task-local native family scenario and adapter/policy test passed.; Canonical registry remains IMPLEMENTED_UNVERIFIED; no Rosetta bridge parity or registry evidence promotion in this task.; Dynamic generation pool admission and full dependency closure remain outside this package. |
| CORE_CS2_062 | fixed_damage | yes | no / no | yes | no | IMPLEMENTED_BUT_RULES_BLOCKED | Existing ManaEngine declaration is preserved.; Canonical rules status: IMPLEMENTED_UNVERIFIED.; No new focused verification or evidence promotion in this harvest. |
| CORE_CS2_074 | weapon_buff | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Independent family/action scenarios required before rules verification. |
| CORE_CS2_108 | destroy_followup | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Independent family/action scenarios required before rules verification. |
| CORE_DS1_184 | discover_deck | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| CORE_DS1_185 | fixed_damage | no | yes / yes | no | yes | IMPLEMENTED_SCOPED_VERIFIED | Task-local native family scenario and adapter/policy test passed.; Canonical registry remains IMPLEMENTED_UNVERIFIED; no Rosetta bridge parity or registry evidence promotion in this task.; Dynamic generation pool admission and full dependency closure remain outside this package. |
| CORE_EX1_238 | overload_composition | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Independent family/action scenarios required before rules verification. |
| CORE_EX1_302 | damage_outcome_followup | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Independent family/action scenarios required before rules verification. |
| CORE_EX1_391 | damage_outcome_followup | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Independent family/action scenarios required before rules verification. |
| CORE_EX1_610 | reactive_secret | yes | no / no | no | no | DEFERRED_RULES_EVIDENCE | Reuse Secret dispatcher with reviewed before/after attack window; not Ice Barrier semantics by text similarity. |
| CORE_GIL_836 | discover_predicate | yes | yes / yes | yes | no | IMPLEMENTED_BUT_RULES_BLOCKED | Existing ManaEngine declaration is preserved.; Canonical rules status: UNKNOWN.; No new focused verification or evidence promotion in this harvest.; Dynamic dependencies remain unresolved: BATTLECRY_DISCOVER_PLAYER_CLASS_NEUTRAL |
| CORE_LOOT_101 | reactive_secret | yes | no / no | yes | no | IMPLEMENTED_BUT_RULES_BLOCKED | Existing ManaEngine declaration is preserved.; Canonical rules status: IMPLEMENTED_UNVERIFIED.; No new focused verification or evidence promotion in this harvest. |
| CORE_SW_108 | fixed_hand_generation | yes | yes / yes | yes | no | IMPLEMENTED_BUT_RULES_BLOCKED | Existing ManaEngine declaration is preserved.; Canonical rules status: IMPLEMENTED_UNVERIFIED.; No new focused verification or evidence promotion in this harvest. |
| CORE_WON_337 | random_summon | yes | no / no | no | no | DEFERRED_DYNAMIC_DEPENDENCY | Reachable runtime pool/state selector is unresolved: MINION_BASE_COST_4_ANY_CLASS |
| CORE_WON_350 | discover_predicate | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| CORE_YOP_001 | discover_predicate | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| Core_LOE_115 | choose_one_discover | no | yes / yes | no | no | DEFERRED_DYNAMIC_DEPENDENCY | Reachable runtime pool/state selector is unresolved: MINION_DISCOVER_PLAYER_CLASS_NEUTRAL, SPELL_DISCOVER_PLAYER_CLASS_NEUTRAL |
| DINO_406 | tribal_multi_zone_buff | yes | no / no | no | no | DEFERRED_RULES_EVIDENCE | Determine exact zones of 'your Elementals', current stats and application/death sequence. |
| DINO_417 | temporary_board_keywords | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Snapshot membership, lost/replaced minions and death ordering; not a DK session requirement solely due to card class. |
| EDR_251 | provenance_filtered_draw | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| EDR_273 | discover_predicate | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| EDR_522 | hidden_zone_copy | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| EDR_528 | discover_dark_gift | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| EDR_531 | destroy_followup | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Independent family/action scenarios required before rules verification. |
| EDR_570 | choose_one_composition | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Independent family/action scenarios required before rules verification. |
| EDR_811 | corpses_dark_gift | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| EDR_813 | corpses_choose_one | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Full definitions resolve Ant Husk EDR_813at and option IDs EDR_813a/EDR_813b; resource legality and option availability still need review. |
| EDR_872 | choose_one_discover | no | yes / yes | no | no | DEFERRED_DYNAMIC_DEPENDENCY | Reachable runtime pool/state selector is unresolved: SPELL_MAGE, SPELL_DRUID |
| END_017 | quest_excluded_from_random | no | yes / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| END_020 | damage_outcome_followup | no | yes / yes | no | no | DEFERRED_DYNAMIC_DEPENDENCY | Reachable runtime pool/state selector is unresolved: MINION_BASE_COST_1_ANY_CLASS |
| END_024 | reactive_secret | yes | no / no | yes | no | IMPLEMENTED_BUT_RULES_BLOCKED | Existing ManaEngine declaration is preserved.; Canonical rules status: UNKNOWN.; No new focused verification or evidence promotion in this harvest. |
| END_025 | conditional_spell_return | yes | no / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| END_027 | discover_dark_gift | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| FIR_900 | discover_dark_gift | yes | no / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| FIR_906 | school_discard_composition | yes | no / no | no | no | DEFERRED_RULES_EVIDENCE | Independent family/action scenarios required before rules verification. |
| FIR_909 | random_distinct_targets | yes | no / no | no | no | DEFERRED_RULES_EVIDENCE | Confirm distinct sampling, fewer than 3 enemies, packet/death ordering and Spell Damage application. |
| FIR_910 | school_discard_composition | yes | no / no | no | no | DEFERRED_RULES_EVIDENCE | Review discard-between-instructions and whether discarded source is still a candidate; no generated pool, only actual hand. |
| FIR_911 | smoldering_hand_age | yes | no / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| FIR_914 | smoldering_hand_age | yes | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| FIR_916 | smoldering_hand_age | yes | no / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| FIR_920 | discover_dark_gift | yes | no / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| FIR_923 | state_scaled_damage | yes | no / no | no | no | DEFERRED_RULES_EVIDENCE | Independent family/action scenarios required before rules verification. |
| FIR_939 | discover_dark_gift | yes | no / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| FIR_941 | deck_draw_copy_summon | yes | no / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| FIR_954 | damage_outcome_followup | yes | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Capture target owner before damage/death; draw/fatigue timing needs independent review. |
| JAIL_125 | random_school_generation | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| JAIL_307 | state_scaled_damage | yes | no / no | no | no | DEFERRED_RULES_EVIDENCE | Two damage instructions with distinct death/reaction boundaries; deck-size >=25 reduction combines with generated instance discount. |
| JAIL_319 | refresh_discover_outlier | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| JAIL_386 | cast_when_drawn_shuffle | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| JAIL_732 | future_generated_state | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| JAIL_801 | held_spell_transform | yes | no / no | yes | no | IMPLEMENTED_BUT_RULES_BLOCKED | Existing ManaEngine declaration is preserved.; Canonical rules status: UNKNOWN.; No new focused verification or evidence promotion in this harvest. |
| JAIL_940 | death_history_replay | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| MEND_300 | future_companion_override | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TIME_006 | fixed_summon_composition | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Independent family/action scenarios required before rules verification. |
| TIME_026 | cast_when_drawn_shuffle | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TIME_039 | hidden_zone_copy | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TIME_212 | sequential_damage | no | yes / yes | no | no | DEFERRED_RULES_EVIDENCE | Death boundary and damage-trigger interleaving between packets require review; do not reuse Sleet's admission blindly. |
| TIME_447 | stat_keyword_enchant | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TIME_701 | discover_deck | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TIME_EVENT_999 | rewind_discover | no | yes / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_221 | damage_scaled_summon | yes | no / no | no | no | DEFERRED_RULES_EVIDENCE | Sizzling Cinder is a collectible 2/1 with random split-damage Deathrattle, not vanilla token. Review count after prevention, armor/overkill and Spell Damage. |
| TLC_222 | type_filtered_draw_buff | yes | no / no | no | no | DEFERRED_DYNAMIC_DEPENDENCY | Reachable runtime pool/state selector is unresolved: ACTUAL_DECK_DIFFERENT_MINION_TYPES |
| TLC_227 | overload_composition | yes | no / no | no | no | DEFERRED_RULES_EVIDENCE | Re-select enemy incl hero each instruction, ties RNG, deaths, packet scaling, mana-lock state on Mage player. |
| TLC_229 | quest_excluded_from_random | no | yes / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_235 | random_summon | no | yes / yes | no | no | DEFERRED_DYNAMIC_DEPENDENCY | Reachable runtime pool/state selector is unresolved: MINION_BASE_COST_EQUALS_DESTROYED |
| TLC_239 | quest_excluded_from_random | no | yes / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_426 | quest_excluded_from_random | no | yes / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_433 | quest_excluded_from_random | no | yes / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_435 | discover_then_play_other_option | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_442 | discover_then_play_other_option | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_446 | quest_excluded_from_random | no | yes / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_460 | quest_excluded_from_random | no | yes / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_464 | discover_then_play_other_option | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_513 | quest_excluded_from_random | no | yes / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_517 | held_history_damage | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_602 | quest_excluded_from_random | no | yes / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_631 | quest_excluded_from_random | no | yes / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_632 | temporary_hero_power_swap | yes | no / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_817 | quest_excluded_from_random | no | yes / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_824 | discover_then_play_other_option | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_830 | quest_excluded_from_random | no | yes / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_900 | discover_then_play_other_option | no | yes / yes | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
| TLC_EVENT_400 | sidequest_composite_minion | no | yes / no | no | no | DEFERRED_ARCHITECTURE | Existing behavior set does not cover this state/event/choice/session contract honestly. |
