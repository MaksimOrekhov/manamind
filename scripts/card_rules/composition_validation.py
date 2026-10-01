"""Validate an allowlisted effect-composition IR and emit ordinary C++."""
from __future__ import annotations

import hashlib
import re
import sys

from standard_profile import ROOT, load_profile, profile_path
sys.path.insert(0, str(ROOT / "scripts"))
from build_card_support_analysis import collect_card_blocks, norm_text, read_json, sha256  # noqa: E402

DECLARATION = ROOT / "integrations/rosettastone/card_rules/effect_composition.v1.json"
PROFILE = load_profile()
CATALOG = profile_path(PROFILE, "catalog")
RESOURCES = ROOT / "vendor/RosettaStone/Resources/cards.json"
HEADER = ROOT / "vendor/RosettaStone/Includes/Rosetta/PlayMode/CardSets/ManaMindEffectCompositionGen.hpp"
SOURCE = ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/ManaMindEffectCompositionGen.cpp"
MANIFEST = ROOT / "integrations/rosettastone/card_rules/effect_composition.generated.json"

ALLOWLIST = {"CORE_CS2_004", "END_007", "CAP_801", "CORE_SW_066", "CORE_UNG_084", "CORE_OG_149", "CORE_CS2_024", "CORE_CS2_094", "CORE_EX1_129", "CORE_TSC_076", "CORE_GVG_061", "CORE_BOT_222", "CORE_BOT_451", "CORE_RLK_062", "CORE_LOOT_013", "RLK_024", "CORE_LOOT_368", "CORE_OG_031", "FIR_778", "JAIL_007", "CATA_475", "EDR_459", "CATA_304", "CORE_CFM_604", "EDR_476", "EDR_971", "RLK_709", "CATA_612", "TIME_218", "TIME_215", "TLC_620", "TLC_225", "TLC_249", "FIR_909", "CORE_YOP_034", "EDR_110", "CATA_485", "DINO_132", "CORE_RLK_083", "END_026", "TLC_256", "TIME_015", "TLC_401", "RLK_223", "CORE_ICC_210", "CORE_AT_062", "EDR_942", "TIME_100", "EDR_889", "CORE_GVG_059", "CORE_ICC_214", "TLC_EVENT_402", "CORE_KAR_061", "CORE_GVG_103", "EDR_816", "TIME_428", "CORE_OG_211", "CORE_GIL_534", "JAIL_329", "TIME_212", "DINO_406", "CATA_201", "JAIL_441", "CATA_203", "EDR_485", "EDR_571", "FIR_954", "CATA_467", "CORE_DRG_403", "CATA_305", "CORE_CFM_753", "CORE_WW_329", "TIME_037", "JAIL_387", "TLC_828", "END_021", "MEND_305", "DINO_419", "EDR_861", "TLC_621", "TLC_623", "CATA_458", "JAIL_377", "JAIL_456", "CATA_303", "END_014", "TLC_606", "EDR_468", "JAIL_376", "JAIL_462", "EDR_572", "TLC_633"}

