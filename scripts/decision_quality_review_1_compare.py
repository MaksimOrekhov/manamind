"""DECISION-QUALITY-REVIEW-1, step 2: compare recommendations with the frozen blind labels.

Runs only after both label batches are frozen (PROTOCOL section 7, amendment 1). The chosen action and
observed SELF facts come from re-importing the pinned raw logs; no label file is modified. Arms: Frozen
Policy v2 (LIVE baseline), Policy v3, Strategic Scorer v3, Policy v2 + pre-registered guard, uniform random
(analytic), and the player's own move (reference only). Write-once outputs: a public aggregate JSON and an
ignored private per-position file.
"""
from __future__ import annotations

import io
import json
import random
import sys
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import decision_quality_review_1 as dq  # noqa: E402

PUBLIC = dq.REPORT / "results.json"
PRIVATE_OUT = dq.PRIVATE / "compare.private.json"
BOOTSTRAP_DRAWS = 5000
BOOTSTRAP_SEED = 20261026
RATER = "user"
ARMS = ("frozen_v2", "policy_v3", "scorer_v3", "frozen_v2_guard", "uniform", "player")
MODEL_SPECS = ("frozen_v2", "policy_v3")


# ----- frozen labels -----------------------------------------------------------------------------

def frozen_labels(batch: str) -> tuple[dict, dict[str, dict]]:
    path = dq.labels_path(RATER, batch)
    freeze = dq.read_json(path.parent / f"{batch}.freeze.json")
    if dq.sha256_file(path) != freeze["labels_sha256"]:
        raise ValueError(f"{batch} labels changed after freeze")
    labels = dq.latest_labels(path)
    if batch == "pilot" and freeze["pilot_verdict"] != "PASS":
        raise ValueError("pilot did not pass")
    if freeze.get("truncated"):
        labels = {k: v for k, v in labels.items() if k in set(freeze["frozen_screen_ids"])}
    return freeze, labels


def labeled_positions() -> tuple[list[dict], dict]:
    """One record per unique labeled position: label sets in original menu indices."""
    lock = dq.read_json(dq.PRIVATE / "lock.private.json")
    positions, meta, repeats = [], {}, []
    for batch in ("pilot", "main"):
        manifest_text = (dq.PRIVATE / f"{batch}.manifest.private.json").read_text(encoding="utf-8")
        if dq.sha256_bytes(manifest_text.encode("utf-8")) != lock["batches"][batch]["manifest_sha256"]:
            raise ValueError(f"{batch} manifest changed since lock")
        manifest = json.loads(manifest_text)
        freeze, labels = frozen_labels(batch)
        meta[batch] = {"labels_sha256": freeze["labels_sha256"], "labeled_screens": len(labels),
                       "truncated": bool(freeze.get("truncated"))}
        seen = {}
        for screen in manifest["screens"]:
            label = labels.get(screen["screen_id"])
            if label is None:
                continue
            record = to_indices(label, screen["menu_order"])
            if screen["repeat"]:
                repeats.append((seen.get(screen["position_id"]), record))
                continue
            info = manifest["positions"][screen["position_id"]]
            seen[screen["position_id"]] = record
            positions.append({"batch": batch, "screen_id": screen["screen_id"], **info, **record})
    meta["pilot_repeats"] = repeat_agreement([r for r in repeats if r[0] is not None])
    return positions, meta


def to_indices(label: dict, menu_order: list[int]) -> dict:
    """Choices on screen are 1-based positions in ``menu_order``; store original menu indices."""
    original = {str(n): index for n, index in enumerate(menu_order, start=1)}
    marks = defaultdict(set)
    for choice, mark in label["marks"].items():
        marks[mark].add(original[choice])
    return {"status": label["status"], "acceptable": sorted(marks["ACCEPTABLE"]), "blunder": sorted(marks["BLUNDER"]),
            "unsure": sorted(marks["UNSURE"]), "best": sorted(original[str(b)] for b in label.get("best", [])),
            "confidence": label["confidence"], "remembers_game": bool(label.get("remembers_game")),
            "needs_independent_review": bool(label.get("needs_independent_review")),
            "comment": label.get("comment") or ""}


