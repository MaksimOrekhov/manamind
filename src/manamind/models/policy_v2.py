"""Visible entity/action policy v2; no transitions, handles or hidden zones."""
from __future__ import annotations

import math

import numpy as np
import torch
from torch import nn

from manamind.domain.card import CardFeatures
from manamind.domain.entity import LocationEntity
from manamind.encoding.entity_encoder import NUMERIC_FEATURES, PRESENCE_FEATURES, STATE_FLAG_NAMES
from manamind.models.policy import (
    ACTION_FEATURE_NAMES, CARD_EMBEDDING_DIM, POLICY_STATE_FEATURE_NAMES,
    _scaled, encode_legal_actions, encode_policy_state,
)

REPRESENTATION_VERSION = 2
ROLES = ("self_hero", "opponent_hero", "self_hand", "self_board", "opponent_board",
         "self_weapon", "opponent_weapon", "self_hero_power", "opponent_hero_power",
         "self_active_effects", "opponent_active_effects")
KINDS = ("HERO", "HERO_POWER", "MINION", "LOCATION", "SPELL", "WEAPON")
ACTION_VALUES = ("card_cost", "card_attack", "card_health", "card_durability", "card_spell_damage",
                 "source_attack", "source_health", "source_board_position", "hand_index",
                 "target_attack", "target_health", "target_board_position", "target_taunt")
ACTION_V2_FEATURE_NAMES = (
    *ACTION_FEATURE_NAMES, "card_durability", *(f"has_{k}" for k in ACTION_VALUES),
    *(f"source_kind_{k.lower()}" for k in KINDS), *(f"target_kind_{k.lower()}" for k in KINDS),
    "has_source", "has_target", "has_left_neighbor", "has_right_neighbor",
    "source_attack_minus_target_health", "has_source_attack_minus_target_health",
    "target_attack_minus_source_health", "has_target_attack_minus_source_health",
)
LINK_NAMES = ("source", "target", "left_neighbor", "right_neighbor")
HAND_SEMANTICS = ("shatter_left", "shatter_right", "shatter_solo", "shatter_partner_relative_position",
                  "prepare_locked", "prepare_locked_known")
HERO_FEATURES = ("hero_armor", "hero_frozen", "hero_frozen_known", "hero_divine_shield",
                 "hero_divine_shield_known")


def feature_contract(encoder) -> dict:
    """Every ordered column, including vocabulary-dependent categories, is owned by the file."""
    vocab = encoder.vocabulary.to_dict()
    categories = {k: [name for name, _ in sorted(vocab[k].items(), key=lambda item: item[1])]
                  for k in ("type_ids", "class_ids", "race_ids")}
    mechanics = [f"mechanic_index_{i}" for i in range(encoder.vocabulary.mechanics_count)]
    entity = [*NUMERIC_FEATURES, *PRESENCE_FEATURES, *STATE_FLAG_NAMES, *HAND_SEMANTICS,
              *mechanics, *(f"{key}_{name}" for key, names in categories.items() for name in names),
              *(f"role_{role}" for role in ROLES), *HERO_FEATURES]
    state = [*POLICY_STATE_FEATURE_NAMES,
             *(f"{side}_class_{name}" for side in ("self", "opponent") for name in categories["class_ids"])]
    return {"representation_version": REPRESENTATION_VERSION, "state_feature_names": state,
            "entity_feature_names": entity, "action_feature_names": list(ACTION_V2_FEATURE_NAMES),
            "entity_roles": list(ROLES), "action_links": list(LINK_NAMES),
            "normalization": "signed_log1p_clip_10000; categorical_and_masks_unscaled"}


def _one_hot(indices, count):
    return np.eye(count, dtype=np.float32)[indices]


