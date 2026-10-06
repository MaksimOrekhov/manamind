"""Pinned inputs shared by Standard builders, generators and verification tools."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "configs/standard_profile.json"


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def load_profile(path: Path | str | None = None) -> dict:
    if path is None:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--profile", type=Path)
        args, _ = parser.parse_known_args()
        path = args.profile or os.environ.get("MANAMIND_STANDARD_PROFILE") or DEFAULT_PROFILE
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    profile = json.loads(path.read_text(encoding="utf-8"))
    required = {"schema_version", "profile_id", "registry_id", "as_of_date", "scope", "metadata_snapshot", "roots", "bans", "catalog", "engine_overlay", "registry", "reports", "captured_at_utc"}
    if not required <= profile.keys() or profile["schema_version"] != 1:
        raise ValueError("Invalid Standard profile: missing input identities or unsupported schema")
    profile["_path"] = path
    return profile


def profile_path(profile: dict, key: str) -> Path:
    path = Path(profile[key])
    return path if path.is_absolute() else ROOT / path


# Offline observation/import implementation. The live bridge (src/manamind/live) is deliberately
# not part of the canonical training observation identity.
OBSERVATION_SOURCE_ROOTS = (
    "src/manamind/domain",
    "src/manamind/encoding",
    "src/manamind/integrations/rosettastone",
    "src/manamind/integrations/powerlog",
    "src/manamind/models/policy.py",
    "scripts/import_power_log.py",
)


def tree_digest(directory: Path, roots: tuple[str, ...]) -> str:
    files = []
    for name in roots:
        path = directory / name
        files.extend([path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file()))
    return digest({p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in files if "__pycache__" not in p.parts})


def engine_identity() -> dict:
    vendor = ROOT / "vendor/RosettaStone"
    result = subprocess.run(["git", "-C", str(vendor), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    return {"source_commit": result.stdout.strip(), "source_tree_sha256": tree_digest(vendor, ("CMakeLists.txt", "Includes", "Sources", "Extensions", "Resources", "Tests"))}


def execution_identity(profile: dict) -> dict:
    """Source identities only. Never inspect ignored build products here."""
    return {
        "profile_id": profile["profile_id"],
        "profile_sha256": digest({k: v for k, v in profile.items() if not k.startswith("_")}),
        "engine_source_sha256": engine_identity()["source_tree_sha256"],
        "bridge_source_sha256": tree_digest(ROOT, ("integrations/rosettastone/bridge.cpp", "integrations/rosettastone/CMakeLists.txt")),
        "observation_source_sha256": tree_digest(ROOT, OBSERVATION_SOURCE_ROOTS),
        "rules_source_sha256": tree_digest(ROOT, ("scripts/card_rules", *tuple(p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "integrations/rosettastone/card_rules").glob("*.json")) if not p.name.endswith(".evidence.json")), *tuple(p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "scripts").glob("generate_*.py"))))),
        "scenario_source_sha256": tree_digest(ROOT, tuple(p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "scripts").glob("verify_*.py")))),
        "catalog_sha256": hashlib.sha256(profile_path(profile, "catalog").read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
    }
