"""Verify Deathrattle filtered-spell draws and record scoped fingerprints."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from manamind.integrations.rosettastone.rosettastone import (  # noqa: E402
    SimulatorSession, make_simple_test_deck, validate_deck,
)

CASES = (("FIR_929", "MAGE"), ("RLK_511", "DEATHKNIGHT"))
NATIVE_TESTS = ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"
NATIVE_SOURCE = ROOT / "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindFilteredSchoolDrawTests.cpp"
ENGINE_LIBRARY = ROOT / "vendor/RosettaStone/build-mana-py312/lib/RosettaStone.lib"
BRIDGE_MODULE = ROOT / "integrations/rosettastone/build/python/mana_rosetta_bridge.cp312-win_amd64.pyd"
MANIFEST = ROOT / "integrations/rosettastone/card_rules/filtered_school_draw.generated.json"
DECLARATION = ROOT / "integrations/rosettastone/card_rules/filtered_school_draw.v1.json"
GENERATOR = ROOT / "scripts/generate_filtered_school_draw.py"
GENERATED_SOURCE = ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/ManaMindFilteredSchoolDrawGen.cpp"
CAPABILITIES = ROOT / "integrations/rosettastone/card_rules/capabilities.json"
EVIDENCE = ROOT / "integrations/rosettastone/card_rules/filtered_school_draw.evidence.json"


sys.path.insert(0, str(ROOT))
from scripts.verification_evidence import record_execution


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def main() -> None:
    required = (NATIVE_TESTS, NATIVE_SOURCE, ENGINE_LIBRARY, BRIDGE_MODULE,
                MANIFEST, DECLARATION, GENERATOR, GENERATED_SOURCE, CAPABILITIES)
    missing = [path for path in required if not path.exists()]
    if missing:
        raise RuntimeError("Build the engine, UnitTests and bridge before verification: " +
                           ", ".join(str(path) for path in missing))
    native = subprocess.run(
        [str(NATIVE_TESTS), "--test-case=[ManaMind filtered school draw]*"],
        cwd=ROOT / "vendor/RosettaStone", check=True, capture_output=True, text=True)
    print(native.stdout, end="")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    declaration_hash = file_hash(DECLARATION)
    generator_hash = file_hash(GENERATOR)
    generated_hash = file_hash(GENERATED_SOURCE)
    engine_hash = file_hash(ENGINE_LIBRARY)
    capability_hash = file_hash(CAPABILITIES)
    bridge_hash = file_hash(BRIDGE_MODULE)
    scenario_hash = file_hash(NATIVE_SOURCE)
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
            bridge_smoke = "Standard deck legality passed; native scenario covers card effect; session setup is blocked by the known Death Knight gap."
        else:
            game = SimulatorSession(deck, make_simple_test_deck(player_class="MAGE"),
                                    player1_class=player_class, player2_class="MAGE",
                                    shuffle=False, random_seed=29)
            if card_id not in {card.card_id for card in game.observation("PLAYER1").self_hand}:
                raise AssertionError(f"{card_id} missing from bridge-visible opening hand")
            if not game.legal_actions():
                raise AssertionError(f"{card_id}: bridge returned no legal actions")
            bridge_smoke = "Standard deck validation, session creation, visible hand, and legal actions passed"
        entry = next(row for row in manifest["cards"] if row["card_id"] == card_id)
        fingerprints = {
            "rules_fingerprint": canonical_hash({
                "rules_text_sha256": entry["rules_text_sha256"],
                "declaration_sha256": declaration_hash,
                "generator_script_sha256": generator_hash,
                "generated_source_sha256": generated_hash,
            }),
            "pool_membership_sha256": canonical_hash({
                "source": "player deck at resolution", "selector": entry["spell_school"],
                "members": "profile/deck dependent; not closed by this pilot",
            }),
            "pool_predicate_version": "DRAW_FROM_MATCHING_DECK_SPELL_SCHOOL_V1",
            "capability_fingerprint": capability_hash,
            "engine_build_fingerprint": engine_hash,
            "scenario_fingerprint": canonical_hash({
                "native_scenario_sha256": scenario_hash,
                "bridge_verifier_sha256": file_hash(Path(__file__)),
                "bridge_module_sha256": bridge_hash,
            }),
        }
        cards[card_id] = {
            **fingerprints,
            "status": "VERIFIED_SCOPED",
            "scope": f"Deathrattle draws one {entry['spell_school']} spell from the controller's deck; available deck members and complete closure are out of scope.",
            "native_test": "[ManaMind filtered school draw]* passed",
            "native_assertion_output": native.stdout.strip(),
            "bridge_smoke": bridge_smoke,
            "training_eligible": False,
        }
        print(f"PASS {card_id}: {bridge_smoke}")
    evidence = {
        "schema_version": 1,
        "package": "filtered_school_draw",
        "catalog_sha256": manifest["catalog_sha256"],
        "declaration_sha256": declaration_hash,
        "generator_script_sha256": generator_hash,
        "generated_source_sha256": generated_hash,
        "capability_file_sha256": capability_hash,
        "engine_library_sha256": engine_hash,
        "native_scenario_sha256": scenario_hash,
        "bridge_module_sha256": bridge_hash,
        "training_eligible": False,
        "cards": cards,
    }
    evidence = record_execution(evidence)
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
