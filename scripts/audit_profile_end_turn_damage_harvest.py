"""Record scoped verification for the current fixed end-turn damage pair."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from manamind.integrations.rosettastone.rosettastone import (  # noqa: E402
    SimulatorSession,
    make_simple_test_deck,
)
from scripts.verification_evidence import record_execution  # noqa: E402

PROFILE = ROOT / "configs/training_profiles/meta_training_20261002_v1.json"
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
EVIDENCE = ROOT / "integrations/rosettastone/card_rules/profile_verification_harvest_20261003_v2.evidence.json"
UNIT_TESTS = ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"
ROSETTA = ROOT / "vendor/RosettaStone"
SOURCE = ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/CoreCardsGen.cpp"
NATIVE_TEST_SOURCE = ROOT / "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindEffectCompositionTests.cpp"
CASES = {
    "CATA_999": {
        "name": "Earthen Drake",
        "native_filter": "[ManaMind trigger] - CATA_999 damages the enemy hero at its controller's turn end",
        "bridge_function": "verify_earthen_drake_end_turn_damage",
        "expected_damage": 4,
    },
    "CATA_475": {
        "name": "Scalebreaker Bulwark",
        "native_filter": "[ManaMind effect composition] - CATA_475 damages all enemies at its controller's turn end",
        "bridge_function": None,
        "expected_damage": 2,
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def run_earthen_bridge() -> str:
    path = ROOT / "scripts/verify_current_standard_scenarios.py"
    spec = importlib.util.spec_from_file_location("current_standard_scenarios", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load Earthen Drake bridge scenario")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.verify_earthen_drake_end_turn_damage()
    return "PASS: enemy hero loses 4 only after controller end turn"


def run_scalebreaker_bridge() -> str:
    player = make_simple_test_deck(player_class="PALADIN")
    player[0] = "CATA_475"
    opponent = make_simple_test_deck(player_class="WARRIOR")
    game = SimulatorSession(
        player, opponent,
        player1_class="PALADIN", player2_class="WARRIOR",
        shuffle=False, random_seed=20261003,
    )
    for _ in range(30):
        state = game.observation("PLAYER1")
        if state.active_player == "SELF":
            action = next(
                (item for item in game.legal_actions()
                 if item["type"] == "PLAY_CARD" and item.get("card_id") == "CATA_475"),
                None,
            )
            if action is not None:
                hero_before = state.opponent.hero_health
                game.apply_action(action)
                if game.observation("PLAYER1").opponent.hero_health != hero_before:
                    raise AssertionError("Scalebreaker must not damage immediately when played")
                end_turn = next(item for item in game.legal_actions() if item["type"] == "END_TURN")
                game.apply_action(end_turn)
                hero_after = game.observation("PLAYER1").opponent.hero_health
                if hero_after != hero_before - 2:
                    raise AssertionError(f"Scalebreaker expected {hero_before - 2} hero health, got {hero_after}")
                return f"PASS: enemy hero {hero_before}->{hero_after} at controller end turn"
        end_turn = next(item for item in game.legal_actions() if item["type"] == "END_TURN")
        game.apply_action(end_turn)
    raise AssertionError("Scalebreaker did not become playable in bridge scenario")


def main() -> None:
    native_outputs: dict[str, str] = {}
    bridge_outputs = {
        "CATA_999": run_earthen_bridge(),
        "CATA_475": run_scalebreaker_bridge(),
    }
    for card_id, row in CASES.items():
        result = subprocess.run(
            [str(UNIT_TESTS), f"--test-case={row['native_filter']}"],
            cwd=ROSETTA, capture_output=True, text=True, errors="replace", check=False,
        )
        output = result.stdout + result.stderr
        print(output, end="")
        if result.returncode or "Status: SUCCESS!" not in output:
            raise RuntimeError(f"Native scenario failed for {card_id}")
        native_outputs[card_id] = output
        print(f"{card_id}: {bridge_outputs[card_id]}")

    cards = json.loads(CATALOG.read_text(encoding="utf-8"))["cards"]
    profile_hash = canonical_hash(json.loads(PROFILE.read_text(encoding="utf-8")))
    source_hash = sha256(SOURCE)
    evidence_rows = {}
    for card_id, row in CASES.items():
        card = next(item for item in cards if item["id"] == card_id)
        bridge = {"scenario": row["bridge_function"] or "deterministic_CATA_475_bridge", "result": bridge_outputs[card_id]}
        evidence_rows[card_id] = {
            "status": "VERIFIED_SCOPED",
            "scope": f"Root-specific native trigger scenario plus configured bridge scenario confirming {row['expected_damage']} damage to the reviewed enemy target at the controller's turn end. No transitive closure, full-deck readiness or training admission claim.",
            "training_scope": "SCOPED_PACKAGE_ONLY",
            "profile_manifest_sha256": profile_hash,
            "rules_fingerprint": canonical_hash({
                "card": card,
                "source_sha256": source_hash,
                "native_test_source_sha256": sha256(NATIVE_TEST_SOURCE),
                "target_contract": row["expected_damage"],
            }),
            "pool_membership_sha256": canonical_hash(f"NO_DYNAMIC_OUTCOME_POOL_{card_id}_V1"),
            "pool_predicate_version": f"NO_DYNAMIC_OUTCOME_POOL_{card_id}_V1",
            "capability_fingerprint": source_hash,
            "scenario_fingerprint": canonical_hash({
                "native_output": native_outputs[card_id],
                "bridge_result": bridge,
                "verifier_sha256": sha256(Path(__file__)),
            }),
            "bridge_action_status": "VERIFIED_SCOPED",
            "native_test": row["native_filter"],
            "bridge_result": bridge,
            "dependency_review": {
                "scope": "STATIC_ROOT_TRIGGER_REVIEWED",
                "reviewed_static_dependencies": [],
                "dynamic_pools": [],
            },
            "training_eligible": False,
        }

    existing = json.loads(EVIDENCE.read_text(encoding="utf-8")) if EVIDENCE.exists() else {}
    evidence = {
        **existing,
        "cards": {**existing.get("cards", {}), **evidence_rows},
        "package_results": {
            **existing.get("package_results", {}),
            "end_turn_enemy_damage_verification_v1": {
                "verified_roots": sorted(CASES),
                "native_outputs": native_outputs,
                "bridge_outputs": bridge_outputs,
                "static_dependencies": {card_id: [] for card_id in CASES},
                "dependency_closure_gained": 0,
                "training_eligible": False,
            },
        },
        "training_eligible": False,
    }
    EVIDENCE.write_text(
        json.dumps(record_execution(evidence), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"PASS: explicit scoped evidence written to {EVIDENCE}")


if __name__ == "__main__":
    main()
