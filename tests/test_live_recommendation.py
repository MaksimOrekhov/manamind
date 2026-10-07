"""End-to-end LIVE policy safety, replay and independent collector behavior."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import run_manamind  # noqa: E402
from collect_power_logs import Collector  # noqa: E402
from live_fixtures import CANARIES, LiveLog, desc  # noqa: E402
from power_log_fixtures import SECRET_NAME, build_game  # noqa: E402
from test_live_session import drive, make, snapshots  # noqa: E402
from test_live_tail import Clock, append, write  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.encoding.state_encoder import StateEncoder  # noqa: E402
from manamind.live.recorder import Recorder  # noqa: E402
from manamind.live.recommendation import (  # noqa: E402
    PolicyRecommender, RecommendationUnavailable, render_recommendation,
)
from manamind.live.runner import LiveRunner  # noqa: E402
from manamind.live.session import LiveSession  # noqa: E402
from manamind.live.trust import LiveStatus  # noqa: E402
from manamind.models.policy import ACTION_FEATURE_NAMES, PolicyNetwork  # noqa: E402
from manamind.models.policy_v2 import PolicyNetworkV2, feature_contract  # noqa: E402
from manamind.models.policy_inputs import representation_of  # noqa: E402
from manamind.training.policy_checkpoint import identity, save_policy_checkpoint  # noqa: E402
from replay_live_recommendations import replay_summary  # noqa: E402

CARDS = ROOT / "data/cards/standard_current_enUS.json"
CATALOG = CardCatalog.from_json(CARDS)


@pytest.fixture(params=[1, 2])
def recommender(tmp_path, monkeypatch, request):
    encoder = StateEncoder(CATALOG)
    if request.param == 1:
        policy = PolicyNetwork(card_count=encoder.vocabulary.card_count)
    else:
        contract = feature_contract(encoder)
        policy = PolicyNetworkV2(card_count=encoder.vocabulary.card_count,
                                 state_feature_count=len(contract["state_feature_names"]),
                                 entity_feature_count=len(contract["entity_feature_names"]), hidden_size=16)
    split = {"dataset_sha256": "a" * 64, "game_ids": {
        "train": ["a" * 64], "validation": ["b" * 64], "test": ["c" * 64]}}
    config = {"seed": 4}
    meta = {"dataset_sha256": "a" * 64, "split": split, "split_sha256": identity(split),
            "config": config, "config_sha256": identity(config)}
    checkpoint = tmp_path / "policy.pt"
    save_policy_checkpoint(checkpoint, policy, encoder, meta)
    import manamind.live.recommendation as recommendation
    monkeypatch.setattr(recommendation, "REVIEWED_CHECKPOINT_SHA256",
                        hashlib.sha256(checkpoint.read_bytes()).hexdigest())
    return PolicyRecommender(checkpoint), checkpoint


def test_compatible_checkpoint_and_tamper_refuse_inference(recommender, monkeypatch):
    scorer, path = recommender
    assert scorer.checkpoint["schema"] == ("manamind.real_policy_baseline/1" if representation_of(scorer.policy) == 1
                                           else "manamind.real_policy/2")
    import manamind.live.recommendation as recommendation
    monkeypatch.setattr(recommendation, "REVIEWED_CHECKPOINT_SHA256", "0" * 64)
    with pytest.raises(RecommendationUnavailable, match="CHECKPOINT_IDENTITY_MISMATCH"):
        PolicyRecommender(path)
    payload = torch.load(path, weights_only=True)
    payload["state_encoding_schema_version"] = -1
    torch.save(payload, path)
    monkeypatch.setattr(recommendation, "REVIEWED_CHECKPOINT_SHA256",
                        hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(RecommendationUnavailable, match="CHECKPOINT_INCOMPATIBLE"):
        PolicyRecommender(path)


def test_runtime_catalog_must_match_checkpoint(recommender):
    scorer, _ = recommender
    with pytest.raises(RecommendationUnavailable, match="RUNTIME_CATALOG_MISMATCH"):
        scorer.require_catalog(CardCatalog())
    session, snap = ready(LiveLog().create_game().mulligan().self_decision(1))
    session.catalog = CardCatalog()
    with pytest.raises(RecommendationUnavailable, match="RUNTIME_CATALOG_MISMATCH"):
        scorer.score(snap, session)


def ready(log: LiveLog):
    session = make()
    snap = snapshots(drive(session, log.lines))
    assert len(snap) == 1
    return session, snap[0]


def test_complete_menu_targets_placements_end_turn_and_stable_rank(recommender):
    scorer, _ = recommender
    log = LiveLog().create_game().mulligan()
    log.entity(51, "CS2_231", {"CARDTYPE": "MINION", "ZONE": "PLAY", "CONTROLLER": 2,
                                 "ZONE_POSITION": 2, "ATK": 2, "HEALTH": 3})
    log.begin_turn(1).options()
    target_line = next(i for i, line in enumerate(log.lines) if "target 0 entity=" in line)
    log.lines.insert(target_line + 1,
                     log.lines[target_line].replace("target 0 entity=", "target 1 entity=").replace(
                         desc(50, "PLAY", 1, "CS2_168", 2), desc(51, "PLAY", 2, "CS2_231", 2)))
    session, snap = ready(log)
    seen = []
    original = scorer.policy.forward
    def capture(*inputs):
        if representation_of(scorer.policy) == 1:
            seen.append((inputs[1].clone(), inputs[3].clone()))
        else:
            seen.append((inputs[3].clone(), inputs[4][:, 0].clone()))
        return original(*inputs)
    scorer.policy.forward = capture
    first = scorer.score(snap, session)
    second = scorer.score(snap, session)
    assert first.menu_size == 6  # END_TURN, ATTACK, 2 targets x 2 insertion slots
    assert first.identity == second.identity
    assert [(a.index, a.score) for a in first.ranked] == [(a.index, a.score) for a in second.ranked]
    action_rows, card_ids = seen[0]
    play = action_rows[:, ACTION_FEATURE_NAMES.index("play_card")].bool()
    assert play.sum().item() == 4
    assert len({tuple(row.tolist()) for row in action_rows[play]}) == 4
    assert len(set(card_ids[play].tolist())) == 1
    text = render_recommendation(first)
    assert action_rows[:, ACTION_FEATURE_NAMES.index("end_turn")].sum().item() == 1
    assert "win probability" in text and SECRET_NAME not in text and "handle" not in text


def test_unknown_card_and_hidden_canaries_remain_safe(recommender):
    scorer, _ = recommender
    log = LiveLog(canaries=True).create_game().mulligan()
    log.canary_reveals().opponent_hand_identity()
    log.entity(45, "LOCATION_UNKNOWN", {"CARDTYPE": "LOCATION", "ZONE": "PLAY", "CONTROLLER": 1,
                                         "ZONE_POSITION": 2, "HEALTH": 3, "EXHAUSTED": 0})
    log.begin_turn(1)
    log.raw("GameState", "DebugPrintOptions", "id=1")
    log.raw("GameState", "DebugPrintOptions", "option 0 type=END_TURN mainEntity= error=INVALID errorParam=")
    log.raw("GameState", "DebugPrintOptions",
            f"option 1 type=POWER mainEntity={desc(45, 'PLAY', 2, 'LOCATION_UNKNOWN', 1)} error=NONE errorParam=")
    session, snap = ready(log)
    result = scorer.score(snap, session)
    assert result.menu_size == 2
    text = render_recommendation(result)
    assert all(secret not in text for secret in CANARIES)
    assert SECRET_NAME not in text and "Opponent#" not in text
    assert scorer.encoder.vocabulary.card_id("LOCATION_UNKNOWN") == 1


@pytest.mark.parametrize("status", [LiveStatus.SYNCING, LiveStatus.UNTRUSTED,
                                     LiveStatus.WAITING_FOR_GAME, LiveStatus.GAME_OVER])
def test_nonready_and_opponent_snapshots_fail_closed(recommender, status):
    scorer, _ = recommender
    session, snap = ready(LiveLog().create_game().mulligan().self_decision(1))
    session.status = status
    with pytest.raises(RecommendationUnavailable):
        scorer.score(snap, session)
    session.status = LiveStatus.READY
    from dataclasses import replace
    with pytest.raises(RecommendationUnavailable):
        scorer.score(replace(snap, active_player="OPPONENT"), session)


def test_send_option_new_options_and_game_over_invalidate_immediately(recommender):
    scorer, _ = recommender
    log = LiveLog().create_game().mulligan().self_decision(1)
    session, snap = ready(log)
    scorer.score(snap, session)
    log.lines.clear()
    log.send_option(1)
    session.feed(log.lines, 3000)
    assert session.current_snapshot is None and session.status is LiveStatus.SYNCING
    with pytest.raises(RecommendationUnavailable):
        scorer.score(snap, session)
    log.lines.clear()
    log.options()
    events = drive(session, log.lines, now=4000)
    newer = snapshots(events)
    assert len(newer) == 1 and newer[0].decision["options_id"] != snap.decision["options_id"]
    log.lines.clear()
    log.complete()
    session.feed(log.lines, 5000)
    assert session.current_snapshot is None and session.status is LiveStatus.GAME_OVER


@pytest.mark.parametrize("transition", ["new_options", "task_advance", "disconnect",
                                      "source_change", "file_discontinuity", "game_reset"])
def test_other_decision_supersession_paths_clear_current_snapshot(recommender, transition):
    scorer, _ = recommender
    session, snap = ready(LiveLog().create_game().mulligan().self_decision(1))
    scorer.score(snap, session)
    if transition == "new_options":
        log = LiveLog()
        log.raw("GameState", "DebugPrintOptions", "id=2")
        session.feed(log.lines, 3000)
    elif transition == "task_advance":
        log = LiveLog()
        log.raw("PowerTaskList", "DebugDump", "ID=999 ParentID=0 PreviousID=0 TaskCount=1")
        session.feed(log.lines, 3000)
    elif transition == "disconnect":
        session.disconnected("NO_POWER_LOG")
    elif transition == "source_change":
        session.new_source("next-session")
    elif transition == "file_discontinuity":
        session.file_discontinuity(True)
    else:
        log = LiveLog()
        log.raw("GameState", "DebugPrintPower", "BLOCK_START BlockType=GAME_RESET")
        session.feed(log.lines, 3000)
    assert session.current_snapshot is None
    assert session.status is not LiveStatus.READY
    with pytest.raises(RecommendationUnavailable):
        scorer.score(snap, session)


class DummyCollector:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail
        self.stats = type("Stats", (), {"parse_failures": 0, "matches_imported": 0})()
    def scan_once(self):
        self.calls += 1
        if self.fail:
            raise OSError("private collector path")
    def write_summary(self):
        pass


def test_unified_startup_no_history_new_game_recorder_invalidation_and_lane_failure(tmp_path, recommender):
    scorer, _ = recommender
    logs = tmp_path / "Logs"
    old = LiveLog().create_game().mulligan().self_decision(1).send_option(1).complete()
    power = write(logs / "Hearthstone_2026_10_06_10_00_00/Power.log", old.lines)
    clock = Clock()
    recorder = Recorder(tmp_path / "data/raw/live", catalog_path=CARDS)
    live = LiveRunner(logs, LiveSession(CATALOG), recorder, clock=clock)
    collector = DummyCollector(fail=True)
    printed = []
    runtime = run_manamind.UnifiedRuntime(live, collector, scorer, emit=printed.append, collector_seconds=1)
    for _ in range(5):
        runtime.step(clock.now); clock.advance(0.05)
    assert not any("#1 " in row for row in printed)
    assert collector.calls == 1 and any("collection warning" in row for row in printed)
    fresh = LiveLog(seed=2).create_game().mulligan().self_decision(1)
    append(power, "\n".join(fresh.lines) + "\n")
    for _ in range(6):
        runtime.step(clock.now); clock.advance(0.05)
    assert runtime.decisions_scored == 1
    assert any("EXPERIMENTAL_NEURAL_POLICY" in row for row in printed)
    assert list((tmp_path / "data/raw/live").rglob("snapshots.jsonl"))
    fresh.lines.clear()
    fresh.send_option(1)
    append(power, "\n".join(fresh.lines) + "\n")
    runtime.step(clock.now)
    assert runtime.active_identity is None
    assert any("invalidated" in row for row in printed)
    assert SECRET_NAME not in "\n".join(printed)


def test_real_collector_retains_once_and_restart_with_recommendations_unavailable(tmp_path):
    logs = tmp_path / "Logs"
    write(logs / "Power.log", build_game(seed=17))
    data = tmp_path / "data"
    def make_runtime():
        live = LiveRunner(logs, LiveSession(CATALOG), Recorder(data / "raw/live", catalog_path=CARDS),
                          clock=Clock())
        collector = Collector(logs, data / "raw/collected", data / "processed_real", CARDS, emit=lambda _: None)
        return run_manamind.UnifiedRuntime(live, collector, None, emit=lambda _: None)
    first = make_runtime()
    first.step(0)
    assert first.collector.stats.matches_imported == 1
    assert len(list((data / "raw/collected").glob("*.log"))) == 1
    assert len(list((data / "processed_real").glob("*.jsonl"))) == 1
    restarted = make_runtime()
    restarted.step(0)
    assert restarted.collector.stats.matches_imported == 0
    assert len(list((data / "raw/collected").glob("*.log"))) == 1
    assert len(list((data / "processed_real").glob("*.jsonl"))) == 1


def test_offline_recording_replay_keeps_rankings_and_hashes(tmp_path, recommender):
    scorer, _ = recommender
    logs = tmp_path / "Logs"
    power = write(logs / "Power.log", [""], newline=False)
    clock = Clock()
    recorder = Recorder(tmp_path / "data/raw/live", catalog_path=CARDS)
    live = LiveRunner(logs, LiveSession(CATALOG), recorder, clock=clock)
    log = LiveLog().create_game().mulligan().self_decision(1)
    for start in range(0, len(log.lines), 9):
        append(power, "\n".join(log.lines[start:start+9]) + "\n")
        for _ in range(4):
            live.step(); clock.advance(0.05)
    for _ in range(4):
        live.step(); clock.advance(0.05)
    recordings = list((tmp_path / "data/raw/live").rglob("meta.json"))
    assert len(recordings) == 1
    result = replay_summary([recordings[0].parent], scorer)
    assert result["recorded_hashes_match"] and result["ranking_replay_identical"]
    assert result["scored"] == 1
    assert result["latency_ms"]["p99"] >= 0
