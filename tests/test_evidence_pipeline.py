"""Evidence pipeline: determinism, output safety, privacy canary, schema guard, CLI."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from evidence_fixtures import ACCOUNT_LO, BATTLETAG, blk, flat, meta, play_game, tag

from manamind.evidence import EXTRACTOR_VERSION
from manamind.evidence import extract as extract_module
from manamind.evidence import pipeline as pipeline_module
from manamind.evidence.extract import GameResult
from manamind.evidence.pipeline import run_extraction
from manamind.evidence.privacy import PrivacyError
from manamind.evidence.schema import SchemaError, validate_observation

ROOT = Path(__file__).resolve().parents[1]
BODY = flat(tag(6, "ZONE", "PLAY"), blk("POWER", 6, flat(meta("DAMAGE", 3, 50), tag(50, "DAMAGE", 3),
                                                       tag(50, "LAST_AFFECTED_BY", 6))))
MINION_BODY = flat(tag(7, "ZONE", "PLAY"), blk("POWER", 7, flat(meta("DAMAGE", 3, 50), tag(50, "DAMAGE", 3),
                                                                tag(50, "LAST_AFFECTED_BY", 7))))
SECRETS = (BATTLETAG, "SecretPlayer", "Rival", "7777", ACCOUNT_LO, "PlayerName", "GameAccountId", "BattleTag")


@pytest.fixture()
def logs(tmp_path):
    folder = tmp_path / "logs"
    folder.mkdir()
    (folder / "a.log").write_text(play_game(BODY, seed=11).text(), encoding="utf-8")
    (folder / "b.log").write_text(play_game(MINION_BODY, entity=7, seed=12).text(), encoding="utf-8")
    (folder / "a_copy.log").write_text(play_game(BODY, seed=11).text(), encoding="utf-8")  # same game twice
    return folder


def all_output(directory: Path) -> str:
    return "".join(path.read_text(encoding="utf-8") for path in sorted(directory.iterdir()))


def test_output_is_deterministic_deduplicated_and_never_overwritten(logs, tmp_path):
    one = run_extraction([logs], tmp_path / "one")
    two = run_extraction([logs], tmp_path / "two")
    assert one["games"]["seen"] == 2  # the duplicate slice was dropped by its game key
    for name in ("observations.jsonl", "games.jsonl", "manifest.json"):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()
    assert two["summary"]["observations"] >= 2
    with pytest.raises(FileExistsError):
        run_extraction([logs], tmp_path / "one")
    versioned = run_extraction([logs], tmp_path / "three", extractor_version="evidence-test-other")
    assert versioned["extractor_version"] == "evidence-test-other"
    ids_one = {json.loads(line)["observation_id"] for line in (tmp_path / "one" / "observations.jsonl").open(encoding="utf-8")}
    ids_three = {json.loads(line)["observation_id"] for line in (tmp_path / "three" / "observations.jsonl").open(encoding="utf-8")}
    assert ids_one and not ids_one & ids_three


def test_privacy_canary_is_absent_from_every_output_file(logs, tmp_path):
    manifest = run_extraction([logs], tmp_path / "out")
    text = all_output(tmp_path / "out")
    for secret in SECRETS:
        assert secret not in text
    assert manifest["privacy_scan"]["leaks"] == 0 and manifest["privacy_scan"]["sentinels_checked"] >= 3
    assert "model_input_allowed\":false" in text.replace(" ", "")


def test_exception_messages_never_reach_outputs(logs, tmp_path, monkeypatch):
    def boom(self):
        raise ValueError(f"unexpected {BATTLETAG}")

    monkeypatch.setattr(extract_module.Walker, "walk", boom)
    manifest = run_extraction([logs], tmp_path / "out")
    assert manifest["games"]["skipped"] == {"EXCEPTION_ValueError": 2}
    for secret in SECRETS:
        assert secret not in all_output(tmp_path / "out")


def test_a_leak_fails_the_run_and_removes_the_output(logs, tmp_path, monkeypatch):
    real = pipeline_module.extract_game

    def leaky(*args, **kwargs):
        result = real(*args, **kwargs)
        for observation in result.observations:
            observation["subject"]["related_card_ids"].append(BATTLETAG)
        return result

    monkeypatch.setattr(pipeline_module, "extract_game", leaky)
    with pytest.raises(PrivacyError):
        run_extraction([logs], tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_cli_prints_aggregates_only_and_refuses_existing_output(logs, tmp_path, capsys, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import extract_evidence

    code = extract_evidence.main(["--input", str(logs), "--output", str(tmp_path / "cli")])
    out = capsys.readouterr()
    assert code == 0
    summary = json.loads(out.out)
    assert summary["privacy_scan"]["leaks"] == 0 and summary["games"]["processed"] == 2
    assert not any(secret in out.out + out.err for secret in SECRETS)
    assert extract_evidence.main(["--input", str(logs), "--output", str(tmp_path / "cli")]) == 2

    def explode(*args, **kwargs):
        raise RuntimeError(BATTLETAG)

    monkeypatch.setattr(extract_evidence, "run_extraction", explode)
    assert extract_evidence.main(["--input", str(logs), "--output", str(tmp_path / "cli2")]) == 1
    err = capsys.readouterr().err
    assert "RuntimeError" in err and BATTLETAG not in err


def test_source_has_no_name_leaking_constructs():
    forbidden = ("repr(", "print(", "PlayerReference", ".player.name", "traceback", "logging")
    allowed_regex_module = "privacy.py"
    for path in sorted((ROOT / "src" / "manamind" / "evidence").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path.name} uses {token}"
        if path.name != allowed_regex_module:
            assert "PlayerName" not in text, path.name


def test_schema_rejects_inference_without_inputs_fact_with_inputs_and_model_input(logs, tmp_path):
    run_extraction([logs], tmp_path / "out")
    rows = [json.loads(line) for line in (tmp_path / "out" / "observations.jsonl").open(encoding="utf-8")]
    good = next(r for r in rows if r["inferences"])
    validate_observation(good)

    broken = copy.deepcopy(good)
    broken["inferences"][0]["inputs"] = []
    with pytest.raises(SchemaError):
        validate_observation(broken)
    broken = copy.deepcopy(good)
    broken["facts"][0]["inputs"] = ["f1"]
    with pytest.raises(SchemaError):
        validate_observation(broken)
    broken = copy.deepcopy(good)
    broken["privacy"]["model_input_allowed"] = True
    with pytest.raises(SchemaError):
        validate_observation(broken)
    broken = copy.deepcopy(good)
    broken["facts"][0]["visibility"] = "OFFLINE_ONLY_HIDDEN"
    with pytest.raises(SchemaError):
        validate_observation(broken)  # the hidden flag must agree with the facts
    broken = copy.deepcopy(good)
    broken["facts"][0]["data"]["entity"] = {"handle": 1, "card_id": "Zorbak#4242"}
    with pytest.raises(SchemaError):
        validate_observation(broken)


def test_default_version_is_in_provenance(logs, tmp_path):
    run_extraction([logs], tmp_path / "out")
    first = json.loads((tmp_path / "out" / "observations.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert first["provenance"]["extractor_version"] == EXTRACTOR_VERSION
    assert first["provenance"]["source_kind"] == "COLLECTED_SLICE"
    assert GameResult  # exported for tests that substitute the extractor


def test_script_runs_as_a_program(logs, tmp_path):
    import subprocess

    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "extract_evidence.py"), "--input", str(logs),
         "--output", str(tmp_path / "proc")],
        capture_output=True, text=True, encoding="utf-8", env={**__import__("os").environ, "PYTHONUTF8": "1"},
    )
    assert done.returncode == 0, done.stderr
    assert not any(secret in done.stdout + done.stderr for secret in SECRETS)
