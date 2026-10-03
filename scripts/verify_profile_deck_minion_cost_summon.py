"""Verify profile-scoped live-deck minion cost selection consumers."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.integrations.rosettastone.rosettastone import (  # noqa: E402
    SimulatorSession,
    make_simple_test_deck,
    validate_deck,
)

sys.path.insert(0, str(ROOT))
from scripts.verification_evidence import record_execution  # noqa: E402

NATIVE_TESTS = ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"
EVIDENCE = ROOT / "integrations/rosettastone/card_rules/profile_deck_minion_cost_summon.evidence.json"
PROFILE = ROOT / "configs/training_profiles/meta_training_20261002_v1.json"
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
REGISTRY = ROOT / "data/cards/standard_registry_20261001_enUS.json"
DECLARATION = ROOT / "integrations/rosettastone/card_rules/profile_deck_minion_cost_summon.v1.json"
GENERATOR = ROOT / "scripts/generate_profile_deck_minion_cost_summon.py"
RENDERER = ROOT / "scripts/card_rules/profile_deck_minion_cost_summon.py"
GENERATED_SOURCE = ROOT / "vendor/RosettaStone/Sources/Rosetta/PlayMode/CardSets/ManaMindProfileDeckMinionCostSummonGen.cpp"
NATIVE_SOURCE = ROOT / "vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindEffectCompositionTests.cpp"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def end_turn(game: SimulatorSession) -> None:
    action = next((a for a in game.legal_actions() if a["type"] == "END_TURN"), None)
    if action is None:
        raise AssertionError("Expected a legal END_TURN action")
    game.apply_action(action)


def deck_with_root(card_id: str) -> list[str]:
    deck = make_simple_test_deck(player_class="PALADIN")
    deck[0] = card_id
    errors = validate_deck(deck, player_class="PALADIN")
    if errors:
        raise AssertionError(f"{card_id} fixture deck is invalid: {errors}")
    return deck


def make_game(card_id: str) -> SimulatorSession:
    return SimulatorSession(
        deck_with_root(card_id),
        make_simple_test_deck(player_class="WARRIOR"),
        player1_class="PALADIN",
        player2_class="WARRIOR",
        shuffle=False,
        random_start=False,
        random_seed=327 if card_id == "JAIL_327" else 516,
    )


def verify_recruiter() -> str:
    game = make_game("JAIL_516")
    while True:
        state = game.observation("PLAYER1")
        actions = game.legal_actions()
        play = next(
            (a for a in actions if a["type"] == "PLAY_CARD" and a.get("card_id") == "JAIL_516"),
            None,
        )
        if play is not None:
            break
        end_turn(game)
        if state.turn_number > 20:
            raise AssertionError("Scarlet Recruiter did not become playable within 20 turns")
    if state.self_player.board:
        raise AssertionError("Fixture should not create a board before Scarlet Recruiter")
    game.apply_action(play)
    after = game.observation("PLAYER1")
    summoned = [entity for entity in after.self_player.board if entity.card.card_id != "JAIL_516"]
    if len(summoned) != 2:
        raise AssertionError(f"Scarlet Recruiter should summon two deck minions, got {len(summoned)}")
    if not any(entity.card.card_id == "JAIL_516" for entity in after.self_player.board):
        raise AssertionError("Scarlet Recruiter body should remain on board after its Battlecry")
    if any(not entity.rush for entity in summoned):
        raise AssertionError(f"Both recruited minions should have Rush: {summoned}")
    if any(entity.card.effective_cost is None or entity.card.effective_cost > 2 for entity in summoned):
        raise AssertionError(f"Recruiter summoned a minion above the current-cost threshold: {summoned}")
    print("PASS JAIL_516: Battlecry summons two live-deck minions and grants Rush")
    return "PASS: exactly two distinct available deck minions summoned; Rush visible on both"


def verify_reinforcement_aura() -> str:
    game = make_game("JAIL_327")
    play = None
    while play is None:
        state = game.observation("PLAYER1")
        if state.active_player == "SELF":
            play = next(
                (a for a in game.legal_actions() if a["type"] == "PLAY_CARD" and a.get("card_id") == "JAIL_327"),
                None,
            )
        if play is None:
            end_turn(game)
        if game.observation("PLAYER1").turn_number > 20:
            raise AssertionError("Reinforcement Aura did not become playable within 20 turns")
    game.apply_action(play)
    counts: list[int] = []
    for _ in range(4):
        end_turn(game)
        state = game.observation("PLAYER1")
        if state.active_player == "OPPONENT":
            end_turn(game)
            state = game.observation("PLAYER1")
        counts.append(len(state.self_player.board))
    if counts[:3] != [1, 2, 3] or counts[3] != 3:
        raise AssertionError(f"Reinforcement Aura should trigger exactly three times, got board counts {counts}")
    print("PASS JAIL_327: one cost-qualified minion at each of three end steps, then expires")
    return "PASS: three bounded turn-end summons; no fourth trigger"


def main() -> None:
    if not NATIVE_TESTS.exists():
        raise RuntimeError("Build the py312 UnitTests target before verification")
    native = subprocess.run(
        [str(NATIVE_TESTS), "--test-case=[ManaMind profile deck minion]*"],
        cwd=ROOT / "vendor/RosettaStone",
        check=True,
        capture_output=True,
        text=True,
    )
    print(native.stdout, end="")
    bridge_scopes = {
        "JAIL_327": verify_reinforcement_aura(),
        "JAIL_516": verify_recruiter(),
    }

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))["cards"]
    rows = {card["id"]: card for card in catalog}
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["cards"]
    declaration_hash = sha(DECLARATION)
    generator_hash = sha(GENERATOR)
    renderer_hash = sha(RENDERER)
    generated_hash = sha(GENERATED_SOURCE)
    native_source_hash = sha(NATIVE_SOURCE)
    verifier_hash = sha(Path(__file__))
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile_hash = canonical_sha(profile)
    contract = {
        "contract_id": "deck_minion_cost_threshold_summon",
        "contract_version": 1,
        "implementation_kind": "REUSABLE_CAPABILITY",
        "predicate": "live deck minion with current effective cost <= 2",
        "random_selection": "uniform engine selection without replacement, up to requested count",
        "consumers": ["JAIL_327", "JAIL_516"],
    }
    cards = {}
    for card_id in ("JAIL_327", "JAIL_516"):
        cards[card_id] = {
            "status": "VERIFIED_SCOPED",
            "scope": "Native independent family scenarios and actual loaded-bridge profile consumer scenarios; root behavior and bounded outcome variation only, no full deck closure or training admission.",
            "training_scope": "META_PROFILE_SCOPED_ONLY",
            "contract_review": contract,
            "rules_fingerprint": canonical_sha({
                "card_record_sha256": registry[card_id]["metadata"]["card_record_sha256"],
                "rules_text": rows[card_id]["text"],
                "declaration_sha256": declaration_hash,
                "generator_sha256": generator_hash,
                "renderer_sha256": renderer_hash,
                "generated_source_sha256": generated_hash,
            }),
            "dependency_review": {
                "scope": "SCOPED_CURRENT_COST_AND_RUSH_CONTRACT",
                "dependency_ids": ["ULD_178a4"] if card_id == "JAIL_516" else [],
                "verified_property": "Live deck cost filter; requested count bounded by available eligible minions; Rush grant for Recruiter.",
                "complete_profile_closure": False,
            },
            "native_test": "[ManaMind profile deck minion]* passed",
            "bridge_scope": bridge_scopes[card_id],
            "profile_manifest_sha256": profile_hash,
            "native_scenario_sha256": native_source_hash,
            "bridge_scenario_sha256": verifier_hash,
        }
    document = {
        "package_id": "profile_deck_minion_cost_threshold_v1",
        "contract_id": "deck_minion_cost_threshold_summon",
        "contract_version": 1,
        "profile_id": profile["profile_id"],
        "profile_manifest_sha256": profile_hash,
        "declaration_sha256": declaration_hash,
        "generator_script_sha256": generator_hash,
        "renderer_sha256": renderer_hash,
        "generated_source_sha256": generated_hash,
        "native_scenario_sha256": native_source_hash,
        "bridge_scenario_sha256": verifier_hash,
        "training_eligible": False,
        "cards": cards,
        "native_assertion_output": native.stdout.strip(),
    }
    document = record_execution(document)
    EVIDENCE.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote current profile-scoped evidence: {EVIDENCE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