def encode_policy_v2(state, actions, encoder, device="cpu") -> tuple:
    """Resolve semantic positions to *local token indices*, never protocol entity IDs.

    Both boards share minion/Location position semantics. All entities are retained;
    there is no truncation or opponent hand/deck/secret identity channel.
    """
    if (state.active_player != "SELF" or state.opponent_known_cards or state.pending_choice_owner is not None
            or state.self_player.known_secrets or state.opponent.known_secrets):
        raise ValueError("Policy v2 requires the reviewed real MAIN_ACTION visibility boundary")
    encoded = encoder.encode(state)
    ids, features, lookup, visible_identity = [], [], {}, {}
    def add(zone, role, keys, hero=None):
        if zone.size != len(keys):
            raise ValueError("Invalid entity alignment")
        values = np.concatenate((zone.numeric, zone.numeric_present, zone.state_flags,
                                 zone.hand_semantic_features, zone.mechanics,
                                 _one_hot(zone.card_type_ids, encoder.vocabulary.card_type_count),
                                 _one_hot(zone.card_class_ids, encoder.vocabulary.card_class_count),
                                 _one_hot(zone.race_ids, encoder.vocabulary.race_count),
                                 np.tile(_one_hot([ROLES.index(role)], len(ROLES)), (zone.size, 1)),
                                 np.zeros((zone.size, len(HERO_FEATURES)), dtype=np.float32)), axis=1)
        if hero is not None:
            values[0, -len(HERO_FEATURES):] = [
                _scaled(hero.armor), float(hero.hero_frozen is True), float(hero.hero_frozen is not None),
                float(hero.hero_divine_shield is True), float(hero.hero_divine_shield is not None)]
        for index, key in enumerate(keys):
            if key in lookup:
                raise ValueError("Duplicate visible entity position")
            lookup[key] = len(ids)
            ids.append(int(zone.card_ids[index]))
            features.append(values[index])

    for side, player in (("self", state.self_player), ("opponent", state.opponent)):
        hero = CardFeatures(current_attack=player.hero_attack, current_health=player.hero_health)
        add(encoder.entity_encoder.encode_optional_card(hero), f"{side}_hero", [(side, "HERO", -1)], player)
    add(encoded.self_hand, "self_hand", [("self", "HAND", i) for i in range(len(state.self_hand))])
    visible_identity.update({("self", "HAND", i): (c.card_id, c.card_type) for i, c in enumerate(state.self_hand)})
    for side, player in (("self", state.self_player), ("opponent", state.opponent)):
        # Sorting is only canonical token order; positions stay explicit and shared.
        for item in sorted((*player.board, *player.locations), key=lambda x: x.board_position):
            kind = "LOCATION" if isinstance(item, LocationEntity) else "MINION"
            zone = (encoder.entity_encoder.encode_locations((item,)) if kind == "LOCATION"
                    else encoder.entity_encoder.encode_board((item,)))
            add(zone, f"{side}_board", [(side, "BOARD", item.board_position)])
            visible_identity[(side, "BOARD", item.board_position)] = (item.card.card_id, kind)
        for role in ("weapon", "hero_power", "active_effects"):
            zone = getattr(encoded, f"{side}_{role}")
            add(zone, f"{side}_{role}", [(side, role.upper(), i) for i in range(zone.size)])
        if player.hero_power is not None:
            visible_identity[(side, "HERO_POWER", 0)] = (player.hero_power.card_id, "HERO_POWER")

    state_features = np.concatenate((encode_policy_state(state, encoder),
        _one_hot([encoded.self_class_id, encoded.opponent_class_id], encoder.vocabulary.card_class_count).ravel()))
    action_features = np.zeros((len(actions), len(ACTION_V2_FEATURE_NAMES)), dtype=np.float32)
    action_features[:, :len(ACTION_FEATURE_NAMES)] = encode_legal_actions(actions)
    card_ids = np.zeros((len(actions), 2), dtype=np.int64)
    links = np.full((len(actions), len(LINK_NAMES)), -1, dtype=np.int64)
    def resolve(key):
        if key not in lookup:
            raise ValueError("Action entity is absent from the current visible state")
        return lookup[key]
    for i, action in enumerate(actions):
        def put(name, value):
            action_features[i, ACTION_V2_FEATURE_NAMES.index(name)] = value
        put("card_durability", _scaled(action.get("card_durability")))
        for name in ACTION_VALUES:
            put(f"has_{name}", float(action.get(name) is not None))
        for role in ("source", "target"):
            kind = action.get(f"{role}_kind")
            if kind in KINDS:
                put(f"{role}_kind_{kind.lower()}", 1.0)
        if action["type"] != "END_TURN":
            source_id = action.get("source_card_id") or action.get("card_id")
            card_ids[i, 0] = encoder.vocabulary.card_id(source_id)
            if action["type"] == "PLAY_CARD":
                position = action["hand_index"]
                if state.self_hand[position].card_id != source_id:
                    raise ValueError("Action source differs from the current hand")
                key = ("self", "HAND", position)
            elif action.get("source_kind") == "HERO":
                key = ("self", "HERO", -1)
            elif action.get("source_kind") == "HERO_POWER":
                key = ("self", "HERO_POWER", 0)
            else:
                key = ("self", "BOARD", action.get("source_board_position"))
            links[i, 0] = resolve(key)
            if key[1] != "HERO" and visible_identity[key] != (source_id, action.get("source_kind")):
                raise ValueError("Action source identity differs from visible entity")
        if "target_kind" in action:
            side = "self" if action["target_side"] == "SELF" else "opponent"
            key = ((side, "HERO", -1) if action["target_kind"] == "HERO"
                   else (side, "BOARD", action.get("target_board_position")))
            links[i, 1] = resolve(key)
            card_ids[i, 1] = encoder.vocabulary.card_id(action.get("target_card_id"))
            if key[1] != "HERO" and visible_identity[key] != (action.get("target_card_id"), action["target_kind"]):
                raise ValueError("Action target identity differs from visible entity")
        position = action["play_position"]
        if position > 0:
            board_count = len(state.self_player.board) + len(state.self_player.locations)
            if action["type"] != "PLAY_CARD" or not 1 <= position <= board_count + 1:
                raise ValueError("Invalid insertion slot")
            if position > 1:
                links[i, 2] = resolve(("self", "BOARD", position - 1))
            if position <= board_count:
                links[i, 3] = resolve(("self", "BOARD", position))
        for j, name in enumerate(LINK_NAMES):
            put(f"has_{name}", float(links[i, j] >= 0))
        for left, right, name in (
            ("source_attack", "target_health", "source_attack_minus_target_health"),
            ("target_attack", "source_health", "target_attack_minus_source_health"),
        ):
            known = action.get(left) is not None and action.get(right) is not None
            put(name, _scaled(action[left] - action[right]) if known else 0.0)
            put(f"has_{name}", float(known))
    return tuple(torch.as_tensor(a, dtype=dtype, device=device) for a, dtype in (
        (state_features, torch.float32), (ids, torch.long), (np.asarray(features), torch.float32),
        (action_features, torch.float32), (card_ids, torch.long), (links, torch.long)))


