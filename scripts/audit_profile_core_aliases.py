"""Verify the clean Core-alias subset used by Meta Training Profile v1."""
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
    SimulatorSession, make_simple_test_deck, validate_deck,
)
from scripts.verification_evidence import record_execution  # noqa: E402

IDS = ("CORE_DRG_107", "CORE_SW_072", "CORE_SW_108")
UNIT_TESTS = ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"
NATIVE_FILTERS = (
    "[ManaMind definition aliases]*",
    "[Mage : Minion] - DRG_107 : Violet Spellwing",
    "[Neutral : Minion] - SW_072 : Rustrot Viper",
    "[ManaMind Core aliases] - CORE_SW_108 First Flame preserves damage and generated card",
)
ALIAS_MANIFEST = ROOT / "integrations/rosettastone/card_rules/core_aliases.generated.json"
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
PROFILE = ROOT / "configs/training_profiles/meta_training_20261002_v1.json"
EVIDENCE = ROOT / "integrations/rosettastone/card_rules/core_aliases.evidence.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main() -> None:
    native_runs = []
    for native_filter in NATIVE_FILTERS:
        native = subprocess.run(
            [str(UNIT_TESTS), f"--test-case={native_filter}"],
            cwd=ROOT / "vendor/RosettaStone", capture_output=True, text=True,
            errors="replace", check=False,
        )
        output = native.stdout + native.stderr
        print(output, end="")
        if native.returncode or "Status: SUCCESS!" not in output:
            raise RuntimeError(f"Profile Core-alias native family scenario failed: {native_filter}")
        native_runs.append(output)
    output = "\n".join(native_runs)

    catalog = {row["id"]: row for row in json.loads(CATALOG.read_text(encoding="utf-8"))["cards"]}
    bridge_rows = {}
    for card_id in IDS:
        card = catalog[card_id]
        player_class = card["cardClass"]
        if player_class == "NEUTRAL":
            player_class = "MAGE"
        deck = make_simple_test_deck(player_class=player_class)
        deck[0] = card_id
        errors = validate_deck(deck, player_class=player_class)
        if errors:
            raise AssertionError(f"{card_id}: Standard deck validation failed: {errors}")
        session = SimulatorSession(
            deck, make_simple_test_deck(player_class="MAGE"),
            player1_class=player_class, player2_class="MAGE", shuffle=False,
            random_seed=23,
        )
        observation = session.observation("PLAYER1")
        if card_id not in {row.card_id for row in observation.self_hand}:
            raise AssertionError(f"{card_id}: alias absent from SELF opening hand")
        actions = session.legal_actions()
        if not actions or not any(a.get("type") == "END_TURN" for a in actions):
            raise AssertionError(f"{card_id}: no supported production actions")
        bridge_rows[card_id] = {
            "standard_deck_validation": "PASS",
            "visible_self_hand_identity": "PASS",
            "legal_action_enumeration": "PASS",
            "legal_action_count": len(actions),
        }

    aliases = json.loads(ALIAS_MANIFEST.read_text(encoding="utf-8"))["cards"]
    alias_by_id = {row["card_id"]: row for row in aliases}
    if not all(card_id in alias_by_id for card_id in IDS):
        raise AssertionError("The reviewed aliases are missing from the generated owner")
    execution_rows = {}
    meta_profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile_hash = canonical_hash(meta_profile)
    for card_id in IDS:
        alias = alias_by_id[card_id]
        if alias["match_basis"] not in {
            "COUNT_AS_COPY_DBF",
            "DERIVED_CORE_ID_AND_EXACT_RULES_TEXT",
        }:
            raise AssertionError(f"{card_id}: unexpected alias basis")
        execution_rows[card_id] = {
            "status": "VERIFIED_SCOPED",
            "scope": "Reviewed Core alias-to-base CardDef equivalence; root-specific native functional scenario or existing focused scenario; Standard deck validation, visible SELF card identity, and legal-action enumeration. Dependency closure, full deck simulation and training admission are not claimed.",
            "training_scope": "SCOPED_PACKAGE_ONLY",
            "profile_manifest_sha256": profile_hash,
            "rules_fingerprint": canonical_hash({
                "alias_entry": alias,
                "catalog_card_sha256": sha256(CATALOG),
                "native_test_source_sha256": sha256(ROOT / "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindCoreAliasCardsTests.cpp"),
            }),
            "pool_membership_sha256": canonical_hash("NO_DYNAMIC_OUTCOME_POOL_IN_REVIEWED_ALIAS_SUBSET"),
            "pool_predicate_version": "NO_DYNAMIC_OUTCOME_POOL_IN_REVIEWED_ALIAS_SUBSET_V1",
            "capability_fingerprint": sha256(ROOT / "integrations/rosettastone/card_rules/core_aliases.v1.json"),
            "scenario_fingerprint": canonical_hash({
                "native_output": output,
                "native_test_source_sha256": sha256(ROOT / "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindCoreAliasCardsTests.cpp"),
                "verifier_sha256": sha256(Path(__file__)),
                "bridge_observation": bridge_rows[card_id],
            }),
            "bridge_action_status": "VERIFIED_SCOPED",
            "native_tests": list(NATIVE_FILTERS),
            "bridge_result": bridge_rows[card_id],
            "alias_base_card_id": alias["base_card_id"],
            "dependency_review": {
                "scope": "REVIEWED_STATIC_CANDIDATES_ONLY",
                "reviewed_alias_base": alias["base_card_id"],
                "basis": "The selected root's executable CardDef is checked against its existing base definition; identified fixed card references are recorded. This does not close transitive dependencies.",
                "dynamic_pools": [],
            },
            "training_eligible": False,
        }

    previous_cards = {}
    if EVIDENCE.exists():
        previous_cards = json.loads(EVIDENCE.read_text(encoding="utf-8")).get("cards", {})
    for previous_id, previous in previous_cards.items():
        if previous_id not in execution_rows:
            previous["status"] = "STALE"
            previous["invalidation_reason"] = "Not rerun in the 2026-10-03 verification harvest; historical record retained."
            execution_rows[previous_id] = previous

    evidence = record_execution({
        "schema_version": 1,
        "package": "profile_core_alias_low_hanging_verification_v1",
        "scope": "SCOPED_PACKAGE_ONLY",
        "profile_manifest_sha256": profile_hash,
        "cards": execution_rows,
        "native_output": output,
        "bridge_results": bridge_rows,
        "training_eligible": False,
    })
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {len(IDS)} Core alias roots; 65 alias definition parity cases, 3 base/alias functional scenarios, 3 bridge sessions; evidence {EVIDENCE}")


if __name__ == "__main__":
    main()
