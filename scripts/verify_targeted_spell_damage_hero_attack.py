"""Verify the two profile consumers of temporary hero Attack on targeted spells."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.integrations.rosettastone.rosettastone import (  # noqa: E402
    SimulatorSession,
    make_simple_test_deck,
    validate_deck,
)

sys.path.insert(0, str(ROOT))
from scripts.verification_evidence import record_execution  # noqa: E402

NATIVE_TESTS = ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"
EVIDENCE = ROOT / "integrations/rosettastone/card_rules/targeted_spell_damage_hero_attack.evidence.json"
PROFILE = ROOT / "configs/training_profiles/meta_training_20261002_v1.json"
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
REGISTRY = ROOT / "data/cards/standard_registry_20261001_enUS.json"
DECLARATION = ROOT / "integrations/rosettastone/card_rules/effect_composition.v1.json"
GENERATOR = ROOT / "scripts/generate_effect_composition.py"
GENERATED_SOURCE = ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/ManaMindEffectCompositionGen.cpp"
NATIVE_SOURCE = ROOT / "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindEffectCompositionTests.cpp"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def deck_with_front(card_id: str, player_class: str, second: str | None = None) -> list[str]:
    deck = make_simple_test_deck(player_class=player_class)
    deck[0] = card_id
    if second:
        deck[1] = second
    errors = validate_deck(deck, player_class=player_class)
    if errors:
        raise AssertionError(f"{card_id} fixture deck is invalid: {errors}")
    return deck


def end_turn(game: SimulatorSession) -> None:
    action = next((a for a in game.legal_actions() if a["type"] == "END_TURN"), None)
    if action is None:
        raise AssertionError("Expected a legal END_TURN action")
    game.apply_action(action)


def verify_static_shock_target_contract() -> str:
    player_deck = deck_with_front("TIME_218", "SHAMAN", "CORE_UNG_205")
    opponent_deck = make_simple_test_deck(player_class="WARRIOR")
    game = SimulatorSession(
        player_deck,
        opponent_deck,
        player1_class="SHAMAN",
        player2_class="WARRIOR",
        shuffle=False,
        random_start=False,
        random_seed=218,
    )
    state = game.observation("PLAYER1")
    if "TIME_218" not in {card.card_id for card in state.self_hand}:
        raise AssertionError("Static Shock is absent from the opening hand")
    if "CORE_UNG_205" not in {card.card_id for card in state.self_hand}:
        raise AssertionError("Yeti target fixture is absent from the opening hand")

    shock_actions = [
        a for a in game.legal_actions()
        if a["type"] == "PLAY_CARD" and a.get("card_id") == "TIME_218"
    ]
    if shock_actions:
        raise AssertionError("Static Shock must have no legal target while both boards are empty")

    yeti_action = None
    for _ in range(12):
        active = game.observation("PLAYER1").active_player
        actions = game.legal_actions()
        if active == "SELF":
            yeti_action = next(
                (a for a in actions if a["type"] == "PLAY_CARD" and a.get("card_id") == "CORE_UNG_205"),
                None,
            )
            if yeti_action is not None:
                game.apply_action(yeti_action)
                break
        end_turn(game)
    if yeti_action is None:
        raise AssertionError("Could not make the minion target legal within 12 actions")

    choices = [
        a for a in game.legal_actions()
        if a["type"] == "PLAY_CARD" and a.get("card_id") == "TIME_218"
    ]
    if not choices:
        raise AssertionError("Static Shock did not expose a legal minion target")
    if any(a.get("target_entity_id") is None or a.get("target_is_hero") for a in choices):
        raise AssertionError(f"Static Shock exposed a non-minion target: {choices}")
    if any(not a.get("target_is_self") or a.get("target_attack") != 2 or a.get("target_health") != 1 for a in choices):
        raise AssertionError(f"Static Shock target set did not identify the friendly Glacial Shard: {choices}")

    game.apply_action(choices[0])
    after = game.observation("PLAYER1")
    if after.self_player.hero_attack != 1:
        raise AssertionError("Static Shock should grant +1 hero Attack during its turn")
    if after.self_player.board:
        raise AssertionError("Static Shock should deal 1 damage and destroy the 1-Health Glacial Shard")
    end_turn(game)
    if game.observation("PLAYER1").self_player.hero_attack != 0:
        raise AssertionError("Static Shock's hero Attack should expire at end of turn")
    print("PASS TIME_218: minion-only target set, 1 spell damage, temporary hero Attack expiry")
    return "PASS: no target with empty boards; only minion target when available; exact damage and expiry"


def verify_press_the_advantage() -> str:
    player_deck = deck_with_front("END_007", "DRUID")
    opponent_deck = make_simple_test_deck(player_class="WARRIOR")
    game = SimulatorSession(
        player_deck,
        opponent_deck,
        player1_class="DRUID",
        player2_class="WARRIOR",
        shuffle=False,
        random_start=False,
        random_seed=7,
    )
    card_actions = []
    for _ in range(14):
        state = game.observation("PLAYER1")
        actions = game.legal_actions()
        card_actions = [
            a for a in actions
            if a["type"] == "PLAY_CARD" and a.get("card_id") == "END_007"
        ]
        if card_actions:
            break
        end_turn(game)
    if not card_actions:
        raise AssertionError("Press the Advantage did not become playable")
    if not any(a.get("target_is_hero") and not a.get("target_is_self") for a in card_actions):
        raise AssertionError("Press the Advantage must allow targeting the enemy hero")

    state = game.observation("PLAYER1")
    enemy_health = state.opponent.hero_health
    hand_count = len(state.self_hand)
    game.apply_action(next(a for a in card_actions if a.get("target_is_hero") and not a.get("target_is_self")))
    after = game.observation("PLAYER1")
    if after.opponent.hero_health != enemy_health - 1:
        raise AssertionError("Press the Advantage should deal 1 damage to the selected enemy hero")
    if after.self_player.hero_attack != 1 or after.self_player.armor != 1:
        raise AssertionError("Press the Advantage should grant +1 hero Attack and 1 Armor")
    if len(after.self_hand) != hand_count:
        raise AssertionError("Press the Advantage should replace itself with exactly one drawn card")
    end_turn(game)
    if game.observation("PLAYER1").self_player.hero_attack != 0:
        raise AssertionError("Press the Advantage's hero Attack should expire at end of turn")
    print("PASS END_007: character target, 1 damage, +1 Attack, draw, Armor, Attack expiry")
    return "PASS: enemy hero target, exact fixed effects, temporary Attack expiry"


def main() -> None:
    if not NATIVE_TESTS.exists():
        raise RuntimeError("Build the py312 UnitTests target before verification")
    native = subprocess.run(
        [str(NATIVE_TESTS), "--test-case=[ManaMind effect composition]*"],
        cwd=ROOT / "vendor/RosettaStone",
        check=True,
        capture_output=True,
        text=True,
    )
    print(native.stdout, end="")
    time_scope = verify_static_shock_target_contract()
    end_scope = verify_press_the_advantage()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))["cards"]
    rows = {card["id"]: card for card in catalog}
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["cards"]
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile_hash = canonical_sha(profile)
    declaration_hash = sha(DECLARATION)
    generator_hash = sha(GENERATOR)
    generated_hash = sha(GENERATED_SOURCE)
    native_source_hash = sha(NATIVE_SOURCE)
    verifier_hash = sha(Path(__file__))
    contract = {
        "contract_id": "targeted_spell_damage_hero_attack",
        "contract_version": 1,
        "implementation_kind": "GENERIC",
        "effect": "1 spell damage to declared target then +1 hero Attack until end of turn",
        "target_variation": {"END_007": "any character", "TIME_218": "minion only"},
    }
    cards = {}
    for card_id, scope in (("END_007", end_scope), ("TIME_218", time_scope)):
        cards[card_id] = {
            "status": "VERIFIED_SCOPED",
            "scope": "Native independent family scenario and actual loaded-bridge target/action/stat parity; profile roots only, no full deck closure or training admission.",
            "training_scope": "META_PROFILE_SCOPED_ONLY",
            "contract_review": contract,
            "rules_fingerprint": canonical_sha({
                "card_record_sha256": registry[card_id]["metadata"]["card_record_sha256"],
                "rules_text": rows[card_id]["text"],
                "declaration_sha256": declaration_hash,
                "generator_sha256": generator_hash,
                "generated_source_sha256": generated_hash,
            }),
            "dependency_review": {
                "scope": "SCOPED_EXISTING_ENCHANT_CONTRACT",
                "dependency_ids": ["BTA_02pe"],
                "verified_property": "+1 hero Attack expires at end of controller's turn",
                "complete_profile_closure": False,
            },
            "native_test": "[ManaMind effect composition]* passed",
            "bridge_scope": scope,
            "profile_manifest_sha256": profile_hash,
            "native_scenario_sha256": native_source_hash,
            "bridge_scenario_sha256": verifier_hash,
        }
    document = {
        "package_id": "targeted_spell_damage_hero_attack_v1",
        "contract_id": "targeted_spell_damage_hero_attack",
        "contract_version": 1,
        "profile_id": profile["profile_id"],
        "profile_manifest_sha256": profile_hash,
        "declaration_sha256": declaration_hash,
        "generator_script_sha256": generator_hash,
        "generated_source_sha256": generated_hash,
        "native_scenario_sha256": native_source_hash,
        "bridge_scenario_sha256": verifier_hash,
        "training_eligible": False,
        "cards": cards,
        "native_assertion_output": native.stdout.strip(),
    }
    document = record_execution(document)
    EVIDENCE.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote current profile-scoped evidence: {EVIDENCE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