def repeat_agreement(pairs: list[tuple[dict, dict]]) -> dict:
    out = []
    for first, second in pairs:
        a, b = set(first["acceptable"]), set(second["acceptable"])
        out.append({"same_status": first["status"] == second["status"],
                    "acceptable_jaccard": len(a & b) / len(a | b) if a | b else 1.0,
                    "same_blunders": set(first["blunder"]) == set(second["blunder"])})
    return {"pairs": len(out), "items": out,
            "note": "Descriptive only (n = 3): amendment 1 records rater stability as NOT MEASURED."}


# ----- re-import ---------------------------------------------------------------------------------

def reimport(game_ids: set[str]) -> dict[str, dict]:
    """Pinned raw logs only (SHA-256 from the lock); returns decision_id -> example with observed facts."""
    from manamind.cards.catalog import CardCatalog
    from manamind.integrations.powerlog.lines import read_complete_lines, split_games
    from manamind.integrations.powerlog.policy_import import extract_match

    lock = dq.read_json(dq.PRIVATE / "lock.private.json")
    inventory = dq.read_json(dq.PRIVATE / "inventory.private.json")
    catalog = CardCatalog.from_json(dq.CATALOG)
    examples = {}
    for match in inventory["matches"]:
        if match["game_id"] not in game_ids:
            continue
        path = dq.COLLECTED / match["source"]
        if dq.sha256_file(path) != lock["raw_log_sha256"][match["source"]]:
            raise ValueError("raw log changed since lock")
        segments = split_games(read_complete_lines(path))
        facts = {}
        rows, _ = extract_match(segments[0], catalog, observer=lambda d, f: facts.__setitem__(d, f),
                                prepare_actions=True)
        for row in rows:
            row["observed_facts"] = facts.get(row["decision_id"])
            examples[row["decision_id"]] = row
    return examples


# ----- arms --------------------------------------------------------------------------------------

def policy_rankings(name: str, rows: list[dict]) -> dict[str, list[int]]:
    """Full menu ranking by logits; models without Prepare support rank the menu without PREPARE_CARD, as LIVE."""
    import new_matches_eval_1 as base
    import torch

    from manamind.domain.serialization import game_state_from_dict
    from manamind.models.policy_inputs import encode_policy_inputs, representation_of
    from manamind.training.policy_checkpoint import load_policy_checkpoint

    spec = next(m for m in base.MODELS if m["name"] == name)
    data = (ROOT / spec["path"]).read_bytes()
    if dq.sha256_bytes(data) != spec["sha256"]:
        raise ValueError(f"checkpoint changed: {name}")
    policy, encoder, _ = load_policy_checkpoint(io.BytesIO(data), device="cpu", allow_prepare=True)
    policy.eval()
    representation = representation_of(policy)
    out = {}
    with torch.inference_mode():
        for row in rows:
            keep = [i for i, a in enumerate(row["legal_actions"])
                    if spec["supports_prepare"] or a["type"] != "PREPARE_CARD"]
            actions = [row["legal_actions"][i] for i in keep]
            inputs = encode_policy_inputs(game_state_from_dict(row["state"]), actions, encoder,
                                          representation=representation, device="cpu")
            values = policy(*inputs)
            if values.ndim != 1 or values.shape[0] != len(actions) or not torch.isfinite(values).all():
                raise ValueError(f"invalid logits for {name}")
            logits = values.tolist()
            out[row["decision_id"]] = [keep[j] for j in sorted(range(len(actions)), key=lambda j: (-logits[j], j))]
    return out


