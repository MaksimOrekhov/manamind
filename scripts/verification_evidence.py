"""Explicit execution evidence; only producers inspect local native artifacts."""
from __future__ import annotations

import hashlib
import json
import re

from scripts.standard_profile import ROOT, execution_identity, load_profile


def artifact_identities() -> dict:
    paths = {
        "engine_library": ROOT / "vendor/RosettaStone/build-mana-py312/lib/RosettaStone.lib",
        "native_tests": ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe",
        "bridge_module": ROOT / "integrations/rosettastone/build/python/mana_rosetta_bridge.cp312-win_amd64.pyd",
    }
    return {name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for name, path in paths.items()}


def record_execution(document: dict) -> dict:
    """Call only after native scenarios and bridge smoke have completed successfully."""
    identity = execution_identity(load_profile())
    artifacts = artifact_identities()
    build_path = ROOT / "integrations/rosettastone/build/execution_identity.json"
    if not build_path.exists():
        raise ValueError("Run scripts/build_native_identity.py before producing evidence")
    build = json.loads(build_path.read_text(encoding="utf-8"))
    if build.get("build_result") != "PASS" or build.get("execution_identity") != identity or build.get("artifacts") != artifacts:
        raise ValueError("Build source/binary identity differs; rebuild before producing evidence")
    from pathlib import Path
    from manamind.integrations.rosettastone.rosettastone import _load_bridge
    loaded_hash = hashlib.sha256(Path(_load_bridge().__file__).read_bytes()).hexdigest()
    if loaded_hash != artifacts["bridge_module"]["sha256"]:
        raise ValueError("The process loaded a bridge different from the recorded build")
    document["schema_version"] = 2
    document["execution_identity"] = identity
    document["artifacts"] = artifacts
    document["execution_result"] = {"native_scenarios": "PASS", "bridge_smoke": "PASS"}
    return document


def scoped_status(document: dict, card_id: str, identity: dict) -> dict:
    row = document.get("cards", {}).get(card_id, {})
    result = {"status": "STALE_OR_INCOMPLETE", "verification_scope": row.get("scope"), "historical_status": row.get("status"), "reason": "Evidence lacks a complete explicit execution identity."}
    if document.get("schema_version") != 2 or not row:
        return result
    if document.get("execution_identity") != identity:
        return {**result, "status": "STALE", "reason": "Explicit execution source/profile fingerprints differ from current inputs."}
    artifacts = document.get("artifacts", {})
    if not all(re.fullmatch(r"[0-9a-f]{64}", artifacts.get(key, {}).get("sha256", "")) for key in ("engine_library", "native_tests", "bridge_module")):
        return result
    if document.get("execution_result") != {"native_scenarios": "PASS", "bridge_smoke": "PASS"} or row.get("status") != "VERIFIED_SCOPED":
        return result
    return {**result, "status": "CURRENT", "reason": "Explicit successful execution matches the current pinned source/profile inputs."}