class PolicyNetworkV2(nn.Module):
    """Shared entity projection and candidate-conditioned attention over visible tokens."""
    representation_version = REPRESENTATION_VERSION

    def __init__(self, card_count, state_feature_count, entity_feature_count, hidden_size=64, dropout=0.1):
        super().__init__()
        self.state_feature_count = state_feature_count
        self.entity_feature_count = entity_feature_count
        self.hidden_size = hidden_size
        self.dropout = dropout
        self.card_embedding = nn.Embedding(card_count, CARD_EMBEDDING_DIM, padding_idx=0)
        self.entity_encoder = nn.Sequential(nn.Linear(entity_feature_count + CARD_EMBEDDING_DIM, hidden_size), nn.Tanh())
        self.global_encoder = nn.Sequential(nn.Linear(state_feature_count, hidden_size), nn.Tanh())
        self.action_encoder = nn.Sequential(nn.Linear(len(ACTION_V2_FEATURE_NAMES) + 2 * CARD_EMBEDDING_DIM
                                                      + 2 * hidden_size, hidden_size), nn.Tanh())
        self.scorer = nn.Sequential(nn.Linear(6 * hidden_size, hidden_size), nn.Tanh(),
                                    nn.Dropout(dropout), nn.Linear(hidden_size, 1))

    def forward(self, state, ids, entities, actions, card_ids, links):
        n = actions.shape[0]
        if (state.shape != (self.state_feature_count,) or ids.ndim != 1 or len(ids) < 2
                or entities.shape != (len(ids), self.entity_feature_count)
                or actions.shape != (n, len(ACTION_V2_FEATURE_NAMES)) or n == 0
                or card_ids.shape != (n, 2) or links.shape != (n, 4)
                or bool((links < -1).any()) or bool((links >= len(ids)).any())):
            raise ValueError("Incompatible policy v2 input shapes or entity links")
        tokens = self.entity_encoder(torch.cat((entities, self.card_embedding(ids)), dim=-1))
        gathered = tokens[links.clamp_min(0)] * links.ge(0).unsqueeze(-1)
        source, target, left, right = gathered.unbind(dim=1)
        query = self.action_encoder(torch.cat((actions, self.card_embedding(card_ids).flatten(1), source, target), dim=-1))
        attention = torch.softmax(query @ tokens.T / math.sqrt(self.hidden_size), dim=-1)
        context = attention @ tokens
        global_rows = self.global_encoder(state).expand(n, -1)
        return self.scorer(torch.cat((query, global_rows, context, source * target, left, right), dim=-1)).squeeze(-1)
