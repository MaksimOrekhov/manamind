from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import new_matches_eval_1 as eval1  # noqa: E402
import run_manamind  # noqa: E402
from manamind.live.snapshot import state_hash  # noqa: E402
from manamind.live.snapshot_join import collapse_identical_main_action_snapshots  # noqa: E402
from manamind.outcome.shadow import action_digest  # noqa: E402


def _snapshot(*, seq: int = 1, state: dict | None = None, decision: dict | None = None) -> dict:
    snapshot_state = state if state is not None else {"turn": 3, "hand": ["CARD_1"]}
    return {
        "schema": "manamind.live.snapshot/1",
        "seq": seq,
        "status": "READY",
        "reason": None,
        "game_key": "a" * 64,
        "session": "Hearthstone_test",
        "source": {"line_in_game": 42},
        "client_build": 123,
        "game_type": "GT_RANKED",
        "format": "FT_STANDARD",
        "phase": "SELF_DECISION",
        "turn": 3,
        "active_player": "SELF",
        "state": snapshot_state,
        "decision": decision if decision is not None else {
            "kind": "MAIN_ACTION", "options_id": 17, "legal": [1, 2],
        },
        "state_hash": state_hash(snapshot_state),
    }


def test_identical_main_action_snapshots_collapse_when_only_seq_differs():
    first = _snapshot(seq=8)
    second = {**first, "seq": 9}

    result = collapse_identical_main_action_snapshots([first, second])

    assert result.reason is None
    assert result.snapshot == first
    assert result.source_rows == 2


@pytest.mark.parametrize("conflict", ["state", "decision", "source"])
def test_conflicting_repeated_snapshots_fail_closed(conflict):
    first = _snapshot(seq=8)
    second = {**first, "seq": 9}
    if conflict == "state":
        changed_state = {**first["state"], "turn": 4}
        second["state"] = changed_state
        second["state_hash"] = state_hash(changed_state)
    elif conflict == "decision":
        second["decision"] = {**first["decision"], "legal": [1, 3]}
    else:
        second["source"] = {"line_in_game": 43}

    result = collapse_identical_main_action_snapshots([first, second])

    assert result.snapshot is None
    assert result.reason == "CONFLICTING_SNAPSHOTS"


def test_repeated_snapshot_sequence_must_be_unambiguous():
    first = _snapshot(seq=8)
    duplicate_sequence = {**first}

    result = collapse_identical_main_action_snapshots([first, duplicate_sequence])

    assert result.snapshot is None
    assert result.reason == "AMBIGUOUS_SNAPSHOT_SEQ"


def test_repeated_join_does_not_weaken_full_ordered_menu_check():
    actions = [{"type": "END_TURN"}, {"type": "PLAY_CARD", "card_id": "CARD_1"}]
    shadow = {
        "menu_size": len(actions),
        "actions": [{"index": index, "action": action_digest(action)}
                    for index, action in enumerate(actions)],
    }

    assert eval1._match_menu_actions(shadow, actions)
    assert not eval1._match_menu_actions(shadow, list(reversed(actions)))
    assert not eval1._match_menu_actions({**shadow, "menu_size": 1}, actions)


def test_run_manamind_collector_session_limit_defaults_and_forwards(monkeypatch):
    default_args = run_manamind.build_parser().parse_args([])
    explicit_args = run_manamind.build_parser().parse_args(["--collector-max-sessions", "6"])
    captured = {}

    def fake_collector(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return "collector"

    monkeypatch.setattr(run_manamind, "Collector", fake_collector)

    assert default_args.collector_max_sessions == 3
    assert explicit_args.collector_max_sessions == 6
    assert run_manamind._make_collector(explicit_args) == "collector"
    assert captured["kwargs"]["max_sessions"] == 6


def test_run_manamind_rejects_nonpositive_collector_session_limit():
    with pytest.raises(SystemExit, match="collector-max-sessions must be positive"):
        run_manamind.main(["--collector-max-sessions", "0"])
