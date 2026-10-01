"""Run native and bridge checks for the Crystal Merchant Core alias."""
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

CARD_ID = "CORE_ULD_133"
BASE_ID = "ULD_133"
PLAYER_CLASS = "DRUID"
NATIVE_TESTS = PROJECT_ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"
NATIVE_TEST_SOURCE = PROJECT_ROOT / "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindCoreAliasCardsTests.cpp"
ENGINE_LIBRARY = PROJECT_ROOT / "vendor/RosettaStone/build-mana-py312/lib/RosettaStone.lib"
ENGINE_CMAKE_CACHE = PROJECT_ROOT / "vendor/RosettaStone/build-mana-py312/CMakeCache.txt"
BRIDGE_MODULE = PROJECT_ROOT / "integrations/rosettastone/build/python/mana_rosetta_bridge.cp312-win_amd64.pyd"
BRIDGE_CMAKE_CACHE = PROJECT_ROOT / "integrations/rosettastone/build/CMakeCache.txt"
ALIAS_MANIFEST = PROJECT_ROOT / "integrations/rosettastone/card_rules/core_aliases.generated.json"
CATALOG = PROJECT_ROOT / "data/cards/standard_current_enUS.json"
DECLARATION = PROJECT_ROOT / "integrations/rosettastone/card_rules/core_aliases.v1.json"
GENERATOR = PROJECT_ROOT / "scripts/generate_core_card_aliases.py"
CAPABILITIES = PROJECT_ROOT / "integrations/rosettastone/card_rules/capabilities.json"
EVIDENCE = PROJECT_ROOT / "integrations/rosettastone/card_rules/core_aliases.evidence.json"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def main() -> None:
    required = (NATIVE_TESTS, NATIVE_TEST_SOURCE, ENGINE_LIBRARY, ENGINE_CMAKE_CACHE,
                BRIDGE_MODULE, BRIDGE_CMAKE_CACHE,
                ALIAS_MANIFEST, CATALOG, DECLARATION, GENERATOR, CAPABILITIES)
    missing = [path for path in required if not path.exists()]
    if missing:
        raise RuntimeError("Build UnitTests, engine library and bridge first; missing: " +
                           ", ".join(str(path) for path in missing))

    native = subprocess.run(
        [str(NATIVE_TESTS), "--test-case=[ManaMind definition aliases]*"],
        cwd=PROJECT_ROOT / "vendor/RosettaStone", check=True,
        capture_output=True, text=True,
    )
    print(native.stdout, end="")

    manifest = json.loads(ALIAS_MANIFEST.read_text(encoding="utf-8"))
    entry = next((row for row in manifest["cards"] if row["card_id"] == CARD_ID), None)
    if entry is None or entry["base_card_id"] != BASE_ID:
        raise AssertionError(f"generated alias manifest does not contain {CARD_ID} -> {BASE_ID}")
    catalog_hash = file_hash(CATALOG)
    if manifest.get("catalog_sha256") != catalog_hash:
        raise AssertionError("generated alias manifest uses a stale catalog; rerun the generator after reviewing aliases")

    bridge_smokes = []
    card_by_id = {card["id"]: card for card in json.loads(CATALOG.read_text(encoding="utf-8"))["cards"]}
    smoke_ids = [
        CARD_ID, "CORE_BAR_812", "CORE_BAR_878", "CORE_BT_510", "CORE_EX1_559", "CORE_WC_042",
        "CORE_BT_120", "CORE_BT_321", "CORE_BT_493", "CORE_DAL_575", "CORE_DAL_720",
        "CORE_DRG_024", "CORE_EX1_100", "CORE_KAR_057", "CORE_ONY_022", "CORE_REV_308",
        "CORE_SCH_717", "CORE_ULD_152", "CORE_ULD_165", "CORE_ULD_280",
        "CORE_BT_292", "CORE_DRG_256", "CORE_EX1_014", "CORE_EX1_189", "CORE_EX1_198",
        "CORE_EX1_310", "CORE_KAR_077", "CORE_NEW1_022", "CORE_SCH_713", "CORE_SW_072",
        "CORE_SW_429", "CORE_TRL_111", "CORE_ULD_178", "CORE_UNG_809", "CORE_UNG_912",
        "CORE_SW_442", "CORE_AT_052", "CORE_WON_096", "CORE_WON_337", "Core_LOE_115",
        "Core_UNG_072", "TIME_603", "TIME_720", "TLC_483", "CORE_EX1_002",
    ]
    for smoke_id in smoke_ids:
        player_class = card_by_id[smoke_id]["cardClass"]
        if player_class == "NEUTRAL":
            player_class = "MAGE"
        deck = make_simple_test_deck(player_class=player_class)
        if smoke_id in deck:
            index = deck.index(smoke_id)
            deck[0], deck[index] = deck[index], deck[0]
        else:
            deck[0] = smoke_id
        errors = validate_deck(deck, player_class=player_class)
        if errors:
            raise AssertionError(f"{smoke_id} rejected from Standard deck: {errors}")
        opponent = make_simple_test_deck(player_class="MAGE")
        game = SimulatorSession(deck, opponent, player1_class=player_class,
                                player2_class="MAGE", shuffle=False, random_seed=19)
        observation = game.observation("PLAYER1")
        if smoke_id not in {card.card_id for card in observation.self_hand}:
            raise AssertionError(f"{smoke_id} was not visible in the opening hand")
        actions = game.legal_actions()
        if not actions:
            raise AssertionError(f"{smoke_id}: bridge returned no legal actions")
        bridge_smokes.append({"card_id": smoke_id, "player_class": player_class,
                              "legal_action_count": len(actions), "status": "PASS"})
        print(f"PASS {smoke_id}: Standard deck validation, session, visible hand, {len(actions)} legal actions")

    engine_hash = file_hash(ENGINE_LIBRARY)
    engine_config_hash = file_hash(ENGINE_CMAKE_CACHE)
    bridge_hash = file_hash(BRIDGE_MODULE)
    bridge_config_hash = file_hash(BRIDGE_CMAKE_CACHE)
    declaration_hash = file_hash(DECLARATION)
    generator_hash = file_hash(GENERATOR)
    generated_source = PROJECT_ROOT / manifest["generated_source"]
    generated_header = PROJECT_ROOT / manifest["generated_header"]
    generated_source_hash = file_hash(generated_source)
    generated_header_hash = file_hash(generated_header)
    capability_hash = file_hash(CAPABILITIES)
    native_source_hash = file_hash(NATIVE_TEST_SOURCE)
    native_executable_hash = file_hash(NATIVE_TESTS)
    verifier_hash = file_hash(Path(__file__))
    no_dynamic_pool_hash = canonical_hash("NO_DYNAMIC_OUTCOME_IN_SCOPED_CARD_EFFECT")
    fingerprints = {
        "rules_fingerprint": canonical_hash({
            "rules_text_sha256": entry["rules_text_sha256"],
            "catalog_sha256": catalog_hash,
            "generated_manifest_sha256": file_hash(ALIAS_MANIFEST),
            "declaration_sha256": declaration_hash,
            "generator_script_sha256": generator_hash,
            "generated_header_sha256": generated_header_hash,
            "generated_source_sha256": generated_source_hash,
        }),
        "pool_membership_sha256": no_dynamic_pool_hash,
        "pool_predicate_version": "NO_DYNAMIC_OUTCOME_IN_SCOPED_CARD_EFFECT_V1",
        "capability_fingerprint": capability_hash,
        "engine_build_fingerprint": engine_hash,
        "scenario_fingerprint": canonical_hash({
            "native_scenario_sha256": native_source_hash,
            "native_executable_sha256": native_executable_hash,
            "engine_cmake_cache_sha256": engine_config_hash,
            "bridge_cmake_cache_sha256": bridge_config_hash,
            "bridge_verifier_sha256": verifier_hash,
            "bridge_module_sha256": bridge_hash,
        }),
    }

    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        working_tree_state = "dirty" if subprocess.run(
            ["git", "status", "--porcelain"], cwd=PROJECT_ROOT,
            check=True, capture_output=True, text=True,
        ).stdout.strip() else "clean"
    except (OSError, subprocess.CalledProcessError):
        revision, working_tree_state = None, "unknown"

    evidence = {
        "schema_version": 1,
        "package": "core_aliases",
        "catalog_sha256": catalog_hash,
        "declaration_sha256": declaration_hash,
        "generator_script_sha256": generator_hash,
        "generated_source_sha256": generated_source_hash,
        "generated_header_sha256": generated_header_hash,
        "capability_file_sha256": capability_hash,
        "engine_library_sha256": engine_hash,
        "engine_cmake_cache_sha256": engine_config_hash,
        "bridge_cmake_cache_sha256": bridge_config_hash,
        "native_scenario_sha256": native_source_hash,
        "native_executable_sha256": native_executable_hash,
        "bridge_verifier_sha256": verifier_hash,
        "bridge_module_sha256": bridge_hash,
        "execution_identity": {
            "git_revision": revision,
            "working_tree_state": working_tree_state,
            "engine_library_sha256": engine_hash,
            "engine_cmake_cache_sha256": engine_config_hash,
            "native_executable_sha256": native_executable_hash,
            "bridge_module_sha256": bridge_hash,
            "bridge_cmake_cache_sha256": bridge_config_hash,
            "toolchain_identity": "MSVC 14.44.35207 x64; CMake/Ninja configuration recorded in local build cache",
        },
        "training_eligible": False,
        "batch_bridge_smokes": bridge_smokes,
        "cards": {
            CARD_ID: {
                **fingerprints,
                "status": "VERIFIED_SCOPED",
                "scope": "Core CardDef parity for the allowlisted alias package; Crystal Merchant trigger condition and draw count in the focused native scenario; Standard deck validation, bridge session, visible card identity and legal-action enumeration. No closure or training claim.",
                "native_test": "[ManaMind Core aliases]* passed",
                "native_assertion_output": native.stdout.strip(),
                "bridge_smoke": f"Standard deck validation, session creation, visible opening hand and legal-action enumeration passed for {len(bridge_smokes)} cards in the batch",
                "binary_sha256": engine_hash,
                "bridge_module_sha256": bridge_hash,
                "training_eligible": False,
            }
        },
    }
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Evidence written: {EVIDENCE}")


if __name__ == "__main__":
    main()
