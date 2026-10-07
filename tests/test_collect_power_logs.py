from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from hslog import LogParser

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import collect_power_logs as cpl  # noqa: E402
from power_log_fixtures import SECRET_NAME, Clock, build_game, to_text  # noqa: E402

# The collector may load the module as ``scripts.process_completed_match``; patch that very object.
pcm = sys.modules[cpl.process_completed_match.__module__]
CATALOG = ROOT / "data" / "cards" / "standard_current_enUS.json"


class Env:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path / "Logs"
        self.root.mkdir()
        self.raw = tmp_path / "raw"
        self.processed = tmp_path / "processed"
        self.messages: list[str] = []

    def collector(self, **kwargs) -> cpl.Collector:
        return cpl.Collector(
            self.root, self.raw, self.processed, CATALOG,
            emit=self.messages.append, **kwargs,
        )

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def outputs(self) -> list[Path]:
        return sorted(self.processed.glob("*.jsonl")) if self.processed.exists() else []


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def test_completed_ranked_standard_match_is_imported_once(env: Env):
    env.write("Power.log", to_text(build_game(seed=1)))
    collector = env.collector()
    collector.scan_once()
    collector.scan_once()  # unchanged file is not processed again

    assert collector.stats.matches_imported == 1
    assert len(env.outputs()) == 1
    rows = [json.loads(line) for line in env.outputs()[0].read_text(encoding="utf-8").splitlines()]
    assert rows and {row["target"] for row in rows} == {1.0}
    assert len(list(env.raw.glob("*.log"))) == 1  # raw slice kept only in the ignored raw dir
    assert not list(env.processed.glob("*.part"))


def test_same_match_seen_in_a_second_file_is_a_duplicate(env: Env):
    game = build_game(seed=2)
    env.write("Power.log", to_text(game))
    env.write("Power_old.log", to_text(game))
    collector = env.collector()
    collector.scan_once()

    assert collector.stats.matches_imported == 1
    assert collector.stats.duplicates == 1
    assert len(env.outputs()) == 1


def test_incomplete_growing_match_is_not_imported_until_it_completes(env: Env):
    full = build_game(seed=3)
    cut = next(i for i, line in enumerate(full) if "tag=PLAYSTATE" in line)
    path = env.write("Power.log", to_text(full[:cut]))
    collector = env.collector()
    collector.scan_once()
    assert env.outputs() == [] and collector.stats.matches_imported == 0
    assert cpl.SKIPPED_INCOMPLETE not in collector.stats.skipped  # retried, not decided

    path.write_text(to_text(full), encoding="utf-8")
    collector.scan_once()
    assert collector.stats.matches_imported == 1


def test_eof_is_never_completion_and_partial_last_line_is_ignored(env: Env):
    full = build_game(seed=4)
    text = to_text(full, trailing_newline=False)  # last line (COMPLETE) has no newline yet
    env.write("Power.log", text)
    collector = env.collector()
    collector.scan_once()
    assert collector.stats.matches_imported == 0

    env.write("Power.log", text + "\n")
    collector.scan_once()
    assert collector.stats.matches_imported == 1


def test_transient_parse_failure_does_not_crash_and_is_retried(env: Env, monkeypatch):
    env.write("Power.log", to_text(build_game(seed=5)))
    real_import = pcm.import_power_log
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError(f"boom {SECRET_NAME}")
        return real_import(*args, **kwargs)

    monkeypatch.setattr(pcm, "import_power_log", flaky)
    collector = env.collector()
    collector.scan_once()
    assert collector.stats.parse_failures == 1 and env.outputs() == []
    assert not list((env.raw / ".pending").glob("*"))  # no half-written leftovers

    collector.scan_once()
    assert collector.stats.matches_imported == 1
    assert SECRET_NAME not in "\n".join(env.messages)