def mechanics(rows: list[dict]) -> dict[str, dict]:
    """Scorer ranking plus the pre-registered guard inputs: confirmed one-action lethals and SELF_HARM flags."""
    from manamind.domain.serialization import game_state_from_dict
    from manamind.outcome.diagnostics import SELF_HARM, diagnose_menu
    from manamind.outcome.forecast import forecast_alternatives
    from manamind.outcome.live_shadow import load_texts
    from manamind.outcome.model import Status
    from manamind.outcome.observation import context_from_observed
    from manamind.outcome.world import ObservedContext
    from manamind.strategy import score_menu

    texts = load_texts(ROOT)
    out = {}
    for row in rows:
        state = game_state_from_dict(row["state"])
        try:
            context = context_from_observed(row["observed_facts"], state)
        except Exception:  # noqa: BLE001 - unreadable facts mean an all-unknown context, as in LIVE
            context = ObservedContext()
        actions = row["legal_actions"]
        forecasts = forecast_alternatives(state, actions, texts, context)
        lethal = []
        for index, forecast in enumerate(forecasts):
            trusted = forecast.status is Status.EXACT or (
                forecast.own_effect_known and not any(u.alters_listed for u in forecast.unknowns))
            kills = any(c.ref.side == "OPPONENT" and c.ref.zone == "HERO" and c.field == "health"
                        and c.exact and c.after <= 0 for c in forecast.changes)
            if trusted and kills and (state.opponent.secret_count or 0) == 0:
                lethal.append(index)
        diagnosis = diagnose_menu(state, list(zip(range(len(actions)), actions, forecasts)), texts=texts)
        scored = score_menu(state, actions, texts, context, budget_ms=10_000)
        out[row["decision_id"]] = {
            "scorer": list(scored.ranking), "lethal": lethal,
            "self_harm": sorted({f.index for f in diagnosis.flags if f.flag == SELF_HARM}),
            "statuses": dict(Counter(f.status.value for f in forecasts))}
    return out


def guarded(ranking: list[int], lethal: list[int], self_harm: list[int]) -> list[int]:
    """PROTOCOL section 7: a confirmed lethal goes first (best by Policy rank); SELF_HARM sinks below the rest."""
    order = list(ranking)
    if lethal:
        first = min(lethal, key=order.index)
        order.remove(first)
        order.insert(0, first)
    harmed = [i for i in order if i in set(self_harm) and not (lethal and i == order[0])]
    return [i for i in order if i not in harmed] + harmed


# ----- metrics -----------------------------------------------------------------------------------

def scores(position: dict, ranking: list[int] | None, menu_size: int) -> dict:
    acceptable, blunder, best = set(position["acceptable"]), set(position["blunder"]), set(position["best"])
    if ranking is None:  # uniform: exact expectations
        def any_in_top3(k):
            return 1 - comb(menu_size - k, 3) / comb(menu_size, 3)
        return {"top1_acceptable": len(acceptable) / menu_size, "top1_blunder": len(blunder) / menu_size,
                "top3_any_acceptable": any_in_top3(len(acceptable)),
                "best_in_top3": any_in_top3(len(best)) if best else None}
    top3 = set(ranking[:3])
    return {"top1_acceptable": float(ranking[0] in acceptable), "top1_blunder": float(ranking[0] in blunder),
            "top3_any_acceptable": float(bool(top3 & acceptable)),
            "best_in_top3": float(bool(top3 & best)) if best else None}


METRICS = ("top1_acceptable", "top1_blunder", "top3_any_acceptable", "best_in_top3")


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def summarize(rows: list[dict]) -> dict:
    return {arm: {m: mean([r["scores"][arm][m] for r in rows if arm in r["scores"]]) for m in METRICS}
            for arm in ARMS} | {"positions": len(rows), "matches": len({r["game_id"] for r in rows})}


