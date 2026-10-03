"""Focused, profile-scoped verification for the second low-hanging harvest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from manamind.integrations.rosettastone.rosettastone import (  # noqa: E402
    SimulatorSession,
)
from scripts.verification_evidence import record_execution  # noqa: E402

PROFILE_PATH = ROOT / "configs/training_profiles/meta_training_20261002_v1.json"
CATALOG_PATH = ROOT / "data/cards/standard_current_enUS.json"
DECLARATION_PATH = ROOT / "integrations/rosettastone/card_rules/effect_composition.v1.json"
DECLARATION_SOURCE = ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/ManaMindEffectCompositionGen.cpp"
UNIT_TESTS = ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"
EVIDENCE_PATH = ROOT / "integrations/rosettastone/card_rules/profile_verification_harvest_20261003_v2.evidence.json"

PACKAGE = {
    "package_id": "priest_minion_enchant_verification_v1",
    "cards": {
        "CORE_CS2_004": {
            "native_filter": "[ManaMind effect composition] - CORE_CS2_004 enchants a minion then draws",
            "dependency": "CS2_004e",
            "expectation": "Give a minion +2 Health and draw one card; this spell has no friendly-only target requirement.",
        },
        "CAP_801": {
            "native_filter": "[ManaMind effect composition] - CAP_801 applies Taunt, stats, and Reborn",
            "dependency": "CS2_009e",
            "expectation": "Give a minion +2/+3, Taunt and Reborn; this spell has no friendly-only target requirement.",
        },
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def all_target_actions(game: SimulatorSession, card_id: str) -> dict[bool, dict]:
    return {
        bool(action.get("target_is_self")): action
        for action in game.legal_actions()
        if action.get("type") == "PLAY_CARD"
        and action.get("card_id") == card_id
        and not action.get("target_is_hero", False)
    }


def setup_two_boards(card_id: str) -> SimulatorSession:
    from scripts.verify_standard_meta_rules_group_2 import end_turn, start_game

    game = start_game(card_id, "PRIEST")
    # The shared bridge test deck uses 1-cost minions, not free minions.
    def play_first_minion() -> None:
        action = next(
            (candidate for candidate in game.legal_actions()
             if candidate.get("type") == "PLAY_CARD"
             and candidate.get("card_type") == "MINION"),
            None,
        )
        if action is None:
            raise AssertionError(f"{card_id}: no legal minion available to seed a target")
        game.apply_action(action)

    # Develop one minion on each side without attacking, then return to Priest.
    play_first_minion()
    end_turn(game)
    play_first_minion()
    end_turn(game)
    if game.observation("PLAYER1").active_player != "SELF":
        raise AssertionError(f"{card_id}: expected Priest's turn after both boards were set up")
    return game


def resolve_target_case(card_id: str, friendly_target: bool) -> dict:
    from scripts.verify_standard_meta_rules_group_2 import end_turn

    game = setup_two_boards(card_id)
    observation = game.observation("PLAYER1")
    if card_id not in {card.card_id for card in observation.self_hand}:
        raise AssertionError(f"{card_id}: root absent from visible SELF opening hand")
    if not observation.self_player.board or not observation.opponent.board:
        raise AssertionError(f"{card_id}: expected one public minion on each side")

    selected_action = None
    target_actions: dict[bool, dict] = {}
    for _ in range(8):
        if game.observation("PLAYER1").active_player == "SELF":
            target_actions = all_target_actions(game, card_id)
            selected_action = target_actions.get(friendly_target)
            if selected_action is not None:
                break
        end_turn(game)
    if selected_action is None:
        raise AssertionError(
            f"{card_id}: missing legal {'friendly' if friendly_target else 'enemy'} minion target; "
            f"target sides exposed={sorted(target_actions)}"
        )

    before_obs = game.observation("PLAYER1")
    before_board = before_obs.self_player.board if friendly_target else before_obs.opponent.board
    before = before_board[0]
    before_hand = before_obs.self_player.hand_size
    if card_id == "CORE_CS2_004":
        before_health = before.max_health
        game.apply_action(selected_action)
        after_obs = game.observation("PLAYER1")
        after_board = after_obs.self_player.board if friendly_target else after_obs.opponent.board
        after = after_board[0]
        if after.max_health != before_health + 2:
            raise AssertionError(f"Power Word: Shield should add 2 max Health: {before_health} -> {after.max_health}")
        if after_obs.self_player.hand_size != before_hand:
            raise AssertionError(
                "Power Word: Shield should replace the played spell with one draw "
                f"(hand {before_hand} -> {after_obs.self_player.hand_size})"
            )
    elif card_id == "CAP_801":
        before_attack = before.current_attack
        before_health = before.max_health
        game.apply_action(selected_action)
        after_obs = game.observation("PLAYER1")
        after_board = after_obs.self_player.board if friendly_target else after_obs.opponent.board
        after = after_board[0]
        if after.current_attack != before_attack + 2 or after.max_health != before_health + 3:
            raise AssertionError(
                f"Haunt should add +2/+3: attack {before_attack}->{after.current_attack}, "
                f"health {before_health}->{after.max_health}"
            )
        if not after.taunt or not after.reborn:
            raise AssertionError(f"Haunt should grant Taunt and Reborn: taunt={after.taunt}, reborn={after.reborn}")
        if after_obs.self_player.hand_size != before_hand - 1:
            raise AssertionError(f"Haunt should consume one card: {before_hand}->{after_obs.self_player.hand_size}")
    else:
        raise AssertionError(f"No verifier for {card_id}")

    return {
        "deck_validation": "PASS",
        "visible_self_hand_identity": "PASS",
        "legal_friendly_target": "PASS" if friendly_target else "NOT_RUN_IN_THIS_SESSION",
        "legal_enemy_target": "PASS" if not friendly_target else "NOT_RUN_IN_THIS_SESSION",
        "effect_expectation": "PASS",
        "legal_action_enumeration": "PASS",
        "target_action_count": len(target_actions),
    }


def main() -> None:
    native_outputs: dict[str, str] = {}
    cards: dict[str, dict] = {}
    bridge_outputs: dict[str, dict] = {}
    composition = {
        row["card_id"]: row for row in json.loads(DECLARATION_PATH.read_text(encoding="utf-8"))["cards"]
    }

    for card_id, expected in PACKAGE["cards"].items():
        native = subprocess.run(
            [str(UNIT_TESTS), f"--test-case={expected['native_filter']}"],
            cwd=ROOT / "vendor/RosettaStone", capture_output=True, text=True,
            errors="replace", check=False,
        )
        native_output = native.stdout + native.stderr
        print(native_output, end="")
        if native.returncode or "Status: SUCCESS!" not in native_output:
            raise RuntimeError(f"Focused native scenario failed for {card_id}")
        native_outputs[card_id] = native_output

        friendly = resolve_target_case(card_id, True)
        enemy = resolve_target_case(card_id, False)
        bridge_outputs[card_id] = {"friendly_target_case": friendly, "enemy_target_case": enemy}
        declaration = composition[card_id]
        rules_fingerprint = canonical_hash({
            "declaration": declaration,
            "declaration_source_sha256": sha256(DECLARATION_SOURCE),
            "catalog_card": next(
                row for row in json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["cards"]
                if row["id"] == card_id
            ),
        })
        cards[card_id] = {
            "status": "VERIFIED_SCOPED",
            "scope": "Root-specific native rules scenario plus two configured bridge scenarios covering a legal friendly and enemy minion target, resolved effect and SELF hand observation. Does not claim transitive closure, full-deck readiness or training admission.",
            "training_scope": "SCOPED_PACKAGE_ONLY",
            "profile_manifest_sha256": canonical_hash(json.loads(PROFILE_PATH.read_text(encoding="utf-8"))),
            "rules_fingerprint": rules_fingerprint,
            "pool_membership_sha256": canonical_hash("NO_DYNAMIC_OUTCOME_POOL_IN_REVIEWED_ENCHANT_SPELL_V1"),
            "pool_predicate_version": "NO_DYNAMIC_OUTCOME_POOL_IN_REVIEWED_ENCHANT_SPELL_V1",
            "capability_fingerprint": sha256(DECLARATION_PATH),
            "scenario_fingerprint": canonical_hash({
                "native_output": native_output,
                "verifier_sha256": sha256(Path(__file__)),
                "bridge_results": bridge_outputs[card_id],
            }),
            "bridge_action_status": "VERIFIED_SCOPED",
            "native_tests": [expected["native_filter"]],
            "native_assertions": "see captured native output",
            "bridge_result": bridge_outputs[card_id],
            "dependency_review": {
                "scope": "REVIEWED_FIXED_ENCHANTMENT_ONLY",
                "reviewed_static_dependencies": [expected["dependency"]],
                "dynamic_pools": [],
            },
            "training_eligible": False,
        }
        print(f"PASS {card_id}: native scenario and friendly/enemy target bridge cases")

    evidence = {
        "schema_version": 1,
        "package": "meta_profile_low_hanging_verification_harvest_v2",
        "scope": "SCOPED_PACKAGE_ONLY",
        "profile_manifest_sha256": canonical_hash(json.loads(PROFILE_PATH.read_text(encoding="utf-8"))),
        "cards": cards,
        "package_results": {
            PACKAGE["package_id"]: {
                "native_outputs": native_outputs,
                "bridge_outputs": bridge_outputs,
                "verified_roots": sorted(cards),
                "dependency_closure_gained": 0,
                "training_eligible": False,
            }
        },
        "training_eligible": False,
    }
    EVIDENCE_PATH.write_text(
        json.dumps(record_execution(evidence), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_meta_training_profile_audit.py")],
        cwd=ROOT, check=True,
    )
    print(f"PASS: current scoped evidence written to {EVIDENCE_PATH}")


if __name__ == "__main__":
    main()
