"""Structural validation of observation records (mirrors EVIDENCE_BUNDLE_SCHEMA_PROPOSAL.json).

Errors carry a field path and a stable code only, never a value.
"""

from __future__ import annotations

import re

from . import EVIDENCE_LIMITS, OBSERVATION_SCHEMA

VISIBILITY = {"PUBLIC_TO_SELF", "SELF_PRIVATE", "OFFLINE_ONLY_HIDDEN"}
BASIS = {"CREATOR_TAG", "LAST_AFFECTED_BY_SAME_UNIT", "UNIT_OWNER", "NESTED_ONLY", "UNATTRIBUTED"}
FACT_KINDS = {
    "BLOCK_STRUCTURE", "PLAY_TARGET", "COST_PAYMENT", "DAMAGE_PACKET", "HEALING_PACKET", "ZONE_MOVE",
    "ENTITY_CREATED", "ENTITY_TRANSFORMED", "ENTITY_REVEALED", "ENCHANTMENT_ATTACHED", "ENCHANTMENT_REMOVED",
    "STAT_DELTA", "KEYWORD_DELTA", "DEATH", "CHOICE_OFFERED", "CHOICE_MADE", "TARGET_LEGALITY",
    "TURN_STEP_CONTEXT", "CONTROL_CHANGE",
}
INFERENCE_KINDS = {
    "CONDITION_EVALUATED_FROM_BEFORE_STATE", "DEATH_BY_DAMAGE", "DESTROY_WITHOUT_DAMAGE",
    "STAT_CHANGE_EXPLAINED_BY_ENCHANTMENT", "STAT_CHANGE_UNEXPLAINED", "SPELL_DAMAGE_OR_MODIFIER_PRESENT",
    "DIVINE_SHIELD_ABSORBED", "BATTLECRY_FROM_OWN_POWER_BLOCK", "REPEATED_TRIGGER_COUNT",
    "HIDDEN_CONDITION_IMPLIED_BY_OUTCOME", "CANDIDATE_SET_FROM_BEFORE_STATE",
}
CONFOUNDER_KINDS = {
    "FOREIGN_ENCHANTMENT_ACTIVE", "FOREIGN_UNIT_WITH_EFFECTS_IN_WINDOW", "STALE_LAST_AFFECTED_BY",
    "MULTIPLE_OWNER_UNITS", "AURA_RECALC_OUTSIDE_BLOCK", "UNKNOWN_TAG_IDS_IN_WINDOW", "HIDDEN_CONDITION_INPUT",
    "DAMAGE_OR_HEAL_MODIFIER_PRESENT", "MISSING_CREATOR_TAG", "MODE_OR_BUILD_OUTSIDE_SCOPE",
}
ROLES = {
    "PLAYED_CARD", "HERO_POWER_USE", "LOCATION_ACTIVATION", "ATTACKER", "TRIGGER_SOURCE", "DEATHRATTLE_SOURCE",
    "TURN_PHASE_TRIGGER_SOURCE", "ENCHANTMENT_SOURCE", "SECRET_OR_QUEST_SOURCE", "GENERATED_OUTCOME",
    "CONTROL_SAMPLE",
}
TOP_LEVEL = {
    "schema", "observation_id", "subject", "provenance", "window", "public_states", "support_detection", "facts",
    "inferences", "confounders", "attribution_summary", "triage", "evidence_limits", "privacy",
}
CARD_ID = re.compile(r"^[A-Za-z0-9_]{1,64}$")


class SchemaError(ValueError):
    def __init__(self, path: str, code: str) -> None:
        super().__init__(f"{code} at {path}")
        self.path, self.code = path, code


def _require(condition: bool, path: str, code: str) -> None:
    if not condition:
        raise SchemaError(path, code)


def _check_ref(ref, path: str) -> None:
    _require(isinstance(ref, dict) and isinstance(ref.get("handle"), int), path, "ENTITY_REF")
    card_id = ref.get("card_id")
    _require(card_id is None or (isinstance(card_id, str) and bool(CARD_ID.match(card_id))), path, "CARD_ID")


def validate_observation(obs: dict) -> None:
    _require(set(obs) == TOP_LEVEL, "$", "TOP_LEVEL_KEYS")
    _require(obs["schema"] == OBSERVATION_SCHEMA, "schema", "SCHEMA_VERSION")
    _require(re.fullmatch(r"[0-9a-f]{16}", obs["observation_id"]) is not None, "observation_id", "ID_FORMAT")
    subject = obs["subject"]
    _require(subject["role"] in ROLES and bool(CARD_ID.match(subject["card_id"])), "subject", "SUBJECT")
    _require(re.fullmatch(r"[0-9a-f]{16}", obs["provenance"]["game_key16"]) is not None, "provenance", "GAME_KEY")
    _require(obs["provenance"]["source"] == "POWER_LOG", "provenance", "SOURCE")
    _require(obs["support_detection"]["basis"] in ("ENGINE_EFFECTIVE_INVENTORY", "DECLARATION_PROXY"),
             "support_detection", "BASIS")
    privacy = obs["privacy"]
    _require(privacy["model_input_allowed"] is False and privacy["names_removed"] is True, "privacy", "CONSTANTS")
    _require(tuple(obs["evidence_limits"]) == EVIDENCE_LIMITS, "evidence_limits", "LIMITS")

    fact_ids: set[str] = set()
    hidden = False
    for index, fact in enumerate(obs["facts"]):
        path = f"facts[{index}]"
        _require(set(fact) == {"fact_id", "kind", "unit_id", "visibility", "raw_ref", "attribution", "data"},
                 path, "FACT_KEYS")  # a fact never has inputs: that makes it an inference
        _require(fact["kind"] in FACT_KINDS and fact["visibility"] in VISIBILITY, path, "FACT_ENUM")
        _require(fact["attribution"]["basis"] in BASIS, path, "ATTRIBUTION_BASIS")
        _require(fact["fact_id"] not in fact_ids, path, "FACT_DUPLICATE")
        fact_ids.add(fact["fact_id"])
        hidden = hidden or fact["visibility"] == "OFFLINE_ONLY_HIDDEN"
        for key in ("entity", "enchantment", "target", "creator", "attached_to", "option_card"):
            ref = fact["data"].get(key)
            if isinstance(ref, dict):
                _check_ref(ref, f"{path}.data.{key}")
    _require(privacy["contains_offline_only_hidden"] == hidden, "privacy", "HIDDEN_FLAG")
    for index, inference in enumerate(obs["inferences"]):
        path = f"inferences[{index}]"
        _require(inference["kind"] in INFERENCE_KINDS, path, "INFERENCE_KIND")
        _require(bool(inference["inputs"]) and set(inference["inputs"]) <= fact_ids, path, "INFERENCE_INPUTS")
        _require(inference["status"] in ("DERIVED", "ASSUMPTION_DEPENDENT"), path, "INFERENCE_STATUS")
        _require(inference["visibility"] in VISIBILITY, path, "INFERENCE_VISIBILITY")
    for index, confounder in enumerate(obs["confounders"]):
        _require(confounder["kind"] in CONFOUNDER_KINDS, f"confounders[{index}]", "CONFOUNDER_KIND")
