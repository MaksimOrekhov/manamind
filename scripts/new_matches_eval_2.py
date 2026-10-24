"""NEW-MATCHES-EVAL-2: lock new independent games, then run fixed inference only.

Reuses EVAL-1's checkpoint, metric and shadow-analysis functions without changing
its protocol, inputs or results. Full states and per-decision outputs stay ignored.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import new_matches_eval_1 as base  # noqa: E402
from live_join_coverage_1 import _pair_reason, _read_candidate_snapshots  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.integrations.powerlog.policy_import import PolicyImportError  # noqa: E402
from manamind.live.snapshot import canonical_json  # noqa: E402
from manamind.live.snapshot_join import collapse_identical_main_action_snapshots  # noqa: E402
from manamind.training.real_policy import validate_example  # noqa: E402

PRIVATE = ROOT / "data/processed_new_matches_eval_2"
REPORT = ROOT / "reports/new_matches_eval_2"
PRIOR = ROOT / "data/processed_new_matches_eval_1/protocol.private.json"
CODE_PATHS = (
    "scripts/new_matches_eval_2.py", "scripts/new_matches_eval_1.py",
    "scripts/live_join_coverage_1.py", "src/manamind/live/snapshot_join.py",
    "src/manamind/live/journal_join.py",
)
PRIMARY = ("retrained_v2", "policy_v3", "control_v3_seed42",
           "prepare_v2_seed42", "prepare_v3_seed42")


def digest(value):
    return base._sha256_bytes(canonical_json(value).encode("utf-8"))


def exclusion_reason(prefix, heldout, history, prior_prefixes):
    """Decide by ID before opening any raw log or snapshot."""
    if len(prefix) != 16 or any(c not in "0123456789abcdef" for c in prefix):
        return "LEGACY_FILENAME_WITHOUT_MATCH_KEY"
    if any(g.startswith(prefix) for g in heldout):
        return "PROTECTED_FRESH_HOLDOUT_ID_ONLY"
    if any(g.startswith(prefix) for g in history):
        return "MATCH_ID_IN_PRIOR_SPLIT_OR_EVALUATION"
    if prefix in prior_prefixes:
        return "SOURCE_ALREADY_IN_EVAL_1_INVENTORY"
    return None


def assert_independent(rows, heldout, history, prior_ids):
    ids = [r["example"]["decision_id"] for r in rows]
    games = {r["example"]["game_id"] for r in rows}
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate decision IDs")
    if games & (set(heldout) | set(history) | set(prior_ids)):
        raise ValueError("evaluation overlaps protected or previously used matches")
    keys = [(r["example"]["game_id"], r["example"]["provenance"]["state_hash"],
             r["example"]["decision_id"].rsplit(":", 1)[1]) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate decision join keys")


def join_reason(example, key, snapshots, groups, raw_count):
    if raw_count != 1:
        return "AMBIGUOUS_RAW_DECISION_KEY"
    if not snapshots:
        return "LIVE_SNAPSHOT_NOT_MATCHED"
    collapsed = collapse_identical_main_action_snapshots(snapshots)
    if collapsed.snapshot is None:
        return collapsed.reason
    if canonical_json(collapsed.snapshot["state"]) != canonical_json(example["state"]):
        return "LIVE_STATE_MISMATCH"
    reason = _pair_reason(example, key, snapshots, groups,
                          require_snapshot_sequence_membership=True)
    if reason:
        return reason
    for kind in ("strategy", "outcome"):
        # The legacy digest helper indexes a dict; additionally refuse duplicate
        # indices even if an extra repeated entry has the same digest.
        if any(len(record.get("actions", [])) != len(example["legal_actions"])
               for record in groups[kind][key]):
            return f"{kind.upper()}_MENU_DUPLICATE_INDEX"
    return None


def inventory():
    plan = base._read_json(ROOT / base.SPLIT_PLAN)
    heldout = set(plan["parts"]["fresh_holdout"])
    if len(heldout) != 9:
        raise ValueError("expected nine protected IDs")
    history, models = base._load_history(heldout)  # identity/metadata only, no forward pass
    prior = base._read_json(PRIOR)
    if len(prior["eligible_match_ids"]) != 13:
        raise ValueError("unexpected EVAL-1 identity")
    prior_prefixes = {Path(r["source"]).stem for r in prior["source_inventory"]}
    prior_prefixes.update(r["match_id_prefix"] for r in prior["matches"])
    prior_prefixes.update(Path(p).stem for p in prior["inputs"]["raw_log_sha256"])
    for g in prior["eligible_match_ids"]:
        history[g].add("new_matches_eval_1")
    raw = sorted((ROOT / "data/raw/collected").glob("*.log"))
    sources, candidates = [], []
    for path in raw:
        reason = exclusion_reason(path.stem, heldout, history, prior_prefixes)
        if reason:
            sources.append({"source": str(path.relative_to(ROOT)), "category": "EXCLUDED", "reason": reason})
        else:
            candidates.append(path)
    pending = [p for p in (ROOT / "data/raw/collected/.pending").rglob("*.log")
               if not any(g.startswith(p.stem) for g in heldout)]
    for path in pending:
        sources.append({"source": str(path.relative_to(ROOT)), "category": "INCOMPLETE",
                        "reason": "COLLECTOR_PENDING_SLICE"})
    live_dirs = [d for session in (ROOT / "data/raw/live").glob("Hearthstone_*") if session.is_dir()
                 for d in session.iterdir() if d.is_dir() and not any(g.startswith(d.name) for g in heldout)]
    shadows, shadow_hashes = base._load_shadow_rows({p.stem for p in candidates}, heldout)
    groups = base._group_shadows(shadows)
    catalog = CardCatalog.from_json(ROOT / base.CARDS)
    rows, diagnostic, match_info = [], [], []
    raw_hashes, snapshot_hashes = {}, {}
    skips, exclusions = Counter(), Counter()
    seen_games = set()
    recovered = 0
    for path in candidates:
        relative = str(path.relative_to(ROOT))
        raw_hashes[relative] = base.sha256_file(path)
        try:
            examples, summary = base._load_match_rows(path, catalog)
        except (PolicyImportError, ValueError, OSError) as error:
            sources.append({"source": relative, "category": "IMPORT_FAILED",
                            "reason": error.reason if isinstance(error, PolicyImportError) else type(error).__name__})
            continue
        game = summary["game_id"]
        if game in heldout or game in history:
            raise ValueError("candidate content overlaps forbidden match ID")
        if not game.startswith(path.stem) or game in seen_games:
            sources.append({"source": relative, "category": "EXCLUDED", "reason": "ID_MISMATCH_OR_DUPLICATE"})
            continue
        seen_games.add(game)
        skips.update(summary["skip_reasons"])
        snapshots, _, parse_error = _read_candidate_snapshots(game)
        for p in base._find_live_snapshots(game):
            snapshot_hashes[str(p.relative_to(ROOT))] = base.sha256_file(p)
        key_of = lambda e: (game, int(e["decision_id"].rsplit(":", 1)[1]), e["provenance"]["state_hash"])
        counts = Counter(key_of(e) for e in examples)
        reasons = Counter()
        matched = []
        for example in examples:
            validate_example(example, allow_prepare=True)
            key = key_of(example)
            reason = (f"SNAPSHOT_{parse_error}" if parse_error else
                      join_reason(example, key, snapshots.get(key, []), groups, counts[key]))
            if reason:
                reasons[reason] += 1
                diagnostic.append({"example": example, "exclusion_reason": reason})
                continue
            recovered += int(len(snapshots[key]) > 1)
            item = {"example": example}
            for kind, target in (("prediction", "recommendation"), ("strategy", "strategy"), ("outcome", "outcome")):
                item[target] = base._one_record(groups[kind][key], kind)[0]
            rows.append(item)
            matched.append(example)
        exclusions.update(reasons)
        classes = sorted({e["state"]["self_player"].get("player_class") or "UNKNOWN" for e in examples})
        info = {"game_id": game, "class": classes[0] if len(classes) == 1 else "UNKNOWN",
                "archetype": "UNKNOWN", "archetype_reason": "No verified decklist or archetype metadata",
                "imported_decisions": len(examples), "strict_decisions": len(matched),
                "summary": summary, "decision_exclusions": dict(reasons)}
        match_info.append(info)
        sources.append({"source": relative, "category": "NEW_ELIGIBLE" if matched else "UNVERIFIED",
                        "reason": None if matched else "NO_EXACT_LIVE_JOIN", "game_id": game,
                        "imported_decisions": len(examples), "strict_decisions": len(matched),
                        "decision_exclusions": dict(reasons)})
    assert_independent(rows, heldout, history, prior["eligible_match_ids"])
    matches = sorted({r["example"]["game_id"] for r in rows})
    decisions = sorted(r["example"]["decision_id"] for r in rows)
    prepared = [r for r in rows if any(a["type"] == "PREPARE_CARD" for a in r["example"]["legal_actions"])]
    chosen_prepare = sum(r["example"]["legal_actions"][r["example"]["chosen_action_index"]]["type"] == "PREPARE_CARD"
                         for r in prepared)
    inputs = {"split_plan_sha256": base.sha256_file(ROOT / base.SPLIT_PLAN),
              "catalog_sha256": base.sha256_file(ROOT / base.CARDS),
              "usage_registry_sha256": base.sha256_file(ROOT / base.USAGE_REGISTRY),
              "prior_protocol_sha256": base.sha256_file(PRIOR),
              "raw_log_sha256": raw_hashes, "live_snapshot_sha256": snapshot_hashes,
              "candidate_shadow_rows_sha256": shadow_hashes}
    stats = {"raw_collected_log_files": len(raw), "new_nonoverlap_raw_candidates": len(candidates),
             "completed_matches_imported": len(match_info), "new_eligible_matches": len(matches),
             "new_eligible_decisions": len(rows), "prepare_decisions": len(prepared),
             "prepare_chosen": chosen_prepare, "importer_skip_reasons": dict(skips),
             "decision_exclusions": dict(exclusions), "diagnostic_only_decisions": len(diagnostic),
             "recovered_identical_snapshot_decisions": recovered,
             "previous_eval_1_matches_excluded": len(prior["eligible_match_ids"])}
    # Retain the field contract expected by the reused public summary function.
    for key in ("keyed_collected_match_logs", "legacy_filename_logs", "protected_raw_log_prefixes_skipped",
                "prepare_menu_decisions_imported", "prepare_menu_decisions_live_matched", "prepare_chosen_live_matched",
                "collector_pending_logs", "live_recording_directories_nonprotected"):
        stats[key] = 0
    stats["keyed_collected_match_logs"] = sum(len(p.stem) == 16 for p in raw)
    stats["legacy_filename_logs"] = len(raw) - stats["keyed_collected_match_logs"]
    stats["protected_raw_log_prefixes_skipped"] = sum(any(g.startswith(p.stem) for g in heldout) for p in raw)
    stats["collector_pending_logs"] = len(pending)
    stats["live_recording_directories_nonprotected"] = len(live_dirs)
    stats["prepare_menu_decisions_imported"] = sum(any(a["type"] == "PREPARE_CARD" for a in e["example"]["legal_actions"])
                                                   for e in rows + diagnostic)
    stats["prepare_menu_decisions_live_matched"] = len(prepared)
    stats["prepare_chosen_live_matched"] = chosen_prepare
    stats["prepare_menu_decision_exclusions"] = dict(Counter(e["exclusion_reason"] for e in diagnostic
        if any(a["type"] == "PREPARE_CARD" for a in e["example"]["legal_actions"])))
    protocol = {
        "schema": "manamind.new_matches_eval_2/private_protocol/1", "status": "PROTOCOL_LOCKED",
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "source_commit": base._git_head(),
        "source_code_sha256": base.sha256_file(ROOT / CODE_PATHS[0]),
        "code_sha256": {p: base.sha256_file(ROOT / p) for p in CODE_PATHS},
        "inputs": inputs, "eligible_match_ids": matches, "eligible_decision_ids": decisions,
        "dataset_identity_sha256": digest({"matches": matches, "decisions": decisions, "inputs": inputs}),
        "models": models, "matches": match_info, "source_inventory": sources, "inventory": stats,
        "history_ids": sorted(history), "prior_match_ids": prior["eligible_match_ids"],
        "protected_fresh_holdout": {"count": 9, "ids": sorted(heldout), "opened": False, "inference_run": False},
        "protocol": {
            "hypothesis": "Fixed existing candidates may improve imitation over Frozen v2 across newly collected classes.",
            "baseline": "frozen_v2", "primary_candidates": list(PRIMARY), "additional": ["control_v2_seed42"],
            "main_comparison": "All seven fixed seed42 models, identical ordinary full ordered legal menus.",
            "metrics": ["cross_entropy", "top1", "top3", "mrr", "uniform_random", "top1_pairwise_agreement"],
            "top3_rule": "Menus with at least three actions only; ties use original menu order.",
            "pairing": "Unique raw key; same full state/hash/options ID; identical snapshots except seq; shadow seq belongs to group; no conflicting journals; complete ordered menus; block-corroborated player choice.",
            "uncertainty": {"method": "paired whole-match bootstrap", "draws": 5000, "seed": base.BOOTSTRAP_SEED,
                            "primary_family_correction": "Bonferroni simultaneous 99% intervals for five candidates; marginal 95% also reported"},
            "verdict_rule": "Fewer than 10 strict ordinary matches: INSUFFICIENT_DATA. Otherwise candidate improvement requires simultaneous CE CI <0 and Top1 CI >0, same signs on match-balanced means, and no sign reversal when leaving one class out. Regression requires simultaneous CE CI >0 and Top1 CI <0. Else NO_CLEAR_WINNER. No automatic live promotion.",
            "class_rule": "At least 5 games per class for descriptive comparisons; fewer marked insufficient. No class-specific model choice. Archetypes remain UNKNOWN without verified deck metadata.",
            "review_rule": "Up to 20 unique decisions, round-robin over EVAL-1 fixed disagreement categories sorted by score/ID; check every legal action with existing forecaster. CONFIRMED_ERROR only if a strict EXACT living-self lethal exists and model top1 is EXACT nonlethal; heuristic gaps alone are DISAGREEMENT_ONLY. PARTIAL/unsupported coverage is INSUFFICIENT_COVERAGE. No multistep lethal claim.",
            "prepare_rule": "Only Prepare v2/v3 on exactly joined compatible menus; zero examples does not block ordinary comparison.",
            "training_or_finetuning": False, "live_policy_changed": False,
        },
    }
    return protocol, rows, diagnostic


def public_protocol(p):
    result = base._public_protocol(p)
    result.update(schema="manamind.new_matches_eval_2/results/1", inventory=p["inventory"], code_sha256=p["code_sha256"])
    result["source_manifest_sha256"] = digest(p["inputs"])
    result["classes"] = class_inventory(p)
    return result


def class_inventory(p):
    groups = defaultdict(list)
    for m in p["matches"]:
        groups[m["class"]].append(m)
    return {c: {"completed_games": len(ms), "strict_games": sum(m["strict_decisions"] > 0 for m in ms),
                "imported_decisions": sum(m["imported_decisions"] for m in ms),
                "strict_decisions": sum(m["strict_decisions"] for m in ms), "archetypes": "UNKNOWN"}
            for c, ms in sorted(groups.items())}


def verify(p, rows):
    for path, sha in p["code_sha256"].items():
        if base.sha256_file(ROOT / path) != sha:
            raise ValueError("locked evaluation code changed")
    for path, key in ((ROOT / base.SPLIT_PLAN, "split_plan_sha256"), (ROOT / base.CARDS, "catalog_sha256"),
                      (ROOT / base.USAGE_REGISTRY, "usage_registry_sha256"), (PRIOR, "prior_protocol_sha256")):
        if base.sha256_file(path) != p["inputs"][key]:
            raise ValueError("locked metadata changed")
    heldout = set(p["protected_fresh_holdout"]["ids"])
    assert_independent(rows, heldout, p["history_ids"], p["prior_match_ids"])
    for key in ("raw_log_sha256", "live_snapshot_sha256"):
        for path, sha in p["inputs"][key].items():
            if base.sha256_file(ROOT / path) != sha:
                raise ValueError("locked source changed")
    _, shadows = base._load_shadow_rows({Path(x).stem for x in p["inputs"]["raw_log_sha256"]}, heldout)
    if shadows != p["inputs"]["candidate_shadow_rows_sha256"]:
        raise ValueError("locked journals changed")
    matches = sorted({r["example"]["game_id"] for r in rows})
    decisions = sorted(r["example"]["decision_id"] for r in rows)
    if matches != p["eligible_match_ids"] or decisions != p["eligible_decision_ids"]:
        raise ValueError("locked membership changed")
    if digest({"matches": matches, "decisions": decisions, "inputs": p["inputs"]}) != p["dataset_identity_sha256"]:
        raise ValueError("locked dataset identity changed")
    if base.sha256_file(PRIVATE / "decisions.private.jsonl") != p["private_decisions_sha256"]:
        raise ValueError("locked decisions changed")
    for model in base.MODELS:
        if base.sha256_file(ROOT / model["path"]) != model["sha256"]:
            raise ValueError("checkpoint changed")
        if base.sha256_file(ROOT / model["metrics"]) != p["models"][model["name"]]["metrics_sha256"]:
            raise ValueError("checkpoint metadata changed")


def simultaneous_bootstrap(rows, left, right):
    """Same paired clusters as EVAL-1, with prespecified family-adjusted tails."""
    import numpy as np
    games = sorted({r["example"]["game_id"] for r in rows})
    if not games:
        return {}
    draws = np.random.default_rng(base.BOOTSTRAP_SEED).integers(0, len(games), size=(5000, len(games)))
    out = {}
    for metric in base.METRIC_NAMES:
        sums, counts = [], []
        for game in games:
            indices = [i for i, r in enumerate(rows) if r["example"]["game_id"] == game
                       and left[i][metric] is not None and right[i][metric] is not None]
            sums.append(sum(float(left[i][metric]) - float(right[i][metric]) for i in indices))
            counts.append(len(indices))
        ns = np.asarray(counts)[draws].sum(axis=1)
        values = np.asarray(sums)[draws].sum(axis=1)[ns > 0] / ns[ns > 0]
        out[metric] = {"ci99": np.percentile(values, [0.5, 99.5]).tolist() if len(values) else None}
    return out


def review_cases(predictions, selected):
    from manamind.domain.serialization import game_state_from_dict
    from manamind.outcome.forecast import forecast_action
    from manamind.outcome.live_shadow import load_texts
    from manamind.outcome.model import Status

    categories = selected["private_examples"]
    ids = []
    for rank in range(6):
        for category in sorted(categories):
            group = categories[category]
            if rank < len(group) and group[rank]["decision_id"] not in ids:
                ids.append(group[rank]["decision_id"])
    ids = ids[:20]
    lookup = {p["example"]["decision_id"]: p for p in predictions}
    texts = load_texts(ROOT)
    cases, counts = [], Counter()
    for sid in ids:
        item = lookup[sid]
        e = item["example"]
        state = game_state_from_dict(e["state"])
        context = base.context_from_dict(item["outcome"].get("context", {}))
        forecasts, errors = [], []
        for action in e["legal_actions"]:
            try:
                forecasts.append(forecast_action(state, action, texts, context))
                errors.append(None)
            except Exception as error:
                forecasts.append(None)
                errors.append(type(error).__name__)
        def living_lethal(f):
            if f is None or f.status is not Status.EXACT:
                return False
            after = f.exact_state()
            return after.self_player.hero_health > 0 and after.opponent.hero_health <= 0
        lethal = [i for i, f in enumerate(forecasts) if living_lethal(f)]
        per_model = {}
        for name, scores in item["model_scores"].items():
            if "logits" not in scores:
                continue
            order = sorted(range(len(scores["logits"])), key=lambda i: (-scores["logits"][i], i))
            top = forecasts[order[0]]
            confirmed = bool(lethal and top is not None and top.status is Status.EXACT
                             and not living_lethal(top))
            status = "CONFIRMED_ERROR" if confirmed else "INSUFFICIENT_COVERAGE" if any(
                f is None or f.status is not Status.EXACT for f in forecasts) else "DISAGREEMENT_ONLY"
            per_model[name] = {"classification": status, "top3": [{"index": i, "action": e["legal_actions"][i],
                                  "logit": scores["logits"][i]} for i in order[:3]],
                               "reason": "EXACT_ALIVE_SELF_LETHAL_MISSED_TOP1" if confirmed else
                                         "Partial mechanics prevent strict ranking" if status == "INSUFFICIENT_COVERAGE" else
                                         "Different choices do not establish an error"}
        classification = "CONFIRMED_ERROR" if any(v["classification"] == "CONFIRMED_ERROR" for v in per_model.values()) else (
            "INSUFFICIENT_COVERAGE" if any(v["classification"] == "INSUFFICIENT_COVERAGE" for v in per_model.values())
            else "DISAGREEMENT_ONLY")
        counts[classification] += 1
        cases.append({**item, "models_review": per_model, "classification": classification,
                      "confidence": "strict within existing one-action forecaster" if classification == "CONFIRMED_ERROR" else "undetermined",
                      "suspicion_categories": [c for c, group in categories.items() if any(r["decision_id"] == sid for r in group)],
                      "exact_lethal_indices": lethal, "recomputed_forecasts": [f.to_dict() if f else {"error": error}
                          for f, error in zip(forecasts, errors)]})
    return {"cases": cases, "summary": {"reviewed_decisions": len(cases), "classification_counts": dict(counts),
            "confirmed_errors_by_model": dict(Counter(name for c in cases for name, v in c["models_review"].items()
                if v["classification"] == "CONFIRMED_ERROR")),
            "scope": "Selected disagreements, not an error-frequency estimate. Exact one-action only; no multistep search."}}


def enrich(p, report, predictions, selected):
    ordinary = [r for r in predictions if not any(a["type"] == "PREPARE_CARD" for a in r["example"]["legal_actions"])]
    names = [m["name"] for m in base.MODELS]
    report.update(public_protocol(p))
    report["status"] = "COMPLETE"
    # Recover the common summary after adding only the EVAL-2 public identity fields.
    report["top1_agreement"] = {f"{a}__{b}": sum(r["model_scores"][a]["top_index"] == r["model_scores"][b]["top_index"]
        for r in ordinary) / len(ordinary) if ordinary else None for a, b in combinations(names, 2)}
    comparisons = report["paired_comparisons"]
    for name in names[1:]:
        left = [r["model_scores"][name] for r in ordinary]
        right = [r["model_scores"]["frozen_v2"] for r in ordinary]
        result = base._paired_cluster_bootstrap(ordinary, left, right)
        result["simultaneous_primary_ci"] = simultaneous_bootstrap(ordinary, left, right) if name in PRIMARY else None
        comparisons[f"{name}_minus_frozen_v2_ordinary"] = result
    per_match = []
    for game in p["eligible_match_ids"]:
        subset = [r for r in ordinary if r["example"]["game_id"] == game]
        if not subset:
            continue
        per_match.append({"alias": digest(game)[:12], "class": subset[0]["example"]["state"]["self_player"].get("player_class"),
                          "models": {n: base._metric_stats([r["model_scores"][n] for r in subset],
                               [len(r["example"]["legal_actions"]) for r in subset]) for n in names}})
    report["per_match_metrics"] = per_match
    class_analysis = {}
    for c in sorted({r["example"]["state"]["self_player"].get("player_class") or "UNKNOWN" for r in ordinary}):
        subset = [r for r in ordinary if (r["example"]["state"]["self_player"].get("player_class") or "UNKNOWN") == c]
        games = {r["example"]["game_id"] for r in subset}
        class_analysis[c] = {"matches": len(games), "decisions": len(subset),
            "status": "DESCRIPTIVE" if len(games) >= 5 else "INSUFFICIENT_MATCHES",
            "models": {n: base._metric_stats([r["model_scores"][n] for r in subset],
                         [len(r["example"]["legal_actions"]) for r in subset]) for n in names},
            "disagreement_rate": sum(len({r["model_scores"][n]["top_index"] for n in names}) > 1 for r in subset) / len(subset),
            "action_type_confusion": {n: {actual: dict(Counter(r["model_scores"][n]["predicted_type"] for r in subset
                if r["model_scores"][n]["chosen_type"] == actual)) for actual in sorted({r["model_scores"][n]["chosen_type"] for r in subset})}
                for n in names}}
    report["class_analysis"] = class_analysis
    robustness = {}
    for name in PRIMARY:
        def differences(sub):
            return {metric: sum(float(r["model_scores"][name][metric]) - float(r["model_scores"]["frozen_v2"][metric])
                     for r in sub) / len(sub) for metric in ("cross_entropy", "top1")} if sub else None
        robustness[name] = {"leave_one_class_out": {c: differences([r for r in ordinary
            if (r["example"]["state"]["self_player"].get("player_class") or "UNKNOWN") != c]) for c in class_analysis},
            "match_balanced_difference": {metric: sum(m["models"][name]["metrics"][metric] - m["models"]["frozen_v2"]["metrics"][metric]
                for m in per_match) / len(per_match) if per_match else None for metric in ("cross_entropy", "top1")},
            "leave_one_match_out": [differences([r for r in ordinary if r["example"]["game_id"] != game])
                for game in sorted({r["example"]["game_id"] for r in ordinary})]}
    report["robustness"] = robustness
    improves, regressions = [], []
    for name in PRIMARY:
        ci = comparisons[f"{name}_minus_frozen_v2_ordinary"]["simultaneous_primary_ci"]
        ce, top = ci.get("cross_entropy", {}).get("ci99"), ci.get("top1", {}).get("ci99")
        balanced = robustness[name]["match_balanced_difference"]
        stable = all(v["cross_entropy"] < 0 and v["top1"] > 0 for v in robustness[name]["leave_one_class_out"].values() if v)
        if ce and top and ce[1] < 0 and top[0] > 0 and balanced["cross_entropy"] < 0 and balanced["top1"] > 0 and stable:
            improves.append(name)
        if ce and top and ce[0] > 0 and top[1] < 0:
            regressions.append(name)
    verdict = "INSUFFICIENT_DATA" if len(per_match) < 10 else "EVIDENCE_FOR_IMPROVEMENT" if improves else (
        "REGRESSION" if regressions else "NO_CLEAR_WINNER")
    review = review_cases(predictions, selected)
    report["case_review"] = review["summary"]
    report.pop("outcome_decision_review", None)  # EVAL-2 uses the stricter living-self Top-1 review above.
    report["conclusion"] = {"imitation_verdict": verdict, "improved_candidates": improves, "regressed_candidates": regressions,
        "strategic_quality": "STRATEGIC_QUALITY_NOT_ESTABLISHED", "live_policy_changed": False,
        "prepare_status": "NO_EXAMPLES" if not p["inventory"]["prepare_decisions"] else "DESCRIPTIVE_ONLY",
        "behavioral_independence_caveat": "Player may have seen Frozen v2 advice; labels measure imitation, not optimal play.",
        "next_priorities": ["Improve verified visible consequence coverage on the observed failure categories; no second rules engine.",
                            "Collect diverse independent games and expert-reviewed choices without visible model advice.",
                            "Only then authorize a small measured Policy experiment; keep Strategic Scorer heuristic until validated."]}
    report["private_examples_file"] = "data/processed_new_matches_eval_2/cases.private.json"
    return report, review


def render(report):
    text = "# NEW-MATCHES-EVAL-2\n\n"
    text += f"Статус: **{report['status']}**. Идентичность выборки: `{report['data_identity_sha256']}`.\n\n"
    i = report["inventory"]
    text += (f"Новых raw-кандидатов: {i['new_nonoverlap_raw_candidates']}; завершённых Ranked Standard после импорта: "
             f"{i['completed_matches_imported']}; строгая выборка: **{i['new_eligible_matches']} матчей, "
             f"{i['new_eligible_decisions']} решений**. Диагностические решения вне основного набора: {i['diagnostic_only_decisions']}. "
             f"Безопасно объединены повторные снимки для {i['recovered_identical_snapshot_decisions']} решений.\n\n"
             "Это новые матчи отдельно от 13 игр EVAL-1. Все источники прежней инвентаризации исключены по ID, "
             "девять fresh_holdout исключены до открытия игровых файлов. Старые результаты не пересчитывались. "
             "Число 25 не использовалось для выбора файлов или остановки.\n\n")
    text += "## Классы и колоды\n\n| Класс | Завершено игр | Строгих игр | Решений |\n|---|---:|---:|---:|\n"
    for c, v in report["classes"].items():
        text += f"| {c} | {v['completed_games']} | {v['strict_games']} | {v['strict_decisions']} |\n"
    text += "\nАрхетипы UNKNOWN: проверенного списка колод нет. Класс не доказывает архетип; разные колоды внутри класса не угадывались.\n\n"
    text += "## Зафиксированный протокол\n\n"
    for key, value in report["protocol"].items():
        text += f"- `{key}`: {json.dumps(value, ensure_ascii=False)}\n"
    text += "\n## Checkpoint SHA-256\n\n"
    text += "\n".join(f"- `{n}`: `{m['sha256']}`" for n, m in report["models"].items()) + "\n\n"
    if report["status"] == "COMPLETE":
        text += f"## A. Имитация\n\nВердикт: **{report['conclusion']['imitation_verdict']}**.\n\n"
        text += "| Модель | CE ↓ | Top-1 ↑ | Top-3 ↑ | MRR ↑ |\n|---|---:|---:|---:|---:|\n"
        for name, item in report["evaluation_sets"]["ordinary_menus"]["models"].items():
            m = item["metrics"]
            if m:
                text += f"| {name} | {m['cross_entropy']:.4f} | {m['top1']:.3f} | {m['top3'] if m['top3'] is None else round(m['top3'], 3)} | {m['mrr']:.3f} |\n"
        text += "\nПарные 95% и одновременные 99% интервалы, uniform baseline, совпадение Top-1, метрики по матчам, классам, "
        text += "типам действий, фазам и размеру меню: `results.json`. Robustness содержит равный вес матчей и исключение по одному классу/матчу. "
        text += "Top-3 имеет отдельный знаменатель: меню от трёх действий. Действие игрока не считается эталоном стратегии.\n\n"
        text += f"Prepare: {report['conclusion']['prepare_status']}; выборов PREPARE_CARD: {i['prepare_chosen']}.\n\n"
        text += "## B. Реальные рекомендации\n\n**STRATEGIC_QUALITY_NOT_ESTABLISHED**. Эвристика Strategic Scorer не является доказательством правильности хода. "
        text += "Outcome Shadow проверяет доступную механику одного действия; поиск цепочки летала не выполнялся.\n\n"
        text += "```json\n" + json.dumps(report["case_review"], ensure_ascii=False, indent=2) + "\n```\n\n"
        text += "Полные выбранные ситуации, состояния, меню, Top-3 семи моделей, ход игрока, оценки scorer, исходные и пересчитанные прогнозы "
        text += "сохранены только в ignored `data/processed_new_matches_eval_2/cases.private.json`. "
        text += "Это целевой разбор расхождений, не оценка частоты ошибок.\n\n"
        text += "## C. Следующий приоритет\n\n" + "\n".join(f"{j}. {v}" for j, v in enumerate(report["conclusion"]["next_priorities"], 1)) + "\n\n"
        text += "LIVE остаётся на Frozen v2. Обучение не выполнялось; checkpoint проверены до и после inference.\n\n"
    text += "## Исключения\n\n```json\n" + json.dumps({"matches": report["exclusion_reasons"],
        "decisions": i["decision_exclusions"], "importer": i["importer_skip_reasons"]}, ensure_ascii=False, indent=2) + "\n```\n\n"
    text += "## Воспроизведение\n\n`.venv/Scripts/python.exe scripts/new_matches_eval_2.py --preflight`, отдельный commit протокола, "
    text += "затем `--evaluate`. Повторная запись существующих private outputs запрещена. Все данные закреплены SHA-256; новые поступления не меняют выборку.\n"
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--evaluate", action="store_true")
    args = parser.parse_args(argv)
    if args.preflight:
        if PRIVATE.exists() or REPORT.exists():
            raise ValueError("refusing to overwrite experiment outputs")
        p, rows, diagnostic = inventory()
        base._write_new_jsonl(PRIVATE / "decisions.private.jsonl", rows)
        base._write_new_jsonl(PRIVATE / "diagnostic.private.jsonl", diagnostic)
        p["private_decisions_sha256"] = base.sha256_file(PRIVATE / "decisions.private.jsonl")
        base._write_new_json(PRIVATE / "protocol.private.json", p)
        result = public_protocol(p)
        base._write_new_json(REPORT / "protocol.json", result)
        base._write_new_json(REPORT / "results.json", result)
        (REPORT / "README.md").write_text(render(result), encoding="utf-8")
        print(json.dumps({"status": "PROTOCOL_LOCKED", "inventory": p["inventory"], "classes": result["classes"]}))
    else:
        if (PRIVATE / "logits.private.jsonl").exists():
            raise ValueError("inference outputs already exist")
        p = base._read_json(PRIVATE / "protocol.private.json")
        rows = [json.loads(line) for line in (PRIVATE / "decisions.private.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        verify(p, rows)
        result, predictions, selected = base._run_evaluation(p, rows)
        # enrich replaces the legacy experiment's verdict and adds prelocked EVAL-2 analyses.
        result, review = enrich(p, result, predictions, selected)
        verify(p, rows)
        base._write_new_jsonl(PRIVATE / "logits.private.jsonl", predictions)
        base._write_new_json(PRIVATE / "cases.private.json", review)
        base._write_new_json(PRIVATE / "selection.private.json", selected)
        (REPORT / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        (REPORT / "README.md").write_text(render(result), encoding="utf-8")
        print(json.dumps({"status": "COMPLETE", "conclusion": result["conclusion"], "case_review": review["summary"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
