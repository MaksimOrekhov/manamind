"""Render the reviewed held-card-gated fixed Battlecry package."""
from __future__ import annotations

import hashlib
import json

from build_card_support_analysis import sha256, write_if_changed
from card_rules.held_card_gate_fixed_battlecry import render, validate
from standard_profile import ROOT, load_profile, profile_path

RULES = ROOT / "integrations/rosettastone/card_rules"
DECLARATION = RULES / "held_card_gate_fixed_battlecry.v1.json"
MANIFEST = RULES / "held_card_gate_fixed_battlecry.generated.json"
HEADER = ROOT / "vendor/RosettaStone/Includes/Rosetta/PlayMode/CardSets/ManaMindHeldCardGateFixedBattlecryGen.hpp"
SOURCE = ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/ManaMindHeldCardGateFixedBattlecryGen.cpp"


def record_hash(row: object) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def main() -> None:
    profile = load_profile()
    catalog_path = profile_path(profile, "catalog")
    catalog = {card["id"]: card for card in json.loads(catalog_path.read_text(encoding="utf-8"))["cards"]}
    resources = {card["id"]: card for card in json.loads((ROOT / "vendor/RosettaStone/Resources/cards.json").read_text(encoding="utf-8"))}
    declaration = json.loads(DECLARATION.read_text(encoding="utf-8"))
    rows = validate(declaration, catalog, resources)
    header, source = render(rows)
    write_if_changed(HEADER, header)
    write_if_changed(SOURCE, source)
    manifest = {key: declaration[key] for key in ("schema_version", "package_id", "contract_id", "contract_version", "implementation_kind", "dependencies")}
    manifest.update({"declaration": DECLARATION.relative_to(ROOT).as_posix(),
                     "declaration_sha256": sha256(DECLARATION),
                     "catalog_sha256": sha256(catalog_path),
                     "renderer_sha256": sha256(ROOT / "scripts/card_rules/held_card_gate_fixed_battlecry.py"),
                     "generated_header": HEADER.relative_to(ROOT).as_posix(),
                     "generated_source": SOURCE.relative_to(ROOT).as_posix(),
                     "cards": [{**row, "rules_text_sha256": record_hash(catalog[row["card_id"]].get("text", "")),
                                "dependencies": sorted({effect["enchantment_ref"] for effect in row["effects"]
                                                        if "enchantment_ref" in effect}),
                                "task_types": sorted({"ConditionTask", "FlagTask", *({"REFRESH_MANA": "RefreshManaTask", "ADD_SELF_ENCHANT": "AddEnchantmentTask", "SET_SELF_TAG": "SetGameTagTask", "DAMAGE_TARGET": "DamageTask"}[effect["op"]] for effect in row["effects"])}),
                                "implementation_kind": "REUSABLE_CAPABILITY", "training_eligible": False}
                               for row in rows], "training_eligible": False})
    write_if_changed(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"Generated {len(rows)} declaration-only held-card-gate consumers.")


if __name__ == "__main__":
    main()