def test_unreadable_file_does_not_stop_the_collector(env: Env, monkeypatch):
    env.write("Power.log", to_text(build_game(seed=6)))

    def broken(_path):
        raise OSError("locked")

    monkeypatch.setattr(cpl, "read_complete_lines", broken)
    collector = env.collector()
    collector.scan_once()
    assert collector.stats.parse_failures == 1
    monkeypatch.undo()
    collector.scan_once()
    assert collector.stats.matches_imported == 1


def test_non_standard_match_is_skipped(env: Env):
    env.write("Power.log", to_text(build_game(seed=7, format_type="FT_WILD")))
    collector = env.collector()
    collector.scan_once()
    assert collector.stats.skipped == {cpl.SKIPPED_NOT_STANDARD: 1}
    assert env.outputs() == []


def test_non_ranked_match_is_skipped(env: Env):
    env.write("Power.log", to_text(build_game(seed=8, game_type="GT_CASUAL")))
    collector = env.collector()
    collector.scan_once()
    assert collector.stats.skipped == {cpl.SKIPPED_NOT_RANKED: 1}
    assert env.outputs() == []


def test_multiple_completed_matches_in_one_log_each_use_their_own_metadata(env: Env):
    clock = Clock()
    games = [
        build_game(seed=10, variant=0, result="WON", clock=clock),
        build_game(seed=11, variant=1, result="LOST", clock=clock),
        build_game(seed=12, variant=2, result="TIED", clock=clock),
    ]
    env.write("Power.log", to_text(*games))
    collector = env.collector()
    collector.scan_once()

    assert collector.stats.matches_imported == 3
    targets = sorted(
        json.loads(path.read_text(encoding="utf-8").splitlines()[0])["target"]
        for path in env.outputs()
    )
    assert targets == [0.0, 0.5, 1.0]


def test_global_game_meta_would_mislabel_games_but_collector_does_not(env: Env):
    """Game A is Ranked Standard; Game B prints no mode at all; C is Casual Wild.

    hslog keeps one global game_meta, so a whole-file parse reports A's values for
    the entire log. The collector must admit only A.
    """
    clock = Clock()
    a = build_game(seed=20, variant=0, clock=clock)
    b = build_game(seed=21, variant=1, game_type=None, format_type=None, clock=clock)
    c = build_game(seed=22, variant=2, game_type="GT_CASUAL", format_type="FT_WILD", clock=clock)
    text = to_text(a, b)

    parser = LogParser()
    parser.read(text.splitlines(keepends=True))
    assert len(parser.games) == 2
    assert parser.game_meta["GameType"].name == "GT_RANKED"  # B silently inherits A

    env.write("Power.log", to_text(a, b, c))
    collector = env.collector()
    collector.scan_once()
    assert collector.stats.matches_imported == 1
    assert collector.stats.skipped == {
        cpl.SKIPPED_METADATA_AMBIGUOUS: 1,
        cpl.SKIPPED_NOT_RANKED: 1,
    }
    assert len(env.outputs()) == 1


def test_wild_game_before_ranked_standard_game_does_not_taint_either(env: Env):
    clock = Clock()
    wild = build_game(seed=30, variant=0, format_type="FT_WILD", clock=clock)
    standard = build_game(seed=31, variant=1, clock=clock)
    env.write("Power.log", to_text(wild, standard))
    collector = env.collector()
    collector.scan_once()
    assert collector.stats.matches_imported == 1
    assert collector.stats.skipped == {cpl.SKIPPED_NOT_STANDARD: 1}


def test_conflicting_metadata_inside_one_game_fails_closed(env: Env):
    env.write("Power.log", to_text(build_game(seed=40, extra_meta=["GameType=GT_CASUAL"])))
    collector = env.collector()
    collector.scan_once()
    assert collector.stats.skipped == {cpl.SKIPPED_METADATA_AMBIGUOUS: 1}
    assert env.outputs() == []


def test_game_that_starts_mid_game_is_not_imported(env: Env):
    env.write("Power.log", to_text(build_game(seed=41, turn_in_header=5)))
    collector = env.collector()
    collector.scan_once()
    assert collector.stats.skipped == {cpl.SKIPPED_MID_GAME_START: 1}
    assert env.outputs() == []


