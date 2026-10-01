"""Run focused registry and bridge smoke checks for the metadata-only batch."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from manamind.integrations.rosettastone.rosettastone import SimulatorSession, make_simple_test_deck, validate_deck  # noqa: E402

CARDS = ("Core_CS2_200", "TIME_053", "TLC_248")
UNIT_TESTS = ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"


def main() -> None:
    if not UNIT_TESTS.exists():
        raise RuntimeError("Build the UnitTests target before verification")
    result = subprocess.run([str(UNIT_TESTS), "--test-case=[ManaMind metadata-only cards]*"],
                            cwd=ROOT / "vendor/RosettaStone", check=True, capture_output=True, text=True)
    print(result.stdout, end="")
    catalog = {card["id"]: card for card in json.loads(
        (ROOT / "data/cards/standard_current_enUS.json").read_text(encoding="utf-8"))["cards"]}
    for card_id in CARDS:
        player_class = catalog[card_id]["cardClass"]
        if player_class == "NEUTRAL":
            player_class = "MAGE"
        deck = make_simple_test_deck(player_class=player_class)
        deck[0] = card_id
        errors = validate_deck(deck, player_class=player_class)
        if errors:
            raise AssertionError(f"{card_id}: Standard deck validation failed: {errors}")
        game = SimulatorSession(deck, make_simple_test_deck(player_class="MAGE"),
                                player1_class=player_class, player2_class="MAGE", shuffle=False, random_seed=59)
        observation = game.observation("PLAYER1")
        if card_id not in {card.card_id for card in observation.self_hand}:
            raise AssertionError(f"{card_id}: not visible in the opening hand")
        actions = game.legal_actions()
        if not actions:
            raise AssertionError(f"{card_id}: no legal actions available")
        print(f"PASS {card_id}: Standard deck, session, opening hand, {len(actions)} legal actions")


if __name__ == "__main__":
    main()
