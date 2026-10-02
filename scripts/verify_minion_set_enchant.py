"""Independent native + production-boundary checks and explicit package evidence."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from hearthstone.enums import CardType, GameTag, Zone  # noqa: E402
from scripts.build_standard_registry import build_registry, read_json  # noqa: E402
from scripts.standard_profile import load_profile, profile_path  # noqa: E402
from scripts.verification_evidence import record_execution  # noqa: E402
from scripts.import_power_log import _card_features, _board_entity, _player_observation  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.domain.serialization import _card, game_state_from_dict  # noqa: E402
from manamind.encoding.state_encoder import StateEncoder  # noqa: E402
from manamind.encoding.entity_encoder import STATE_FLAG_NAMES  # noqa: E402
from manamind.integrations.rosettastone.rosettastone import (  # noqa: E402
    _load_bridge, SimulatorSession, make_simple_test_deck, validate_deck,
)

RULES = ROOT / "integrations/rosettastone/card_rules"
REPORT = ROOT / "reports/minion_set_enchant_v1_20261002"
CASES = (("RLK_048", "DEATHKNIGHT"), ("TLC_233", "DRUID"), ("TIME_447", "PRIEST"))


def parity(raw: dict) -> None:
    before, after = raw["before"], raw["after"]
    card = _card(raw["held_after"])
    catalog = CardCatalog([_card({k: v for k, v in raw["held_after"].items() if not k.startswith("current_")})])
    held = SimpleNamespace(card_id=card.card_id, type=CardType.MINION,
                           tags={GameTag.COST: 4, GameTag.ATK: 4, GameTag.HEALTH: card.current_health})
    assert _card_features(held, catalog) == card
    state = game_state_from_dict(after)
    encoder = StateEncoder(catalog)
    encoded = encoder.encode(state)
    assert encoded.self_hand.numeric_present[:, 7].tolist() == [1.0] * len(state.self_hand)
    assert [c.card_id for c in state.self_hand] == [c["card_id"] for c in after["self_hand"]]
    assert state.opponent_known_cards == () and "opponent_hand" not in after
    assert state.self_player.locations[0].board_position == 1
    assert after["self_player"]["locations"] == before["self_player"]["locations"]
    own = after["self_player"]["board"][0]
    board_card = _card({k: v for k, v in own.items() if k in {
        "card_id", "cost", "attack", "health", "durability", "card_type", "card_class", "race", "mechanics"}})
    catalog = CardCatalog([board_card])
    tags = {GameTag.COST: 4, GameTag.ATK: own["current_attack"], GameTag.HEALTH: own["max_health"],
            GameTag.DAMAGE: own["max_health"] - own["current_health"], GameTag.EXHAUSTED: 1,
            GameTag.TAUNT: int(own["taunt"]), GameTag.DIVINE_SHIELD: int(own["divine_shield"]),
            GameTag.CANT_BE_TARGETED_BY_SPELLS: int(own["cant_be_targeted_by_spells"]),
            GameTag.CANT_BE_TARGETED_BY_HERO_POWERS: int(own["cant_be_targeted_by_hero_powers"])}
    imported = _board_entity(SimpleNamespace(card_id=own["card_id"], type=CardType.MINION, tags=tags), 0, catalog)
    assert imported == state.self_player.board[0], (imported, state.self_player.board[0])
    for flag in ("cant_be_targeted_by_spells", "cant_be_targeted_by_hero_powers"):
        assert encoded.self_board.state_flags[0, STATE_FLAG_NAMES.index(flag)] == float(own[flag])
        assert encoded.self_board.state_flags[0, STATE_FLAG_NAMES.index(flag + "_known")] == 1
    # Independent log-import hero tags; no hidden identity is used for features.
    player = SimpleNamespace(tags={GameTag.HERO_ENTITY: 1})
    hero = SimpleNamespace(id=1, controller=player, card_id="UNKNOWN_HERO", type=CardType.HERO,
                           zone=Zone.PLAY, tags={GameTag.HEALTH: 30,
                           GameTag.DIVINE_SHIELD: int(after["self_player"]["hero_divine_shield"])})
    observation, _ = _player_observation(player, [hero], CardCatalog([]), is_self=True)
    assert observation.hero_divine_shield == state.self_player.hero_divine_shield
    assert encoded.global_features[encoder.global_feature_names.index("self_hero_divine_shield")] != 0


def verify_bridge() -> dict:
    bridge = _load_bridge()
    results = {}
    for cid, player_class in CASES:
        kinds = range(7) if cid == "TIME_447" else (4,)
        for kind in kinds:
            # DK effect fixture uses an available hero; DK session is not claimed.
            raw = bridge.make_minion_set_enchant_fixture(cid, "PRIEST" if player_class == "DEATHKNIGHT" else player_class, kind)
            before, after = raw["before"], raw["after"]
            own = after["self_player"]["board"][0]
            enemy = after["opponent"]["board"][0]
            if cid == "TIME_447":
                actions = [a for a in raw["legal_before"] if a.get("card_id") == cid]
                assert actions and all(a["target_entity_id"] is not None for a in actions)
                assert not any(a["target_entity_id"] == raw["location_entity_id"] for a in actions)
                legal = kind < 4
                # Hero entity ID 0 is valid; the fixture's absent-target sentinel
                # is not an entity. Absence is checked by non-null action targets.
                if kind != 4:
                    assert any(a["target_entity_id"] == raw["target_entity_id"] for a in actions) == legal
                assert raw["held_after"]["current_health"] == (7 if legal else 5)
                if not legal:
                    assert after == before
                elif kind in (0, 1):
                    assert after["self_player" if kind == 0 else "opponent"]["hero_divine_shield"] is True
                else:
                    assert (own if kind == 2 else enemy)["divine_shield"] is True
                transferred = raw["after_transfer"]["self_player"]["board"][-1]
                assert transferred["current_health"] == (7 if legal else 5)
                assert transferred["health"] == 5 and transferred["attack"] == 4
                assert all(c["current_health"] == (7 if legal else 5) for c in after["self_hand"] if c["card_type"] == "MINION")
            elif cid == "RLK_048":
                assert (own["current_attack"], own["max_health"]) == (3, 6)
                assert own["cant_be_targeted_by_spells"] and own["cant_be_targeted_by_hero_powers"]
                assert not any(a.get("card_id") == "CS2_029" and a["target_entity_id"] == raw["friendly_entity_id"] for a in raw["legal_after"])
            else:
                assert (own["current_attack"], own["max_health"], own["taunt"]) == (3, 6, True)
                source = after["self_player"]["board"][-1]
                assert (source["current_attack"], source["max_health"], source["taunt"]) == (2, 3, False)
            assert (enemy["current_attack"], enemy["max_health"]) == (4, 5)
            assert all(c["card_id"] not in {"TIME_447", "RLK_048", "TLC_233"} for c in after["opponent_known_cards"])
            parity(raw)
        deck = make_simple_test_deck(player_class=player_class)
        deck[0] = cid
        assert not validate_deck(deck, player_class=player_class)
        if player_class != "DEATHKNIGHT":
            session = SimulatorSession(deck, make_simple_test_deck(player_class="MAGE"),
                                       player1_class=player_class, player2_class="MAGE", shuffle=False)
            assert cid in {c.card_id for c in session.observation("PLAYER1").self_hand}
            # Production ApplyAction must reject handles not present in legal actions.
            action = next(a for a in session.legal_actions() if a["type"] == "END_TURN")
            invalid = {**action, "type": "PLAY_CARD", "hand_index": 999, "target_entity_id": 999999}
            try:
                session.apply_action(invalid)
            except (ValueError, RuntimeError):
                pass
            else:
                raise AssertionError("invalid/stale action handles accepted")
            session.apply_action(action)
        results[cid] = {"fixture_cases": len(tuple(kinds)), "parity": "PASS", "deck_legality": "PASS",
                        "session": "BLOCKED_DK_HERO_SETUP" if player_class == "DEATHKNIGHT" else "OPENING_AND_HANDLE_REJECTION_PASS"}
    return results


def main() -> None:
    REPORT.mkdir(exist_ok=True)
    manifest = read_json(RULES / "minion_set_enchant.generated.json")
    # This producer certifies the approved package only. New declarations can
    # reuse the renderer, but they need newly reviewed expectations/evidence.
    assert {r["card_id"] for r in manifest["cards"]} == {cid for cid, _ in CASES}
    assert set(manifest["dependencies"]) == {"ICC_210e", "ULD_191e"}
    assert (manifest["dependencies"]["ICC_210e"]["attack_delta"], manifest["dependencies"]["ICC_210e"]["health_delta"]) == (1, 1)
    assert (manifest["dependencies"]["ULD_191e"]["attack_delta"], manifest["dependencies"]["ULD_191e"]["health_delta"]) == (0, 2)
    native = subprocess.run([str(ROOT / "vendor/RosettaStone/build-mana-py312/bin/UnitTests.exe"),
                             "--test-case=[ManaMind minion set enchant]*"],
                            cwd=ROOT / "vendor/RosettaStone", capture_output=True, text=True, errors="replace")
    (REPORT / "native_scenarios.txt").write_text(native.stdout + native.stderr, encoding="utf-8")
    print(native.stdout)
    if native.returncode or "test cases:" not in native.stdout or " 0 |" in native.stdout.split("test cases:")[-1].splitlines()[0]:
        raise RuntimeError("native family scenarios failed or did not execute")
    boundary = verify_bridge()
    (REPORT / "bridge_parity.json").write_text(json.dumps(boundary, indent=2) + "\n", encoding="utf-8")
    profile = load_profile()
    registry, _ = build_registry(read_json(profile_path(profile, "roots")), profile=profile)
    cards = {}
    for row in manifest["cards"]:
        cid = row["card_id"]
        closure = registry["cards"][cid]["dependency_closure"]
        assert closure["known_source_candidate_ids"] == row["dependencies"] and not closure["unresolved_dynamic_pool_ids"]
        cards[cid] = {"status": "VERIFIED_SCOPED", "scope": "Full fixed effect family including lifetime, target legality and observed state; scoped package, no full-profile match gate.",
                      "training_scope": "SCOPED_PACKAGE_ONLY", "bridge_action_status": "VERIFIED_SCOPED",
                      "contract_review": {"contract_id": "minion_set_enchant", "contract_version": 1},
                      "dependency_review": {"scope": "FULL_RULES", "graph_fingerprint": closure["graph_fingerprint"],
                                            "reviewed_edges": row["dependencies"], "dynamic_pools": [],
                                            "basis": "Complete pinned effect review plus exact existing dependency contracts; absent heuristic edges alone are not used."},
                      "boundary": boundary[cid], "training_eligible": False}
    for ref, contract in manifest["dependencies"].items():
        cards[ref] = {"status": "VERIFIED_SCOPED", "scope": "FIXED_STATS_ENCHANT_V1 exact numeric application, damaged recipient and silence; no generated outcomes.",
                      "training_scope": "SCOPED_PACKAGE_ONLY", "dependency_contract": contract, "training_eligible": False}
    evidence = record_execution({"package": "minion_set_enchant_v1", "manifest": manifest,
                                 "native_output": native.stdout, "cards": cards, "training_eligible": False})
    (RULES / "minion_set_enchant.evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("PASS: three roots, two fixed dependency contracts, nine production-boundary fixtures; no training admission.")


if __name__ == "__main__":
    main()
