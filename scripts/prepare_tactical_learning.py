"""Freeze small declared fixtures, independently certified by Action Outcome."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
from dataclasses import asdict
from pathlib import Path

from manamind.domain.card import CardFeatures
from manamind.domain.entity import BoardEntity
from manamind.domain.game_state import GameState, PlayerObservation
from manamind.domain.serialization import game_state_from_dict
from manamind.live.snapshot import state_to_dict
from manamind.training.model_first_1_control import scenario_content_fingerprint, validate_no_control_overlap
from manamind.training.policy_checkpoint import identity, load_policy_checkpoint
from manamind.training.tactical_certificates import certify

ROOT = Path(__file__).resolve().parents[1]
INITIAL = ROOT / "data/processed_policy_retrain_1/seed42_v2/policy.pt"
INITIAL_SHA = "d2f18737be46bc1773997ec5106d1e30fdf2caaf645a3a7c8998956f092d6377"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def menu(state):
    """Complete fixture menu: ready attacks or one castable fixture spell, plus END."""
    opponents = [m for m in state.opponent.board if not m.immune and not m.dormant and not m.stealth]
    taunts = [m for m in opponents if m.taunt]
    actions = []
    sources = [(m.board_position, m.card.card_id, "MINION", m.current_attack, m.current_health)
               for m in state.self_player.board if m.can_attack and not m.frozen and m.current_attack > 0]
    if state.self_player.hero_attack > 0:
        sources.append((-1, "TL_HERO", "HERO", state.self_player.hero_attack, state.self_player.hero_health))

    def target(m, side):
        return {"target_kind": "MINION" if m else "HERO", "target_side": side,
                "target_is_hero": m is None, "target_board_position": m.board_position if m else -1,
                "target_card_id": m.card.card_id if m else None,
                "target_attack": m.current_attack if m else 0,
                "target_health": m.current_health if m else
                (state.self_player if side == "SELF" else state.opponent).hero_health,
                "target_taunt": m.taunt if m else False}
    for pos, card_id, kind, attack, health in sources:
        base = {"type": "ATTACK", "play_position": 0, "source_board_position": pos,
                "source_card_id": card_id, "source_kind": kind, "source_is_hero": kind == "HERO",
                "source_attack": attack, "source_health": health}
        for m in taunts or opponents:
            actions.append({**base, **target(m, "OPPONENT")})
        if not taunts:
            actions.append({**base, **target(None, "OPPONENT")})
    if state.self_hand:
        card = state.self_hand[0]
        base = {"type": "PLAY_CARD", "card_id": card.card_id, "card_type": "SPELL",
                "source_kind": "SPELL", "hand_index": 0, "card_cost": card.effective_cost,
                "play_position": 0}
        if card.card_id == "CORE_CS2_029":
            for side, player in (("SELF", state.self_player), ("OPPONENT", state.opponent)):
                actions.append({**base, **target(None, side)})
                for m in player.board:
                    if not m.immune and not m.dormant and not m.stealth:
                        actions.append({**base, **target(m, side)})
        else:
            actions.append(base)
    actions.append({"type": "END_TURN", "play_position": 0})
    return actions


def fixture(split, family, n, encoder, *, variant=0):
    rng = random.Random(int(identity([split, family, n, variant])[:12], 16))
    plain = [encoder.catalog.get(c["card_id"]) for c in encoder.catalog.to_dict()]
    plain = [c for c in plain if c.card_type == "MINION" and not c.mechanics
             and c.attack is not None and c.health is not None and c.card_id != "Core_CS2_200"]
    rng.shuffle(plain)
    records = []

    def entity(pos, a, h, **flags):
        base = plain[len(records) % len(plain)]
        # IDs may be known or aliases; full base metadata stays identical.
        card = base if rng.random() < 0.5 or split == "control" else CardFeatures(
            **{**asdict(base), "card_id": f"TL_{split}_{family}_{n}_{len(records)}"})
        records.append({"id": card.card_id, "text": "", "type": "MINION", "mechanics": [],
                        "attack": card.attack, "health": card.health})
        return BoardEntity(card, a, h, max(h, 16), pos, **flags)

    self_hp, enemy_hp, armor, shield = 20, 30, 0, False
    own, enemy, hand, weapon = [], [], [], None
    hero_attack = 0
    a, retaliation = rng.randint(2, 5), rng.randint(2, 5)
    goal, certainty = "REMOVE_AND_SURVIVE", "PROVEN_PROPERTY"
    if family in ("armor_finish", "shield_finish", "taunt_finish", "combined_finish", "two_taunts", "hero_shield_finish"):
        goal = "WIN_BY_ATTACKS" if family != "armor_finish" else "WIN_NOW"
        enemy_hp, armor = rng.randint(4, 8), rng.randint(1, 4)
        needed = enemy_hp + armor
        if family == "armor_finish":
            own = [entity(1, needed, 8, can_attack=True, lifesteal=True),
                   entity(2, needed-1, 8, can_attack=True)]
        elif family == "shield_finish":
            armor = 0
            shield = True
            own = [entity(1, 1, 8, can_attack=True), entity(2, enemy_hp, 8, can_attack=True)]
        elif family in ("taunt_finish", "combined_finish"):
            shield = family == "combined_finish"
            own = [entity(1, 1, 8, can_attack=True), entity(2, needed, 8, can_attack=True),
                   entity(3, 1, 8, can_attack=True)]
            enemy = [entity(1, 0, 1, taunt=True)]
        elif family == "two_taunts":
            own = [entity(i+1, v, 8, can_attack=True) for i, v in enumerate([1, 1, needed, 1])]
            enemy = [entity(1, 0, 1, taunt=True), entity(2, 0, 1, taunt=True)]
        else:
            shield = True
            own = [entity(1, 1, 8, can_attack=True)]
            hero_attack = needed
            weapon = CardFeatures(card_id="TL_WEAPON", card_type="WEAPON", attack=needed,
                                  durability=2, current_attack=needed, current_durability=2)
            records.append({"id": "TL_WEAPON", "text": "", "type": "WEAPON", "mechanics": []})
    elif family in ("poison", "poison_taunt", "poison_shield", "stats_target"):
        own = [entity(1, a, retaliation+3, can_attack=True, poisonous=True),
               entity(2, a, retaliation+3, can_attack=True,
                      poisonous=family in ("poison_shield", "stats_target"))]
        enemy = [entity(1, retaliation, a+10, taunt=family == "poison_taunt")]
        if family in ("poison_shield", "stats_target"):
            enemy.append(entity(2, retaliation, a+10, divine_shield=True))
            if family == "stats_target":
                from dataclasses import replace
                enemy[0] = replace(enemy[0], taunt=True)
            # Exactly one source survives retaliation; paired current-Health swap.
            from dataclasses import replace
            own[variant % 2] = replace(own[variant % 2], current_health=retaliation)
            if family == "stats_target" and n >= 4:
                own = [replace(m, poisonous=False, current_health=retaliation+3,
                               current_attack=a+10-i) for i, m in enumerate(own)]
    elif family in ("immune", "lifesteal", "shield_lifesteal"):
        goal = "LOCAL_PARETO"
        own = [entity(1, a, 8, can_attack=True, immune=family == "immune", lifesteal=family != "immune"),
               entity(2, a, 8, can_attack=True)]
        enemy = [entity(1, retaliation, a+5, taunt=True, divine_shield=family == "shield_lifesteal")]
    elif family in ("self_damage", "two_self_damage"):
        goal = "LOCAL_PARETO"
        own = [entity(i+1, a+i, 1) for i in range(2 if family == "two_self_damage" else 1)]
        hand = [CardFeatures(card_id="TL_DAMAGE_ALL", cost=1, current_cost=1,
                             card_class="WARRIOR", card_type="SPELL")]
        records.append({"id": "TL_DAMAGE_ALL", "text": "Deal $1 damage to all minions.", "type": "SPELL"})
    elif family in ("spell_finish", "spell_side"):
        goal = "WIN_NOW" if family == "spell_finish" else "LOCAL_PARETO"
        enemy_hp = rng.randint(2, 6) if family == "spell_finish" else 30
        own = [entity(1, 3, 6)]
        enemy = [entity(1, 3, 6, taunt=True)]
        hand = [encoder.catalog.get("CORE_CS2_029")]
        records.append({"id": "CORE_CS2_029", "text": "Deal $6 damage.", "type": "SPELL"})
    elif family in ("heuristic_trade", "ambiguous_face"):
        certainty = "HEURISTIC" if family == "heuristic_trade" else "AMBIGUOUS"
        goal = "REMOVE_AND_SURVIVE" if family == "heuristic_trade" else "AMBIGUOUS"
        own = [entity(1, a+2, 10, can_attack=True, lifesteal=True)]
        enemy = [entity(1, retaliation, a+1)]
        if family == "ambiguous_face":
            shield = None
    else:
        raise ValueError(family)
    rng.shuffle(own)
    rng.shuffle(enemy)
    from dataclasses import replace
    own = [replace(m, board_position=i+1) for i, m in enumerate(own)]
    enemy = [replace(m, board_position=i+1) for i, m in enumerate(enemy)]
    state = GameState(turn_number=rng.randint(2, 20), active_player="SELF",
                      self_player=PlayerObservation(hero_health=self_hp, hero_max_health=30,
                          hero_divine_shield=False, hero_frozen=False, healing_bonus=0,
                          board=tuple(own), weapon=weapon, hero_attack=hero_attack,
                          hand_size=len(hand), available_mana=4 if hand else 0, max_mana=4,
                          deck_size=20, player_class="MAGE" if hand and hand[0].card_id == "CORE_CS2_029" else "WARRIOR"),
                      opponent=PlayerObservation(hero_health=enemy_hp, hero_max_health=30,
                          armor=armor, hero_divine_shield=shield, hero_frozen=False, healing_bonus=0,
                          board=tuple(enemy), deck_size=20), self_hand=tuple(hand))
    actions = menu(state)
    # Recipe labels, independently checked below by forecasts/sequence proof.
    expected = []
    for i, act in enumerate(actions):
        source = next((m for m in own if m.board_position == act.get("source_board_position")), None)
        target = next((m for m in enemy if m.board_position == act.get("target_board_position")), None)
        if goal == "WIN_NOW":
            if act.get("target_kind") == "HERO" and act.get("target_side") == "OPPONENT" and (
                    act["type"] == "PLAY_CARD" or act.get("source_attack", 0) >= enemy_hp+armor):
                expected.append(i)
        elif goal == "WIN_BY_ATTACKS":
            if act["type"] == "ATTACK" and act["source_attack"] == 1:
                expected.append(i)
        elif goal == "REMOVE_AND_SURVIVE":
            if source and target and not target.divine_shield and source.current_health > target.current_attack and (
                    source.poisonous or source.current_attack >= target.current_health):
                expected.append(i)
        elif goal == "LOCAL_PARETO":
            if family in ("self_damage", "two_self_damage") and act["type"] == "END_TURN":
                expected.append(i)
            elif family == "spell_side" and act.get("target_side") == "OPPONENT":
                expected.append(i)
            elif source and (source.immune or source.lifesteal or family == "shield_lifesteal"):
                expected.append(i)
            elif family in ("lifesteal", "shield_lifesteal") and act["type"] == "END_TURN":
                expected.append(i)
    observed = {"spell_damage": 0, "spell_damage_doubled": False, "healing_does_damage": False,
                "spell_healing_doubled": False, "hand_keywords": [[] for _ in hand]}
    row = {"scenario_id": f"tl1_{split}_{family}_{n}_{variant}", "split": split,
           "family_id": f"tl1_{split}_{family}", "template_id": f"tl1_{split}_{family}",
           "category": family, "state": state_to_dict(state), "legal_actions": actions,
           "correct_actions": [actions[i] for i in expected],
           "certificate": {"certainty": certainty, "goal": goal, "texts": records, "observed": observed,
                           "scope": "Declared synthetic immediate mechanics; not real playing strength"}}
    check = certify(row)
    if set(check["gold"]) != set(expected):
        raise ValueError(f"Independent certificate disagrees: {family} {expected} {check['gold']}")
    return row


def prepare(output, config):
    if sha(INITIAL) != INITIAL_SHA:
        raise ValueError("Initial checkpoint changed")
    _, encoder, _ = load_policy_checkpoint(INITIAL)
    output.mkdir(parents=True, exist_ok=False)
    recipes = {"train": ["armor_finish", "shield_finish", "taunt_finish", "poison", "poison_taunt",
                          "immune", "self_damage", "spell_finish"],
               "validation": ["combined_finish", "poison_shield", "shield_lifesteal", "lifesteal"],
               "control": ["hero_shield_finish", "two_taunts", "stats_target", "two_self_damage", "spell_side",
                            "heuristic_trade", "ambiguous_face"]}
    groups = {}
    for split, families in recipes.items():
        groups[split] = [fixture(split, family, n, encoder) for family in families
                         for n in range(16 if split == "train" else
                                        4 if family in ("two_self_damage", "spell_side") else 8)]
    # Current-Health intervention: preserve every other value including max Health.
    control = groups["control"]
    for n in range(0, 8, 2):
        left = control[16+n]
        right = copy.deepcopy(left)
        right["scenario_id"] += "_health_swap"
        board = right["state"]["self_player"]["board"]
        field = "current_health" if n < 4 else "current_attack"
        board[0][field], board[1][field] = board[1][field], board[0][field]
        right["legal_actions"] = menu(game_state_from_dict(right["state"]))
        gold = certify(right)["gold"]
        right["correct_actions"] = [right["legal_actions"][i] for i in gold]
        control[16+n+1] = right
        left["pair"] = right["pair"] = {"kind": "stats", "id": f"stats_{n}", "field": field}
    for n in range(6):
        base = copy.deepcopy(control[8+n])
        base["pair"] = {"kind": "position", "id": f"position_{n}"}
        control[8+n]["pair"] = base["pair"]
        base["scenario_id"] += "_position"
        for side in ("self_player", "opponent"):
            b = base["state"][side]["board"]
            for m in b:
                m["board_position"] = len(b)+1-m["board_position"]
            b.sort(key=lambda m: m["board_position"])
        base["legal_actions"] = menu(game_state_from_dict(base["state"]))
        base["correct_actions"] = [base["legal_actions"][i] for i in certify(base)["gold"]]
        control.append(base)
    for n in range(6):
        base = copy.deepcopy(control[n])
        base["pair"] = {"kind": "id", "id": f"id_{n}"}
        control[n]["pair"] = base["pair"]
        base["scenario_id"] += "_alias"
        mapping = {}
        for side in ("self_player", "opponent"):
            for m in base["state"][side]["board"]:
                old = m["card"]["card_id"]
                mapping[old] = f"TL_CONTROL_ALIAS_{n}_{side}_{m['board_position']}"
                m["card"]["card_id"] = mapping[old]
        for text in base["certificate"]["texts"]:
            if text["id"] in mapping:
                text["id"] = mapping[text["id"]]
        base["legal_actions"] = menu(game_state_from_dict(base["state"]))
        base["correct_actions"] = [base["legal_actions"][i] for i in certify(base)["gold"]]
        control.append(base)
    # Shuffle menus so END, source and target have no fixed menu index.
    for rows in groups.values():
        for row in rows:
            random.Random(row["scenario_id"]).shuffle(row["legal_actions"])
            check = certify(row)
            wanted = {identity(a) for a in row["correct_actions"]}
            if {identity(row["legal_actions"][i]) for i in check["gold"]} != wanted:
                raise ValueError("Menu permutation changed certificate")
    validate_no_control_overlap(groups["train"]+groups["validation"])
    fingerprints = {k: {scenario_content_fingerprint(r) for r in v} for k, v in groups.items()}
    if any(fingerprints[a] & fingerprints[b] for a, b in
           [("train", "validation"), ("train", "control"), ("validation", "control")]):
        raise ValueError("Content overlap")
    semantic = {k: {semantic_fingerprint(r) for r in v} for k, v in groups.items()}
    if any(semantic[a] & semantic[b] for a, b in
           [("train", "validation"), ("train", "control"), ("validation", "control")]):
        raise ValueError("Identity/position-independent content overlap")
    old_files = [ROOT/"data/evaluation/model_first_1/control_test.jsonl",
                 ROOT/"model-first-2/data/processed_synthetic/model_first_2c/test.jsonl"]
    old = [json.loads(line) for path in old_files for line in path.read_text().splitlines() if line]
    if (semantic["train"] | semantic["validation"]) & {semantic_fingerprint(r) for r in old}:
        raise ValueError("Old test semantic clone")
    for split, rows in groups.items():
        with (output / f"{split}.jsonl").open("x", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, sort_keys=True)+"\n")
    manifest = {"schema": "manamind.tactical_learning/1", "initial_sha256": INITIAL_SHA,
                "hypothesis": "20% certified tactics improves source/target transfer versus matched real-only updates",
                "recipes": recipes, "counts": {k: len(v) for k, v in groups.items()},
                "files": {k: sha(output/f"{k}.jsonl") for k in groups}, "config": config,
                "config_sha256": identity(config), "control_opened": False,
                "source_sha256": {p: sha(ROOT/p) for p in ["scripts/prepare_tactical_learning.py",
                    "src/manamind/training/tactical_certificates.py"]},
                "old_overlap_files": {str(p.relative_to(ROOT)): sha(p) for p in old_files},
                "provenance": "Declared visible fixture facts, explicit texts/modifiers; independent Outcome and bounded integer certificates",
                "sequence_bound": "<=4 one-use sources, <=2 zero-Attack plain Taunts; no reactions",
                "no_old_template_clones": "Every train recipe requires Armor+Lifesteal, hero Shield, Taunt winning-prefix, Poison, Immune or spells; old vanilla local-gold templates excluded"}
    write(output/"manifest.json", manifest)
    return manifest


def semantic_fingerprint(row):
    """Ignore identities, positions, base metadata and turn; retain visible mechanics."""
    state = copy.deepcopy(row["state"])
    state.pop("turn_number", None)
    for side in ("self_player", "opponent"):
        for m in state[side].get("board", []):
            m.pop("board_position", None)
            m["card"] = {"card_type": m["card"].get("card_type"),
                         "mechanics": m["card"].get("mechanics", [])}
        state[side]["board"] = sorted(state[side].get("board", []), key=identity)
    for card in state.get("self_hand", []):
        card.pop("card_id", None)
    return identity(state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output, json.loads(args.config.read_text())), indent=2))
