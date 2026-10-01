"""Run focused native scenarios and bridge load smoke for effect-composition cards."""
from __future__ import annotations
import subprocess
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from manamind.integrations.rosettastone.rosettastone import SimulatorSession, make_simple_test_deck, validate_deck

CARDS = (
    ("CORE_UNG_084", "MAGE"),
    ("CORE_OG_149", "WARRIOR"),
    ("CORE_CS2_024", "MAGE"),
    ("CORE_CS2_094", "PALADIN"),
    ("CORE_EX1_129", "ROGUE"),
    ("CORE_TSC_076", "PALADIN"),
    ("CORE_GVG_061", "PALADIN"),
    ("CORE_BOT_222", "WARLOCK"),
    ("CORE_BOT_451", "SHAMAN"),
    ("CORE_RLK_062", "DEATHKNIGHT"),
    ("CORE_LOOT_013", "WARLOCK"),
    ("RLK_024", "DEATHKNIGHT"),
    ("CORE_LOOT_368", "WARLOCK"),
    ("CORE_OG_031", "SHAMAN"),
    ("FIR_778", "SHAMAN"),
    ("JAIL_007", "MAGE"),
    ("CATA_475", "PALADIN"),
    ("EDR_459", "WARRIOR"),
    ("CATA_304", "PRIEST"),
    ("CORE_CFM_604", "PRIEST"),
    ("EDR_476", "PRIEST"),
    ("EDR_971", "MAGE"),
    ("RLK_709", "DEATHKNIGHT"),
    ("CATA_612", "MAGE"),
    ("TIME_218", "SHAMAN"),
    ("TIME_215", "SHAMAN"),
    ("TLC_620", "WARRIOR"),
    ("TLC_225", "SHAMAN"),
    ("TLC_249", "SHAMAN"),
    ("FIR_909", "HUNTER"),
    ("CORE_YOP_034", "WARRIOR"),
    ("EDR_110", "WARRIOR"),
    ("CATA_485", "MAGE"),
    ("DINO_132", "WARLOCK"),
    ("CORE_RLK_083", "DEATHKNIGHT"),
    ("END_026", "WARLOCK"),
    ("TLC_256", "SHAMAN"),
    ("TIME_015", "PALADIN"),
    ("TLC_401", "DEATHKNIGHT"),
    ("RLK_223", "DEATHKNIGHT"),
)
ADDED_BATCH_IDS = (
    "CORE_EX1_250", "CORE_ICC_210", "CORE_AT_062", "EDR_942", "TIME_100",
    "EDR_889", "CORE_GVG_059", "CORE_EX1_002", "CORE_ICC_214", "TLC_EVENT_402",
    "CORE_KAR_061", "CORE_GVG_103", "EDR_816", "TIME_428", "CORE_OG_211",
    "CORE_GIL_534", "JAIL_329", "TIME_212", "DINO_406", "CATA_201",
    "JAIL_441", "CATA_203", "EDR_485", "EDR_571", "FIR_954",
    "CATA_467", "CORE_DRG_403", "CATA_305", "CORE_CFM_753", "CORE_WW_329",
    "TIME_037", "JAIL_387", "TLC_828", "END_021", "MEND_305",
    "DINO_419", "EDR_861", "TLC_621", "TLC_623", "CATA_458",
    "JAIL_377", "JAIL_456", "CATA_303", "END_014", "TLC_606",
    "EDR_468", "JAIL_376", "JAIL_462", "EDR_572", "TLC_633",
)
catalog = json.loads((ROOT / "data/cards/standard_current_enUS.json").read_text(encoding="utf-8"))["cards"]
# Match RosettaStone's CardLoader default for neutral cards whose metadata omits
# cardClass, such as cards whose class is implied by their set/card text.
classes = {card["id"]: card.get("cardClass", "NEUTRAL") for card in catalog}
missing = set(ADDED_BATCH_IDS) - set(classes)
if missing:
    raise RuntimeError(f"batch cards missing from pinned catalog: {sorted(missing)}")
CARDS += tuple(
    (card_id, classes[card_id] if classes[card_id] != "NEUTRAL" else "MAGE")
    for card_id in ADDED_BATCH_IDS
)
UNIT_TESTS = ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"
ENGINE = ROOT / "vendor/RosettaStone/build-mana-py312/lib/RosettaStone.lib"

def main() -> None:
    if not UNIT_TESTS.exists() or not ENGINE.exists():
        raise RuntimeError("Build the UnitTests target before verification")
    result = subprocess.run([str(UNIT_TESTS), "--test-case=[ManaMind effect composition]*"],
                            cwd=ROOT / "vendor/RosettaStone", check=True, capture_output=True, text=True)
    print(result.stdout, end="")
    for card_id, player_class in CARDS:
        deck = make_simple_test_deck(player_class=player_class)
        index = next((i for i, value in enumerate(deck) if value == card_id), None)
        if index is None:
            deck[0] = card_id
        else:
            deck[0], deck[index] = deck[index], deck[0]
        errors = validate_deck(deck, player_class=player_class)
        if errors:
            raise AssertionError(f"{card_id}: deck validation failed: {errors}")
        if player_class == "DEATHKNIGHT":
            print(f"PASS {card_id}: Standard deck validation; DK session setup remains unsupported")
            continue
        game = SimulatorSession(deck, make_simple_test_deck(player_class="MAGE"),
                                player1_class=player_class, player2_class="MAGE", shuffle=False, random_seed=47)
        state = game.observation("PLAYER1")
        if card_id not in {card.card_id for card in state.self_hand} or not game.legal_actions():
            raise AssertionError(f"{card_id}: missing from opening hand or legal actions unavailable")
        print(f"PASS {card_id}: Standard deck, session, opening hand, legal actions")

if __name__ == "__main__":
    main()
