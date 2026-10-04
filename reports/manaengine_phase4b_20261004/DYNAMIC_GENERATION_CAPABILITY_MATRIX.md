# Capability matrix — manual contract audit

No implementation/rules status promotion. JSON retains all requested axes, exact text and declarations.
F=Fire candidate; W=raw Whelp candidate; WC=working Whelp class candidate. Quest and neutral rows retained for exclusion review.

| ID | Name | Pools | Family | Targeting | New/unreviewed facets | Fixed deps | Dynamic frontier |
|---|---|---|---|---|---|---|---|
| CAP_002 | Follow the Footsteps | W WC | temporary_inherited_effect | NONE | DISCOVER_STEALTH, GRANT_SELF_EFFECT_ONE_TURN |  | STEALTH_DISCOVER_PLAYER_CLASS_NEUTRAL |
| CAP_006 | Tricks of the Trade | W WC | held_history_damage | CHARACTER | HELD_STEALTH_ATTACK_PROGRESS |  |  |
| CAP_101 | Follow the Fuse | W WC | temporary_inherited_effect | RANDOM_ENEMY | RANDOM_ENEMY_DAMAGE, GRANT_PLAYABLE_PIRATE_EFFECT_ONE_TURN |  | ACTUAL_PLAYABLE_HAND_PIRATES |
| CAP_402 | Follow the Evidence | W WC | temporary_inherited_effect | NONE | SHUFFLE_OPPONENT_DECK_FIXED, GRANT_PLAYABLE_HAND_EFFECT_ONE_TURN | CAP_400t2t, CAP_402e | ACTUAL_PLAYABLE_HAND_CARDS |
| CATA_136 | Azshara's Triumph | W WC | random_deck_generation | NONE | GENERATE_RANDOM_HIGH_COST_MINIONS, DOUBLE_GENERATED_STATS, SHUFFLE_SELF_DECK |  | MINION_BASE_COST_AT_LEAST_8_ANY_CLASS |
| CATA_302 | Mend | W WC | healing_draw | MINION | HEAL_MINION_TO_FULL |  |  |
| CATA_303 | Purifying Breath | F  | damage_outcome_followup | MINION_AND_ENEMY_HERO | IF_KILLED, HEAL_ENEMY_HERO |  |  |
| CATA_485 | Sleet Storm | W WC | sequential_damage | CHARACTER_THEN_RANDOM_ENEMY_MINION |  |  |  |
| CATA_528 | Sigil of the Seas | W WC | delayed_fixed_summon | NONE | NEXT_OWN_TURN_SUMMON_FIXED | CATA_528t |  |
| CATA_554 | Earthen Roar | W WC | stat_set_retarget | ENEMY_MINION | SET_HEALTH_1, HOLDING_DRAGON, SECOND_TARGET_CHOICE |  |  |
| CATA_581 | Decimation | F  | state_scaled_damage | ALL_MINIONS | DAMAGE_ALL_MINIONS, BOARD_COUNT_SCALING |  |  |
| CATA_582 | Searing Fissure | F  | area_damage_hero_attack | ALL_MINIONS_AND_SELF_HERO | DAMAGE_ALL_MINIONS | CS2_045e |  |
| CATA_585 | Torch | F W WC | excess_damage_return_outlier | DAMAGED_MINION | DAMAGE_DAMAGED_MINION, NO_SPELLPOWER, EXCESS_DAMAGE, RETURN_SELF_WITH_DAMAGE |  | SELF_VARIANT:CATA_585 |
| CATA_621 | Gelbin's Triumph | W WC | random_persistent_aura | NONE | GENERATE_RANDOM_PALADIN_AURA, EXTEND_AURA_DURATION |  | PALADIN_AURA_SPELLS |
| CORE_AT_037 | Living Roots | W WC | choose_one_composition | CHARACTER_IF_DAMAGE_OPTION | CHOOSE_ONE | AT_037a, AT_037b, AT_037t |  |
| CORE_AT_055 | Flash Heal | W WC | healing_draw | CHARACTER | HEAL_CHARACTER |  |  |
| CORE_BAR_801 | Wound Prey | W WC | fixed_summon_composition | CHARACTER |  | BAR_035t |  |
| CORE_BOT_222 | Spirit Bomb | W WC | fixed_damage | MINION_THEN_OWN_HERO | DAMAGE_OWN_HERO |  |  |
| CORE_BOT_451 | Voltaic Burst | W WC | overload_composition | NONE | OVERLOAD | BOT_102t |  |
| CORE_CS1_130 | Holy Smite | W WC | fixed_damage | MINION |  |  |  |
| CORE_CS2_004 | Power Word: Shield | W WC | stat_keyword_enchant | MINION | BUFF_MINION_HEALTH | CS2_004e |  |
| CORE_CS2_029 | Fireball | F  | fixed_damage | CHARACTER |  |  |  |
| CORE_CS2_032 | Flamestrike | F  | fixed_damage | ENEMY_MINIONS |  |  |  |
| CORE_CS2_062 | Hellfire | F  | fixed_damage | ALL_CHARACTERS |  |  |  |
| CORE_CS2_074 | Deadly Poison | W WC | weapon_buff | FRIENDLY_WEAPON | BUFF_WEAPON_ATTACK | CS2_074e |  |
| CORE_CS2_108 | Execute | W WC | destroy_followup | DAMAGED_ENEMY_MINION | DESTROY_DAMAGED_ENEMY_MINION |  |  |
| CORE_DS1_184 | Tracking | W WC | discover_deck | NONE | DISCOVER_ACTUAL_DECK, DRAW_SELECTED |  | ACTUAL_DECK_INSTANCES |
| CORE_DS1_185 | Arcane Shot | W WC | fixed_damage | CHARACTER |  |  |  |
| CORE_EX1_238 | Lightning Bolt | W WC | overload_composition | CHARACTER | OVERLOAD |  |  |
| CORE_EX1_302 | Mortal Coil | W WC | damage_outcome_followup | MINION | IF_KILLED |  |  |
| CORE_EX1_391 | Slam | W WC | damage_outcome_followup | MINION | IF_SURVIVES |  |  |
| CORE_EX1_610 | Explosive Trap | F  | reactive_secret | NONE | SECRET_HERO_ATTACKED, DAMAGE_ALL_ENEMIES |  |  |
| CORE_GIL_836 | Blazing Invocation | F W WC | discover_predicate | NONE | DISCOVER_BATTLECRY |  | BATTLECRY_DISCOVER_PLAYER_CLASS_NEUTRAL |
| CORE_LOOT_101 | Explosive Runes | F  | reactive_secret | NONE | DAMAGE_AND_EXCESS |  |  |
| CORE_SW_108 | First Flame | F W WC | fixed_hand_generation | MINION |  | SW_108t |  |
| CORE_WON_337 | Ironforge Portal | F  | random_summon | NONE | RANDOM_SUMMON |  | MINION_BASE_COST_4_ANY_CLASS |
| CORE_WON_350 | I Know a Guy | W WC | discover_predicate | NONE | DISCOVER_TAUNT, BUFF_GENERATED_STATS |  | TAUNT_DISCOVER_PLAYER_CLASS_NEUTRAL |
| CORE_YOP_001 | Illidari Studies | W WC | discover_predicate | NONE | DISCOVER_OUTCAST, NEXT_OUTCAST_COST_REDUCTION |  | OUTCAST_DISCOVER_PLAYER_CLASS_NEUTRAL |
| Core_LOE_115 | Raven Idol | W WC | choose_one_discover | NONE | CHOOSE_ONE, DISCOVER_MINION, DISCOVER_SPELL | LOE_115a, LOE_115b | MINION_DISCOVER_PLAYER_CLASS_NEUTRAL, SPELL_DISCOVER_PLAYER_CLASS_NEUTRAL |
| DINO_406 | Fire Breath | F  | tribal_multi_zone_buff | CHARACTER_AND_ELEMENTALS | BUFF_ELEMENTALS | ICC_210e |  |
| DINO_417 | Soulrest Ceremony | W WC | temporary_board_keywords | FRIENDLY_BOARD | BUFF_BOARD_ATTACK, GRANT_RUSH, END_TURN_DESTROY |  |  |
| EDR_251 | Dragonscale Armaments | W WC | provenance_filtered_draw | SELF | DRAW_STARTED_IN_DECK, DRAW_NOT_STARTED_IN_DECK |  | ACTUAL_DECK_BY_START_PROVENANCE |
| EDR_273 | Symbiosis | W WC | discover_predicate | NONE | DISCOVER_OTHER_CLASS_CHOOSE_ONE |  | OTHER_CLASS_CHOOSE_ONE |
| EDR_522 | Mimicry | W WC | hidden_zone_copy | OPPONENT | OPPONENT_DRAW, COPY_DRAWN_TO_HAND |  | ACTUAL_OPPONENT_DRAWN_INSTANCES |
| EDR_528 | Nightmare Fuel | W WC | discover_dark_gift | NONE | DISCOVER_OPPONENT_DECK_COPY, COMBO, DARK_GIFT |  | ACTUAL_OPPONENT_DECK_MINIONS, DARK_GIFT_OPTIONS |
| EDR_531 | Siphoning Growth | W WC | destroy_followup | FRIENDLY_MINION_AND_SELF_HERO | DESTROY_FRIENDLY_MINION |  |  |
| EDR_570 | Ominous Nightmares | W WC | choose_one_composition | DAMAGED_MINION_IF_BUFF_OPTION | CHOOSE_ONE, DAMAGE_ALL_MINIONS, BUFF_DAMAGED_MINION |  |  |
| EDR_811 | Rite of Atrocity | W WC | corpses_dark_gift | NONE | DISCOVER_UNDEAD, SPEND_CORPSES, DARK_GIFT |  | UNDEAD_DISCOVER_PLAYER_CLASS_NEUTRAL, DARK_GIFT_OPTIONS |
| EDR_813 | Morbid Swarm | W WC | corpses_choose_one | MINION_IF_DAMAGE_OPTION | CHOOSE_ONE, SPEND_CORPSES | EDR_813a, EDR_813b, EDR_813at |  |
| EDR_872 | Spark of Life | W WC | choose_one_discover | NONE | CHOOSE_ONE, DISCOVER_CLASS_SPELL |  | SPELL_MAGE, SPELL_DRUID |
| END_017 | Battle at the End Time | W  | quest_excluded_from_random | NONE | QUEST_LONG_LIVED_STATE, REWARD_GENERATION |  | QUEST_REWARD_BY_ROOT |
| END_020 | Eternal Toil | W WC | damage_outcome_followup | MINION | IF_SURVIVES, IF_KILLED, RANDOM_SUMMON |  | MINION_BASE_COST_1_ANY_CLASS |
| END_024 | Flames of Infinity | F  | reactive_secret | NONE | INFINITE_DAMAGE_HIGHEST_HEALTH |  |  |
| END_025 | Eternal Firebolt | F  | conditional_spell_return | MINION | LIFESTEAL, IF_KILLED, END_TURN_RETURN_SELF |  | SELF_VARIANT:END_025 |
| END_027 | Wings of Eternity | W WC | discover_dark_gift | NONE | DISCOVER_PAST_DRAGON, DARK_GIFT | EDR_102t | DRAGON_FROM_PAST, DARK_GIFT_OPTIONS |
| FIR_900 | Cremate | F  | discover_dark_gift | NONE | DISCOVER_MINION, DARK_GIFT | EDR_102t | MINION_DISCOVER_PLAYER_CLASS_NEUTRAL, DARK_GIFT_OPTIONS |
| FIR_906 | Overheat | F  | school_discard_composition | FRIENDLY_BOARD | BUFF_FRIENDLY_BOARD, RANDOM_HAND_NATURE_DISCARD, CONDITIONAL_EXTRA_BUFF |  |  |
| FIR_909 | Bursting Shot | F  | random_distinct_targets | UP_TO_THREE_DISTINCT_ENEMIES | DAMAGE_RANDOM_DISTINCT_ENEMIES |  |  |
| FIR_910 | Scorching Winds | F  | school_discard_composition | CHARACTER | RANDOM_HAND_FIRE_DISCARD, CONDITIONAL_EXTRA_DAMAGE |  |  |
| FIR_911 | Smoldering Grove | F  | smoldering_hand_age | SELF | HAND_TURN_UPGRADE, AUTO_DISCARD |  |  |
| FIR_914 | Smoldering Strength | F W WC | smoldering_hand_age | FRIENDLY_MINION | BUFF_FRIENDLY_MINION, HAND_TURN_UPGRADE, AUTO_DISCARD | FIR_914e |  |
| FIR_916 | Smoldering Ascent | F  | smoldering_hand_age | ENEMY_MINIONS | HAND_TURN_UPGRADE, AUTO_DISCARD |  |  |
| FIR_920 | Smoke Bomb | F  | discover_dark_gift | NONE | DISCOVER_COMBO_BATTLECRY_STEALTH_MINION, DARK_GIFT | EDR_102t | COMBO_BATTLECRY_STEALTH_DISCOVER_PLAYER_CLASS_NEUTRAL, DARK_GIFT_OPTIONS |
| FIR_923 | Flames of the Firelord | F  | state_scaled_damage | RANDOM_ENEMY_MINION | HELD_COST_AT_LEAST_8, CONDITIONAL_DAMAGE |  |  |
| FIR_939 | Shadowflame Suffusion | F  | discover_dark_gift | CHARACTER | DISCOVER_WARRIOR_MINION, DARK_GIFT | EDR_102t | WARRIOR_MINIONS, DARK_GIFT_OPTIONS |
| FIR_941 | Searing Reflection | F  | deck_draw_copy_summon | NONE | DRAW_MINION, COPY_AS_8_8, DIVINE_SHIELD, SUMMON_COPY |  | ACTUAL_DECK_MINIONS |
| FIR_954 | Conflagrate | F W WC | damage_outcome_followup | MINION_AND_ITS_OWNER | DRAW_TARGET_OWNER |  |  |
| JAIL_125 | Cold Snap | W WC | random_school_generation | ENEMY_CHARACTER | GENERATE_RANDOM_FROST_SPELL |  | FROST_SPELL_ANY_CLASS |
| JAIL_307 | Crowd Control | F  | state_scaled_damage | ALL_MINIONS | DAMAGE_ALL_MINIONS, REPEAT_TWO, DECK_SIZE_COST_REDUCTION |  |  |
| JAIL_319 | The Skeleton Key | W WC | refresh_discover_outlier | NONE | DISCOVER_SPELL, REPEAT_REFRESH_OPTIONS, RANDOM_SELF_DAMAGE |  | SPELL_DISCOVER_PLAYER_CLASS_NEUTRAL |
| JAIL_386 | Scramble for Gear | W WC | cast_when_drawn_shuffle | SELF | SHUFFLE_FIXED, CAST_WHEN_DRAWN | JAIL_386t |  |
| JAIL_732 | Void Soul | W WC | future_generated_state | NONE | RANDOM_DEMON_SUMMON, FUTURE_VOID_SOUL_UPGRADE |  | DEMON_COST_FUTURE_VOID_SOUL |
| JAIL_801 | Molten Gold | F  | held_spell_transform | CHARACTER |  | JAIL_801t |  |
| JAIL_940 | Undeath Sentence | W WC | death_history_replay | NONE | RANDOM_FRIENDLY_DEATH_HISTORY, TRIGGER_DEATHRATTLE |  | DEATHRATTLES_FROM_FRIENDLY_GAME_HISTORY |
| MEND_300 | Tame Pet | W WC | future_companion_override | SELF | FUTURE_ANIMAL_COMPANION_REPLACEMENT |  | BEAST_COST_PREVIOUS_COMPANION_PLUS_1 |
| TIME_006 | Mirror Dimension | W WC | fixed_summon_composition | NONE | HOLDING_DRAGON, CONDITIONAL_COUNT | TIME_006t1 |  |
| TIME_026 | Entropic Continuity | W WC | cast_when_drawn_shuffle | FRIENDLY_BOARD | BUFF_FRIENDLY_BOARD, SHUFFLE_FIXED, CAST_WHEN_DRAWN | TIME_025t, TIME_026e |  |
| TIME_039 | Deja Vu | W WC | hidden_zone_copy | NONE | DISCOVER_OPPONENT_HAND, COPY_TO_HAND |  | ACTUAL_OPPONENT_HAND_INSTANCES |
| TIME_212 | Lightning Rod | W WC | sequential_damage | FRIENDLY_MINION_THEN_RANDOM_ENEMY_MINION | DAMAGE_FRIENDLY_MINION |  |  |
| TIME_447 | Power Word: Barrier | W WC | stat_keyword_enchant | CHARACTER_AND_HAND | SHIELD_CHARACTER, BUFF_HAND_HEALTH | ULD_191e |  |
| TIME_701 | Waveshaping | W WC | discover_deck | NONE | DISCOVER_ACTUAL_DECK, DRAW_SELECTED, BOTTOM_UNSELECTED |  | ACTUAL_DECK_INSTANCES |
| TIME_EVENT_999 | Sands of Time | W  | rewind_discover | NONE | REWIND, DISCOVER_ANY_CLASS_SPELL, DISCOVER_OWN_CLASS_ON_REWIND |  | SPELL_ANY_CLASS, SPELL_PLAYER_CLASS |
| TLC_221 | Sizzling Swarm | F  | damage_scaled_summon | CHARACTER | SUMMON_COUNT_DAMAGE_DEALT | TLC_249 |  |
| TLC_222 | Flight of the Firehawk | F  | type_filtered_draw_buff | SELF | DRAW_DIFFERENT_MINION_TYPES, BUFF_DRAWN_STATS |  | ACTUAL_DECK_DIFFERENT_MINION_TYPES |
| TLC_227 | Lava Flow | F  | overload_composition | LOWEST_HEALTH_ENEMY | LOWEST_HEALTH_ENEMY_DAMAGE, REPEAT_THREE, OVERLOAD |  |  |
| TLC_229 | Spirit of the Mountain | W  | quest_excluded_from_random | NONE | QUEST_LONG_LIVED_STATE, REWARD_GENERATION |  | QUEST_REWARD_BY_ROOT |
| TLC_235 | Life Cycle | W WC | random_summon | MINION | DESTROY_MINION, RANDOM_SAME_COST_REPLACEMENT |  | MINION_BASE_COST_EQUALS_DESTROYED |
| TLC_239 | Restore the Wild | W  | quest_excluded_from_random | NONE | QUEST_LONG_LIVED_STATE, REWARD_GENERATION |  | QUEST_REWARD_BY_ROOT |
| TLC_426 | Dive the Golakka Depths | W  | quest_excluded_from_random | NONE | QUEST_LONG_LIVED_STATE, REWARD_GENERATION |  | QUEST_REWARD_BY_ROOT |
| TLC_433 | Reanimate the Terror | W  | quest_excluded_from_random | NONE | QUEST_LONG_LIVED_STATE, REWARD_GENERATION |  | QUEST_REWARD_BY_ROOT |
| TLC_435 | Crypt Map | W WC | discover_then_play_other_option | NONE | DISCOVER_FROST_RUNE, IF_PLAY_THIS_TURN_PICK_OTHER |  | FROST_RUNE_CARDS |
| TLC_442 | Submerged Map | W WC | discover_then_play_other_option | NONE | DISCOVER_MURLOC, IF_PLAY_THIS_TURN_PICK_OTHER |  | MURLOC_DISCOVER_PLAYER_CLASS_NEUTRAL |
| TLC_446 | Escape the Underfel | W  | quest_excluded_from_random | NONE | QUEST_LONG_LIVED_STATE, REWARD_GENERATION |  | QUEST_REWARD_BY_ROOT |
| TLC_460 | The Forbidden Sequence | W  | quest_excluded_from_random | NONE | QUEST_LONG_LIVED_STATE, REWARD_GENERATION |  | QUEST_REWARD_BY_ROOT |
| TLC_464 | Mountain Map | W WC | discover_then_play_other_option | NONE | DISCOVER_UNPLAYED_TYPE, IF_PLAY_THIS_TURN_PICK_OTHER |  | MINIONS_UNPLAYED_TYPES |
| TLC_513 | Lie in Wait | W  | quest_excluded_from_random | NONE | QUEST_LONG_LIVED_STATE, REWARD_GENERATION |  | QUEST_REWARD_BY_ROOT |
| TLC_517 | Knockback | W WC | held_history_damage | MINION | GAME_SHUFFLE_COUNT |  |  |
| TLC_602 | Enter the Lost City | W  | quest_excluded_from_random | NONE | QUEST_LONG_LIVED_STATE, REWARD_GENERATION |  | QUEST_REWARD_BY_ROOT |
| TLC_631 | Unleash the Colossus | W  | quest_excluded_from_random | NONE | QUEST_LONG_LIVED_STATE, REWARD_GENERATION |  | QUEST_REWARD_BY_ROOT |
| TLC_632 | Story of Sulfuras | F  | temporary_hero_power_swap | NONE | REPLACE_HERO_POWER, TWO_USE_RETURN, RANDOM_ENEMY_DAMAGE | TLC_632t, TLC_632t2 |  |
| TLC_817 | Reach Equilibrium | W  | quest_excluded_from_random | NONE | QUEST_LONG_LIVED_STATE, REWARD_GENERATION |  | QUEST_REWARD_BY_ROOT |
| TLC_824 | Odd Map | W WC | discover_then_play_other_option | NONE | DISCOVER_ODD_ATTACK_BEAST, IF_PLAY_THIS_TURN_PICK_OTHER |  | ODD_BASE_ATTACK_BEAST_DISCOVER_PLAYER_CLASS_NEUTRAL |
| TLC_830 | The Food Chain | W  | quest_excluded_from_random | NONE | QUEST_LONG_LIVED_STATE, REWARD_GENERATION |  | QUEST_REWARD_BY_ROOT |
| TLC_900 | Hive Map | W WC | discover_then_play_other_option | NONE | DISCOVER_FEL_SPELL, IF_PLAY_THIS_TURN_PICK_OTHER |  | FEL_SPELL_DISCOVER_PLAYER_CLASS_NEUTRAL |
| TLC_EVENT_400 | Storm the Gates | W  | sidequest_composite_minion | NONE | SIDEQUEST, SUMMON_BEAST_UNDEAD_COUNT, CRAFT_ZOMBEAST |  | ZOMBEAST_COMPONENTS |
