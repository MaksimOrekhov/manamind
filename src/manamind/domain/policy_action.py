"""Version 1 real MAIN_ACTION fields shared by imports and ML consumers.

Semantic fields contain visible identities/current stats only. Hand indices are
zero-based; board positions and play insertion slots are one-based as in
Power.log. Entity IDs, option IDs and localized names are private matching data.
"""
REAL_POLICY_ACTION_SCHEMA_VERSION = 1
ACTION_TYPES = frozenset({"PLAY_CARD", "ATTACK", "HERO_POWER", "ACTIVATE_LOCATION", "END_TURN"})
ACTION_FIELDS = frozenset({
    "type", "card_id", "card_type", "card_cost", "card_attack", "card_health",
    "card_spell_damage", "card_durability", "hand_index", "play_position", "source_kind", "source_card_id",
    "source_is_hero", "source_attack", "source_health", "source_board_position",
    "target_kind", "target_side", "target_card_id", "target_is_hero", "target_is_self",
    "target_attack", "target_health", "target_board_position", "target_taunt",
})
