"""Record scoped verification for Spider Rider's existing AFTER_ATTACK trigger."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verification_evidence import record_execution

PROFILE = ROOT / "configs/training_profiles/meta_training_20261002_v1.json"
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
EVIDENCE = ROOT / "integrations/rosettastone/card_rules/profile_verification_harvest_20261003_v2.evidence.json"
UNIT_TESTS = ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"
ROSETTA = ROOT / "vendor/RosettaStone"
CARD_ID = "JAIL_872"
NATIVE_FILTER = "[ManaMind trigger] - JAIL_872 draws after its hero attacks"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def run_bridge_scenario() -> dict[str, str]:
    from scripts.verify_standard_meta_rules_group_2 import verify_spider_rider

    verify_spider_rider()
    return {
        "scenario": "verify_spider_rider",
        "hero_attack_action": "PASS",
        "hand_size_increases_by_one": "PASS",
        "configured_bridge_actions": "PASS",
    }


def main() -> None:
    result = subprocess.run(
        [str(UNIT_TESTS), f"--test-case={NATIVE_FILTER}"],
        cwd=ROSETTA,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    native_output = result.stdout + result.stderr
    print(native_output, end="")
    if result.returncode or "Status: SUCCESS!" not in native_output:
        raise RuntimeError("Spider Rider native scenario failed")
    bridge = run_bridge_scenario()

    cards = json.loads(CATALOG.read_text(encoding="utf-8"))["cards"]
    card = next(item for item in cards if item["id"] == CARD_ID)
    card_source = ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/CoreCardsGen.cpp"
    test_source = ROOT / "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindEffectCompositionTests.cpp"
    source_hash = sha256(card_source)
    profile_hash = canonical_hash(json.loads(PROFILE.read_text(encoding="utf-8")))
    row = {
        "status": "VERIFIED_SCOPED",
        "scope": "Root-specific native hero-attack trigger scenario plus configured bridge action scenario confirming exactly one draw after the SELF hero attacks. Does not claim other attack-source semantics, full dependency closure, deck readiness or training admission.",
        "training_scope": "SCOPED_PACKAGE_ONLY",
        "profile_manifest_sha256": profile_hash,
        "rules_fingerprint": canonical_hash({
            "card": card,
            "card_source_sha256": source_hash,
            "native_test_source_sha256": sha256(test_source),
            "dependencies": [],
        }),
        "pool_membership_sha256": canonical_hash("NO_DYNAMIC_OUTCOME_POOL_SPIDER_RIDER_V1"),
        "pool_predicate_version": "NO_DYNAMIC_OUTCOME_POOL_SPIDER_RIDER_V1",
        "capability_fingerprint": source_hash,
        "scenario_fingerprint": canonical_hash({
            "native_output": native_output,
            "bridge_result": bridge,
            "verifier_sha256": sha256(Path(__file__)),
        }),
        "bridge_action_status": "VERIFIED_SCOPED",
        "native_test": NATIVE_FILTER,
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
        "cards": {**existing.get("cards", {}), CARD_ID: row},
        "package_results": {
            **existing.get("package_results", {}),
            "spider_rider_hero_attack_draw_verification_v1": {
                "verified_roots": [CARD_ID],
                "native_output": native_output,
                "bridge_output": bridge,
                "static_dependencies": [],
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
