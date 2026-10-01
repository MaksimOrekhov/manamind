"""Run native scenarios and bridge smoke for repeated trigger-draw cards."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from manamind.integrations.rosettastone.rosettastone import (  # noqa: E402
    SimulatorSession, make_simple_test_deck, validate_deck,
)

CASES = (("CORE_DMF_067", "WARLOCK"), ("RLK_708", "DEATHKNIGHT"),
         ("CORE_RLK_657", "DRUID"))
NATIVE_TESTS = PROJECT_ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"
ENGINE_LIBRARY = PROJECT_ROOT / "vendor/RosettaStone/build-mana-py312/lib/RosettaStone.lib"
NATIVE_TEST_SOURCE = PROJECT_ROOT / "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindRepeatedTriggerDrawTests.cpp"
DECLARATION = PROJECT_ROOT / "integrations/rosettastone/card_rules/repeated_trigger_draw.v1.json"
GENERATOR = PROJECT_ROOT / "scripts/generate_repeated_trigger_draw.py"
GENERATED_MANIFEST = PROJECT_ROOT / "integrations/rosettastone/card_rules/repeated_trigger_draw.generated.json"
GENERATED_SOURCE = PROJECT_ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/ManaMindRepeatedTriggerDrawGen.cpp"
CAPABILITIES = PROJECT_ROOT / "integrations/rosettastone/card_rules/capabilities.json"
EVIDENCE = PROJECT_ROOT / "integrations/rosettastone/card_rules/repeated_trigger_draw.evidence.json"
BRIDGE = PROJECT_ROOT / "integrations/rosettastone/build/python/mana_rosetta_bridge.cp312-win_amd64.pyd"


sys.path.insert(0, str(PROJECT_ROOT))
from scripts.verification_evidence import record_execution


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def main() -> None:
    if not NATIVE_TESTS.exists() or not ENGINE_LIBRARY.exists() or not BRIDGE.exists():
        raise RuntimeError("Build UnitTests, RosettaStone.lib, and the bridge before package verification")
    native = subprocess.run([str(NATIVE_TESTS), "--test-case=[ManaMind repeated trigger draw]*"],
                            cwd=PROJECT_ROOT / "vendor/RosettaStone", check=True,
                            capture_output=True, text=True)
    print(native.stdout, end="")
    manifest = json.loads(GENERATED_MANIFEST.read_text(encoding="utf-8"))
    engine_hash = file_hash(ENGINE_LIBRARY)
    declaration_hash = file_hash(DECLARATION)
    generator_hash = file_hash(GENERATOR)
    generated_source_hash = file_hash(GENERATED_SOURCE)
    capability_hash = file_hash(CAPABILITIES)
    native_scenario_hash = file_hash(NATIVE_TEST_SOURCE)
    bridge_scenario_hash = file_hash(Path(__file__))
    bridge_hash = file_hash(BRIDGE)
    cards = {}
    for card_id, player_class in CASES:
        deck = make_simple_test_deck(player_class=player_class)
        if card_id in deck:
            index = deck.index(card_id)
            deck[0], deck[index] = deck[index], deck[0]
        else:
            deck[0] = card_id
        errors = validate_deck(deck, player_class=player_class)
        if errors:
            raise AssertionError(f"{card_id} rejected from Standard deck: {errors}")
        if player_class == "DEATHKNIGHT":
            bridge_smoke = "Standard deck legality passed; session creation is blocked by the known Death Knight setup gap."
        else:
            opponent = make_simple_test_deck(player_class="MAGE")
            game = SimulatorSession(deck, opponent, player1_class=player_class,
                                    player2_class="MAGE", shuffle=False, random_seed=23)
            if card_id not in {card.card_id for card in game.observation("PLAYER1").self_hand}:
                raise AssertionError(f"{card_id} missing from bridge-visible opening hand")
            if not game.legal_actions():
                raise AssertionError(f"{card_id}: bridge has no legal actions")
            bridge_smoke = "Standard deck validation, session creation, visible hand, and legal action enumeration passed"
        entry = next(item for item in manifest["cards"] if item["card_id"] == card_id)
        fingerprints = {
            "rules_fingerprint": canonical_hash({
                "rules_text_sha256": entry["rules_text_sha256"],
                "declaration_sha256": declaration_hash,
                "generator_script_sha256": generator_hash,
                "generated_source_sha256": generated_source_hash,
            }),
            "pool_membership_sha256": canonical_hash(
                "DECK_DRAW_OUTCOMES_PROFILE_SPECIFIC; closure out of scope"
                if "DRAW" in " ".join(entry["battlecry_effects"] + entry["deathrattle_effects"])
                else "NO_DYNAMIC_OUTCOME_IN_SCOPED_ARMOR_EFFECT"),
            "pool_predicate_version": "DECK_DRAW_OUTCOMES_PROFILE_SPECIFIC_V1"
                if "DRAW" in " ".join(entry["battlecry_effects"] + entry["deathrattle_effects"])
                else "NO_DYNAMIC_OUTCOME_IN_SCOPED_ARMOR_EFFECT_V1",
            "capability_fingerprint": capability_hash,
            "engine_build_fingerprint": engine_hash,
            "scenario_fingerprint": canonical_hash({
                "native_scenario_sha256": native_scenario_hash,
                "bridge_smoke_sha256": bridge_scenario_hash,
                "bridge_module_sha256": bridge_hash,
            }),
        }
        cards[card_id] = {
            **fingerprints,
            "status": "VERIFIED_SCOPED",
            "scope": "Battlecry and Deathrattle draw recipient/count for the tested cases; deck-draw outcome closure is not verified.",
            "native_test": "[ManaMind repeated trigger draw]* passed",
            "bridge_smoke": bridge_smoke,
            "native_assertion_output": native.stdout.strip(),
            "binary_sha256": engine_hash,
            "bridge_module_sha256": bridge_hash,
        }
        print(f"PASS {card_id}: {bridge_smoke}")
    evidence = {
        "schema_version": 1, "package": "repeated_trigger_draw",
        "catalog_sha256": manifest["catalog_sha256"],
        "declaration_sha256": declaration_hash,
        "generator_script_sha256": generator_hash,
        "generated_source_sha256": generated_source_hash,
        "capability_file_sha256": capability_hash,
        "engine_library_sha256": engine_hash,
        "native_scenario_sha256": native_scenario_hash,
        "bridge_smoke_sha256": bridge_scenario_hash,
        "training_eligible": False, "cards": cards,
    }
    evidence = record_execution(evidence)
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
