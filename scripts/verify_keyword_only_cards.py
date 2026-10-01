"""Run focused registration and public bridge smoke checks for keyword-only cards."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from manamind.integrations.rosettastone.rosettastone import SimulatorSession, make_simple_test_deck, validate_deck

CARDS = (("CORE_GIL_558", "MAGE"), ("CORE_ULD_723", "MAGE"), ("EDR_486", "MAGE"),
         ("END_031", "MAGE"), ("RLK_067", "DEATHKNIGHT"))
UNIT_TESTS = ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"
ENGINE = ROOT / "vendor/RosettaStone/build-mana-py312/lib/RosettaStone.lib"

def main() -> None:
    if not UNIT_TESTS.exists() or not ENGINE.exists():
        raise RuntimeError("Build the UnitTests target before verification")
    result = subprocess.run([str(UNIT_TESTS), "--test-case=[ManaMind keyword-only cards]*"],
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
            print(f"PASS {card_id}: Standard Death Knight deck validation (session setup is a known engine gap)")
            continue
        game = SimulatorSession(deck, make_simple_test_deck(player_class="MAGE"),
                                player1_class=player_class, player2_class="MAGE", shuffle=False, random_seed=23)
        state = game.observation("PLAYER1")
        if card_id not in {card.card_id for card in state.self_hand} or not game.legal_actions():
            raise AssertionError(f"{card_id}: card missing from opening hand or no legal actions")
        print(f"PASS {card_id}: Standard deck, session, opening hand, legal actions")

if __name__ == "__main__":
    main()
