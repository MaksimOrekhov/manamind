"""Record scoped native/bridge verification for Royal Librarian."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from manamind.integrations.rosettastone.policy import (  # noqa: E402
    ACTION_FEATURE_NAMES,
    encode_legal_actions,
)
from manamind.integrations.rosettastone.rosettastone import (  # noqa: E402
    SimulatorSession,
    make_simple_test_deck,
    validate_decks,
)
from scripts.verification_evidence import record_execution  # noqa: E402

PROFILE = ROOT / "configs/training_profiles/meta_training_20261002_v1.json"
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
EVIDENCE = ROOT / "integrations/rosettastone/card_rules/profile_verification_harvest_20261003_v2.evidence.json"
UNIT_TESTS = ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"
ROSETTA = ROOT / "vendor/RosettaStone"
CARD_ID = "CORE_SW_066"
NATIVE_FILTERS = [
    "[Neutral : Minion] - SW_066 : Royal Librarian",
    "[ManaMind effect composition] - CORE_SW_066 silences the selected minion",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def start_bridge_game() -> SimulatorSession:
    player = make_simple_test_deck(player_class="WARRIOR")
    player[0] = CARD_ID
    opponent = make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        player, opponent, player1_class="WARRIOR", player2_class="WARRIOR"
    )
    if errors:
        raise AssertionError(f"Royal Librarian bridge deck invalid: {errors}")
    return SimulatorSession(
        player, opponent, player1_class="WARRIOR", player2_class="WARRIOR",
        shuffle=False, random_seed=20261003,
    )


def verify_royal_librarian_bridge() -> dict[str, str]:
    trade_game = start_bridge_game()
    trade_actions = [
        action for action in trade_game.legal_actions()
        if action["type"] == "TRADE_CARD" and action.get("card_id") == CARD_ID
    ]
    if len(trade_actions) != 1:
        raise AssertionError("Expected exactly one Royal Librarian Tradeable action")
    encoded = encode_legal_actions(trade_actions)
    trade_feature = ACTION_FEATURE_NAMES.index("trade_card")
    if encoded.shape != (1, len(ACTION_FEATURE_NAMES)) or encoded[0, trade_feature] != 1.0:
        raise AssertionError("Tradeable action did not preserve bridge action encoding")
    hand_size = trade_game.observation("PLAYER1").self_player.hand_size
    trade_game.apply_action(trade_actions[0])
    if trade_game.observation("PLAYER1").self_player.hand_size != hand_size:
        raise AssertionError("Trade should exchange one hand card for one replacement")

    game = start_bridge_game()
    worgen = next(
        (action for action in game.legal_actions()
         if action["type"] == "PLAY_CARD" and action.get("card_id") == "CORE_EX1_010"),
        None,
    )
    if worgen is None:
        raise AssertionError("Expected supported Worgen Infiltrator in deterministic opening hand")
    game.apply_action(worgen)
    while game.observation("PLAYER1").turn_number < 4 or game.observation("PLAYER1").active_player != "SELF":
        end_turn = next(
            (action for action in game.legal_actions() if action["type"] == "END_TURN"),
            None,
        )
        if end_turn is None:
            raise AssertionError("Could not advance the deterministic bridge game to turn four")
        game.apply_action(end_turn)
    silence = next(
        (action for action in game.legal_actions()
         if action["type"] == "PLAY_CARD" and action.get("card_id") == CARD_ID
         and action.get("target_is_self")),
        None,
    )
    if silence is None:
        raise AssertionError("Royal Librarian should expose a legal friendly target on turn four")
    game.apply_action(silence)
    board = game.observation("PLAYER1").self_player.board
    target = next((minion for minion in board if minion.card.card_id == "CORE_EX1_010"), None)
    if target is None or not target.silenced:
        raise AssertionError("Royal Librarian did not silence the selected Worgen")
    return {
        "trade_action_and_encoded_feature": "PASS",
        "trade_replacement_preserves_hand_size": "PASS",
        "friendly_target_legal": "PASS",
        "selected_target_silenced": "PASS",
    }


def main() -> None:
    native_outputs: list[str] = []
    for test_filter in NATIVE_FILTERS:
        result = subprocess.run(
            [str(UNIT_TESTS), f"--test-case={test_filter}"],
            cwd=ROSETTA, capture_output=True, text=True, errors="replace", check=False,
        )
        output = result.stdout + result.stderr
        print(output, end="")
        if result.returncode or "Status: SUCCESS!" not in output:
            raise RuntimeError(f"Native verification failed for {test_filter}")
        native_outputs.append(output)

    bridge_result = verify_royal_librarian_bridge()
    bridge = {
        "deterministic_bridge_scenario": "verify_royal_librarian_bridge",
        **bridge_result,
    }

    catalog_cards = json.loads(CATALOG.read_text(encoding="utf-8"))["cards"]
    card = next(item for item in catalog_cards if item["id"] == CARD_ID)
    source = ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/CoreCardsGen.cpp"
    composition_source = ROOT / "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindEffectCompositionTests.cpp"
    profile_hash = canonical_hash(json.loads(PROFILE.read_text(encoding="utf-8")))
    source_hash = sha256(source)
    evidence_row = {
        "status": "VERIFIED_SCOPED",
        "scope": "Root-specific native CardDef/composition scenarios plus existing configured bridge scenario for Tradeable replacement and targeted Silence. No dependency closure, full-deck readiness or training admission claim.",
        "training_scope": "SCOPED_PACKAGE_ONLY",
        "profile_manifest_sha256": profile_hash,
        "rules_fingerprint": canonical_hash({
            "card": card,
            "card_source_sha256": source_hash,
            "native_source_sha256": sha256(composition_source),
            "dependencies": [],
        }),
        "pool_membership_sha256": canonical_hash("NO_DYNAMIC_OUTCOME_POOL_ROYAL_LIBRARIAN_V1"),
        "pool_predicate_version": "NO_DYNAMIC_OUTCOME_POOL_ROYAL_LIBRARIAN_V1",
        "capability_fingerprint": source_hash,
        "scenario_fingerprint": canonical_hash({
            "native_outputs": native_outputs,
            "bridge_result": bridge,
            "verifier_sha256": sha256(Path(__file__)),
        }),
        "bridge_action_status": "VERIFIED_SCOPED",
        "native_test": NATIVE_FILTERS,
        "bridge_result": bridge,
        "dependency_review": {
            "scope": "ROOT_EFFECT_AND_TRADEABLE_ACTION_REVIEWED",
            "reviewed_static_dependencies": [],
            "dynamic_pools": [],
        },
        "training_eligible": False,
    }
    existing = json.loads(EVIDENCE.read_text(encoding="utf-8")) if EVIDENCE.exists() else {}
    evidence = {
        **existing,
        "cards": {**existing.get("cards", {}), CARD_ID: evidence_row},
        "package_results": {
            **existing.get("package_results", {}),
            "royal_librarian_trade_silence_verification_v1": {
                "verified_roots": [CARD_ID],
                "native_outputs": native_outputs,
                "bridge_outputs": bridge,
                "static_dependencies": [],
                "dependency_closure_gained": 0,
                "training_eligible": False,
            },
        },
        "training_eligible": False,
    }
    EVIDENCE.write_text(
        json.dumps(record_execution(evidence), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"PASS: explicit scoped evidence written to {EVIDENCE}")


if __name__ == "__main__":
    main()
