"""Harvest existing fixed spell-damage roots in the pinned Meta Profile."""
from __future__ import annotations

import hashlib
import json
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from manamind.integrations.rosettastone.rosettastone import (  # noqa: E402
    SimulatorSession, make_simple_test_deck, validate_deck,
)
from scripts.verification_evidence import record_execution  # noqa: E402

UNIT_TESTS = ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
PROFILE_PATH = ROOT / "configs/training_profiles/meta_training_20261002_v1.json"
NATIVE_TEST_SOURCE = ROOT / "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/CoreCardsGenTests.cpp"
FAMILY_TEST_SOURCE = ROOT / "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindEffectCompositionTests.cpp"
FAMILIES = {
    "profile_single_target_spell_damage_verification_v1": {
        "evidence": "profile_single_target_spell_damage.evidence.json",
        "cards": {
            "CORE_CS2_029": ("MAGE", "[Mage : Spell] - CORE_CS2_029 : Fireball", NATIVE_TEST_SOURCE),
            "CORE_CS2_072": ("ROGUE", "[Rogue : Spell] - CORE_CS2_072 : Backstab", NATIVE_TEST_SOURCE),
            "CORE_CS2_024": ("MAGE", "[ManaMind effect composition] - CORE_CS2_024 damages and freezes its target", FAMILY_TEST_SOURCE),
            "CORE_ICC_055": ("WARLOCK", "[Warlock : Spell] - CORE_ICC_055 : Drain Soul", NATIVE_TEST_SOURCE),
        },
    },
    "profile_enemy_board_damage_verification_v1": {
        "evidence": "profile_enemy_board_damage.evidence.json",
        "cards": {
            "CORE_CS2_062": ("WARLOCK", "[Warlock : Spell] - CORE_CS2_062 : Hellfire", NATIVE_TEST_SOURCE),
            "CORE_EX1_129": ("ROGUE", "[ManaMind effect composition] - CORE_EX1_129 damages all enemy minions then draws", FAMILY_TEST_SOURCE),
        },
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", choices=tuple(FAMILIES))
    args = parser.parse_args()
    catalog = {r["id"]: r for r in json.loads(CATALOG.read_text(encoding="utf-8"))["cards"]}
    meta_profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    profile_hash = canonical_hash(meta_profile)
    verifier_hash = sha256(Path(__file__))

    packages = {args.package: FAMILIES[args.package]} if args.package else FAMILIES
    for package_id, family in packages.items():
        rows = {}
        native_outputs = {}
        bridge_outputs = {}
        for card_id, (player_class, test_filter, test_source) in family["cards"].items():
            native = subprocess.run(
                [str(UNIT_TESTS), f"--test-case={test_filter}"],
                cwd=ROOT / "vendor/RosettaStone", capture_output=True,
                text=True, errors="replace", check=False,
            )
            native_output = native.stdout + native.stderr
            print(native_output, end="")
            if native.returncode or "Status: SUCCESS!" not in native_output:
                raise RuntimeError(f"Native family scenario failed for {card_id}")
            native_outputs[card_id] = native_output

            deck = make_simple_test_deck(player_class=player_class)
            deck[0] = card_id
            errors = validate_deck(deck, player_class=player_class)
            if errors:
                raise AssertionError(f"{card_id}: Standard deck validation failed: {errors}")
            session = SimulatorSession(
                deck, make_simple_test_deck(player_class="MAGE"),
                player1_class=player_class, player2_class="MAGE", shuffle=False,
                random_seed=31,
            )
            observation = session.observation("PLAYER1")
            if card_id not in {r.card_id for r in observation.self_hand}:
                raise AssertionError(f"{card_id}: absent from SELF opening hand")
            actions = session.legal_actions()
            if not actions or not any(a.get("type") == "END_TURN" for a in actions):
                raise AssertionError(f"{card_id}: bridge did not enumerate current legal actions")
            bridge_result = {
                "deck_validation": "PASS",
                "visible_self_hand_identity": "PASS",
                "legal_action_enumeration": "PASS",
                "legal_action_count": len(actions),
            }
            bridge_outputs[card_id] = bridge_result
            card_record = catalog[card_id]
            rows[card_id] = {
                "status": "VERIFIED_SCOPED",
                "scope": "Existing root-specific native behavior test plus configured-bridge Standard deck acceptance, visible SELF-hand identity and legal-action enumeration. No transitive closure, full-deck readiness or training admission claim.",
                "training_scope": "SCOPED_PACKAGE_ONLY",
                "profile_manifest_sha256": profile_hash,
                "rules_fingerprint": canonical_hash({
                    "catalog_record_sha256": sha256(CATALOG),
                    "card_id": card_id,
                    "rules_text": card_record.get("text", ""),
                    "native_test_source_sha256": sha256(test_source),
                }),
                "pool_membership_sha256": canonical_hash("NO_GENERATED_CARD_POOL_IN_REVIEWED_SPELL_EFFECT"),
                "pool_predicate_version": "NO_GENERATED_CARD_POOL_IN_REVIEWED_SPELL_EFFECT_V1",
                "capability_fingerprint": canonical_hash({
                    "native_task_source": test_source.relative_to(ROOT).as_posix(),
                    "existing_rules": ["DamageTask", "native target requirements", "existing secondary effect"],
                }),
                "scenario_fingerprint": canonical_hash({
                    "native_output": native_output,
                    "native_test_source_sha256": sha256(test_source),
                    "verifier_sha256": verifier_hash,
                    "bridge_result": bridge_result,
                }),
                "bridge_action_status": "VERIFIED_SCOPED",
                "native_test": test_filter,
                "bridge_result": bridge_result,
                "training_eligible": False,
            }

        output_path = ROOT / "integrations/rosettastone/card_rules" / family["evidence"]
        doc = record_execution({
            "schema_version": 1,
            "package": package_id,
            "scope": "SCOPED_PACKAGE_ONLY",
            "profile_manifest_sha256": profile_hash,
            "cards": rows,
            "native_outputs": native_outputs,
            "bridge_outputs": bridge_outputs,
            "training_eligible": False,
        })
        output_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"PASS {package_id}: {len(rows)} roots, native scenarios and bridge sessions")


if __name__ == "__main__":
    main()
