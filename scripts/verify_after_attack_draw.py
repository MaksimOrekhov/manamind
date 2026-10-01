"""Smoke-check generated after-attack effects through the public bridge."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from manamind.integrations.rosettastone.rosettastone import (  # noqa: E402
    SimulatorSession,
    make_simple_test_deck,
    validate_deck,
)


CASES = (
    ("CAP_003", "ROGUE"),
    ("EDR_253", "PALADIN"),
    ("CORE_NX2_028", "WARRIOR"),
    ("TLC_478", "WARRIOR"),
    ("TLC_840", "DEMONHUNTER"),
)
NATIVE_TESTS = PROJECT_ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"
ENGINE_LIBRARY = PROJECT_ROOT / "vendor/RosettaStone/build-mana-py312/lib/RosettaStone.lib"
NATIVE_TEST_SOURCE = PROJECT_ROOT / "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindAfterAttackDrawTests.cpp"
DECLARATION = PROJECT_ROOT / "integrations/rosettastone/card_rules/after_attack_draw.v1.json"
GENERATOR = PROJECT_ROOT / "scripts/generate_after_attack_draw.py"
GENERATED_MANIFEST = PROJECT_ROOT / "integrations/rosettastone/card_rules/after_attack_draw.generated.json"
GENERATED_SOURCE = PROJECT_ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/ManaMindAfterAttackDrawGen.cpp"
CAPABILITIES = PROJECT_ROOT / "integrations/rosettastone/card_rules/capabilities.json"
EVIDENCE = PROJECT_ROOT / "integrations/rosettastone/card_rules/after_attack_draw.evidence.json"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def main() -> None:
    if not NATIVE_TESTS.exists() or not ENGINE_LIBRARY.exists():
        raise RuntimeError("Build the py312 UnitTests target before running package verification")
    native = subprocess.run([str(NATIVE_TESTS), "--test-case=[ManaMind after attack draw]*"],
                            cwd=PROJECT_ROOT / "vendor/RosettaStone", check=True,
                            capture_output=True, text=True)
    print(native.stdout, end="")
    manifest = json.loads(GENERATED_MANIFEST.read_text(encoding="utf-8"))
    native_scope_hash = file_hash(NATIVE_TEST_SOURCE)
    bridge_scope_hash = file_hash(Path(__file__))
    capability_fingerprint = file_hash(CAPABILITIES)
    generated_source_hash = file_hash(GENERATED_SOURCE)
    declaration_fingerprint = file_hash(DECLARATION)
    generator_fingerprint = file_hash(GENERATOR)
    engine_fingerprint = file_hash(ENGINE_LIBRARY)
    bridge_module_fingerprint = file_hash(PROJECT_ROOT / "integrations/rosettastone/build/python/mana_rosetta_bridge.cp312-win_amd64.pyd")
    card_evidence = {}
    for card_id, player_class in CASES:
        deck = make_simple_test_deck(player_class=player_class)
        if card_id in deck:
            index = deck.index(card_id)
            deck[0], deck[index] = deck[index], deck[0]
        else:
            deck[0] = card_id
        errors = validate_deck(deck, player_class=player_class)
        if errors:
            raise AssertionError(f"{card_id} rejected from current Standard deck: {errors}")
        opponent = make_simple_test_deck(player_class="MAGE")
        game = SimulatorSession(deck, opponent, player1_class=player_class,
                                player2_class="MAGE", shuffle=False, random_seed=19)
        state = game.observation("PLAYER1")
        if card_id not in {card.card_id for card in state.self_hand}:
            raise AssertionError(f"{card_id} was not loaded into the bridge player's opening hand")
        if not game.legal_actions():
            raise AssertionError(f"{card_id}: bridge returned no legal actions")
        print(f"PASS {card_id}: Standard deck validation, session creation, visible hand, legal actions")
        package_entry = next(row for row in manifest["cards"] if row["card_id"] == card_id)
        fingerprints = {
            "rules_fingerprint": canonical_hash({
                "rules_text_sha256": package_entry["rules_text_sha256"],
                "declaration_sha256": declaration_fingerprint,
                "generator_script_sha256": generator_fingerprint,
                "generated_source_sha256": generated_source_hash,
            }),
            "pool_membership_sha256": canonical_hash("DECK_DRAW_OUTCOMES_PROFILE_SPECIFIC; closure out of scope"),
            "pool_predicate_version": "DECK_DRAW_OUTCOMES_PROFILE_SPECIFIC_V1",
            "capability_fingerprint": capability_fingerprint,
            "engine_build_fingerprint": engine_fingerprint,
            "scenario_fingerprint": canonical_hash({
                "native_scenario_sha256": native_scope_hash,
                "bridge_smoke_sha256": bridge_scope_hash,
                "bridge_module_sha256": bridge_module_fingerprint,
            }),
        }
        card_evidence[card_id] = {
            **fingerprints,
            "status": "VERIFIED_SCOPED",
            "scope": "AFTER_ATTACK trigger actor and declared fixed effects; deck-draw outcome closure is not verified.",
            "native_test": "[ManaMind after attack draw]* passed",
            "bridge_smoke": "Standard deck validation, session creation, visible hand, and legal action enumeration passed",
            "native_assertion_output": native.stdout.strip(),
            "binary_sha256": engine_fingerprint,
            "bridge_module_sha256": bridge_module_fingerprint,
        }
    evidence_doc = {
        "schema_version": 1,
        "package": "after_attack_draw",
        "catalog_sha256": manifest["catalog_sha256"],
        "declaration_sha256": declaration_fingerprint,
        "generator_script_sha256": generator_fingerprint,
        "generated_source_sha256": generated_source_hash,
        "capability_file_sha256": capability_fingerprint,
        "engine_library_sha256": engine_fingerprint,
        "native_scenario_sha256": native_scope_hash,
        "bridge_smoke_sha256": bridge_scope_hash,
        "training_eligible": False,
        "cards": card_evidence,
    }
    EVIDENCE.write_text(json.dumps(evidence_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
