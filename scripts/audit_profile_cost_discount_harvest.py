"""Verify existing Prep/Felscreamer cost effects in native and bridge runs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from manamind.integrations.rosettastone.rosettastone import (  # noqa: E402
    SimulatorSession,
    make_simple_test_deck,
    validate_decks,
)
from scripts.verification_evidence import record_execution  # noqa: E402

PROFILE_PATH = ROOT / "configs/training_profiles/meta_training_20261002_v1.json"
CATALOG_PATH = ROOT / "data/cards/standard_current_enUS.json"
UNIT_TESTS = ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"
EVIDENCE_PATH = ROOT / "integrations/rosettastone/card_rules/profile_verification_harvest_20261003_v2.evidence.json"
PACKAGE_ID = "cost_discount_expiry_verification_v1"
CASES = {
    "CORE_EX1_145": {
        "native_filter": "[Rogue : Spell] - CORE_EX1_145 : Preparation",
        "dependency": "EX1_145o",
        "expectation": "Spells in hand cost 2 less after Preparation; the next spell cast consumes the aura, and turn end expires it.",
    },
    "CORE_BT_416": {
        "native_filter": "[Demon Hunter : Minion] - CORE_BT_416 : Raging Felscreamer",
        "dependency": "BT_416e",
        "expectation": "Demon minions in hand cost 2 less after the Battlecry; the first Demon minion played consumes the aura, non-Demons are unaffected.",
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_session(player_class: str, top_cards: list[str]) -> SimulatorSession:
    player_deck = make_simple_test_deck(player_class=player_class)
    for index, card_id in enumerate(top_cards):
        player_deck[index] = card_id
    enemy_deck = make_simple_test_deck(player_class="WARRIOR")
    errors = validate_decks(
        player_deck, enemy_deck,
        player1_class=player_class, player2_class="WARRIOR",
    )
    if errors:
        raise AssertionError(f"{player_class} test deck invalid: {errors}")
    return SimulatorSession(
        player_deck, enemy_deck,
        player1_class=player_class, player2_class="WARRIOR",
        shuffle=False, random_seed=20261003,
    )


def end_turn(game: SimulatorSession) -> None:
    action = next((item for item in game.legal_actions() if item["type"] == "END_TURN"), None)
    if action is None:
        raise AssertionError("No END_TURN action while advancing controlled session")
    game.apply_action(action)


def card_costs(game: SimulatorSession, card_id: str) -> list[int]:
    return [card.effective_cost for card in game.observation("PLAYER1").self_hand if card.card_id == card_id]


def card_action(game: SimulatorSession, card_id: str) -> dict | None:
    return next(
        (action for action in game.legal_actions()
         if action.get("type") == "PLAY_CARD" and action.get("card_id") == card_id),
        None,
    )


def verify_preparation() -> dict:
    deck = ["CORE_EX1_145", "CORE_EX1_278", "CORE_EX1_278"]
    game = make_session("ROGUE", deck)
    if not {card.card_id for card in game.observation("PLAYER1").self_hand}.issuperset(set(deck)):
        raise AssertionError("Preparation and both Shiv controls must start in the visible SELF hand")

    preparation = card_action(game, "CORE_EX1_145")
    if preparation is None:
        raise AssertionError("Preparation must be a legal turn-one action")
    game.apply_action(preparation)
    discounted = card_costs(game, "CORE_EX1_278")
    if discounted != [0, 0]:
        raise AssertionError(f"Preparation should reduce both hand spells by 2 before the next cast: {discounted}")
    shiv = card_action(game, "CORE_EX1_278")
    if shiv is None:
        raise AssertionError("Discounted Shiv should be a legal bridge action")
    game.apply_action(shiv)
    remaining = card_costs(game, "CORE_EX1_278")
    if remaining != [2]:
        raise AssertionError(f"Casting the next spell should consume Preparation: {remaining}")
    cast_case = {"deck_validation": "PASS", "visible_self_hand_identity": "PASS", "cost_before": 2,
                 "cost_after_preparation": [0, 0], "first_spell_action": "PASS", "cost_after_first_spell": 2}

    expires = make_session("ROGUE", deck)
    preparation = card_action(expires, "CORE_EX1_145")
    if preparation is None:
        raise AssertionError("Preparation must be legal in the turn-expiry control")
    expires.apply_action(preparation)
    if card_costs(expires, "CORE_EX1_278") != [0, 0]:
        raise AssertionError("Preparation did not discount held Shiv before end of turn")
    end_turn(expires)
    end_turn(expires)
    if expires.observation("PLAYER1").active_player != "SELF":
        end_turn(expires)
    after_expiry = card_costs(expires, "CORE_EX1_278")
    if after_expiry != [2, 2]:
        raise AssertionError(f"Preparation must expire at turn end: {after_expiry}")
    cast_case["turn_end_expiry"] = "PASS"
    return cast_case


def verify_felscreamer() -> dict:
    # Use Battlefiend as the Demon consumer and the already-present CORE_BT_480
    # minion as a non-Demon control (the pinned catalog marks it race=None).
    deck = ["CORE_BT_416", "CORE_BT_351", "CORE_BT_351"]
    game = make_session("DEMONHUNTER", deck)
    if not set(deck).issubset({card.card_id for card in game.observation("PLAYER1").self_hand}):
        raise AssertionError("Felscreamer and both Demon controls must start in the visible SELF hand")

    action = None
    for _ in range(10):
        if game.observation("PLAYER1").active_player == "SELF":
            action = card_action(game, "CORE_BT_416")
            if action is not None:
                break
        end_turn(game)
    if action is None:
        raise AssertionError("Raging Felscreamer did not become a legal action at 4 mana")
    game.apply_action(action)
    battlefiend_cost = card_costs(game, "CORE_BT_351")
    non_demon_cost = card_costs(game, "CORE_BT_480")
    if battlefiend_cost != [0, 0] or non_demon_cost != [1]:
        raise AssertionError(
            f"Felscreamer filter/delta mismatch: Battlefiend={battlefiend_cost}, "
        f"non-Demon CORE_BT_480={non_demon_cost}"
        )
    discounted_demon = card_action(game, "CORE_BT_351")
    if discounted_demon is None:
        raise AssertionError("Discounted Battlefiend should be a legal bridge action")
    game.apply_action(discounted_demon)
    remaining_battlefiends = card_costs(game, "CORE_BT_351")
    if remaining_battlefiends != [1]:
        raise AssertionError(
            "Playing the first Demon should consume the discount: "
            f"Battlefiend={remaining_battlefiends}"
        )
    return {
        "deck_validation": "PASS",
        "visible_self_hand_identity": "PASS",
        "Demon_costs_after_Battlecry": {"CORE_BT_351": battlefiend_cost},
        "non_Demon_CORE_BT_480_cost_unchanged": non_demon_cost,
        "discounted_demon_action": "PASS",
        "remaining_demons_after_first_play": {
            "CORE_BT_351": remaining_battlefiends,
        },
    }


def main() -> None:
    native_outputs: dict[str, str] = {}
    for card_id, row in CASES.items():
        result = subprocess.run(
            [str(UNIT_TESTS), f"--test-case={row['native_filter']}"],
            cwd=ROOT / "vendor/RosettaStone", capture_output=True,
            text=True, errors="replace", check=False,
        )
        output = result.stdout + result.stderr
        print(output, end="")
        if result.returncode or "Status: SUCCESS!" not in output:
            raise RuntimeError(f"Native scenario failed for {card_id}")
        native_outputs[card_id] = output

    bridge = {
        "CORE_EX1_145": verify_preparation(),
        "CORE_BT_416": verify_felscreamer(),
    }
    print("PASS CORE_EX1_145: next spell consumption and turn-end expiry")
    print("PASS CORE_BT_416: Demon-only filter and first-Demon consumption")

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["cards"]
    identity = {
        "CORE_EX1_145": ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/CoreCardsGen.cpp",
        "CORE_BT_416": ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/CoreCardsGen.cpp",
    }
    native_source = ROOT / "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/CoreCardsGenTests.cpp"
    execution_cards = {}
    profile_hash = canonical_hash(json.loads(PROFILE_PATH.read_text(encoding="utf-8")))
    for card_id, row in CASES.items():
        catalog_card = next(card for card in catalog if card["id"] == card_id)
        dependency = row["dependency"]
        rules_fp = canonical_hash({
            "card": catalog_card,
            "source_sha256": sha256(identity[card_id]),
            "native_test_source_sha256": sha256(native_source),
            "dependency_id": dependency,
        })
        execution_cards[card_id] = {
            "status": "VERIFIED_SCOPED",
            "scope": "Root-specific native cost/lifetime scenario plus configured bridge actions checking effective held-card costs, first qualifying consumer and expiry/consumption behavior. No transitive closure, full-deck readiness or training admission claim.",
            "training_scope": "SCOPED_PACKAGE_ONLY",
            "profile_manifest_sha256": profile_hash,
            "rules_fingerprint": rules_fp,
            "pool_membership_sha256": canonical_hash("NO_DYNAMIC_OUTCOME_POOL_IN_COST_DISCOUNT_EFFECT_V1"),
            "pool_predicate_version": "NO_DYNAMIC_OUTCOME_POOL_IN_COST_DISCOUNT_EFFECT_V1",
            "capability_fingerprint": sha256(identity[card_id]),
            "scenario_fingerprint": canonical_hash({
                "native_output": native_outputs[card_id],
                "verifier_sha256": sha256(Path(__file__)),
                "bridge_result": bridge[card_id],
            }),
            "bridge_action_status": "VERIFIED_SCOPED",
            "native_test": row["native_filter"],
            "bridge_result": bridge[card_id],
            "dependency_review": {
                "scope": "REVIEWED_FIXED_ENCHANTMENT_ONLY",
                "reviewed_static_dependencies": [dependency],
                "dynamic_pools": [],
            },
            "training_eligible": False,
        }

    existing = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8")) if EVIDENCE_PATH.exists() else {}
    evidence = {
        "schema_version": 1,
        "package": "meta_profile_low_hanging_verification_harvest_v2",
        "scope": "SCOPED_PACKAGE_ONLY",
        "profile_manifest_sha256": profile_hash,
        "cards": {**existing.get("cards", {}), **execution_cards},
        "package_results": {
            **existing.get("package_results", {}),
            PACKAGE_ID: {
                "verified_roots": sorted(execution_cards),
                "native_outputs": native_outputs,
                "bridge_outputs": bridge,
                "static_dependencies": {card_id: row["dependency"] for card_id, row in CASES.items()},
                "dependency_closure_gained": 0,
                "training_eligible": False,
            },
        },
        "training_eligible": False,
    }
    EVIDENCE_PATH.write_text(
        json.dumps(record_execution(evidence), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"PASS: explicit evidence written to {EVIDENCE_PATH}")


if __name__ == "__main__":
    main()
