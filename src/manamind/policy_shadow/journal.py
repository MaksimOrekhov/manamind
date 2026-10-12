"""Append-only, thread-safe journal of the model shadow; a file of its own, never the Policy prediction journal."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

MODEL_SHADOW_MAX_BYTES = 64 * 1024 * 1024


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ModelShadowJournal:
    """One JSON object per line. At ``max_bytes`` the file is renamed (never deleted) to ``<stem>.<UTC>.jsonl``."""

    def __init__(self, path: Path, *, max_bytes: int = MODEL_SHADOW_MAX_BYTES) -> None:
        self.path = Path(path)
        self.max_bytes = max_bytes
        self._lock = threading.Lock()

    @classmethod
    def beside(cls, prediction_journal: Path, **kwargs) -> ModelShadowJournal:
        prediction_journal = Path(prediction_journal)
        return cls(prediction_journal.with_name(f"{prediction_journal.stem}.model_shadow.jsonl"), **kwargs)

    def append(self, row: dict) -> None:
        text = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                size = self.path.stat().st_size
            except FileNotFoundError:
                size = 0
            if size >= self.max_bytes:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                target, counter = self.path.with_name(f"{self.path.stem}.{stamp}.jsonl"), 0
                while target.exists():          # never replace an earlier rotation, even within one clock tick
                    counter += 1
                    target = self.path.with_name(f"{self.path.stem}.{stamp}-{counter}.jsonl")
                self.path.replace(target)
            with self.path.open("a", encoding="utf-8", newline="\n") as file:
                file.write(text + "\n")
                file.flush()
