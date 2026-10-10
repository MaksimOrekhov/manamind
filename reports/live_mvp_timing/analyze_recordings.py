"""Read-only, sanitized timing evidence for LIVE-MVP recordings (no raw log output)."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from manamind.cards.catalog import CardCatalog
from manamind.live.replay import recorded_hashes
from manamind.live.session import LiveSession
from manamind.live.snapshot import Snapshot
from manamind.live.recommendation import PolicyRecommender, RecommendationUnavailable

METHOD = re.compile(r"^[DWE] (\S+) (\w+)\.(\w+)\(\) - (.*)$")


class TimingSession(LiveSession):
    def __init__(self, catalog):
        super().__init__(catalog)
        self.line_number = 0
        self.now_ms = 0
        self.method = "TICK"
        self.turn_start = None
        self.menus = {}
        self.active_menu = None
        self.emissions = {}

    def _line(self, line, now_ms):
        self.line_number += 1
        self.now_ms = now_ms
        match = METHOD.match(line)
        self.method = "OTHER"
        if match:
            log_time, owner, method, message = match.groups()
            message = message.strip()
            self.method = f"{owner}.{method}"
            if owner == "GameState" and method == "DebugPrintPower":
                turn = re.match(r"TAG_CHANGE Entity=GameEntity tag=TURN value=(\d+)", message)
                if turn:
                    self.turn_start = {"turn": int(turn[1]), "read_ms": now_ms, "log_time": log_time}
            if self.method == "GameState.DebugPrintOptions":
                start = re.match(r"id=(\d+)", message)
                if start:
                    options_id = int(start[1])
                    gate = self.game.gate if self.game else None
                    self.active_menu = self.menus[options_id] = {
                        "options_id": options_id, "line": self.line_number,
                        "read_ms": now_ms, "log_time": log_time, "turn_start": self.turn_start,
                        "q_created_at_start": gate.q_created if gate else None,
                        "q_ended_at_start": gate.q_ended if gate else None,
                        "task_lists_created": 0, "task_lists_ended": 0, "emissions": [],
                    }
                if self.active_menu:
                    self.active_menu.update(menu_last_line=self.line_number, menu_last_ms=now_ms,
                                            menu_last_log_time=log_time)
            elif self.active_menu and not self.active_menu.get("send"):
                menu = self.active_menu
                if self.method == "GameState.SendOption":
                    menu["send"] = {"line": self.line_number, "read_ms": now_ms, "log_time": log_time}
                elif owner == "GameState":
                    menu.setdefault("state_superseded", {"line": self.line_number,
                                    "read_ms": now_ms, "method": self.method})
                elif self.method == "PowerTaskList.DebugDump":
                    task = re.match(r"ID=(\d+) ParentID=", message)
                    if task:
                        marker = {"id": int(task[1]), "read_ms": now_ms, "log_time": log_time}
                        menu["task_lists_created"] += 1
                        menu.setdefault("first_task_created", marker)
                        menu["last_task_created"] = marker
                elif self.method == "PowerProcessor.EndCurrentTaskList":
                    task = re.match(r"m_currentTaskList=(\d+)", message)
                    if task:
                        marker = {"id": int(task[1]), "read_ms": now_ms, "log_time": log_time}
                        menu["task_lists_ended"] += 1
                        menu.setdefault("first_task_ended", marker)
                        menu["last_task_ended"] = marker
        super()._line(line, now_ms)

    def _invalidate_current(self):
        snapshot = self.current_snapshot
        if snapshot and snapshot.seq in self.emissions:
            self.emissions[snapshot.seq]["invalidated"] = {
                "read_ms": self.now_ms, "line": self.line_number, "method": self.method,
            }
        super()._invalidate_current()

    def _try_emit(self, game):
        pending = game.gate.pending
        menu = self.menus.get(pending.options_id) if pending else None
        if menu and pending.complete:
            menu.setdefault("complete_ms", self.now_ms)
            if game.gate.settled:
                menu.setdefault("first_gate_ready_ms", self.now_ms)
        before = self.current_snapshot
        super()._try_emit(game)
        snapshot = self.current_snapshot
        if snapshot and snapshot is not before:
            row = {"seq": snapshot.seq, "read_ms": self.now_ms, "line": self.line_number,
                   "turn": snapshot.turn, "available_at_batch_end": False}
            self.emissions[snapshot.seq] = row
            self.menus[snapshot.decision["options_id"]]["emissions"].append(row)

    def tick(self, now_ms, partial_line=False):
        self.now_ms = now_ms
        self.method = "TICK"
        return super().tick(now_ms, partial_line)


def analyze(directory, catalog, journal, scorer=None):
    lines = (directory / "slice.log").read_text(encoding="utf-8").splitlines()
    trace = [json.loads(x) for x in (directory / "tail_trace.jsonl").read_text().splitlines()]
    meta = json.loads((directory / "meta.json").read_text())
    session = TimingSession(catalog)
    hashes = []
    replayed_snapshots = []
    scored = set()
    score_latencies = []
    index = 0
    for row in trace:
        count = int(row["n"])
        chunk = lines[index:index + count]
        index += count
        events = session.feed(chunk, row["t"], catchup=bool(row.get("catchup"))) if count else []
        events += session.tick(row["t"])
        hashes.extend(e.state_hash for e in events if isinstance(e, Snapshot))
        replayed_snapshots.extend(e for e in events if isinstance(e, Snapshot))
        if session.current_snapshot:
            snapshot = session.current_snapshot
            emission = session.emissions[snapshot.seq]
            emission["available_at_batch_end"] = True
            if scorer and snapshot.seq not in scored:
                scored.add(snapshot.seq)
                try:
                    result = scorer.score(snapshot, session)
                    emission["score_result"] = "SCORED"
                    score_latencies.append(result.latency_ms)
                except RecommendationUnavailable as error:
                    emission["score_result"] = str(error)
    if index != len(lines) or any(b["t"] < a["t"] for a, b in zip(trace, trace[1:])):
        raise ValueError("incomplete or non-monotonic trace")
    actual = [x for x in journal if x["match_id"] == meta["game_key"]]
    by_decision = {}
    for row in actual:
        by_decision.setdefault(row["decision_id"], []).append(row)
    journal_summary = []
    for key, rows in by_decision.items():
        _, seq, options_id, _ = key.split(":")
        recommendation = next((x for x in rows if x["event"] == "RECOMMENDATION"), None)
        invalidation = next((x for x in rows if x["event"] == "INVALIDATION"), None)
        result = {"seq": int(seq), "options_id": int(options_id),
                  "events": [x["event"] for x in rows]}
        if recommendation and invalidation:
            result["journal_visible_ms"] = round((datetime.fromisoformat(invalidation["invalidated_at_utc"])
                         - datetime.fromisoformat(recommendation["recommended_at_utc"])).total_seconds() * 1000, 3)
        result["reasons"] = [x["reason"] for x in rows if "reason" in x]
        journal_summary.append(result)
    menus = list(session.menus.values())
    for menu in menus:
        send = menu.get("send")
        if send:
            menu["menu_to_send_ms"] = send["read_ms"] - menu["menu_last_ms"]
            if "last_task_ended" in menu:
                menu["last_task_end_to_send_ms"] = send["read_ms"] - menu["last_task_ended"]["read_ms"]
            menu["ready_state_ms_before_send"] = sum(
                max(0, min(send["read_ms"], e.get("invalidated", {}).get("read_ms", send["read_ms"]))
                    - e["read_ms"]) for e in menu["emissions"] if e["available_at_batch_end"]
            )
    old = {x["decision"]["options_id"]: x for x in
           [json.loads(x) for x in (directory / "snapshots.jsonl").read_text().splitlines()]}
    mismatches = sum(s.decision["options_id"] in old and
                     (s.state_hash != old[s.decision["options_id"]]["state_hash"] or
                      s.decision != old[s.decision["options_id"]]["decision"])
                     for s in replayed_snapshots)
    visible = [x["journal_visible_ms"] for x in journal_summary if "journal_visible_ms" in x]
    return {
        "recording": directory.relative_to(ROOT).as_posix(), "game_key_prefix": meta["game_key"][:16],
        "input_sha256": {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                         for name in ("slice.log", "tail_trace.jsonl", "snapshots.jsonl", "meta.json")},
        "lines": len(lines), "batches": len(trace), "catchup_batches": sum(bool(x.get("catchup")) for x in trace),
        "options_messages": len(menus), "snapshots": len(hashes),
        "recorded_hashes_match": hashes == recorded_hashes(directory),
        "batch_available_snapshots": sum(x["available_at_batch_end"] for x in session.emissions.values()),
        "menus_with_snapshots": sum(bool(m["emissions"]) for m in menus),
        "menus_surviving_until_send": sum(any(e.get("invalidated", {}).get("method") == "GameState.SendOption"
                                             for e in m["emissions"]) for m in menus),
        "same_menu_state_or_actions_mismatches": mismatches,
        "scored_snapshots": sum(e.get("score_result") == "SCORED" for e in session.emissions.values()),
        "scored_unique_menus": sum(any(e.get("score_result") == "SCORED" for e in m["emissions"]) for m in menus),
        "scored_menus_surviving_until_send": sum(any(e.get("score_result") == "SCORED" and
            e.get("invalidated", {}).get("method") == "GameState.SendOption" for e in m["emissions"]) for m in menus),
        "score_refusals": dict(Counter(e["score_result"] for e in session.emissions.values()
                                       if e.get("score_result") not in (None, "SCORED"))),
        "score_latency_ms": {"median": median(score_latencies), "max": max(score_latencies)} if score_latencies else None,
        "journal_visible_ms": {"median": median(visible), "min": min(visible), "max": max(visible)} if visible else None,
        "invalidation_methods": dict(Counter(x["invalidated"]["method"] for x in session.emissions.values()
                                            if "invalidated" in x)),
        "journal_events": dict(Counter(x["event"] for x in actual)),
        "journal": journal_summary, "menus": menus,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--checkpoint-sha256")
    args = parser.parse_args()
    catalog = CardCatalog.from_json(ROOT / "data/cards/standard_current_enUS.json")
    journal_path = ROOT / "data/raw/live/prediction_journal.jsonl"
    journal = [json.loads(x) for x in journal_path.read_text().splitlines()] if journal_path.exists() else []
    if args.checkpoint and not args.checkpoint_sha256:
        parser.error("--checkpoint requires an explicit --checkpoint-sha256")
    scorer = PolicyRecommender(args.checkpoint, expected_sha256=args.checkpoint_sha256) if args.checkpoint else None
    if scorer:
        scorer.require_catalog(catalog)
    results = [analyze(path.resolve(), catalog, journal, scorer) for path in args.recordings]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"label": args.label, "recordings": results}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([{k: x[k] for k in ("game_key_prefix", "options_messages", "snapshots",
               "batch_available_snapshots", "recorded_hashes_match", "invalidation_methods",
               "menus_with_snapshots", "menus_surviving_until_send", "same_menu_state_or_actions_mismatches",
               "scored_snapshots", "scored_unique_menus", "scored_menus_surviving_until_send",
               "journal_visible_ms", "score_refusals")} for x in results]))


if __name__ == "__main__":
    main()
