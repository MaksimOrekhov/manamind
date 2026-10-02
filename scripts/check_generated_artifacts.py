"""Rebuild pinned source-derived artifacts and fail if any committed output differs."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from standard_profile import ROOT, load_profile, profile_path

GENERATORS = ("core_card_aliases", "effect_composition", "after_attack_draw", "repeated_trigger_draw", "filtered_school_draw", "keyword_only_cards", "metadata_only_cards", "minion_set_enchant")


def check_ownership() -> None:
    owners = {}
    generated_sources = {}
    for path in sorted((ROOT / "integrations/rosettastone/card_rules").glob("*.generated.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if "generated_source" in manifest:
            generated_sources[(ROOT / manifest["generated_source"]).resolve()] = path.name
        for row in manifest["cards"]:
            card_id = row["card_id"]
            if card_id in owners:
                raise ValueError(f"Duplicate generated owner for {card_id}: {owners[card_id]} and {path.name}")
            owners[card_id] = path.name
    literal_owners = {}
    for path in sorted((ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets").glob("*.cpp")):
        source = re.sub(r"/\*.*?\*/|//[^\n]*", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
        for card_id in re.findall(r'cards\.emplace\(\s*"([^\"]+)"', source):
            if card_id in literal_owners:
                raise ValueError(f"Duplicate literal CardDef for {card_id}: {literal_owners[card_id]} and {path.name}")
            literal_owners[card_id] = path.name
            if card_id in owners and generated_sources.get(path.resolve()) != owners[card_id]:
                raise ValueError(f"Manual/generated ownership conflict for {card_id}: {path.name} and {owners[card_id]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path)
    args = parser.parse_args()
    profile = load_profile(args.profile)
    outputs = {profile_path(profile, key) for key in ("roots", "catalog", "engine_overlay", "registry")}
    outputs.update(profile_path(profile, "reports") / name for name in ("summary.json", "summary.md"))
    for path in (ROOT / "integrations/rosettastone/card_rules").glob("*.generated.json"):
        outputs.add(path)
        manifest = json.loads(path.read_text(encoding="utf-8"))
        outputs.update(ROOT / manifest[key] for key in ("generated_header", "generated_source") if key in manifest)
    before = {path: path.read_bytes().replace(b"\r\n", b"\n") if path.exists() else None for path in outputs}
    environment = {**os.environ, "MANAMIND_STANDARD_PROFILE": str(profile["_path"])}
    for script in ("build_standard_profile", *("generate_" + name for name in GENERATORS), "build_standard_registry"):
        subprocess.run([sys.executable, str(ROOT / "scripts" / (script + ".py"))], cwd=ROOT, env=environment, check=True)
    check_ownership()
    changed = [str(path) for path, content in before.items() if not path.exists() or path.read_bytes().replace(b"\r\n", b"\n") != content]
    if changed:
        raise SystemExit("Generated outputs were stale:\n" + "\n".join(sorted(changed)))
    print(f"{len(outputs)} pinned outputs reproduced; generated ownership is unique.")


if __name__ == "__main__":
    main()