def bootstrap(rows: list[dict], pairs: list[tuple[str, str]]) -> dict:
    """Whole-match resampling: 95% percentile intervals for every arm/metric and paired differences."""
    by_match = defaultdict(list)
    for r in rows:
        by_match[r["game_id"]].append(r)
    matches = sorted(by_match)
    rng = random.Random(BOOTSTRAP_SEED)
    draws = defaultdict(list)
    for _ in range(BOOTSTRAP_DRAWS):
        sample = [r for g in (rng.choice(matches) for _ in matches) for r in by_match[g]]
        for arm in ARMS:
            for m in METRICS:
                value = mean([r["scores"][arm][m] for r in sample if arm in r["scores"]])
                if value is not None:
                    draws[(arm, m)].append(value)
        for left, right in pairs:
            for m in ("top1_acceptable", "top1_blunder"):
                a = mean([r["scores"][left][m] for r in sample])
                b = mean([r["scores"][right][m] for r in sample])
                draws[(f"{left}-{right}", m)].append(a - b)

    def ci(values):
        values = sorted(values)
        return [values[int(0.025 * len(values))], values[int(0.975 * len(values)) - 1]] if values else None
    point = summarize(rows)
    out = {"arms": {arm: {m: {"mean": point[arm][m], "ci95": ci(draws[(arm, m)])} for m in METRICS} for arm in ARMS},
           "paired": {}}
    for left, right in pairs:
        out["paired"][f"{left} - {right}"] = {
            m: {"mean": mean([r["scores"][left][m] for r in rows]) - mean([r["scores"][right][m] for r in rows]),
                "ci95": ci(draws[(f"{left}-{right}", m)])} for m in ("top1_acceptable", "top1_blunder")}
    return out


def family(action: dict) -> str:
    return action["type"] if action["type"] != "PLAY_CARD" else f"PLAY_{action.get('card_type')}"


