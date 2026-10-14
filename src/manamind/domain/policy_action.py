"""Version 1 real MAIN_ACTION fields shared by imports and ML consumers.

Semantic fields contain visible identities/current stats only. Hand indices are
zero-based; board positions and play insertion slots are one-based as in
Power.log. Entity IDs, option IDs and localized names are private matching data.
"""
REAL_POLICY_ACTION_SCHEMA_VERSION = 1
ACTION_TYPES = frozenset({"PLAY_CARD", "ATTACK", "HERO_POWER", "ACTIVATE_LOCATION", "END_TURN"})
# Experimental (PREPARE-ROOTS-1): a Prepare card's second root. A menu containing it is NOT a version 1 menu, so rows
# that carry it use their own action schema number and the version 1 training loaders refuse them.
PREPARE_ACTION_SCHEMA_VERSION = 2
PREPARE_ACTION_TYPES = ACTION_TYPES | {"PREPARE_CARD"}
ACTION_FIELDS = frozenset({
    "type", "card_id", "card_type", "card_cost", "card_attack", "card_health",
    "card_spell_damage", "card_durability", "hand_index", "play_position", "source_kind", "source_card_id",
    "source_is_hero", "source_attack", "source_health", "source_board_position",
    "target_kind", "target_side", "target_card_id", "target_is_hero", "target_is_self",
    "target_attack", "target_health", "target_board_position", "target_taunt",
})
