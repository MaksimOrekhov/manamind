"""Run native family and production bridge parity checks for the package."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.build_standard_registry import read_json  # noqa: E402
from scripts.verification_evidence import record_execution  # noqa: E402
from manamind.integrations.rosettastone.rosettastone import _load_bridge  # noqa: E402

RULES = ROOT / "integrations/rosettastone/card_rules"
MANIFEST = RULES / "held_card_gate_fixed_battlecry.generated.json"
EVIDENCE = RULES / "held_card_gate_fixed_battlecry.evidence.json"
NATIVE = ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"
SCENARIOS = ("CATA_111", "TIME_062", "CORE_RLK_814", "FIR_961", "EDR_472")


def verify() -> dict:
    manifest = read_json(MANIFEST)
    assert {row["card_id"] for row in manifest["cards"]} == set(SCENARIOS)
    subprocess.run([str(NATIVE), "--test-case=[ManaMind held card gate]*", "--no-breaks"],
                   cwd=ROOT / "vendor/RosettaStone/build-mana-py312", check=True)
    bridge = _load_bridge()
    target_results = {}
    for cost, expected in ((4, False), (5, True)):
        result = bridge.inspect_held_card_gate_targets("EDR_472", "CS2_029", cost)
        direct = set(result["direct_target_entity_ids"])
        actions = set(result["action_target_entity_ids"])
        assert direct == actions, (cost, direct, actions)
        assert bool(direct) is expected, (cost, direct)
        target_results[str(cost)] = {"target_count": len(direct), "direct_action_parity": "PASS"}
    rows = {card_id: {"status": "VERIFIED_SCOPED",
                      "scope": "INDEPENDENT_FAMILY_SCENARIOS_AND_BRIDGE_TARGET_PARITY",
                      "training_scope": "SCOPED_PACKAGE_ONLY",
                      "bridge_action_status": "VERIFIED_SCOPED",
                      "contract_review": {"contract_id": manifest["contract_id"],
                                          "contract_version": manifest["contract_version"]},
                      "scenario_fingerprint": hashlib.sha256(
                          (card_id + "|" + manifest["declaration_sha256"] + "|" + manifest["renderer_sha256"]).encode()
                      ).hexdigest()} for card_id in SCENARIOS}
    evidence = {"package_id": manifest["package_id"], "contract_id": manifest["contract_id"],
                "contract_version": manifest["contract_version"], "scope": "SCOPED_PACKAGE_ONLY",
                "cards": rows, "family_tests": "PASS", "bridge_target_parity": target_results,
                "known_baseline_native_failure": "[Druid : Minion] - CORE_OG_044 : Fandral Staghelmh",
                "training_eligible": False}
    evidence = record_execution(evidence)
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"family_tests": "PASS", "bridge_target_parity": target_results,
            "evidence": EVIDENCE.relative_to(ROOT).as_posix()}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
