"""Explicit allowlist BEFORE file reads. Private IDs never enter published results."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from manamind.cards.catalog import CardCatalog
from manamind.integrations.powerlog.lines import inspect_segment, read_complete_lines, split_games
from manamind.integrations.powerlog.policy_import import PolicyImportError, extract_match

REPO = Path(__file__).resolve().parents[2]
CARDS = ("CORE_EX1_238", "CORE_AT_055", "CORE_ICC_055", "FIR_906")
PRIVATE = REPO / "data/processed_real/card_ir_outcome_parity_1_fc501cee"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


class AllowedData:
    def __init__(self, repo=REPO):
        self.repo = repo
        self.plan_path = repo / "data/processed_policy_prepare_1/split_plan.json"
        plan = read(self.plan_path)
        self.held = set(plan["parts"]["fresh_holdout"])
        self.allowed = set().union(*(set(plan["parts"][p]) for p in ("train", "validation", "test_seen")))
        all_ids = self.held | self.allowed
        if self.held & self.allowed or len({g[:16] for g in all_ids}) != len(all_ids):
            raise ValueError("Split overlap or prefix collision; no match files opened")
        self.prefixes = {g[:16] for g in self.allowed}
        self.held_prefixes = {g[:16] for g in self.held}

    def files(self, relative, pattern, full_ids=False):
        # Filtering is deliberately before .read_bytes(), .read_text() or parsing.
        for path in sorted((self.repo / relative).glob(pattern)):
            key = path.stem if full_ids else (path.parent.name if pattern.endswith("observations.jsonl") else path.stem)[:16]
            if key in (self.allowed if full_ids else self.prefixes):
                yield path

    def policy(self):
        games, manifest = {}, {}
        for path in self.files("data/processed_policy_prepare_1/dataset", "*.jsonl", full_ids=True):
            raw = path.read_bytes()
            manifest[path.relative_to(self.repo).as_posix()] = hashlib.sha256(raw).hexdigest()
            rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
            if any(r["game_id"] != path.stem for r in rows):
                raise ValueError("Policy file identity mismatch")
            games[path.stem] = sorted(rows, key=lambda r: int(r["decision_id"].rsplit(":", 1)[1]))
        return games, manifest


def selected(row):
    action = row["legal_actions"][row["chosen_action_index"]]
    return action.get("type") == "PLAY_CARD" and action.get("card_id") in CARDS


def prepare():
    """Freeze allowed inputs and pre-action contexts before the forecast/scoring run."""
    source = AllowedData()
    games, hashes = source.policy()
    chosen = {g: [r for r in rows if selected(r)] for g, rows in games.items() if any(selected(r) for r in rows)}
    contexts, reasons, stats = {}, {}, Counter()
    catalog_path = REPO / "data/cards/standard_current_enUS.json"
    catalog = CardCatalog.from_json(catalog_path)
    for number, (game, rows) in enumerate(sorted(chosen.items()), start=1):
        path = REPO / "data/raw/collected" / (game[:16] + ".log")
        assert game in source.allowed and game[:16] not in source.held_prefixes
        if not path.exists():
            for row in rows:
                reasons[row["decision_id"]] = "NO_SAFELY_ADDRESSABLE_RAW"
            continue
        hashes[path.relative_to(REPO).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        collected = {}
        try:
            segments = list(split_games(read_complete_lines(path)))
            if len(segments) != 1 or inspect_segment(segments[0]).start_key != game:
                raise ValueError("PER_MATCH_IDENTITY_MISMATCH")
            imported, _ = extract_match(segments[0], catalog,
                                      lambda decision, found: collected.__setitem__(decision, found), prepare_actions=True)
            imported = {r["decision_id"]: r for r in imported}
            for row in rows:
                key = row["decision_id"]
                regenerated = imported.get(key)
                same = regenerated is not None and regenerated["provenance"]["state_hash"] == row["provenance"]["state_hash"]
                if same and collected.get(key) is not None:
                    contexts[key] = collected[key].to_dict()
                    reasons[key] = "EXACT_DECISION_AND_STATE_HASH"
                else:
                    reasons[key] = "CONTEXT_NOT_EXACTLY_ASSOCIATED"
        except (PolicyImportError, ValueError):
            for row in rows:
                reasons[row["decision_id"]] = "RAW_CONTEXT_REEXTRACTION_REFUSED"
        stats["raw_matches_reextracted"] += 1
        print(f"pre-action context preparation: {number}/{len(chosen)} eligible selected games", flush=True)
    # Freeze evidence bytes, but do not inspect outcome content until predictions exist.
    evidence_paths = list(source.files("data/processed_evidence/collected", "*/observations.jsonl"))
    for path in evidence_paths:
        hashes[path.relative_to(REPO).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    hashes[source.plan_path.relative_to(REPO).as_posix()] = hashlib.sha256(source.plan_path.read_bytes()).hexdigest()
    hashes[catalog_path.relative_to(REPO).as_posix()] = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    PRIVATE.mkdir(parents=True, exist_ok=False)
    write_new(PRIVATE / "inputs.json", hashes)
    write_new(PRIVATE / "contexts.json", dict(contexts=contexts, reasons=reasons))
    public = dict(allowed_policy_games=len(games), selected_games=len(chosen),
                  selected_actions_by_card=dict(Counter(r["legal_actions"][r["chosen_action_index"]]["card_id"] for rows in chosen.values() for r in rows)),
                  pre_context_associations=dict(Counter(reasons.values())),
                  raw_matches_reextracted=stats["raw_matches_reextracted"], eligible_evidence_files=len(evidence_paths),
                  protected_policy_files_skipped_unopened=len(source.held),
                  protected_evidence_directories_skipped_unopened=sum(p.is_dir() and p.name[:16] in source.held_prefixes for p in (REPO / "data/processed_evidence/collected").iterdir()),
                  unknown_evidence_directories_skipped_unopened=sum(p.is_dir() and p.name[:16] not in source.prefixes | source.held_prefixes for p in (REPO / "data/processed_evidence/collected").iterdir()),
                  aggregate_inputs_sha256=hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
                  split_plan_sha256=hashes[source.plan_path.relative_to(REPO).as_posix()],
                  privacy="Only aggregate hashes/counts published; per-match paths, IDs and contexts stay ignored; aggregate observed_facts file never opened")
    write_new(Path(__file__).parent / "data_manifest.json", public)
    print(json.dumps(public, indent=2))


if __name__ == "__main__":
    prepare()