SELF_SUMMON_ALLOWLIST = {"CORE_RLK_062"}
GENERATED_ENCHANTMENT_ALLOWLIST = {"ICC_210e", "CATA_467e", "CORE_DRG_403e", "CATA_305e", "CORE_WW_329e", "TIME_037e", "JAIL_387e", "TLC_828e", "END_021e", "MEND_305e", "DINO_419e", "TLC_623e", "CATA_458e", "EDR_468e", "END_014e", "JAIL_376e", "EDR_572e"}
ROOT_FIELDS = {"schema_version", "catalog_path", "catalog_sha256", "cards"}
CARD_FIELDS = {"card_id", "activation", "play_requirements", "dependencies", "effects"}
REQS = {"REQ_TARGET_TO_PLAY", "REQ_MINION_TARGET", "REQ_TARGET_IF_AVAILABLE", "REQ_NONSELF_TARGET", "REQ_FRIENDLY_TARGET", "REQ_ENEMY_TARGET", "REQ_LEGENDARY_TARGET", "REQ_TARGET_WITH_RACE"}
TARGETS = {"TARGET": "EntityType::TARGET", "SOURCE": "EntityType::SOURCE", "HERO": "EntityType::HERO", "HEROES": "EntityType::HEROES", "FRIENDS": "EntityType::FRIENDS", "ENEMY_HERO": "EntityType::ENEMY_HERO", "ENEMIES": "EntityType::ENEMIES", "ALL_MINIONS_NOSOURCE": "EntityType::ALL_MINIONS_NOSOURCE", "MINIONS_NOSOURCE": "EntityType::MINIONS_NOSOURCE", "ENEMY_MINIONS": "EntityType::ENEMY_MINIONS"}
TAGS = {"REBORN": "GameTag::REBORN", "DIVINE_SHIELD": "GameTag::DIVINE_SHIELD", "RUSH": "GameTag::RUSH"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def metadata_only_rush_token(card: dict) -> bool:
    text = card.get("text", "")
    labels = [value.strip().lower() for value in re.findall(r"<b>([^<]+)</b>", text, flags=re.I)]
    remainder = re.sub(r"<b>[^<]+</b>", "", text, flags=re.I)
    remainder = norm_text(re.sub(r"</?[^>]+>", "", remainder)).strip(" ,.;:")
    return (card.get("type") == "MINION" and card.get("collectible") is not True and
            set(card.get("mechanics", [])) == {"RUSH"} and labels == ["rush"] and not remainder)


def validate():
    declaration = read_json(DECLARATION)
    require(set(declaration) == ROOT_FIELDS, "unexpected top-level IR fields")
    require(declaration["schema_version"] == 1, "unsupported IR schema")
    require(declaration["catalog_path"] == PROFILE["catalog"], "catalog is not allowlisted")
    catalog_hash = sha256(CATALOG)
    require(declaration["catalog_sha256"] == catalog_hash, "catalog fingerprint changed; re-review the package")
    catalog = {x["id"]: x for x in read_json(CATALOG)["cards"] if x.get("id")}
    resources = {x["id"]: x for x in read_json(RESOURCES) if x.get("id")}
    blocks = collect_card_blocks()
    other_owners = set()
    for filename in ("core_aliases.generated.json", "after_attack_draw.generated.json",
                     "repeated_trigger_draw.generated.json", "filtered_school_draw.generated.json",
                     "keyword_only.generated.json", "metadata_only.generated.json"):
        path = ROOT / "integrations/rosettastone/card_rules" / filename
        if path.exists():
            other_owners.update(item.get("card_id") for item in read_json(path).get("cards", []))
    rows = declaration["cards"]
    require(len(rows) == len(ALLOWLIST), "package must contain all and only the allowlisted IDs")
    declared_ids = {row.get("card_id") for row in rows if isinstance(row, dict)}
    seen = set()
    validated = []
    for row in rows:
        require(isinstance(row, dict) and set(row) == CARD_FIELDS, "unexpected card IR fields")
        card_id = row["card_id"]
        require(card_id in ALLOWLIST and card_id not in seen, f"card ID is duplicate or not allowlisted: {card_id}")
        require(card_id not in other_owners, f"card ID is owned by another generated route: {card_id}")
        seen.add(card_id)
        card = catalog.get(card_id)
        require(card is not None and card.get("text", "").strip(), f"current rules metadata missing: {card_id}")
        require(card_id not in blocks, f"direct manual/generated CardDef still owns {card_id}")
        activation = row["activation"]
        require((activation == "BATTLECRY" and card.get("type") in {"MINION", "WEAPON"} and "battlecry" in card.get("text", "").lower()) or
                (activation == "DEATHRATTLE" and card.get("type") in {"MINION", "WEAPON"} and "deathrattle" in card.get("text", "").lower()) or
                (activation == "BATTLECRY_AND_DEATHRATTLE" and card.get("type") == "MINION" and "battlecry" in card.get("text", "").lower() and "deathrattle" in card.get("text", "").lower()) or
                (activation == "TURN_END" and card.get("type") == "MINION" and "at the end of your turn" in norm_text(card.get("text", "")).lower()) or
                (activation == "TURN_START_EACH" and card.get("type") == "MINION" and "at the start of each turn" in norm_text(card.get("text", "")).lower()) or
                (activation == "AFTER_HERO_ATTACK" and card.get("type") in {"MINION", "WEAPON"} and "after your hero attacks" in norm_text(card.get("text", "")).lower()) or
                (activation == "AFTER_CAST" and card.get("type") == "MINION" and "after you cast a spell" in norm_text(card.get("text", "")).lower()) or
                (activation == "AFTER_CAST_ON_MINION" and card.get("type") == "MINION" and "after you cast a spell on a minion" in norm_text(card.get("text", "")).lower()) or
                (activation == "SPELL_PLAY" and card.get("type") == "SPELL"), f"activation/card-type mismatch: {card_id}")
        reqs = row["play_requirements"]
        require(isinstance(reqs, list) and len(reqs) == len(set(reqs)) and set(reqs) <= REQS, f"invalid play requirements: {card_id}")
        if "REQ_TARGET_WITH_RACE" in reqs:
            require(card_id in {"MEND_305", "DINO_419", "TLC_633"}, f"REQ_TARGET_WITH_RACE has not been source-reviewed for {card_id}")
        dependencies = row["dependencies"]
        require(isinstance(dependencies, list) and len(dependencies) == len(set(dependencies)), f"invalid dependencies: {card_id}")
        for dep_id in dependencies:
            dep = resources.get(dep_id) or catalog.get(dep_id)
            if dep is None and dep_id in GENERATED_ENCHANTMENT_ALLOWLIST:
                continue
            require(dep is not None, f"dependency metadata missing: {card_id} -> {dep_id}")
            require(dep.get("type") in {"ENCHANTMENT", "MINION", "WEAPON", "SPELL"}, f"unsupported dependency type: {card_id} -> {dep_id}")
            if dep.get("text", "").strip() and dep_id not in blocks and dep_id not in declared_ids and dep_id not in GENERATED_ENCHANTMENT_ALLOWLIST and not (dep_id == card_id and card_id in SELF_SUMMON_ALLOWLIST):
                require(metadata_only_rush_token(dep),
                        f"dependency rules source is not registered or metadata-only Rush token is unreviewed: {card_id} -> {dep_id}")
        effects = row["effects"]
        require(isinstance(effects, list) and effects, f"effects must be a non-empty list: {card_id}")
        normalized_effects = []
        for effect in effects:
            require(isinstance(effect, dict) and isinstance(effect.get("op"), str), f"invalid effect in {card_id}")
            op = effect["op"]
            if op in {"DAMAGE", "BATTLECRY_DAMAGE", "DEATHRATTLE_DAMAGE"}:
                require(set(effect) == {"op", "target", "amount", "spell_damage"}, f"invalid DAMAGE fields in {card_id}")
                require(effect["target"] in TARGETS and isinstance(effect["amount"], int) and 1 <= effect["amount"] <= 30, f"invalid DAMAGE parameters in {card_id}")
                require(isinstance(effect["spell_damage"], bool), f"spell_damage must be explicit in {card_id}")
                if op == "BATTLECRY_DAMAGE":
                    require(activation == "BATTLECRY_AND_DEATHRATTLE", f"BATTLECRY_DAMAGE requires dual trigger activation in {card_id}")
                if op == "DEATHRATTLE_DAMAGE":
                    require(activation == "BATTLECRY_AND_DEATHRATTLE", f"DEATHRATTLE_DAMAGE requires dual trigger activation in {card_id}")
                if card_id == "TIME_212":
                    require(activation == "SPELL_PLAY" and
                            {"REQ_TARGET_TO_PLAY", "REQ_MINION_TARGET", "REQ_FRIENDLY_TARGET"} <= set(reqs),
                            "TIME_212 damage requires a selected friendly minion")
                if card_id == "DINO_406":
                    require(activation == "SPELL_PLAY" and "REQ_TARGET_TO_PLAY" in set(reqs),
                            "Fire Breath requires its selected damage target")
                if card_id == "JAIL_441":
                    require(activation == "SPELL_PLAY" and
                            {"REQ_TARGET_TO_PLAY", "REQ_MINION_TARGET"} <= set(reqs),
                            "Drink Blood requires a selected minion")
            elif op == "ENCHANT":
                require(set(effect) == {"op", "target", "id"}, f"invalid ENCHANT fields in {card_id}")
                require(effect["target"] in TARGETS and effect["id"] in dependencies, f"undeclared enchantment reference in {card_id}")
            elif op in {"DRAW", "ARMOR"}:
                require(set(effect) == {"op", "amount"} and isinstance(effect["amount"], int) and 1 <= effect["amount"] <= 10, f"invalid {op} parameters in {card_id}")
            elif op == "DRAW_RACES":
                require(set(effect) == {"op", "races"} and card_id == "CORE_KAR_061" and
                        activation == "BATTLECRY" and effect["races"] == ["BEAST", "DRAGON", "MURLOC"],
                        f"DRAW_RACES is limited to The Curator's reviewed Battlecry in {card_id}")
            elif op == "DRAW_MINION_MIN_COST":
                require(set(effect) == {"op", "min_cost", "amount"} and card_id == "EDR_485" and
                        activation == "DEATHRATTLE" and effect["min_cost"] == 7 and effect["amount"] == 1,
                        f"minimum-cost minion draw is limited to Rotheart Dryad in {card_id}")
            elif op == "DRAW_SPELL_MIN_COST":
                require(set(effect) == {"op", "min_cost", "amount"} and card_id == "EDR_571" and
                        activation == "DEATHRATTLE" and effect["min_cost"] == 5 and effect["amount"] == 1,
                        f"minimum-cost spell draw is limited to Fae Trickster in {card_id}")
            elif op == "BUFF_SOURCE_ATTACK_EACH_TURN":
                require(set(effect) == {"op", "enchantment_id"} and card_id == "CORE_GVG_103" and
                        activation == "TURN_START_EACH" and effect["enchantment_id"] == "EX1_162o" and
                        resources.get("EX1_162o", {}).get("type") == "ENCHANTMENT",
                        "attack growth is limited to Micro Machine's existing +1 Attack enchantment")
            elif op == "BUFF_OTHER_MINIONS_ATTACK":
                require(set(effect) == {"op", "enchantment_id"} and card_id == "EDR_816" and
                        activation == "TURN_END" and effect["enchantment_id"] == "EX1_162o" and
                        resources.get("EX1_162o", {}).get("type") == "ENCHANTMENT",
                        "other-minion attack buff is limited to Monstrous Mosquito")
            elif op == "BUFF_OTHER_MINIONS_HEALTH":
                require(set(effect) == {"op", "enchantment_id"} and card_id == "TIME_428" and
                        activation == "TURN_END" and effect["enchantment_id"] == "DRG_057e" and
                        resources.get("DRG_057e", {}).get("type") == "ENCHANTMENT",
                        "other-minion Health buff is limited to Yesterloc")
            elif op == "BUFF_SOURCE_AFTER_HERO_ATTACK":
                require(set(effect) == {"op", "enchantment_id"} and card_id == "CORE_GIL_534" and
                        activation == "AFTER_HERO_ATTACK" and effect["enchantment_id"] == "ICC_210e" and
                        resources.get("ICC_210e", {}).get("type") == "ENCHANTMENT",
                        "after-attack self-buff is limited to Hench-Clan Thug")
            elif op == "BUFF_PALADINS_AFTER_HERO_ATTACK":
                require(set(effect) == {"op", "enchantment_id", "amount"} and card_id == "JAIL_329" and
                        activation == "AFTER_HERO_ATTACK" and effect["enchantment_id"] == "ICC_210e" and
                        effect["amount"] == 2 and resources.get("ICC_210e", {}).get("type") == "ENCHANTMENT",
                        "Paladin attack buff is limited to Truth Seeker")
            elif op == "BUFF_FRIENDLY_ELEMENTALS":
                require(set(effect) == {"op", "enchantment_id"} and card_id == "DINO_406" and
                        activation == "SPELL_PLAY" and effect["enchantment_id"] == "ICC_210e" and
                        resources.get("ICC_210e", {}).get("type") == "ENCHANTMENT",
                        "Elemental buff is limited to Fire Breath")
            elif op == "HEAL":
                require(set(effect) == {"op", "target", "amount"} and effect["target"] in TARGETS and
                        isinstance(effect["amount"], int) and 1 <= effect["amount"] <= 30,
                        f"invalid HEAL parameters in {card_id}")
            elif op == "SET_TAG":
                require(set(effect) == {"op", "target", "tag", "value"}, f"invalid SET_TAG fields in {card_id}")
                require(effect["target"] in {"TARGET", "SOURCE", "HERO"} and effect["tag"] in TAGS and effect["value"] in (0, 1), f"unreviewed tag setting in {card_id}")
                if effect["tag"] == "DIVINE_SHIELD":
                    require((effect["target"] == "SOURCE" and activation == "AFTER_CAST") or
                            (effect["target"] == "HERO" and activation == "BATTLECRY" and card_id == "TIME_015") or
                            (effect["target"] == "HERO" and activation == "TURN_END" and card_id == "EDR_942"),
                            f"DIVINE_SHIELD selector/activation is outside a reviewed case in {card_id}")
                elif effect["tag"] == "REBORN":
                    require(effect["target"] == "TARGET", f"REBORN can only be set on the selected target in {card_id}")
                else:
                    require(card_id == "DINO_419" and activation == "BATTLECRY" and
                            effect["target"] == "TARGET" and effect["value"] == 1 and
                            "REQ_TARGET_WITH_RACE" in reqs,
                            "RUSH can only be granted to the selected Beast by Herbivore Assistant")
            elif op == "SILENCE":
                require(set(effect) == {"op", "target"} and effect["target"] == "TARGET", f"invalid SILENCE parameters in {card_id}")
            elif op == "FREEZE":
                require(set(effect) == {"op", "target"} and effect["target"] in {"TARGET", "SOURCE"}, f"invalid FREEZE parameters in {card_id}")
            elif op == "SUMMON":
                require(set(effect) == {"op", "card_id", "amount"} and effect["card_id"] in dependencies,
                        f"invalid or undeclared SUMMON dependency in {card_id}")
                require((resources.get(effect["card_id"]) or catalog.get(effect["card_id"], {})).get("type") == "MINION" and
                        isinstance(effect["amount"], int) and 1 <= effect["amount"] <= 7,
                        f"invalid SUMMON parameters in {card_id}")
            elif op == "SUMMON_ANIMAL_COMPANIONS":
                require(set(effect) == {"op", "card_ids"} and card_id == "CORE_OG_211" and
                        activation == "SPELL_PLAY" and effect["card_ids"] == ["NEW1_032", "NEW1_033", "NEW1_034"] and
                        all((resources.get(value) or catalog.get(value, {})).get("type") == "MINION" for value in effect["card_ids"]),
                        "SUMMON_ANIMAL_COMPANIONS is limited to Call of the Wild's three fixed dependencies")
            elif op == "EQUIP":
                require(set(effect) == {"op", "card_id"} and effect["card_id"] in dependencies and
                        resources.get(effect["card_id"], {}).get("type") == "WEAPON",
                        f"invalid or undeclared EQUIP dependency in {card_id}")
            elif op == "ADD_TO_HAND":
                require(set(effect) == {"op", "card_id", "amount"} and effect["card_id"] in dependencies and
                        (resources.get(effect["card_id"]) or catalog.get(effect["card_id"], {})).get("type") == "SPELL" and
                        isinstance(effect["amount"], int) and 1 <= effect["amount"] <= 10,
                        f"invalid or undeclared ADD_TO_HAND dependency in {card_id}")
            elif op == "ARMOR_DAMAGE":
                require(set(effect) == {"op", "target"} and effect["target"] == "TARGET" and
                        activation == "SPELL_PLAY" and "REQ_TARGET_TO_PLAY" in reqs and
                        "REQ_MINION_TARGET" in reqs and "REQ_ENEMY_TARGET" in reqs,
                        f"ARMOR_DAMAGE is limited to targeted enemy-minion spells in {card_id}")
            elif op == "RANDOM_SPLIT_DAMAGE":
                require(set(effect) == {"op", "amount"} and effect["amount"] == 2 and
                        activation == "DEATHRATTLE",
                        f"RANDOM_SPLIT_DAMAGE is limited to the reviewed two-ping Deathrattle in {card_id}")
            elif op == "RANDOM_DESTROY_ENEMY_MINION":
                require(set(effect) == {"op"} and card_id == "CORE_ICC_214" and activation == "DEATHRATTLE",
                        f"RANDOM_DESTROY_ENEMY_MINION is limited to Obsidian Statue in {card_id}")
            elif op == "DESTROY_ALL_MINIONS":
                require(set(effect) == {"op"} and card_id == "TLC_EVENT_402" and activation == "DEATHRATTLE",
                        f"DESTROY_ALL_MINIONS is limited to Staff of the Endbringer in {card_id}")
            elif op == "RETURN_ENEMY_MINIONS":
                require(set(effect) == {"op"} and card_id == "CATA_201" and activation == "BATTLECRY",
                        f"RETURN_ENEMY_MINIONS is limited to Twilight Mistress in {card_id}")
            elif op == "REFRESH_HERO_POWER":
                require(set(effect) == {"op"} and card_id == "JAIL_441" and activation == "SPELL_PLAY",
                        f"REFRESH_HERO_POWER is limited to Drink Blood in {card_id}")
            elif op == "DESTROY_LEGENDARY_TARGET":
                require(set(effect) == {"op"} and card_id == "CATA_203" and activation == "SPELL_PLAY" and
                        {"REQ_TARGET_TO_PLAY", "REQ_MINION_TARGET", "REQ_LEGENDARY_TARGET"} <= set(reqs),
                        f"DESTROY_LEGENDARY_TARGET is limited to Garona's Last Stand in {card_id}")
            elif op == "DAMAGE_THEN_TARGET_OWNER_DRAWS":
                require(set(effect) == {"op", "amount", "spell_damage"} and card_id == "FIR_954" and
                        activation == "SPELL_PLAY" and effect["amount"] == 5 and effect["spell_damage"] is True and
                        {"REQ_TARGET_TO_PLAY", "REQ_MINION_TARGET"} <= set(reqs),
                        f"damage-and-owner-draw is limited to Conflagrate in {card_id}")
            elif op == "RANDOM_OTHER_FRIENDLY_BUFF":
                if card_id == "CORE_ICC_210":
                    require(set(effect) == {"op", "enchantment_id"} and activation == "TURN_END" and
                            effect.get("enchantment_id") == "ICC_210e",
                            "RANDOM_OTHER_FRIENDLY_BUFF is limited to Shadow Ascendant's audited contract")
                elif card_id == "EDR_889":
                    require(set(effect) == {"op", "enchantment_id", "race"} and activation == "TURN_END" and
                            effect.get("enchantment_id") == "ICC_210e" and effect.get("race") == "DRAGON",
                            "RANDOM_OTHER_FRIENDLY_BUFF is limited to Petal Peddler's Dragon selector")
                else:
                    raise ValueError(f"RANDOM_OTHER_FRIENDLY_BUFF is not allowlisted for {card_id}")
                require(resources.get("ICC_210e", {}).get("type") == "ENCHANTMENT",
                        f"missing reviewed +1/+1 enchantment in {card_id}")
            elif op == "RANDOM_FRIENDLY_ATTACK_BUFF":
                require(set(effect) == {"op", "enchantment_id"} and card_id == "CATA_467" and
                        activation == "AFTER_HERO_ATTACK" and effect["enchantment_id"] == "CATA_467e",
                        "RANDOM_FRIENDLY_ATTACK_BUFF is limited to Command Claw's post-attack trigger")
            elif op == "OPPONENT_HERO_POWER_SET_COST":
                require(set(effect) == {"op", "cost", "enchantment_id"} and card_id == "CORE_DRG_403" and
                        activation == "BATTLECRY" and effect["cost"] == 2 and
                        effect["enchantment_id"] == "CORE_DRG_403e",
                        "OPPONENT_HERO_POWER_SET_COST is limited to the audited current CORE version of Blowtorch Saboteur")
            elif op == "INCREASE_SOURCE_HEALTH_IF_UNDAMAGED":
                require(set(effect) == {"op", "enchantment_id"} and card_id == "CATA_305" and
                        activation == "TURN_END" and effect["enchantment_id"] == "CATA_305e",
                        "INCREASE_SOURCE_HEALTH_IF_UNDAMAGED is limited to Incensed Matriarch")
            elif op == "BUFF_HAND_MINIONS":
                require(set(effect) == {"op", "enchantment_id"} and
                        ((card_id == "TIME_100" and activation == "TURN_END") or
                         (card_id == "CORE_CFM_753" and activation == "BATTLECRY")) and
                        effect["enchantment_id"] == "ICC_210e" and
                        resources.get("ICC_210e", {}).get("type") == "ENCHANTMENT",
                        "BUFF_HAND_MINIONS is limited to the reviewed +1/+1 hand-buff cases")
            elif op == "BUFF_HAND_TAUNT_MINIONS":
                require(set(effect) == {"op", "enchantment_id"} and card_id == "CORE_WW_329" and
                        activation == "BATTLECRY" and effect["enchantment_id"] == "CORE_WW_329e",
                        "BUFF_HAND_TAUNT_MINIONS is limited to the reviewed Taunt-only hand buff")
            elif op == "DRAW_MINION_AND_BUFF_HAND_HEALTH":
                require(set(effect) == {"op", "enchantment_id"} and card_id == "TIME_037" and
                        activation == "BATTLECRY" and effect["enchantment_id"] == "TIME_037e",
                        "DRAW_MINION_AND_BUFF_HAND_HEALTH is limited to Disciple of the Dove")
            elif op == "BUFF_HAND_MINIONS_AND_LEGENDARIES":
                require(set(effect) == {"op", "base_enchantment_id", "legendary_enchantment_id"} and
                        card_id == "JAIL_387" and activation == "SPELL_PLAY" and
                        effect["base_enchantment_id"] == "ICC_210e" and
                        effect["legendary_enchantment_id"] == "JAIL_387e",
                        "BUFF_HAND_MINIONS_AND_LEGENDARIES is limited to Release the Beasts")
            elif op == "BUFF_BEASTS_ALL_ZONES":
                require(set(effect) == {"op", "enchantment_id"} and card_id == "TLC_828" and
                        activation == "SPELL_PLAY" and effect["enchantment_id"] == "TLC_828e",
                        "BUFF_BEASTS_ALL_ZONES is limited to Supreme Dinomancy")
            elif op == "BUFF_HAND_MINIONS_AND_WEAPONS_ATTACK":
                require(set(effect) == {"op", "enchantment_id"} and card_id == "END_021" and
                        activation == "BATTLECRY" and effect["enchantment_id"] == "END_021e",
                        "BUFF_HAND_MINIONS_AND_WEAPONS_ATTACK is limited to Dimensional Weaponsmith")
            elif op == "RANDOM_FRIENDLY_BEAST_HAND_BUFF":
                require(set(effect) == {"op", "enchantment_id"} and card_id == "MEND_305" and
                        activation == "SPELL_PLAY" and effect["enchantment_id"] == "MEND_305e" and
                        {"REQ_TARGET_TO_PLAY", "REQ_MINION_TARGET", "REQ_FRIENDLY_TARGET"} <= set(reqs),
                        "RANDOM_FRIENDLY_BEAST_HAND_BUFF is limited to Nurturing Nature")
            elif op == "BOTH_PLAYERS_GAIN_EMPTY_CRYSTAL":
                require(set(effect) == {"op"} and card_id == "EDR_861" and activation == "DEATHRATTLE",
                        "BOTH_PLAYERS_GAIN_EMPTY_CRYSTAL is limited to Tranquil Treant")
            elif op == "DESTROY_TOP_THREE_OWN_DECK":
                require(set(effect) == {"op"} and card_id == "TLC_621" and activation == "DEATHRATTLE",
                        "DESTROY_TOP_THREE_OWN_DECK is limited to Willful Watcher")
            elif op == "RANDOM_OTHER_DAMAGED_FRIENDLY_MINION_BUFF":
                require(set(effect) == {"op", "enchantment_id"} and card_id == "TLC_623" and
                        activation == "TURN_END" and effect["enchantment_id"] == "TLC_623e",
                        "RANDOM_OTHER_DAMAGED_FRIENDLY_MINION_BUFF is limited to the reviewed end-turn trigger")
            elif op == "BUFF_ALL_SPELLS_HAND_DECK_SPELLPOWER":
                require(set(effect) == {"op", "enchantment_id"} and card_id == "CATA_458" and
                        activation == "BATTLECRY" and effect["enchantment_id"] == "CATA_458e",
                        "BUFF_ALL_SPELLS_HAND_DECK_SPELLPOWER is limited to Archmage Kalec")
            elif op == "DRAW_ANOTHER_IF_FIRST_COST_AT_MOST_2":
                require(set(effect) == {"op"} and card_id == "JAIL_377" and activation == "SPELL_PLAY",
                        "DRAW_ANOTHER_IF_FIRST_COST_AT_MOST_2 is limited to Holy Bola!")
            elif op == "DRAW_IF_DECK_HAS_AT_LEAST_25":
                require(set(effect) == {"op"} and card_id == "JAIL_456" and activation == "BATTLECRY",
                        "DRAW_IF_DECK_HAS_AT_LEAST_25 is limited to P1CK-P0K3T")
            elif op == "IF_TARGET_DIES":
                expected = {
                    "CATA_303": ("SPELL_PLAY", "HEAL_ENEMY_HERO_5"),
                    "END_014": ("SPELL_PLAY", "BUFF_RANDOM_FRIENDLY_3_3"),
                    "TLC_606": ("BATTLECRY", "GAIN_ARMOR_5"),
                }
                require(set(effect) == {"op", "outcome"} and card_id in expected and
                        (activation, effect["outcome"]) == expected[card_id] and
                        any(prior["op"] == "DAMAGE" and prior["target"] == "TARGET"
                            for prior in normalized_effects),
                        f"IF_TARGET_DIES must follow target damage in a reviewed card-specific outcome: {card_id}")
                if card_id == "END_014":
                    require("END_014e" in dependencies, "Synchronized Spark must declare its buff enchantment")
            elif op == "BUFF_DAMAGED_FRIENDLY_MINIONS":
                require(set(effect) == {"op", "enchantment_id"} and card_id == "JAIL_376" and
                        activation == "DEATHRATTLE" and effect["enchantment_id"] == "JAIL_376e",
                        "BUFF_DAMAGED_FRIENDLY_MINIONS is limited to Ball and Chain")
            elif op == "DRAW_BEAST":
                require(set(effect) == {"op", "amount"} and card_id == "EDR_226" and
                        activation == "DEATHRATTLE" and effect["amount"] == 1,
                        "DRAW_BEAST is limited to Beastly Beauty's one-Beast Deathrattle")
            elif op == "DRAW_TWO_AND_CHARGE_IF_BOTH_MINIONS":
                require(set(effect) == {"op"} and card_id == "JAIL_462" and activation == "BATTLECRY",
                        "DRAW_TWO_AND_CHARGE_IF_BOTH_MINIONS is limited to Getaway Hogdriver")
            elif op == "DRAW_TWO_DRAGONS_REDUCE_COST":
                require(set(effect) == {"op", "enchantment_id"} and card_id == "EDR_572" and
                        activation == "DEATHRATTLE" and effect["enchantment_id"] == "EDR_572e" and
                        "EDR_572e" in dependencies,
                        "DRAW_TWO_DRAGONS_REDUCE_COST is limited to Tormented Dreadwing")
            elif op == "RANDOM_FRIENDLY_KEYWORDS":
                require(set(effect) == {"op", "tags"} and card_id == "CORE_GVG_059" and
                        activation == "BATTLECRY" and effect["tags"] == ["DIVINE_SHIELD", "TAUNT"],
                        "RANDOM_FRIENDLY_KEYWORDS is limited to Coghammer's audited Battlecry")
            elif op == "RANDOM_DAMAGE":
                require(set(effect) == {"op", "target", "amount", "hits", "spell_damage"} and
                        effect["target"] in {"ENEMIES", "ENEMY_MINIONS"} and
                        isinstance(effect["amount"], int) and 1 <= effect["amount"] <= 30 and
                        isinstance(effect["hits"], int) and 1 <= effect["hits"] <= 10 and
                        isinstance(effect["spell_damage"], bool) and
                        (activation in {"SPELL_PLAY", "TURN_END", "DEATHRATTLE", "AFTER_CAST"} or
                         (card_id == "RLK_223" and activation == "BATTLECRY_AND_DEATHRATTLE" and
                          effect["target"] == "ENEMIES" and effect["amount"] == 2 and effect["hits"] == 1 and
                          effect["spell_damage"] is False)),
                        f"invalid repeated random damage parameters in {card_id}")
            else:
                raise ValueError(f"unsupported operation {op!r} in {card_id}")
            normalized_effects.append(effect)
        referenced_dependencies = {effect["id"] for effect in normalized_effects if effect["op"] == "ENCHANT"}
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] == "RANDOM_OTHER_FRIENDLY_BUFF")
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] == "RANDOM_FRIENDLY_ATTACK_BUFF")
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] == "OPPONENT_HERO_POWER_SET_COST")
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] == "INCREASE_SOURCE_HEALTH_IF_UNDAMAGED")
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] == "BUFF_HAND_MINIONS")
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] == "BUFF_HAND_TAUNT_MINIONS")
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] == "DRAW_MINION_AND_BUFF_HAND_HEALTH")
        referenced_dependencies.update(effect["base_enchantment_id"] for effect in normalized_effects if effect["op"] == "BUFF_HAND_MINIONS_AND_LEGENDARIES")
        referenced_dependencies.update(effect["legendary_enchantment_id"] for effect in normalized_effects if effect["op"] == "BUFF_HAND_MINIONS_AND_LEGENDARIES")
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] == "BUFF_BEASTS_ALL_ZONES")
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] in {"BUFF_HAND_MINIONS_AND_WEAPONS_ATTACK", "RANDOM_FRIENDLY_BEAST_HAND_BUFF"})
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] == "RANDOM_OTHER_DAMAGED_FRIENDLY_MINION_BUFF")
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] == "BUFF_ALL_SPELLS_HAND_DECK_SPELLPOWER")
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] in {"BUFF_DAMAGED_FRIENDLY_MINIONS", "DRAW_TWO_DRAGONS_REDUCE_COST"})
        if card_id == "END_014":
            referenced_dependencies.update("END_014e" for effect in normalized_effects if effect["op"] == "IF_TARGET_DIES" and effect["outcome"] == "BUFF_RANDOM_FRIENDLY_3_3")
        referenced_dependencies.update(effect["card_id"] for effect in normalized_effects if effect["op"] in {"SUMMON", "EQUIP"})
        referenced_dependencies.update(value for effect in normalized_effects if effect["op"] == "SUMMON_ANIMAL_COMPANIONS" for value in effect["card_ids"])
        referenced_dependencies.update(effect["card_id"] for effect in normalized_effects if effect["op"] == "ADD_TO_HAND")
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] == "BUFF_SOURCE_ATTACK_EACH_TURN")
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] == "BUFF_OTHER_MINIONS_ATTACK")
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] == "BUFF_OTHER_MINIONS_HEALTH")
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] == "BUFF_SOURCE_AFTER_HERO_ATTACK")
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] == "BUFF_PALADINS_AFTER_HERO_ATTACK")
        referenced_dependencies.update(effect["enchantment_id"] for effect in normalized_effects if effect["op"] == "BUFF_FRIENDLY_ELEMENTALS")
        require(referenced_dependencies == set(dependencies), f"dependency list must exactly match effect references: {card_id}")
        for index, effect in enumerate(normalized_effects):
            if effect["op"] == "ARMOR_DAMAGE":
                require(any(prior["op"] == "ARMOR" for prior in normalized_effects[:index]),
                        f"ARMOR_DAMAGE must follow an explicit ARMOR effect in {card_id}")
        validated.append({"card_id": card_id, "name": card.get("name"), "activation": activation,
                          "rules_text_sha256": hashlib.sha256(norm_text(card.get("text", "")).encode()).hexdigest(),
                          "play_requirements": reqs, "dependencies": dependencies, "effects": normalized_effects,
                          "training_eligible": False})
    require(seen == ALLOWLIST, "declaration is missing allowlisted cards")
    return validated, catalog_hash