def main() -> None:
    if PUBLIC.exists() or PRIVATE_OUT.exists():
        raise SystemExit("refusing to overwrite comparison outputs")
    positions, meta = labeled_positions()
    examples = reimport({p["game_id"] for p in positions})
    pool = {json.loads(line)["decision_id"]: json.loads(line)
            for line in (dq.PRIVATE / "pool.private.jsonl").read_text(encoding="utf-8").splitlines()}
    rows = []
    for p in positions:
        example = examples[p["decision_id"]]
        locked = pool[p["decision_id"]]
        if dq.canonical(example["legal_actions"]) != dq.canonical(locked["legal_actions"]) or \
                dq.canonical(example["state"]) != dq.canonical(locked["state"]):
            raise ValueError("re-imported position differs from the locked one")
        rows.append(example)
    rankings = {name: policy_rankings(name, rows) for name in MODEL_SPECS}
    mech = mechanics(rows)
    records = []
    for p, row in zip(positions, rows):
        d = row["decision_id"]
        menu = row["legal_actions"]
        ranks = {"frozen_v2": rankings["frozen_v2"][d], "policy_v3": rankings["policy_v3"][d],
                 "scorer_v3": mech[d]["scorer"],
                 "frozen_v2_guard": guarded(rankings["frozen_v2"][d], mech[d]["lethal"], mech[d]["self_harm"]),
                 "player": [row["chosen_action_index"]]}
        record = {**p, "menu_size": len(menu), "chosen": row["chosen_action_index"], "rankings": ranks,
                  "lethal": mech[d]["lethal"], "self_harm": mech[d]["self_harm"],
                  "forecast_statuses": mech[d]["statuses"],
                  "top1_family": {arm: family(menu[r[0]]) for arm, r in ranks.items()},
                  "blunder_families": [family(menu[i]) for i in p["blunder"]]}
        if p["status"] == "LABELED":
            record["scores"] = {arm: scores(p, r, len(menu)) for arm, r in ranks.items()}
            record["scores"]["player"] = {k: (v if k in ("top1_acceptable", "top1_blunder") else None)
                                          for k, v in record["scores"]["player"].items()}
            record["scores"]["uniform"] = scores(p, None, len(menu))
        records.append(record)
    labeled = [r for r in records if r["status"] == "LABELED"]
    pairs = [("frozen_v2", "uniform"), ("frozen_v2_guard", "frozen_v2"), ("policy_v3", "frozen_v2"),
             ("scorer_v3", "frozen_v2")]
    slices = {}
    for name, key in (("batch", lambda r: r["batch"]), ("self_class", lambda r: r["self_class"]),
                      ("menu_bucket", lambda r: r["menu_bucket"])):
        groups = defaultdict(list)
        for r in labeled:
            groups[key(r)].append(r)
        slices[name] = {k: summarize(v) for k, v in sorted(groups.items())}
    v2_blunders = [r for r in labeled if r["scores"]["frozen_v2"]["top1_blunder"] == 1.0]
    v2_not_ok = [r for r in labeled if r["scores"]["frozen_v2"]["top1_acceptable"] == 0.0]
    taxonomy = {
        "v2_top1_blunder_positions": len(v2_blunders),
        "v2_top1_not_acceptable_positions": len(v2_not_ok),
        "v2_top1_family_when_blunder": dict(Counter(r["top1_family"]["frozen_v2"] for r in v2_blunders)),
        "v2_top1_family_when_not_acceptable": dict(Counter(r["top1_family"]["frozen_v2"] for r in v2_not_ok)),
        "v2_top1_family_all": dict(Counter(r["top1_family"]["frozen_v2"] for r in labeled)),
        "blunder_marks_by_family": dict(Counter(f for r in labeled for f in r["blunder_families"])),
        "positions_with_any_blunder_mark": sum(bool(r["blunder"]) for r in labeled),
        "mechanically_checkable_v2_blunders": sum(
            1 for r in v2_blunders if r["rankings"]["frozen_v2"][0] in r["self_harm"]
            or (r["lethal"] and r["rankings"]["frozen_v2"][0] not in r["lethal"])),
        "guard": {"positions_with_confirmed_lethal": sum(bool(r["lethal"]) for r in records),
                  "positions_with_self_harm_flag": sum(bool(r["self_harm"]) for r in records),
                  "top1_changed": sum(r["rankings"]["frozen_v2_guard"][0] != r["rankings"]["frozen_v2"][0]
                                      for r in records)},
        "remembered_positions": sum(r["remembers_game"] for r in records),
    }
    sensitivity = summarize([r for r in labeled if not r["remembers_game"]])
    public = {
        "schema": "manamind.decision_quality_review_1/results/1", "created_at_utc": dq.now(),
        "source_commit": dq.git_head(), "code_sha256": dq.sha256_file(Path(__file__)),
        "labels": meta,
        "positions": len(records), "labeled": len(labeled),
        "insufficient_information": len(records) - len(labeled),
        "label_shape": {"mean_menu_size": mean([r["menu_size"] for r in labeled]),
                        "mean_acceptable_per_position": mean([len(r["acceptable"]) for r in labeled]),
                        "mean_acceptable_share": mean([len(r["acceptable"]) / r["menu_size"] for r in labeled]),
                        "positions_with_best": sum(bool(r["best"]) for r in labeled),
                        "confidence": dict(Counter(r["confidence"] for r in labeled))},
        "bootstrap": {"draws": BOOTSTRAP_DRAWS, "seed": BOOTSTRAP_SEED, "unit": "whole match"},
        "results": bootstrap(labeled, pairs), "slices": slices, "taxonomy": taxonomy,
        "without_remembered_positions": sensitivity,
        "rater_stability": "NOT_MEASURED (PROTOCOL amendment 1)",
    }
    dq.write_once(PRIVATE_OUT, json.dumps(records, ensure_ascii=False, indent=1) + "\n")
    dq.write_once(PUBLIC, json.dumps(public, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({k: public[k] for k in ("positions", "labeled", "results", "taxonomy")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
