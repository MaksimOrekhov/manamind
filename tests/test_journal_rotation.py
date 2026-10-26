"""JOURNAL-ROTATION-SAFETY-1: rotating the Outcome/Strategy shadow files must never overwrite or lose a row."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from manamind.live import prediction_journal
from manamind.live.prediction_journal import PredictionJournal

FROZEN = "20261026T120000000000Z"


class FakeDatetime:
    """Stands in for ``datetime`` inside the journal module: ``now()`` yields the given stamps (the last one repeats)."""

    def __init__(self, *stamps):
        self.stamps = list(stamps)

    def now(self, tz=None):
        stamp = self.stamps.pop(0) if len(self.stamps) > 1 else self.stamps[0]
        return datetime.strptime(stamp, "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc)

    def __getattr__(self, name):                      # anything else the module needs from datetime
        return getattr(datetime, name)


def snap(seq):
    return SimpleNamespace(game_key="g" * 64, seq=seq, decision={"options_id": 1}, state_hash="h" * 64)


WRITERS = {
    "outcome": (lambda j: j.shadow_path, lambda j, s: j.outcome_shadow(s, {"schema": "x", "actions": ["p" * 60]})),
    "strategy": (lambda j: j.strategy_path, lambda j, s: j.strategy_shadow(s, {"schema": "x", "ranking": ["p" * 60]})),
}


@pytest.fixture
def frozen_clock(monkeypatch):
    monkeypatch.setattr(prediction_journal, "datetime", FakeDatetime(FROZEN))


def rotation_index(path):
    parts = path.name.split(".")
    return int(parts[-2]) if parts[-2].isdigit() and len(parts[-2]) == 6 else 0     # legacy names count as 0


def rows_of(journal, kind):
    active = WRITERS[kind][0](journal)
    files = sorted(active.parent.glob(active.stem + ".*.jsonl"), key=lambda p: (rotation_index(p), p.name)) + [active]
    return [json.loads(line)["seq"] for f in files if f.exists() for line in f.read_text(encoding="utf-8").splitlines()]


def archives(journal, kind):
    active = WRITERS[kind][0](journal)
    return sorted(active.parent.glob(active.stem + ".*.jsonl"))


@pytest.mark.parametrize("kind", sorted(WRITERS))
def test_identical_timestamps_never_overwrite_an_archive(tmp_path, frozen_clock, kind):
    journal = PredictionJournal(tmp_path / "journal.jsonl", shadow_max_bytes=1)
    write = WRITERS[kind][1]
    for seq in range(1, 21):
        write(journal, snap(seq))
    assert len(archives(journal, kind)) == 19                     # every row but the last rotated into its own archive
    assert rows_of(journal, kind) == list(range(1, 21))           # each id exactly once, original order
    assert journal.rotation_failures == 0


@pytest.mark.parametrize("kind", sorted(WRITERS))
def test_restart_keeps_existing_archives_and_order(tmp_path, frozen_clock, kind):
    write = WRITERS[kind][1]
    first = PredictionJournal(tmp_path / "journal.jsonl", shadow_max_bytes=1)
    for seq in range(1, 6):
        write(first, snap(seq))
    before = {p.name: p.read_bytes() for p in archives(first, kind)}
    second = PredictionJournal(tmp_path / "journal.jsonl", shadow_max_bytes=1)       # new process, same directory
    for seq in range(6, 11):
        write(second, snap(seq))
    after = {p.name: p.read_bytes() for p in archives(second, kind)}
    assert all(after[name] == data for name, data in before.items())
    assert rows_of(second, kind) == list(range(1, 11))


@pytest.mark.parametrize("kind", sorted(WRITERS))
def test_a_preexisting_archive_with_the_colliding_name_is_untouched(tmp_path, frozen_clock, kind):
    journal = PredictionJournal(tmp_path / "journal.jsonl", shadow_max_bytes=1)
    active = WRITERS[kind][0](journal)
    sentinel_names = [f"{active.stem}.{FROZEN}.000001.jsonl", f"{active.stem}.{FROZEN}.jsonl"]   # new and legacy style
    for name in sentinel_names:
        (tmp_path / name).write_text('{"seq":-1}\n', encoding="utf-8")
    write = WRITERS[kind][1]
    for seq in range(1, 4):
        write(journal, snap(seq))
    for name in sentinel_names:
        assert (tmp_path / name).read_text(encoding="utf-8") == '{"seq":-1}\n'
    assert sorted(r for r in rows_of(journal, kind) if r > 0) == [1, 2, 3]


def test_the_index_ignores_the_clock_even_when_time_runs_backwards(tmp_path, monkeypatch):
    monkeypatch.setattr(prediction_journal, "datetime", FakeDatetime(
        "20261026T120000000000Z", "20261026T110000000000Z", "20261026T130000000000Z", "20261026T100000000000Z"))
    journal = PredictionJournal(tmp_path / "journal.jsonl", shadow_max_bytes=1)
    for seq in range(1, 6):
        journal.outcome_shadow(snap(seq), {"schema": "x"})
    assert sorted(rotation_index(p) for p in archives(journal, "outcome")) == [1, 2, 3, 4]
    by_index = sorted(archives(journal, "outcome"), key=rotation_index)
    seqs = [json.loads(p.read_text(encoding="utf-8").strip())["seq"] for p in by_index]
    assert seqs == [1, 2, 3, 4]                                    # rotation order == index order


def test_both_journals_rotate_independently_and_keep_every_row(tmp_path, frozen_clock):
    journal = PredictionJournal(tmp_path / "journal.jsonl", shadow_max_bytes=1)
    for seq in range(1, 9):
        WRITERS["outcome"][1](journal, snap(seq))
        WRITERS["strategy"][1](journal, snap(100 + seq))
    assert rows_of(journal, "outcome") == list(range(1, 9))
    assert rows_of(journal, "strategy") == list(range(101, 109))
    assert not set(a.name for a in archives(journal, "outcome")) & set(a.name for a in archives(journal, "strategy"))


def test_many_rotations_keep_each_unique_id_exactly_once(tmp_path):
    journal = PredictionJournal(tmp_path / "journal.jsonl", shadow_max_bytes=400)       # real clock, many rotations
    for seq in range(1, 201):
        journal.outcome_shadow(snap(seq), {"schema": "x", "actions": ["q" * 30]})
    seen = rows_of(journal, "outcome")
    assert seen == list(range(1, 201)) and len(archives(journal, "outcome")) > 10


@pytest.mark.parametrize("failure", ["replace", "reserve"])
def test_a_failed_rotation_loses_nothing_and_still_records_the_new_row(tmp_path, frozen_clock, monkeypatch, failure):
    journal = PredictionJournal(tmp_path / "journal.jsonl", shadow_max_bytes=1)
    for seq in range(1, 4):
        journal.outcome_shadow(snap(seq), {"schema": "x"})
    archived_before = {p.name: p.read_bytes() for p in archives(journal, "outcome")}
    real_replace, real_open = os.replace, Path.open

    def broken_replace(src, dst):
        raise PermissionError("locked")

    def broken_open(self, mode="r", *args, **kwargs):
        if mode == "x":
            raise PermissionError("cannot create")
        return real_open(self, mode, *args, **kwargs)

    with monkeypatch.context() as patched:
        if failure == "replace":
            patched.setattr(os, "replace", broken_replace)
        else:
            patched.setattr(Path, "open", broken_open)
        journal.outcome_shadow(snap(4), {"schema": "x"})
        journal.outcome_shadow(snap(5), {"schema": "x"})
    assert os.replace is real_replace and Path.open is real_open
    assert journal.rotation_failures == 2
    assert {p.name: p.read_bytes() for p in archives(journal, "outcome")} == archived_before   # no stray placeholder
    assert rows_of(journal, "outcome") == [1, 2, 3, 4, 5]
    journal.outcome_shadow(snap(6), {"schema": "x"})                                           # rotation works again
    assert rows_of(journal, "outcome") == [1, 2, 3, 4, 5, 6]


def test_an_append_failure_is_not_swallowed(tmp_path, monkeypatch):
    journal = PredictionJournal(tmp_path / "journal.jsonl", shadow_max_bytes=10**9)
    journal.outcome_shadow(snap(1), {"schema": "x"})
    monkeypatch.setattr(PredictionJournal, "_append", lambda self, event, path=None: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        journal.outcome_shadow(snap(2), {"schema": "x"})
    monkeypatch.undo()
    assert rows_of(journal, "outcome") == [1]
