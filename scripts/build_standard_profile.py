"""Rebuild the roots snapshot and the shared Standard catalog from one pinned profile."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from standard_profile import ROOT, load_profile, profile_path


def write_json(path: Path, value: object) -> None:
    content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if not path.exists() or path.read_bytes() != content.encode("utf-8"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path)
    args = parser.parse_args()
    profile = load_profile(args.profile)
    subprocess.run([sys.executable, str(ROOT / "scripts/build_standard_root_pool.py"), "--profile", str(profile["_path"])], check=True)
    roots = json.loads(profile_path(profile, "roots").read_text(encoding="utf-8"))
    cards = [item["metadata"] for item in roots["roots"]]
    catalog = {"schema_version": 1, "game": "Hearthstone", "format": "STANDARD", "valid_as_of": profile["as_of_date"], "profile_id": profile["profile_id"], "source": roots["source_name"], "source_sha256": roots["source_sha256"], "root_membership_sha256": roots["root_membership_sha256"], "cards": cards}
    write_json(profile_path(profile, "catalog"), catalog)
    print(f"Profile {profile['profile_id']}: {len(cards)} catalog roots")


if __name__ == "__main__":
    main()
