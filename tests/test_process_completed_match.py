"""LIVE-0D: one completed raw match feeds Value, Policy and mechanic-observation processors."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]

import collect_power_logs as cpl  # noqa: E402
import import_policy_power_log as policy_cli  # noqa: E402
from test_real_policy_dataset import fixture  # noqa: E402

# The collector may load the module as ``scripts.process_completed_match``; patch that very object.
pcm = sys.modules[cpl.process_completed_match.__module__]
CATALOG = ROOT / "data" / "cards" / "standard_current_enUS.json"


class Env:
    def __init__(self, tmp_path: Path) -> None:
        self.logs = tmp_path / "Logs"
        self.logs.mkdir()
        self.raw = tmp_path / "raw"
        self.processed = tmp_path / "processed"
        self.policy = tmp_path / "policy"
        self.evidence = tmp_path / "evidence"
        self.messages: list[str] = []
        (self.logs / "Power.log").write_text("\n".join(fixture(seed=1).lines) + "\n", encoding="utf-8")

    def collector(self) -> cpl.Collector:
        return cpl.Collector(self.logs, self.raw, self.processed, CATALOG, policy_output=self.policy,
                             evidence_output=self.evidence, emit=self.messages.append)

    def count(self) -> dict[str, int]:
        return {
            "raw": len(list(self.raw.glob("*.log"))),
            "value": len(list(self.processed.glob("*.jsonl"))),
            "policy": len(list(self.policy.glob("*.jsonl"))),
            "observations": len(list(self.evidence.glob("*/observations.jsonl"))),
        }


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def test_completed_match_produces_raw_and_every_dataset(env: Env):
    collector = env.collector()
    collector.scan_once()

    assert env.count() == {"raw": 1, "value": 1, "policy": 1, "observations": 1}
    text = "\n".join(env.messages)
    for label in ("raw match saved", "Value examples: 1", "Policy examples: 1", "mechanic observations:"):
        assert label in text
    assert collector.stats.matches_imported == 1 and collector.stats.processor_failures == {}


def test_automatic_and_manual_policy_paths_share_one_implementation(env: Env, monkeypatch):
    assert pcm.import_policy_log.__module__.endswith("import_policy_power_log")
    assert pcm.import_policy_log.__name__ == policy_cli.import_log.__name__ == "import_log"
    seen = []
    real = pcm.import_policy_log
    monkeypatch.setattr(pcm, "import_policy_log",
                        lambda *args, **kwargs: seen.append(args[0]) or real(*args, **kwargs))
    env.collector().scan_once()
    assert len(seen) == 1 and seen[0].parent == env.raw

    # The manual importer over the same raw slice yields the same game: rejected as a duplicate.
    manual = policy_cli.import_log(seen[0], env.policy, pcm.CardCatalog.from_json(CATALOG), segmented=True)
    assert manual["games_imported"] == 0 and manual["game_skip_reasons"] == {"DUPLICATE_MATCH": 1}


def test_policy_failure_keeps_raw_value_and_session(env: Env, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("policy exploded")

    monkeypatch.setattr(pcm, "import_policy_log", boom)
    collector = env.collector()
    collector.scan_once()

    assert env.count() == {"raw": 1, "value": 1, "policy": 0, "observations": 1}
    assert collector.stats.matches_imported == 1 and collector.stats.parse_failures == 0
    assert collector.stats.processor_failures == {"policy": 1}
    assert any("Policy examples: FAILED" in m for m in env.messages)
    assert "policy exploded" not in "\n".join(env.messages)
    state = json.loads((env.raw / "collector_state.json").read_text(encoding="utf-8"))
    assert list(state["games"].values()) == [cpl.IMPORTED]

    # Backfill from the preserved raw match recovers the missing dataset.
    monkeypatch.undo()
    raw = next(env.raw.glob("*.log"))
    results = pcm.process_completed_match(raw, pcm.Outputs(env.processed, env.policy, env.evidence), CATALOG)
    assert {k: v.status for k, v in results.items()} == {
        "value": pcm.DUPLICATE, "policy": pcm.OK, "observations": pcm.DUPLICATE}
    assert env.count() == {"raw": 1, "value": 1, "policy": 1, "observations": 1}


def test_reprocessing_the_same_match_creates_no_duplicates(env: Env):
    env.collector().scan_once()
    before = env.count()
    raw = next(env.raw.glob("*.log"))
    outputs = pcm.Outputs(env.processed, env.policy, env.evidence)

    results = pcm.process_completed_match(raw, outputs, CATALOG)

    assert {r.status for r in results.values()} == {pcm.DUPLICATE}
    assert env.count() == before


def test_restarted_collector_without_state_does_not_duplicate_any_dataset(env: Env):
    env.collector().scan_once()
    (env.raw / "collector_state.json").unlink()
    again = env.collector()
    again.scan_once()
    assert env.count() == {"raw": 1, "value": 1, "policy": 1, "observations": 1}
    assert again.stats.matches_imported == 0 and again.stats.duplicates == 1


def test_backfill_cli_processes_a_raw_folder(env: Env, tmp_path: Path, capsys, monkeypatch):
    env.collector().scan_once()
    out = tmp_path / "backfill"
    argv = ["process_completed_match.py", str(env.raw), "--cards", str(CATALOG),
            "--value-output", str(out / "value"), "--policy-output", str(out / "policy"),
            "--evidence-output", str(out / "evidence")]
    monkeypatch.setattr(sys, "argv", argv)
    assert pcm.main() == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["matches"] == 1
    assert {name: p["OK"] for name, p in summary["processors"].items()} == {
        "value": 1, "policy": 1, "observations": 1}


def test_expected_policy_rejection_is_skipped_not_a_failure(env: Env, tmp_path: Path, capsys, monkeypatch):
    env.collector().scan_once()
    raw = next(env.raw.glob("*.log"))
    lines = raw.read_text(encoding="utf-8").splitlines()
    reset = lines[-2].split("GameState")[0] + "GameState.DebugPrintPower() - BLOCK_START BlockType=GAME_RESET Entity=1"
    reset_dir = tmp_path / "reset"
    reset_dir.mkdir()
    (reset_dir / "match.log").write_text("\n".join(lines[:-1] + [reset] + lines[-1:]) + "\n", encoding="utf-8")

    results = pcm.process_completed_match(
        reset_dir / "match.log", pcm.Outputs(tmp_path / "v", tmp_path / "p", tmp_path / "e"), CATALOG)
    assert results["policy"].status == pcm.SKIPPED
    assert results["policy"].detail["game_skip_reasons"] == {"GAME_RESET": 1}
    assert not list((tmp_path / "p").glob("*.jsonl"))

    # The backfill CLI treats it as a correct outcome, not an error.
    monkeypatch.setattr(sys, "argv", ["x", str(reset_dir), "--cards", str(CATALOG),
                                      "--value-output", str(tmp_path / "v2"), "--policy-output", str(tmp_path / "p2"),
                                      "--evidence-output", str(tmp_path / "e2")])
    pcm.main()
    assert json.loads(capsys.readouterr().out)["processors"]["policy"]["SKIPPED"] == 1


def test_collector_logs_policy_skip_without_counting_a_failure(env: Env, monkeypatch):
    monkeypatch.setattr(pcm, "import_policy_log", lambda *a, **k: {
        "games_imported": 0, "decisions_labeled": 0, "game_skip_reasons": {"GAME_RESET": 1}})
    collector = env.collector()
    collector.scan_once()
    assert collector.stats.processor_failures == {}
    assert any("Policy examples: skipped (GAME_RESET)" in m for m in env.messages)


def test_interrupted_evidence_extraction_leaves_no_final_directory_and_recovers(env: Env, tmp_path: Path, monkeypatch):
    env.collector().scan_once()
    raw = next(env.raw.glob("*.log"))
    outputs = pcm.Outputs(tmp_path / "v", tmp_path / "p", tmp_path / "e")
    real = pcm.run_extraction

    def crash_after_directory_created(inputs, output_dir, **kwargs):
        Path(output_dir).mkdir(parents=True)
        (Path(output_dir) / "observations.jsonl").write_text("{", encoding="utf-8")
        raise RuntimeError("interrupted")

    monkeypatch.setattr(pcm, "run_extraction", crash_after_directory_created)
    assert pcm.process_completed_match(raw, outputs, CATALOG)["observations"].status == pcm.FAILED
    assert list(outputs.evidence.iterdir()) == []  # neither final nor partial directory remains

    monkeypatch.setattr(pcm, "run_extraction", real)
    recovered = pcm.process_completed_match(raw, outputs, CATALOG)["observations"]
    assert recovered.status == pcm.OK and (outputs.evidence / raw.stem / "manifest.json").exists()


def test_whitelist_covers_match_gates_but_not_operational_reasons():
    assert {"GAME_RESET", "SELF_AMBIGUOUS", "MID_GAME_START"} <= pcm.POLICY_MATCH_SKIP_REASONS
    assert not {"DATASET_INVALIDATED", "VALUE_DATASET_DESTINATION", "INVALID_MATCH_ID",
                "PARSE_ERROR"} & pcm.POLICY_MATCH_SKIP_REASONS


def test_invalidated_policy_dataset_is_a_failure(env: Env, monkeypatch, capsys):
    env.policy.mkdir(parents=True)
    (env.policy / "INVALIDATED.json").write_text("{}", encoding="utf-8")
    collector = env.collector()
    collector.scan_once()
    assert collector.stats.processor_failures == {"policy": 1}
    assert any("Policy examples: FAILED (DATASET_INVALIDATED)" in m for m in env.messages)
    assert env.count()["raw"] == 1 and env.count()["value"] == 1  # nothing else is lost

    raw = next(env.raw.glob("*.log"))
    monkeypatch.setattr(sys, "argv", ["x", str(raw), "--cards", str(CATALOG),
                                      "--value-output", str(env.processed),
                                      "--policy-output", str(env.policy),
                                      "--evidence-output", str(env.evidence)])
    assert pcm.main() == 1
    assert json.loads(capsys.readouterr().out)["processors"]["policy"]["FAILED"] == 1


def test_value_dataset_destination_as_policy_output_is_a_failure(env: Env, tmp_path: Path):
    raw_dir = tmp_path / "other"
    env.collector().scan_once()
    wrong = tmp_path / "processed_real" / "policy"
    result = pcm.process_completed_match(
        next(env.raw.glob("*.log")), pcm.Outputs(raw_dir / "v", wrong, raw_dir / "e"), CATALOG)["policy"]
    assert result.status == pcm.FAILED
    assert result.detail["game_skip_reasons"] == {"VALUE_DATASET_DESTINATION": 1}


def test_unknown_importer_reason_fails_closed(env: Env, monkeypatch):
    monkeypatch.setattr(pcm, "import_policy_log", lambda *a, **k: {
        "games_imported": 0, "decisions_labeled": 0, "game_skip_reasons": {"INVALID_MATCH_ID": 1}})
    collector = env.collector()
    collector.scan_once()
    assert collector.stats.processor_failures == {"policy": 1}