def test_restart_is_idempotent_with_and_without_state_file(env: Env):
    env.write("Power.log", to_text(build_game(seed=50)))
    env.collector().scan_once()
    assert len(env.outputs()) == 1

    restarted = env.collector()
    restarted.scan_once()
    assert restarted.stats.matches_imported == 0 and len(env.outputs()) == 1

    (env.raw / "collector_state.json").unlink()  # lost state: importer fingerprint still dedups
    again = env.collector()
    again.scan_once()
    assert again.stats.matches_imported == 0
    assert len(env.outputs()) == 1
    assert again.stats.duplicates == 1


def test_corrupt_state_file_does_not_crash(env: Env):
    env.raw.mkdir(parents=True)
    (env.raw / "collector_state.json").write_text("{not json", encoding="utf-8")
    env.write("Power.log", to_text(build_game(seed=51)))
    collector = env.collector()
    collector.scan_once()
    assert collector.stats.matches_imported == 1


def test_rotated_and_new_session_files_do_not_duplicate_old_matches(env: Env):
    clock = Clock()
    first = build_game(seed=60, variant=0, clock=clock)
    second = build_game(seed=61, variant=1, clock=clock)
    env.write("Hearthstone_2026_01_01_10_00_00/Power.log", to_text(first))
    collector = env.collector()
    collector.scan_once()
    assert len(env.outputs()) == 1

    # Rotation: old content renamed to Power_old.log, new Power.log continues; a
    # restart creates another session folder that also contains the old match.
    env.write("Hearthstone_2026_01_01_10_00_00/Power_old.log", to_text(first))
    env.write("Hearthstone_2026_01_01_10_00_00/Power.log", to_text(second))
    env.write("Hearthstone_2026_01_01_12_00_00/Power.log", to_text(first, second))
    collector.scan_once()
    restarted = env.collector()
    restarted.scan_once()

    assert len(env.outputs()) == 2
    assert collector.stats.matches_imported == 2  # first + the genuinely new second match
    assert restarted.stats.matches_imported == 0


def test_candidate_scan_is_bounded_to_recent_sessions(tmp_path: Path):
    for index in range(5):
        session = tmp_path / f"Hearthstone_2026_01_0{index + 1}_00_00_00"
        session.mkdir()
        (session / "Power.log").write_text("", encoding="utf-8")
        os.utime(session, (1000 + index, 1000 + index))
    found = cpl.candidate_files(tmp_path, max_sessions=2)
    assert [p.parent.name for p in found] == [
        "Hearthstone_2026_01_05_00_00_00",
        "Hearthstone_2026_01_04_00_00_00",
    ]


def test_normal_output_and_summary_never_contain_player_names(env: Env):
    env.write("Power.log", to_text(build_game(seed=70), build_game(seed=71, variant=1, game_type="GT_CASUAL")))
    collector = env.collector()
    collector.scan_once()
    summary_path = collector.write_summary()
    everything = "\n".join(env.messages) + summary_path.read_text(encoding="utf-8")
    everything += (env.raw / "collector_state.json").read_text(encoding="utf-8")

    assert SECRET_NAME not in everything and "Opponent#" not in everything
    assert any("Ranked Standard · WIN" in message for message in env.messages)
    assert json.loads(summary_path.read_text(encoding="utf-8"))["matches_imported"] == 1
    for path in env.outputs():
        assert SECRET_NAME not in path.read_text(encoding="utf-8")  # importer contract


def test_cli_once_prints_compact_privacy_safe_output(env: Env, capsys, monkeypatch):
    env.write("Power.log", to_text(build_game(seed=80)))
    monkeypatch.setattr(sys, "argv", [
        "collect_power_logs.py", "--logs-root", str(env.root), "--once",
        "--raw-output", str(env.raw), "--processed-output", str(env.processed),
        "--cards", str(CATALOG),
    ])
    assert cpl.main() == 0
    captured = capsys.readouterr()
    assert "ManaMind collector" in captured.out and "1 imported" in captured.out
    assert SECRET_NAME not in captured.out + captured.err
    assert len(env.outputs()) == 1


