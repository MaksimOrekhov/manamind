import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import decision_quality_review_1 as dq  # noqa: E402


def _state(turn=5, menu_extra=0):
    hero_power = {"card_id": "HERO_10bchp", "card_type": "HERO_POWER", "current_cost": 1, "mechanics": []}
    player = {"player_class": "DEMONHUNTER", "hero_health": 30, "hero_max_health": 30, "armor": 0, "hero_attack": 0,
              "available_mana": 3, "max_mana": 3, "board": [], "locations": [], "active_effects": [],
              "known_secrets": [], "hero_power": hero_power, "weapon": None, "deck_size": 20, "hand_size": 1}
    return {"active_player": "SELF", "pending_choice_owner": None, "turn_number": turn,
            "self_player": player, "opponent": dict(player, player_class="WARRIOR"),
            "self_hand": [{"card_id": "CORE_EX1_238", "card_type": "SPELL", "current_cost": 1, "mechanics": []}],
            "opponent_known_cards": []}


def _example(game, n, turn, size=3, **extra):
    menu = [{"type": "END_TURN", "play_position": 0}] + [
        {"type": "PLAY_CARD", "card_id": "CORE_EX1_238", "card_type": "SPELL", "hand_index": 0, "card_cost": 1,
         "target_kind": "HERO", "target_side": side, "play_position": 0}
        for side in ("OPPONENT", "SELF")] + [{"type": "HERO_POWER", "source_card_id": "HERO_10bchp", "x": i}
                                             for i in range(size - 3)]
    row = {"decision_id": f"{game}:x:{n}:h{n}", "game_id": game, "provenance": {"state_hash": f"h{n}"},
           "state": _state(turn), "legal_actions": menu, "chosen_action_index": 1, "final_result": 1.0}
    row.update(extra)
    return row


def test_exclusion_is_decided_by_id_before_opening():
    heldout, used = {"a" * 16 + "rest"}, {"b" * 16 + "rest"}
    assert dq.exclusion_reason("game02", heldout, used, set(), "game02.log") == "LEGACY_FILENAME_WITHOUT_MATCH_KEY"
    assert dq.exclusion_reason("a" * 16, heldout, used, set(), "x.log") == "PROTECTED_FRESH_HOLDOUT_ID_ONLY"
    assert dq.exclusion_reason("b" * 16, heldout, used, set(), "x.log") == "MATCH_ID_USED_BEFORE"
    assert dq.exclusion_reason("c" * 16, heldout, used, {"c" * 16 + ".log"}, "c" * 16 + ".log") == \
        "SOURCE_IN_EVAL_2_INVENTORY"
    assert dq.exclusion_reason("d" * 16, heldout, used, set(), "d.log") is None


def test_blind_position_drops_choice_and_result():
    blind = dq.blind_position(_example("g1", 1, 3))
    assert "chosen_action_index" not in blind and "final_result" not in blind
    assert set(blind) == {"decision_id", "game_id", "state_hash", "state", "legal_actions"}


def test_eligibility():
    assert dq.eligible(_example("g", 1, 3)) is None
    small = _example("g", 1, 3)
    small["legal_actions"] = small["legal_actions"][:2]
    assert dq.eligible(small) == "MENU_TOO_SMALL"


def _pool(matches=20, per_match=12):
    return [dq.blind_position(_example(f"{m:016x}", n, turn=n, size=3 + (n % 12)))
            for m in range(matches) for n in range(per_match)]


def test_sampling_is_deterministic_and_respects_caps():
    pool = _pool()
    classes = {p["game_id"]: ("WARLOCK" if int(p["game_id"], 16) % 3 else "DEMONHUNTER") for p in pool}
    first, second = dq.select_samples(pool, classes), dq.select_samples(list(reversed(pool)), classes)
    assert [p["decision_id"] for p in first["main"]] == [p["decision_id"] for p in second["main"]]
    assert len(first["pilot"]) == dq.PILOT_UNIQUE and len({p["game_id"] for p in first["pilot"]}) == dq.PILOT_UNIQUE
    assert len(first["main"]) == dq.MAIN_UNIQUE
    per_match = {}
    for p in first["main"]:
        per_match[p["game_id"]] = per_match.get(p["game_id"], 0) + 1
    assert max(per_match.values()) <= dq.MAIN_PER_MATCH_CAP
    turns = [(p["game_id"], dq.turn_of(p)) for p in first["main"] + first["pilot"]]
    assert len(turns) == len(set(turns))
    assert set(p["decision_id"] for p in first["main_repeats"]) <= set(p["decision_id"] for p in first["main"])


def test_screens_put_repeats_last_and_menu_is_a_permutation():
    pool = _pool()
    classes = {p["game_id"]: "WARLOCK" for p in pool}
    samples = dq.select_samples(pool, classes)
    screens = dq.screens_for("pilot", samples["pilot"], samples["pilot_repeats"])
    assert [s["repeat"] for s in screens] == [False] * dq.PILOT_UNIQUE + [True] * dq.PILOT_REPEATS
    for s in screens:
        position = next(p for p in pool if dq.position_id(p) == s["position_id"])
        assert sorted(s["menu_order"]) == list(range(len(position["legal_actions"])))


def test_rendered_screen_passes_blind_audit():
    texts = dq.CardTexts()
    position = dq.blind_position(_example("e" * 16, 1, 4))
    screen = {"screen_id": "P001", "position_id": dq.position_id(position), "repeat": False, "menu_order": [2, 0, 1]}
    rendered = dq.render_screen(texts, position, screen)
    assert dq.audit_payload({"screens": [rendered]}) == []
    assert rendered["hand"][0]["name"] == "Lightning Bolt" and rendered["hand"][0]["known_text"]
    assert [m["choice"] for m in rendered["menu"]] == [1, 2, 3]
    assert "repeat" not in rendered and "position_id" not in rendered


