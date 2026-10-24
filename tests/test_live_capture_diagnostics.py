from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from manamind.live.capture_diagnostics import build_capture_report  # noqa: E402
from manamind.live.snapshot import Snapshot, state_hash  # noqa: E402
from collect_power_logs import Collector  # noqa: E402
from process_completed_match import ProcessorResult  # noqa: E402


MATCH_ID = "a" * 64


def _snapshot() -> Snapshot:
    state = {"turn": 3}
    return Snapshot(
        seq=1,
        status="READY",
        reason=None,
        game_key=MATCH_ID,
        session="session",
        client_build=123,
        game_type="GT_RANKED",
        format="FT_STANDARD",
        phase="SELF_DECISION",
        turn=3,
        active_player="SELF",
        state=state,
        decision={"kind": "MAIN_ACTION", "options_id": 8, "legal": [{"kind": "END_TURN"}]},
        state_hash=state_hash(state),
        source={"line_in_game": 10},
    )


def test_capture_report_strictly_joins_snapshot_and_journals(tmp_path: Path):
    live_root = tmp_path / "live"
    recording = live_root / "session" / MATCH_ID[:16]
    recording.mkdir(parents=True)
    snapshot = _snapshot()
    (recording / "meta.json").write_text(json.dumps({"game_key": MATCH_ID}), encoding="utf-8")
    (recording / "capture_summary.json").write_text(json.dumps({
        "game_key": MATCH_ID,
        "options_packets_seen": 1,
        "trusted_snapshots_emitted": 1,
        "trust_rejections": {},
        "superseded_menus": 0,
        "recording_failures": {},
    }), encoding="utf-8")
    (recording / "snapshots.jsonl").write_text(snapshot.to_json() + "\n", encoding="utf-8")
    decision_id = f"{MATCH_ID}:1:8:{snapshot.state_hash}"
    (live_root / "prediction_journal.jsonl").write_text(json.dumps({
        "event": "RECOMMENDATION",
        "match_id": MATCH_ID,
        "decision_id": decision_id,
        "state_hash": snapshot.state_hash,
    }) + "\n", encoding="utf-8")
    policy_path = tmp_path / "policy.jsonl"
    policy_path.write_text(json.dumps({
        "game_id": MATCH_ID,
        "decision_id": f"{MATCH_ID}:8",
        "provenance": {"state_hash": snapshot.state_hash},
    }) + "\n", encoding="utf-8")

    report = build_capture_report(MATCH_ID, {
        "status": "OK",
        "decisions_total": 1,
        "decisions_labeled": 1,
        "decisions_skipped": 0,
        "decision_skip_reasons": {},
    }, live_root, live_root, policy_path)

    assert report["collector"]["power_log_decisions"] == 1
    assert report["live"]["snapshots_saved"] == 1
    assert report["live"]["valid_trusted_snapshots"] == 1
    assert report["strict_identity"]["labeled_policy_decisions_with_exact_snapshot"] == 1
    assert report["journals"]["rows_by_kind"]["prediction"] == 1
    assert report["journals"]["strict_labeled_decisions_with_row"]["prediction"] == 1


def test_collector_reports_imported_match_without_live_recording(tmp_path: Path):
    raw = tmp_path / "raw" / "collected"
    collector = Collector(
        tmp_path / "logs",
        raw,
        tmp_path / "processed",
        tmp_path / "cards.json",
        state_path=tmp_path / "state.json",
        policy_output=tmp_path / "policy",
        evidence_output=tmp_path / "evidence",
        emit=lambda _: None,
    )
    collector._write_capture_diagnostics(MATCH_ID, {"policy": ProcessorResult(
        "OK",
        detail={"decisions_total": 3, "decisions_labeled": 2,
                "decisions_skipped": 1, "decision_skip_reasons": {"NO_SELECTION": 1}},
    )})

    report = json.loads((raw / "capture_reports" / f"{MATCH_ID[:16]}.json").read_text(encoding="utf-8"))

    assert report["collector"]["power_log_decisions"] == 3
    assert report["live"]["status"] == "NO_LIVE_RECORDING"
    assert report["live"]["absence_reason"] == "LIVE_NOT_OBSERVED_OR_NOT_RECORDED"
    assert report["missed_reason_counts"] == {"LIVE_NOT_OBSERVED_OR_NOT_RECORDED": 3}


def test_in_memory_observation_identifies_a_failed_recorder(tmp_path: Path):
    report = build_capture_report(MATCH_ID, {
        "status": "OK",
        "decisions_total": 2,
        "decisions_labeled": 2,
        "decision_skip_reasons": {},
    }, tmp_path / "missing-recordings", tmp_path / "missing-journals", tmp_path / "missing-policy.jsonl",
       live_observation={
           "game_key": MATCH_ID,
           "live_observed": True,
           "trusted_snapshots_emitted": 2,
           "snapshots_saved": 1,
           "trust_rejections": {},
           "recording_failures": {"FILE_IO_ERROR": 1},
       })

    assert report["live"]["status"] == "LIVE_OBSERVED_NO_RECORDING"
    assert report["live"]["absence_reason"] == "RECORDING_WRITE_FAILED"
    assert report["missed_reason_counts"] == {
        "RECORDING_FILE_IO_ERROR": 1,
        "SNAPSHOT_NOT_SAVED": 1,
    }