def test_cli_requires_an_existing_logs_root(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MANAMIND_HEARTHSTONE_LOGS", raising=False)
    monkeypatch.setattr(sys, "argv", ["collect_power_logs.py", "--logs-root", str(tmp_path / "missing")])
    with pytest.raises(SystemExit):
        cpl.main()


def test_no_real_raw_or_processed_data_is_tracked_and_no_log_fixtures_exist():
    assert not list((ROOT / "tests").rglob("*.log"))
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "data/raw", "data/processed_real"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git unavailable")
    assert tracked == []


def _line_index(lines: list[str], needle: str) -> int:
    return next(i for i, line in enumerate(lines) if needle in line)


def _state_games(env: Env) -> dict:
    path = env.raw / "collector_state.json"
    return json.loads(path.read_text(encoding="utf-8"))["games"] if path.exists() else {}


def test_create_game_before_mode_lines_stays_retryable_then_imports(env: Env):
    full = build_game(seed=90)
    cut = _line_index(full, "GameType=")  # CREATE_GAME and header written, mode not yet
    path = env.write("Power.log", to_text(full[:cut]))
    collector = env.collector()
    collector.scan_once()

    assert collector.stats.skipped == {}
    assert _state_games(env) == {} and collector._known == {}
    assert env.outputs() == []

    path.write_text(to_text(full), encoding="utf-8")  # rest of the match arrives
    collector.scan_once()
    assert collector.stats.matches_imported == 1
    assert collector.stats.skipped == {}


def test_only_one_of_game_type_and_format_stays_retryable(env: Env):
    full = build_game(seed=91)
    cut = _line_index(full, "FormatType=")  # GameType written, FormatType not yet
    path = env.write("Power.log", to_text(full[:cut]))
    collector = env.collector()
    collector.scan_once()
    assert collector.stats.skipped == {} and _state_games(env) == {}

    path.write_text(to_text(full), encoding="utf-8")
    collector.scan_once()
    assert collector.stats.matches_imported == 1


def test_wrong_mode_is_not_decided_until_the_game_completes(env: Env):
    full = build_game(seed=92, game_type="GT_CASUAL")
    cut = _line_index(full, "tag=PLAYSTATE")
    path = env.write("Power.log", to_text(full[:cut]))
    collector = env.collector()
    collector.scan_once()
    assert collector.stats.skipped == {} and _state_games(env) == {}

    path.write_text(to_text(full), encoding="utf-8")
    collector.scan_once()
    assert collector.stats.skipped == {cpl.SKIPPED_NOT_RANKED: 1}


def test_missing_or_conflicting_metadata_is_terminal_only_after_completion(env: Env):
    clock = Clock()
    missing = build_game(seed=93, game_type=None, format_type=None, clock=clock)
    conflicting = build_game(seed=94, extra_meta=["FormatType=FT_WILD"], clock=clock)
    env.write("Power.log", to_text(missing, conflicting))
    collector = env.collector()
    collector.scan_once()

    assert collector.stats.skipped == {cpl.SKIPPED_METADATA_AMBIGUOUS: 2}
    assert set(_state_games(env).values()) == {cpl.SKIPPED_METADATA_AMBIGUOUS}
    assert env.outputs() == []


def test_completed_casual_and_wild_keep_their_final_skip_statuses(env: Env):
    clock = Clock()
    casual = build_game(seed=95, game_type="GT_CASUAL", clock=clock)
    wild = build_game(seed=96, format_type="FT_WILD", clock=clock)
    env.write("Power.log", to_text(casual, wild))
    collector = env.collector()
    collector.scan_once()

    assert collector.stats.skipped == {cpl.SKIPPED_NOT_RANKED: 1, cpl.SKIPPED_NOT_STANDARD: 1}
    assert sorted(_state_games(env).values()) == sorted(
        [cpl.SKIPPED_NOT_RANKED, cpl.SKIPPED_NOT_STANDARD]
    )
    assert env.outputs() == []