def test_audit_finds_forbidden_keys_anywhere():
    assert dq.audit_payload({"screens": [{"menu": [{"chosen_action_index": 0}]}]}) == ["$.screens[0].menu[0].chosen_action_index"]
    assert dq.audit_payload({"final_result": 1}) == ["$.final_result"]


def test_rich_text_allows_only_bold_and_italic():
    out = dq.rich_text("<b>Battlecry:</b> Deal $3 damage. <script>x</script> Herald {0}.")
    assert out == "<b>Battlecry:</b> Deal 3 damage. x Herald [?]."
    assert dq.rich_text("<b>Hero Power</b> Gain $d2 Armor. +$a1 Attack, restore #3.") == \
        "<b>Hero Power</b> Gain 2 Armor. +1 Attack, restore 3."


SCREEN = {"menu": [{"choice": 1}, {"choice": 2}, {"choice": 3}]}


@pytest.mark.parametrize("label, ok", [
    ({"status": "LABELED", "marks": {"1": "ACCEPTABLE", "3": "BLUNDER"}, "best": [], "confidence": "HIGH"}, True),
    ({"status": "LABELED", "marks": {"1": "ACCEPTABLE", "2": "ACCEPTABLE"}, "best": [1, 2], "confidence": "LOW"}, True),
    ({"status": "LABELED", "marks": {"3": "BLUNDER"}, "best": [], "confidence": "HIGH"}, False),
    ({"status": "LABELED", "marks": {"1": "UNSURE"}, "best": [1], "confidence": "HIGH"}, False),
    ({"status": "LABELED", "marks": {"9": "ACCEPTABLE"}, "best": [], "confidence": "HIGH"}, False),
    ({"status": "INSUFFICIENT_INFORMATION", "marks": {}, "best": [], "insufficient_reasons": ["CARD_TEXT_MISSING"],
      "confidence": "MEDIUM"}, True),
    ({"status": "INSUFFICIENT_INFORMATION", "marks": {}, "best": [], "insufficient_reasons": [],
      "confidence": "MEDIUM"}, False),
    ({"status": "LABELED", "marks": {"1": "ACCEPTABLE"}, "best": [], "confidence": None}, False),
])
def test_label_validation(label, ok):
    assert (dq.validate_label(label, SCREEN) == []) is ok


def test_rater_name_is_restricted():
    with pytest.raises(ValueError):
        dq.labels_path("../x", "pilot")


def test_pilot_verdict():
    screens = [{"screen_id": f"P{i:03d}", "menu": []} for i in range(1, 19)]
    manifest = {"screens": [{"screen_id": s["screen_id"], "repeat": i >= 15} for i, s in enumerate(screens)]}
    labels = {s["screen_id"]: {"status": "LABELED", "active_seconds": 60, "display_problem": False} for s in screens}
    assert dq.pilot_verdict(screens, labels, manifest)["pilot_verdict"] == "PASS"
    labels["P001"].update(status="INSUFFICIENT_INFORMATION", insufficient_reasons=["DISPLAY_PROBLEM"])
    for sid in ("P002", "P003", "P004"):
        labels[sid].update(display_problem=True)
    verdict = dq.pilot_verdict(screens, labels, manifest)
    assert verdict["pilot_verdict"] == "FAIL" and not verdict["checks"]["P2_display"]
    del labels["P005"]
    assert not dq.pilot_verdict(screens, labels, manifest)["checks"]["P1_complete"]


def test_server_saves_valid_labels_and_refuses_main_before_pilot(tmp_path, monkeypatch):
    import json
    import threading
    import urllib.error
    import urllib.request

    monkeypatch.setattr(dq, "PRIVATE", tmp_path)
    payload = {"batch": "pilot", "screens": [{"screen_id": "P001", "menu": [{"choice": 1}, {"choice": 2}]}]}
    text = json.dumps(payload)
    (tmp_path / "pilot.payload.private.json").write_text(text, encoding="utf-8")
    lock = {"batches": {"pilot": {"payload_sha256": dq.sha256_bytes(text.encode("utf-8"))},
                        "main": {"status": "READY"}}}
    (tmp_path / "lock.private.json").write_text(json.dumps(lock), encoding="utf-8")
    with pytest.raises(SystemExit):
        dq.make_server("main", "tester", 0)
    server = dq.make_server("pilot", "tester", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def post(label):
        request = urllib.request.Request(base + "/api/label", data=json.dumps(label).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    try:
        assert post({"screen_id": "P001", "status": "LABELED", "marks": {}, "best": [], "confidence": "HIGH"}) == 400
        assert post({"screen_id": "P001", "status": "LABELED", "marks": {"2": "ACCEPTABLE"}, "best": [],
                     "confidence": "HIGH", "active_seconds": 12, "chosen_action_index": 0}) == 200
        with urllib.request.urlopen(base + "/api/batch") as response:
            batch = json.loads(response.read())
        assert batch["labels"]["P001"]["marks"] == {"2": "ACCEPTABLE"}
    finally:
        server.shutdown()
        server.server_close()
    saved = (tmp_path / "labels" / "tester" / "pilot.labels.jsonl").read_text(encoding="utf-8")
    assert "chosen_action_index" not in saved and '"rater":"tester"' in saved
