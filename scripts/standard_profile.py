"""Pinned Standard profile inputs shared by the source-derived catalog builders."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "configs/standard_profile.json"


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
    required = {"schema_version", "profile_id", "as_of_date", "scope", "metadata_snapshot", "roots", "bans", "catalog", "captured_at_utc"}
    if not required <= profile.keys() or profile["schema_version"] != 1:
        raise ValueError("Invalid Standard profile: missing input identities or unsupported schema")
    profile["_path"] = path
    return profile


def profile_path(profile: dict, key: str) -> Path:
    path = Path(profile[key])
    return path if path.is_absolute() else ROOT / path
