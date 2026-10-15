"""POLICY-PREPARE-DATA-1: build the isolated, Prepare-aware real-policy corpus and its audit (data only, no training).

One command rebuilds everything into a NEW directory (it refuses to touch an existing one):

    python scripts/build_policy_prepare_corpus.py

Output tree (``data/processed_policy_prepare_1`` by default):
    dataset/      rows imported with ``prepare_actions=True`` (action schema 1 and 2), one JSONL + manifest per match
    baseline_v1/  the same raw logs through the unchanged default importer, for comparison only (never for training)
    audit.json, comparison.json, usage_registry.json, split_plan.json, encoder_check.json, manifest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.domain.serialization import game_state_from_dict  # noqa: E402
from manamind.integrations.powerlog.lines import inspect_segment, read_complete_lines, split_games  # noqa: E402
from manamind.live.snapshot import canonical_json  # noqa: E402
from manamind.training.policy_checkpoint import identity  # noqa: E402
from manamind.training.real_policy import audit_dataset, load_examples  # noqa: E402

from refresh_real_policy_dataset import (  # noqa: E402
    _git_sha, compare_datasets, dataset_identity, quality_summary, raw_logs, read_dataset_unchecked, rebuild_once,
    sha256_file,
)

SPLIT_ALGORITHM = "policy_prepare_data_1_split/1"
DEFAULT_SEED = 20261015
MIN_FRESH_MATCHES = 10            # fewer independent matches than this cannot give a usable held-out estimate
MIN_FRESH_PREPARE_CHOICES = 20    # ... nor can fewer real Prepare choices verify the new action
BATTLETAG = re.compile(r"\w+#\d{3,}")
HANDLE_WORDS = ("entity_id", "entity_name", "option_id", "options_id", "handle", "battletag", "player_name", "account")
RETRAINED_V2 = "data/processed_policy_retrain_1/seed42_v2/policy.pt"
POLICY_V3 = "data/processed_policy_v3/experiment_1/final/architecturev3_seed42/policy.pt"
STORED_DATASETS = ("data/processed_policy_v3/dataset", "data/processed_policy_real/refresh_obs1_final")
FROZEN_V3_SPLIT = "data/processed_policy_v3/frozen_split.json"
CV_FOLDS = "data/processed_policy_v3/experiment_1/cv/folds.json"
USAGE_REGISTRIES = ("data/processed_policy_real/refresh_20261008/experiment_usage_registry.json",
                    "data/processed_policy_real/refresh_20261008_reviewfix/experiment_usage_registry.json",
                    "data/processed_policy_real/refresh_obs1_final/experiment_usage_registry.json")
SHADOW_EVAL_REPORTS = ("reports/model_shadow_eval_1/eval_20261013.json",)


# -- raw log selection -------------------------------------------------------------------------------------------------

def segment_ids(path: Path) -> list[str]:
    """Match identities (hash of the CREATE_GAME header) of every game section in one raw log."""
    found = []
    for segment in split_games(read_complete_lines(Path(path))):
        try:
            key = inspect_segment(segment).start_key
        except Exception:                      # an unreadable section is judged later by the importer
            key = None
        if key:
            found.append(key)
    return found


def select_logs(primary: list[Path], extras: list[Path]) -> tuple[list[Path], list[dict]]:
    """Primary logs always; an extra log only when none of its matches is already supplied.

    This keeps one raw source per match, so a copy of a match (a LIVE slice of a collected game) never competes
    with the collected original.
    """
    covered, sources = set(), []
    for path in sorted(primary, key=lambda p: p.as_posix()):
        ids = segment_ids(path)
        covered.update(ids)
        sources.append({"role": "primary", "matches": len(ids), "sha256": sha256_file(path), "bytes": path.stat().st_size,
                        "name": path.name})
    selected = list(primary)
    for path in sorted(extras, key=lambda p: p.as_posix()):
        ids = segment_ids(path)
        fresh = [i for i in ids if i not in covered]
        record = {"role": "extra", "matches": len(ids), "sha256": sha256_file(path), "bytes": path.stat().st_size,
                  "name": path.name, "new_matches": len(fresh)}
        if ids and len(fresh) == len(ids):
            selected.append(path)
            covered.update(ids)
        else:
            record["role"] = "extra_ignored_duplicate" if ids else "extra_ignored_no_match"
        sources.append(record)
    return selected, sources


def collect_extras(extra_roots: list[Path]) -> list[Path]:
    found = []
    for root in extra_roots:
        root = Path(root)
        if root.is_file():
            found.append(root)
        elif root.is_dir():
            found.extend(p for p in root.rglob("*.log") if p.is_file())
    return found


# -- comparison with the version 1 import of the same raw logs -----------------------------------------------------------

def _chosen(row):
    return row["legal_actions"][row["chosen_action_index"]]


def compare_with_baseline(baseline: list[dict], new: list[dict]) -> dict:
    """Every previously labeled decision must come back byte-identical; anything else is listed, never hidden."""
    old, cur = {r["decision_id"]: r for r in baseline}, {r["decision_id"]: r for r in new}
    identical, differing = 0, Counter()
    differing_examples = []
    for key in sorted(old.keys() & cur.keys()):
        before, after = old[key], cur[key]
        if canonical_json(before) == canonical_json(after):
            identical += 1
            continue
        for field in sorted(set(before) | set(after)):
            if canonical_json(before.get(field)) != canonical_json(after.get(field)):
                differing[field] += 1
        if len(differing_examples) < 10:
            differing_examples.append(key)
    added = [cur[k] for k in sorted(cur.keys() - old.keys())]
    with_prepare = [r for r in added if any(a["type"] == "PREPARE_CARD" for a in r["legal_actions"])]
    return {
        "baseline_decisions": len(old), "new_decisions": len(cur),
        "baseline_matches": len({r["game_id"] for r in baseline}), "new_matches": len({r["game_id"] for r in new}),
        "matches_only_in_baseline": len({r["game_id"] for r in baseline} - {r["game_id"] for r in new}),
        "matches_only_in_new": len({r["game_id"] for r in new} - {r["game_id"] for r in baseline}),
        "common_decisions": len(old.keys() & cur.keys()),
        "common_byte_identical": identical, "common_not_identical": len(old.keys() & cur.keys()) - identical,
        "not_identical_by_field": dict(sorted(differing.items())), "not_identical_examples": differing_examples,
        "baseline_decisions_missing_from_new": len(old.keys() - cur.keys()),
        "added_decisions": len(added),
        "added_with_prepare_in_menu": len(with_prepare),
        "added_without_prepare_in_menu": len(added) - len(with_prepare),
        "added_chosen_types": dict(sorted(Counter(_chosen(r)["type"] for r in added).items())),
        "added_prepare_chosen": sum(_chosen(r)["type"] == "PREPARE_CARD" for r in added),
        "added_schema_versions": dict(sorted(Counter(str(r["action_schema_version"]) for r in added).items())),
    }


def skip_transitions(baseline_dir: Path, new_dir: Path) -> dict:
    """How each importer-visible decision changed status between the two imports (labeled / skip reason)."""
    def statuses(directory):
        result = {}
        for path in sorted(Path(directory).glob("*.audit.json")):
            summary = json.loads(path.read_text(encoding="utf-8"))
            for row in summary["skipped_decisions"]:
                result[row["decision_id"]] = row["reason"]
        labeled = {r["decision_id"] for r in load_examples(directory, allow_prepare=True)}
        for key in labeled:
            result[key] = "LABELED"
        return result
    before, after = statuses(baseline_dir), statuses(new_dir)
    transitions = Counter((before.get(k, "ABSENT"), after.get(k, "ABSENT")) for k in before.keys() | after.keys())
    return {f"{a} -> {b}": n for (a, b), n in sorted(transitions.items()) if a != b}


# -- audit -------------------------------------------------------------------------------------------------------------

def prepare_statistics(rows: list[dict]) -> dict:
    with_prepare = [r for r in rows if any(a["type"] == "PREPARE_CARD" for a in r["legal_actions"])]
    both = prepare_only = 0
    for r in with_prepare:
        play = {a["hand_index"] for a in r["legal_actions"] if a["type"] == "PLAY_CARD"}
        prep = {a["hand_index"] for a in r["legal_actions"] if a["type"] == "PREPARE_CARD"}
        both += bool(play & prep)
        prepare_only += bool(prep - play)
    chosen = [r for r in rows if _chosen(r)["type"] == "PREPARE_CARD"]
    return {
        "decisions_with_prepare_in_menu": len(with_prepare),
        "matches_with_prepare_in_menu": len({r["game_id"] for r in with_prepare}),
        "menus_where_a_card_has_both_play_and_prepare": both,
        "menus_with_a_prepare_only_card": prepare_only,
        "decisions_where_player_chose_prepare": len(chosen),
        "matches_where_player_chose_prepare": len({r["game_id"] for r in chosen}),
        "prepare_chosen_by_card": dict(sorted(Counter(_chosen(r)["card_id"] for r in chosen).items())),
        "prepare_in_menu_by_card": dict(sorted(Counter(
            a["card_id"] for r in with_prepare for a in r["legal_actions"] if a["type"] == "PREPARE_CARD").items())),
        "decisions_with_prepare_in_menu_player_chose_other": len(with_prepare) - len(chosen),
        "action_schema_versions": dict(sorted(Counter(str(r["action_schema_version"]) for r in rows).items())),
    }


def privacy_scan(rows: list[dict]) -> dict:
    """Aggregate checks on top of ``validate_example``; reports counts only, never row content."""
    bad_tag = bad_key = hidden = 0
    for row in rows:
        text = canonical_json(row)
        bad_tag += bool(BATTLETAG.search(text))
        stack = [row["state"], row["legal_actions"]]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                bad_key += sum(any(w in str(k).lower() for w in HANDLE_WORDS) for k in value)
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
        state = game_state_from_dict(row["state"])
        hidden += bool(state.opponent_known_cards or state.pending_choice_owner is not None
                       or state.opponent.known_secrets or state.self_player.known_secrets
                       or state.active_player != "SELF")
    return {"rows_scanned": len(rows), "rows_with_battletag_like_text": bad_tag, "keys_that_look_like_handles": bad_key,
            "rows_violating_visibility_boundary": hidden,
            "verdict": "PASS" if not (bad_tag or bad_key or hidden) else "FAIL"}


def menu_statistics(rows: list[dict]) -> dict:
    sizes = sorted(len(r["legal_actions"]) for r in rows)
    chosen = Counter(_chosen(r)["type"] for r in rows)
    return {"min": sizes[0], "median": statistics.median(sizes), "mean": sum(sizes) / len(sizes), "max": sizes[-1],
            "p90": sizes[int(0.9 * (len(sizes) - 1))],
            "single_action_menus": sum(s == 1 for s in sizes), "menus_of_3_plus": sum(s >= 3 for s in sizes),
            "chosen_action_types": dict(sorted(chosen.items()))}


def audit_corpus(directory: Path, catalog: CardCatalog) -> dict:
    rows = load_examples(directory, allow_prepare=True)
    base = audit_dataset(directory, catalog, allow_prepare=True)
    meta = json.loads((Path(directory) / "refresh_metadata.json").read_text(encoding="utf-8"))
    action_ids = Counter()
    known = {c.card_id for c in catalog}
    for r in rows:
        for a in r["legal_actions"]:
            for key in ("card_id", "source_card_id", "target_card_id"):
                if a.get(key):
                    action_ids["known" if a[key] in known else "unknown"] += 1
    quality = meta["quality"]
    return {
        "matches": quality["matches"], "decisions_labeled": len(rows),
        "decisions_total": base["decisions_total"], "decisions_skipped": base["decisions_skipped"],
        "skip_reasons": base["skip_reasons"], "raw_match_rejections": quality["raw_match_rejections"],
        "outcomes_by_match": quality["outcomes_by_match"], "self_class_by_match": quality["self_class_by_match"],
        "decisions_per_match": quality["decisions_per_match"],
        "menu": menu_statistics(rows), "prepare": prepare_statistics(rows),
        "unknown_public_card_identity_ratio_state_and_actions": base["unknown_card_id_ratio"],
        "unknown_action_card_identity_ratio": (action_ids["unknown"] / sum(action_ids.values())
                                               if action_ids else 0.0),
        "unknown_card_ids": _unknown_summary(rows, known),
        "privacy": privacy_scan(rows),
        "full_validation": "PASS",       # load_examples validated every row with allow_prepare=True
        "import_dataset_identity_sha256": meta["dataset_identity_sha256"],
        "canonical_content_identity_sha256": meta["canonical_content_identity_sha256"],
    }


def _unknown_summary(rows: list[dict], known: set[str]) -> dict:
    """Cards the pinned Standard catalog does not know (heroes, tokens, off-Standard); counts, not the full list."""
    counts = Counter(c for r in rows for c in _all_card_ids(r) if c not in known)
    def family(card_id):
        return ("hero_or_hero_power" if card_id.startswith("HERO_") or card_id.endswith(("hp", "p"))
                else "token_or_generated" if re.search(r"t\d*$", card_id) else "other")
    return {"distinct": len(counts), "occurrences": sum(counts.values()),
            "by_family_occurrences": dict(sorted(Counter(
                {f: sum(n for c, n in counts.items() if family(c) == f)
                 for f in ("hero_or_hero_power", "token_or_generated", "other")}).items())),
            "most_common": dict(counts.most_common(15))}


def _all_card_ids(row):
    found = []
    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("card_id") and item:
                    found.append(item)
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(row["state"])
    visit(row["legal_actions"])
    return found


# -- usage registry and split plan -------------------------------------------------------------------------------------

def _resolve_prefixes(prefixes, game_ids):
    return {g for g in game_ids if any(g.startswith(p) for p in prefixes)}


def usage_registry(repo: Path, game_ids: set[str]) -> dict:
    """Which corpus matches any existing Policy checkpoint, selection run or evaluation has already seen."""
    import torch
    usage: dict[str, Counter] = defaultdict(Counter)
    sources = []

    def note(game, tag):
        if game in game_ids:
            usage[game][tag] += 1

    for path in sorted((repo / "data").glob("processed_policy_*/**/*.pt")):
        try:
            payload = torch.load(path, map_location="cpu", weights_only=False)
            split = payload["experiment"]["split"]["game_ids"]
        except Exception:
            continue
        sources.append({"kind": "checkpoint", "path": path.relative_to(repo).as_posix(), "sha256": sha256_file(path)})
        for part, ids in split.items():
            for game in ids:
                note(game, f"checkpoint_{part}")
    for rel, tag in ((FROZEN_V3_SPLIT, "frozen_v3"),):
        path = repo / rel
        if path.exists():
            sources.append({"kind": "split", "path": rel, "sha256": sha256_file(path)})
            for part, ids in json.loads(path.read_text(encoding="utf-8"))["game_ids"].items():
                for game in ids:
                    note(game, f"{tag}_{part}")
    path = repo / CV_FOLDS
    if path.exists():
        sources.append({"kind": "cross_validation", "path": CV_FOLDS, "sha256": sha256_file(path)})
        for fold in json.loads(path.read_text(encoding="utf-8"))["folds"]:
            for game in (fold if isinstance(fold, list) else fold.get("validation", [])):
                note(game, "cv_fold")
    for rel in USAGE_REGISTRIES:
        path = repo / rel
        if path.exists():
            sources.append({"kind": "usage_registry", "path": rel, "sha256": sha256_file(path)})
            for entry in json.loads(path.read_text(encoding="utf-8"))["entries"]:
                for tag in entry.get("usage", []):
                    note(entry["match_id"], tag.lower())
    for rel in SHADOW_EVAL_REPORTS:
        path = repo / rel
        if path.exists():
            sources.append({"kind": "shadow_evaluation", "path": rel, "sha256": sha256_file(path)})
            prefixes = list(json.loads(path.read_text(encoding="utf-8"))["inputs"]["importer_summaries"])
            for game in _resolve_prefixes(prefixes, game_ids):
                note(game, "model_shadow_eval_1")
    live = {p.parent.name for p in (repo / "data/raw/live").glob("*/*/slice.log")} if (repo / "data/raw/live").exists() else set()
    entries = []
    for game in sorted(game_ids):
        tags = usage.get(game, Counter())
        trained = any(t.endswith(("_train", "_validation")) or t == "cv_fold" for t in tags)
        evaluated = any(t.endswith("_test") or t in {"ml_eval_0_inference", "model_shadow_eval_1"} for t in tags)
        status = "TRAINED_OR_SELECTED" if trained else "EVALUATED_ONLY" if evaluated else "NOT_KNOWN_USED"
        entries.append({"match_id": game, "status": status, "usage": dict(sorted(tags.items())),
                        "live_session_recorded": game[:16] in live})
    return {"schema_version": 1, "sources": sources,
            "status_counts": dict(sorted(Counter(e["status"] for e in entries).items())),
            "live_session_recorded": sum(e["live_session_recorded"] for e in entries), "entries": entries}


def plan_split(rows: list[dict], registry: dict, frozen_parts: dict[str, list[str]] | None, seed: int) -> dict:
    """Whole-match plan. Never-seen matches are reserved; seen ones keep their earlier role; no match is split."""
    by_game = defaultdict(list)
    for r in rows:
        by_game[r["game_id"]].append(r)
    status = {e["match_id"]: e["status"] for e in registry["entries"]}
    frozen = {g: part for part, ids in (frozen_parts or {}).items() for g in ids}
    parts = {"train": [], "validation": [], "test_seen": [], "fresh_holdout": []}
    reason = {}
    for game in sorted(by_game, key=lambda g: hashlib.sha256(f"{seed}:{g}".encode()).hexdigest()):
        if status.get(game) == "NOT_KNOWN_USED":
            part, why = "fresh_holdout", "never seen by a checkpoint, selection run or evaluation"
        elif frozen.get(game) in ("train", "validation"):
            part, why = frozen[game], "keeps its role in the earlier frozen Policy v3 split"
        elif frozen.get(game) == "test" or status.get(game) == "EVALUATED_ONLY":
            part, why = "test_seen", "already used to evaluate an existing checkpoint: not independent"
        else:
            part, why = "train", "was trained or selected on by an earlier run"
        parts[part].append(game)
        reason[game] = why
    for game in parts["fresh_holdout"]:
        if status.get(game) != "NOT_KNOWN_USED":
            raise ValueError("A used match was placed in the fresh holdout")
    membership = {name: set(ids) for name, ids in parts.items()}
    for a in membership:
        for b in membership:
            if a < b and membership[a] & membership[b]:
                raise ValueError("Whole-match split overlap")
    summary = {}
    for name, ids in parts.items():
        selected = [r for g in ids for r in by_game[g]]
        summary[name] = {"matches": len(ids), "decisions": len(selected),
                         "wins": sum(by_game[g][0]["final_result"] == 1.0 for g in ids),
                         "losses": sum(by_game[g][0]["final_result"] == 0.0 for g in ids),
                         "draws": sum(by_game[g][0]["final_result"] == 0.5 for g in ids),
                         "prepare_in_menu": sum(any(a["type"] == "PREPARE_CARD" for a in r["legal_actions"])
                                                for r in selected),
                         "prepare_chosen": sum(_chosen(r)["type"] == "PREPARE_CARD" for r in selected)}
    fresh = summary["fresh_holdout"]
    caveats = ["Policy checkpoints have never trained on prepare_card; every Prepare decision is new to all of them.",
               "'fresh' means unseen by checkpoints, selection runs and the logged evaluations; it does not mean unseen by the"
               " player, who may have followed Top-3 recommendations shown during LIVE sessions (live_session_recorded).",
               "test_seen matches are a continuity check only and must not be reported as independent."]
    verdicts = []
    if fresh["matches"] < MIN_FRESH_MATCHES:
        verdicts.append(f"INSUFFICIENT_FRESH_MATCHES: {fresh['matches']} < {MIN_FRESH_MATCHES}")
    if fresh["prepare_chosen"] < MIN_FRESH_PREPARE_CHOICES:
        verdicts.append(f"INSUFFICIENT_FRESH_PREPARE_CHOICES: {fresh['prepare_chosen']} < {MIN_FRESH_PREPARE_CHOICES}")
    plan = {"algorithm": SPLIT_ALGORITHM, "seed": seed, "parts": {k: sorted(v) for k, v in parts.items()},
            "summary": summary, "assignment_reason": {g: reason[g] for g in sorted(reason)},
            "independence_verdicts": verdicts or ["FRESH_HOLDOUT_SIZE_OK"], "caveats": caveats}
    plan["split_sha256"] = identity({"algorithm": SPLIT_ALGORITHM, "seed": seed, "parts": plan["parts"]})
    return plan


# -- encoder / model-input readiness --------------------------------------------------------------------------------------

def check_encoders(rows: list[dict], catalog: CardCatalog, checkpoints: dict[str, Path]) -> dict:
    """Technical input checks for the v2 and v3 representations. No weights are trained or written."""
    import torch
    from manamind.encoding.state_encoder import StateEncoder
    from manamind.models.policy import ACTION_FEATURE_NAMES
    from manamind.models.policy_inputs import encode_policy_inputs, representation_of
    from manamind.models.policy_v2 import feature_contract
    from manamind.training.policy_checkpoint import load_policy_checkpoint

    prepare_column = ACTION_FEATURE_NAMES.index("prepare_card")
    play_column = ACTION_FEATURE_NAMES.index("play_card")

    def inspect_encoder(encoder, label, model=None):
        contract = feature_contract(encoder)
        sizes = (len(contract["state_feature_names"]), len(contract["entity_feature_names"]),
                 len(contract["action_feature_names"]))
        failures, linked_prepare, unknown_ids, ids_total = Counter(), 0, 0, 0
        v3_equal = 0
        with torch.no_grad():
            for row in rows:
                state = game_state_from_dict(row["state"])
                actions = row["legal_actions"]
                tensors = encode_policy_inputs(state, actions, encoder, representation=2)
                st, ids, ent, act, card_ids, links = tensors
                n = len(actions)
                ok_shape = (tuple(st.shape) == (sizes[0],) and ids.ndim == 1 and len(ids) >= 2
                            and tuple(ent.shape) == (len(ids), sizes[1]) and tuple(act.shape) == (n, sizes[2])
                            and tuple(card_ids.shape) == (n, 2) and tuple(links.shape) == (n, 4))
                if not ok_shape:
                    failures["shape"] += 1
                    continue
                if not all(bool(torch.isfinite(t).all()) for t in (st, ent, act)):
                    failures["non_finite"] += 1
                if bool((links < -1).any()) or bool((links >= len(ids)).any()):
                    failures["link_out_of_range"] += 1
                if not 0 <= row["chosen_action_index"] < n:
                    failures["chosen_index"] += 1
                for i, action in enumerate(actions):
                    if action["type"] == "END_TURN":
                        continue
                    if int(links[i, 0]) < 0 or int(ids[links[i, 0]]) != int(card_ids[i, 0]):
                        failures["source_link_identity"] += 1
                    if action["type"] == "PREPARE_CARD":
                        ok = (float(act[i, prepare_column]) == 1.0 and float(act[i, play_column]) == 0.0
                              and int(links[i, 1]) == -1 and int(links[i, 2]) == -1 and int(links[i, 3]) == -1)
                        linked_prepare += ok
                        failures["prepare_action_features_or_links"] += not ok
                    for key in ("card_id", "source_card_id", "target_card_id"):
                        if action.get(key):
                            ids_total += 1
                            unknown_ids += encoder.vocabulary.card_id(action[key]) == encoder.vocabulary.UNKNOWN_CARD
                again = encode_policy_inputs(state, actions, encoder, representation=3)
                v3_equal += all(torch.equal(a, b) for a, b in zip(tensors, again))
        result = {"label": label, "state_features": sizes[0], "entity_features": sizes[1], "action_features": sizes[2],
                  "rows_checked": len(rows), "failures": {k: v for k, v in sorted(failures.items()) if v},
                  "prepare_actions_encoded_correctly": linked_prepare,
                  "v3_inputs_identical_to_v2": f"{v3_equal}/{len(rows)}",
                  "action_card_ids_mapped_to_unknown": {"unknown": unknown_ids, "total": ids_total}}
        if model is not None:
            before = identity({k: v.tolist() for k, v in model.state_dict().items()})
            model.eval()
            logits_bad = 0
            with torch.no_grad():
                for row in rows:
                    state = game_state_from_dict(row["state"])
                    logits = model(*encode_policy_inputs(state, row["legal_actions"], encoder,
                                                         representation=representation_of(model)))
                    logits_bad += (tuple(logits.shape) != (len(row["legal_actions"]),)
                                   or not bool(torch.isfinite(logits).all()))
            after = identity({k: v.tolist() for k, v in model.state_dict().items()})
            result.update({"forward_rows": len(rows), "forward_rows_with_bad_logits": logits_bad,
                           "weights_unchanged": before == after})
        return result

    report = [inspect_encoder(StateEncoder(catalog), "fresh StateEncoder(current pinned catalog)")]
    for label, path in checkpoints.items():
        if not Path(path).exists():
            report.append({"label": label, "status": "CHECKPOINT_MISSING"})
            continue
        model, encoder, _ = load_policy_checkpoint(Path(path))
        item = inspect_encoder(encoder, label, model)
        item["checkpoint_sha256"] = sha256_file(Path(path))
        report.append(item)
    ok = all(not r.get("failures") and r.get("forward_rows_with_bad_logits", 0) == 0
             and r.get("weights_unchanged", True) and r.get("status") != "CHECKPOINT_MISSING" for r in report)
    return {"checks": report, "verdict": "PASS" if ok else "FAIL"}


# -- driver ------------------------------------------------------------------------------------------------------------

def tree_digest(roots: list[Path]) -> str:
    """Metadata digest (relative path, size, mtime) of existing results; used to prove they were not touched."""
    items = []
    for root in roots:
        for base, _dirs, files in os.walk(root):
            for name in files:
                p = Path(base) / name
                st = p.stat()
                items.append((p.as_posix(), st.st_size, st.st_mtime_ns))
    return identity(sorted(items))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")


def build(args) -> dict:
    out_root = Path(args.out_root).resolve()
    staging = out_root.with_name(f".{out_root.name}.building")
    for path in (out_root, staging):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite or reuse existing output: {path}")
    if "processed_real" in {part.lower() for part in out_root.parts}:
        raise ValueError("The value dataset directory must not receive policy records")
    repo = Path(args.data_root).resolve()          # where existing datasets, checkpoints and reports live
    protected = [p for p in (repo / "data/raw", *sorted((repo / "data").glob("processed_policy_*"))) if p.exists()]
    protected_before = tree_digest(protected)
    cards = Path(args.cards)
    catalog = CardCatalog.from_json(cards)
    primary = raw_logs(Path(args.collected_dir))
    paths, sources = select_logs(primary, collect_extras([Path(p) for p in args.extra_raw]))
    staging.mkdir(parents=True)
    common = dict(repo_root=ROOT, log_paths=paths, source_sha=args.source_sha)
    new_result = rebuild_once(args.collected_dir, staging / "dataset", cards, prepare_actions=True, **common)
    base_result = rebuild_once(args.collected_dir, staging / "baseline_v1", cards, prepare_actions=False, **common)
    determinism = {"verified": False}
    if args.verify_determinism:
        scratch = staging / ".determinism"
        again = rebuild_once(args.collected_dir, scratch / "dataset", cards, prepare_actions=True, **common)
        determinism = {"verified": True, "runs": 2,
                       "identical_content_identity": again["canonical_content_identity_sha256"]
                       == new_result["canonical_content_identity_sha256"]}
        shutil.rmtree(scratch)
        if not determinism["identical_content_identity"]:
            raise ValueError("Two independent builds differ")
    rows = load_examples(staging / "dataset", allow_prepare=True)
    baseline_rows = load_examples(staging / "baseline_v1")
    game_ids = {r["game_id"] for r in rows}
    manifests = [json.loads(p.read_text(encoding="utf-8")) for p in (staging / "dataset").glob("*.audit.json")]
    if len({m["game_id"] for m in manifests}) != len(manifests) or not game_ids <= {m["game_id"] for m in manifests}:
        raise ValueError("Duplicate or inconsistent match manifests")
    audit = audit_corpus(staging / "dataset", catalog)
    comparison = compare_with_baseline(baseline_rows, rows)
    comparison["skip_status_transitions"] = skip_transitions(staging / "baseline_v1", staging / "dataset")
    comparison["stored_datasets"] = {}
    for rel in STORED_DATASETS:                  # earlier stored imports of (a subset of) the same raw logs, read as is
        if (repo / rel).is_dir():
            stored = read_dataset_unchecked(repo / rel)
            comparison["stored_datasets"][rel] = {
                "identity_sha256": dataset_identity(stored), "strict": compare_with_baseline(stored, rows),
                "refresh_style": compare_datasets(stored, rows)}
    registry = usage_registry(repo, game_ids)
    frozen_path = repo / FROZEN_V3_SPLIT
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))["game_ids"] if frozen_path.exists() else None
    plan = plan_split(rows, registry, frozen, args.seed)
    checkpoints = {"retrained_v2": repo / RETRAINED_V2, "policy_v3": repo / POLICY_V3}
    encoder_report = check_encoders(rows, catalog, {} if args.skip_checkpoints else checkpoints)
    protected_after = tree_digest(protected)
    if protected_before != protected_after:
        raise ValueError("An existing raw log or policy dataset changed during the build")
    for name, value in (("audit", audit), ("comparison", comparison), ("usage_registry", registry),
                        ("split_plan", plan), ("encoder_check", encoder_report)):
        write_json(staging / f"{name}.json", value)
    manifest = {
        "schema": "manamind.policy_prepare_corpus/1", "git_source_sha": args.source_sha or _git_sha(ROOT), "seed": args.seed,
        "raw_inputs": sources, "selected_raw_logs": len(paths),
        "input_corpus_fingerprint": new_result["input_corpus_fingerprint"],
        "catalog_file_sha256": sha256_file(cards),
        "importer_source_fingerprint_sha256": new_result["importer_source_fingerprint_sha256"],
        "dataset_identity_sha256": new_result["dataset_identity_sha256"],
        "canonical_content_identity_sha256": new_result["canonical_content_identity_sha256"],
        "baseline_dataset_identity_sha256": base_result["dataset_identity_sha256"],
        "split_sha256": plan["split_sha256"], "determinism": determinism,
        "isolation": {"protected_tree_digest_before": protected_before, "protected_tree_digest_after": protected_after,
                      "unchanged": True},
        "result_hashes": {name: sha256_file(staging / f"{name}.json") for name in
                          ("audit", "comparison", "usage_registry", "split_plan", "encoder_check")},
        "quality": quality_summary(rows, audit_dataset(staging / "dataset", catalog, allow_prepare=True), {}),
        "verdict_inputs": {"audit_privacy": audit["privacy"]["verdict"], "encoder": encoder_report["verdict"],
                           "baseline_byte_identical": comparison["common_not_identical"] == 0
                           and comparison["baseline_decisions_missing_from_new"] == 0,
                           "independence": plan["independence_verdicts"]},
    }
    write_json(staging / "manifest.json", manifest)
    os.replace(staging, out_root)
    return {"out_root": out_root.as_posix(), "manifest": manifest, "audit": audit, "comparison": comparison,
            "split_plan_summary": plan["summary"], "encoder_verdict": encoder_report["verdict"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-root", type=Path, default=ROOT,
                        help="root holding existing datasets/checkpoints (read only); code hashes always use this repo")
    parser.add_argument("--collected-dir", type=Path, default=ROOT / "data/raw/collected")
    parser.add_argument("--extra-raw", type=Path, nargs="*", default=[ROOT / "data/raw/live", ROOT / "data/raw/Power.log"],
                        help="extra raw logs/dirs; used only for matches the collected directory does not hold")
    parser.add_argument("--cards", type=Path, default=ROOT / "data/cards/standard_current_enUS.json")
    parser.add_argument("--out-root", type=Path, default=ROOT / "data/processed_policy_prepare_1")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--source-sha", default=None)
    parser.add_argument("--verify-determinism", action="store_true")
    parser.add_argument("--skip-checkpoints", action="store_true", help="skip the read-only checkpoint forward checks")
    args = parser.parse_args(argv)
    try:
        result = build(args)
    except Exception as error:
        print(json.dumps({"result": "FAILED", "reason": type(error).__name__, "detail": str(error)[:300]}))
        return 1
    print(json.dumps({"out_root": result["out_root"], "audit_matches": result["audit"]["matches"],
                      "decisions": result["audit"]["decisions_labeled"],
                      "verdict_inputs": result["manifest"]["verdict_inputs"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
