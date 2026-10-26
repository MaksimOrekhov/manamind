"""Read-only reconstruction of the frozen 48 labels; no fitting or LIVE changes.

Writes sensitive reconstructions only below the ignored private output directory.
Public reports are a separate, manual evidence assessment, not generated labels.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

PRIVATE = ROOT / "data/processed_policy_error_root_cause_1"
SOURCE = ROOT / "data/processed_decision_quality_review_1"
AUDIT_ROOT = PRIVATE


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def require_disjoint(selected: set[str], heldout: set[str]) -> None:
    """Check full and raw-file-prefix identities before any game-bearing read."""
    if {s[:16] for s in selected} & {s[:16] for s in heldout}:
        raise ValueError("protected match overlap")


def exact_signature(action: dict) -> tuple:
    """Family/target audit: keep exact identities/target; collapse insertion slots only."""
    return tuple(sorted((k, v) for k, v in action.items() if k != "play_position"))


def family(action: dict) -> str:
    return action["type"] + ("_" + action.get("card_type", "UNKNOWN") if action["type"] == "PLAY_CARD" else "")


def aggregate(records: list[dict]) -> dict:
    """A small public projection: no private identities, menus, comments or states."""
    result = {}
    for name, rows in (("errors", [r for r in records if r["case"].startswith("E")]),
                       ("controls", [r for r in records if r["case"].startswith("C")])):
        top = [r["actions"][r["policy_ranking"][0]] for r in rows]
        source = [(r, a) for r, a in zip(rows, top) if a["action"].get("source_card_id")]
        result[name] = {
            "positions": len(rows),
            # Two synthetic hero-stat tokens have no card identity by design.
            "nonhero_unknown_tokens": sum(r["entity_unknown"] - 2 for r in rows),
            "nonhero_tokens": sum(r["entity_total"] - 2 for r in rows),
            "source_actions": len(source),
            "unknown_source": sum(r["cards"][a["action"]["source_card_id"]]["vocabulary_index"] == 1
                                  for r, a in source),
            "acceptable_in_policy_top3": sum(any(r["actions"][i]["acceptable"]
                                                  for i in r["policy_ranking"][:3]) for r in rows),
            "policy_acceptable": sum(a["acceptable"] for a in top),
            "scorer_acceptable": sum(r["actions"][r["scorer_ranking"][0]]["acceptable"] for r in rows),
            "scorer_blunder": sum(r["actions"][r["scorer_ranking"][0]]["blunder"] for r in rows),
            "acceptable_same_family": sum(any(a["acceptable"] and family(a["action"]) == family(t["action"])
                                               for a in r["actions"]) for r, t in zip(rows, top)),
            "acceptable_same_source_type": sum(any(a["acceptable"]
                 and (a["action"]["type"], a["action"].get("source_card_id")) ==
                     (t["action"]["type"], t["action"].get("source_card_id")) for a in r["actions"])
                 for r, t in zip(rows, top)),
        }
    result["label_conflict_collision_positions"] = sum(bool(r["candidate_label_collisions"]) for r in records)
    result["max_single_candidate_logit_change"] = max(r["menu_invariance_error"] for r in records)
    result["paired_scorer"] = {
        "fixes_policy_blunder_with_acceptable": sum(r["actions"][r["policy_ranking"][0]]["blunder"]
            and r["actions"][r["scorer_ranking"][0]]["acceptable"] for r in records),
        "policy_acceptable_to_scorer_blunder": sum(r["actions"][r["policy_ranking"][0]]["acceptable"]
            and r["actions"][r["scorer_ranking"][0]]["blunder"] for r in records),
        "policy_blunder_to_not_blunder": sum(r["actions"][r["policy_ranking"][0]]["blunder"]
            and not r["actions"][r["scorer_ranking"][0]]["blunder"] for r in records),
        "policy_not_blunder_to_scorer_blunder": sum(not r["actions"][r["policy_ranking"][0]]["blunder"]
            and r["actions"][r["scorer_ranking"][0]]["blunder"] for r in records),
    }
    # First eligible frozen ordinal; no score-gap or particularly vivid-case selection.
    predicates = {
        "policy_acceptable": lambda r: r["actions"][r["policy_ranking"][0]]["acceptable"],
        "both_acceptable": lambda r: all(r["actions"][r[k][0]]["acceptable"]
                                         for k in ("policy_ranking", "scorer_ranking")),
        "scorer_blunder": lambda r: r["actions"][r["scorer_ranking"][0]]["blunder"],
        "policy_acceptable_scorer_blunder": lambda r: r["actions"][r["policy_ranking"][0]]["acceptable"]
                                             and r["actions"][r["scorer_ranking"][0]]["blunder"],
        "attack_with_available_draw_discover_or_buff": lambda r:
            r["actions"][r["policy_ranking"][0]]["acceptable"]
            and r["actions"][r["policy_ranking"][0]]["action"]["type"] == "ATTACK"
            and any(a["action"].get("source_card_id") in {"TLC_451", "TIME_026", "CORE_EX1_302"}
                    for a in r["actions"]),
    }
    result["controls_selected"] = {
        k: next((r["case"] for r in sorted(records, key=lambda r: r["ordinal"])
                 if r["case"].startswith("C") and predicate(r)), None)
        for k, predicate in predicates.items()}
    return result


def diagnostic_audit() -> None:
    import decision_quality_review_1 as dq
    from manamind.card_metadata import CardMetadata

    output = PRIVATE / "diagnostics.private.json"
    if output.exists():
        raise SystemExit("refusing to overwrite diagnostics")
    audit = read(PRIVATE / "reconstruction.private.json")
    metadata = CardMetadata.load(audit["metadata_snapshot"])
    cards = {}

    def visit(value):
        if isinstance(value, dict):
            cid = value.get("card_id")
            if cid and cid not in cards:
                m = metadata.get(cid)
                cards[cid] = dict(m) if m is not None else None
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for record in audit["records"]:
        visit(record["state"])
    public = aggregate(audit["records"])
    result = {"script_sha256": digest(Path(__file__)), "aggregate": public,
              "all_visible_cards_metadata": cards,
              "private_reconstruction_sha256": digest(PRIVATE / "reconstruction.private.json"),
              "private_training_sha256": digest(PRIVATE / "training.private.json")}
    dq.write_once(output, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(public, ensure_ascii=False, indent=1))


def training_audit() -> None:
    """Count exposure in the exact checkpoint-owned corpus, never the current pool."""
    import torch

    import decision_quality_review_1 as dq
    from manamind.training.policy_checkpoint import identity

    output = PRIVATE / "training.private.json"
    if output.exists():
        raise SystemExit("refusing to overwrite training diagnostics")
    audit = read(PRIVATE / "reconstruction.private.json")
    checkpoint = ROOT / "data/processed_policy_ml2a/seed42_v2/policy.pt"
    if digest(checkpoint) != audit["checkpoint_sha256"]:
        raise ValueError("checkpoint changed")
    payload = torch.load(checkpoint, map_location="cpu", weights_only=True)
    experiment = payload["experiment"]
    split = experiment["split"]
    held = set(read(dq.SPLIT_PLAN)["parts"]["fresh_holdout"])
    all_ids = {g for ids in split["game_ids"].values() for g in ids}
    require_disjoint(all_ids, held)
    rows, hashes = [], {}
    for game in sorted(all_ids):
        path = checkpoint.parent / "dataset" / f"{game}.jsonl"
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if any(r["game_id"] != game for r in values):
            raise ValueError("unexpected match in frozen training snapshot")
        rows.extend(values)
        hashes[path.name] = digest(path)
    if identity(sorted(rows, key=lambda r: r["decision_id"])) != experiment["dataset_sha256"]:
        raise ValueError("frozen dataset identity changed")
    train = [r for r in rows if r["game_id"] in set(split["game_ids"]["train"])]
    if set(r["decision_id"] for r in train) != set(split["decision_ids"]["train"]):
        raise ValueError("train membership mismatch")
    card_ids = {cid for record in audit["records"] for cid in record["cards"]}
    exposure = {}
    for cid in sorted(card_ids):
        hand_rows = [r for r in train if any(c["card_id"] == cid for c in r["state"]["self_hand"])]
        menu_rows = [r for r in train if any(a.get("source_card_id") == cid for a in r["legal_actions"])]
        chosen_rows = [r for r in train if r["legal_actions"][r["chosen_action_index"]].get("source_card_id") == cid]
        exposure[cid] = {"hand_decisions": len(hand_rows), "menu_decisions": len(menu_rows),
                         "chosen_decisions": len(chosen_rows),
                         "hand_games": len({r["game_id"] for r in hand_rows}),
                         "menu_games": len({r["game_id"] for r in menu_rows})}
    classes = Counter(r["state"]["self_player"]["player_class"] for r in train)
    class_games = {k: len({r["game_id"] for r in train if r["state"]["self_player"]["player_class"] == k})
                   for k in classes}
    # Exposure of the issue, not proof that a logged player action is optimal.
    order_counts = Counter()
    for r in train:
        menu = r["legal_actions"]
        chosen = menu[r["chosen_action_index"]]
        cat = any(a.get("source_card_id") == "TLC_451" for a in menu)
        attacks = any(a["type"] == "ATTACK" for a in menu)
        if cat:
            order_counts["catacombs_available"] += 1
            order_counts["catacombs_chosen"] += int(chosen.get("source_card_id") == "TLC_451")
            if attacks:
                order_counts["catacombs_with_attack"] += 1
                order_counts["catacombs_chosen_with_attack"] += int(chosen.get("source_card_id") == "TLC_451")
    result = {"schema": "manamind.policy_error_root_cause_1/training/1",
              "dataset_sha256": experiment["dataset_sha256"], "dataset_files_sha256": hashes,
              "train_games": len(split["game_ids"]["train"]), "train_decisions": len(train),
              "classes_decisions": dict(classes), "classes_games": class_games,
              "chosen_action_types": dict(Counter(r["legal_actions"][r["chosen_action_index"]]["type"]
                                                  for r in train)),
              "card_exposure": exposure, "order_exposure": dict(order_counts)}
    dq.write_once(output, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({k: result[k] for k in ("train_games", "train_decisions", "classes_decisions",
                                            "classes_games", "order_exposure")}))


def run() -> None:
    import torch

    import decision_quality_review_1 as dq
    import decision_quality_review_1_compare as cmp
    from manamind.card_metadata import CardMetadata
    from manamind.domain.serialization import game_state_from_dict
    from manamind.models.policy_inputs import encode_policy_inputs, representation_of
    from manamind.outcome.forecast import forecast_alternatives
    from manamind.outcome.live_shadow import load_texts
    from manamind.outcome.observation import context_from_observed
    from manamind.strategy import score_menu
    from manamind.training.policy_checkpoint import load_policy_checkpoint
    from new_matches_eval_1 import MODELS

    out = PRIVATE / "reconstruction.private.json"
    if out.exists():
        raise SystemExit("refusing to overwrite private audit")
    torch.set_num_threads(1)
    positions, label_meta = cmp.labeled_positions()
    held = set(read(dq.SPLIT_PLAN)["parts"]["fresh_holdout"])
    require_disjoint({p["game_id"] for p in positions}, held)
    inventory = read(SOURCE / "inventory.private.json")
    require_disjoint({m["game_id"] for m in inventory["matches"]}, held)
    lock = read(SOURCE / "lock.private.json")
    inputs = {name: digest(SOURCE / name) for name in (
        "lock.private.json", "inventory.private.json", "pool.private.jsonl",
        "compare.private.json", "pilot.manifest.private.json", "main.manifest.private.json",
        "labels/user/pilot.labels.jsonl", "labels/user/main.labels.jsonl",
        "labels/user/pilot.freeze.json", "labels/user/main.freeze.json")}
    if inputs["pool.private.jsonl"] != lock["pool_sha256"]:
        raise ValueError("pool changed")
    if inputs["inventory.private.json"] != lock["inventory_sha256"]:
        raise ValueError("inventory changed")
    pool = {r["decision_id"]: r for r in (
        json.loads(line) for line in (SOURCE / "pool.private.jsonl").read_text(encoding="utf-8").splitlines())}
    examples = cmp.reimport({p["game_id"] for p in positions})
    reference = {r["decision_id"]: r for r in read(SOURCE / "compare.private.json")}
    spec = next(m for m in MODELS if m["name"] == "frozen_v2")
    checkpoint = ROOT / spec["path"]
    if digest(checkpoint) != spec["sha256"]:
        raise ValueError("checkpoint changed")
    model, encoder, payload = load_policy_checkpoint(io.BytesIO(checkpoint.read_bytes()), device="cpu")
    model.eval()
    representation = representation_of(model)
    metadata = CardMetadata.load(lock["card_metadata_snapshot"])
    texts = load_texts(ROOT)
    records = []
    error_n = control_n = 0
    for ordinal, p in enumerate(positions, 1):
        example = examples[p["decision_id"]]
        locked = pool[p["decision_id"]]
        for key in ("state", "legal_actions"):
            if dq.canonical(example[key]) != dq.canonical(locked[key]):
                raise ValueError("reimport differs from frozen pool")
        state = game_state_from_dict(example["state"])
        menu = example["legal_actions"]
        keep = [i for i, a in enumerate(menu) if a["type"] != "PREPARE_CARD"]
        actions = [menu[i] for i in keep]
        context = context_from_observed(example["observed_facts"], state)
        with torch.inference_mode():
            tensors = encode_policy_inputs(state, actions, encoder, representation=representation)
            logits = model(*tensors).double()
            if not torch.isfinite(logits).all():
                raise ValueError("nonfinite logits")
            probabilities = logits.softmax(0)
            order = sorted(range(len(keep)), key=lambda i: (-float(logits[i]), i))
            ranking = [keep[i] for i in order]
            top = order[0]
            solo = model(*encode_policy_inputs(state, [actions[top]], encoder, representation=representation))
            menu_invariance_error = abs(float(logits[top]) - float(solo[0]))
        scored = score_menu(state, menu, texts, context, budget_ms=10_000)
        if scored.computed != len(menu):
            raise ValueError("incomplete scorer")
        ref = reference[p["decision_id"]]
        if ranking != ref["rankings"]["frozen_v2"] or list(scored.ranking) != ref["rankings"]["scorer_v3"]:
            raise ValueError("rankings differ from frozen comparison")
        is_error = ranking[0] in p["blunder"]
        if is_error:
            error_n += 1
        else:
            control_n += 1
        case = f"E{error_n:02}" if is_error else f"C{control_n:02}"
        identities = sorted({v for a in menu for k, v in a.items() if k.endswith("card_id") and v})
        # Full before-only descriptions and exact outputs remain private.
        cards = {}
        for card_id in identities:
            m = metadata.get(card_id)
            cards[card_id] = {
                "metadata": dict(m) if m is not None else None,
                "vocabulary_index": encoder.vocabulary.card_id(card_id),
                "checkpoint_catalog_present": card_id in encoder.vocabulary.to_dict()["card_ids"],
            }
        forecasts = forecast_alternatives(state, menu, texts, context)
        action_rows = []
        for i, action in enumerate(menu):
            j = keep.index(i) if i in keep else None
            f = forecasts[i]
            action_rows.append({
                "index": i, "action": action,
                "logit": None if j is None else float(logits[j]),
                "probability": None if j is None else float(probabilities[j]),
                "scorer": scored.actions[i].to_dict(),
                "forecast": f.to_dict(),
                "acceptable": i in p["acceptable"], "blunder": i in p["blunder"],
                "best": i in p["best"],
            })
        # Candidate features include local links and identity columns. Measure exact
        # collisions only; this does not test whether learned attention is useful.
        signatures = [tuple(tensors[3][j].tolist()) + tuple(tensors[4][j].tolist())
                      + tuple(tensors[5][j].tolist()) for j in range(len(keep))]
        conflicts = [(keep[i], keep[j]) for i in range(len(keep)) for j in range(i)
                     if signatures[i] == signatures[j]
                     and ((keep[i] in p["acceptable"] and keep[j] in p["blunder"])
                          or (keep[j] in p["acceptable"] and keep[i] in p["blunder"]))]
        records.append({"case": case, "ordinal": ordinal, "labels": p,
                        "state": example["state"], "actions": action_rows, "cards": cards,
                        "policy_ranking": ranking, "scorer_ranking": list(scored.ranking),
                        "player_choice": example["chosen_action_index"],
                        "input_shapes": [list(t.shape) for t in tensors],
                        "entity_unknown": int((tensors[1] == 1).sum()),
                        "entity_total": len(tensors[1]),
                        "entity_card_indices": tensors[1].tolist(),
                        "candidate_label_collisions": conflicts,
                        "menu_invariance_error": menu_invariance_error})
        print(f"reconstructed {ordinal}/48 ({case})", flush=True)
    if error_n != 12 or control_n != 36:
        raise ValueError("unexpected frozen cohort")
    if any(digest(SOURCE / k) != v for k, v in inputs.items()) or digest(checkpoint) != spec["sha256"]:
        raise ValueError("inputs changed during audit")
    result = {"schema": "manamind.policy_error_root_cause_1/private/1",
              "base_commit": "3e03ca0f919c63892c4c18208e967d2a9c920ecd",
              "script_sha256": digest(Path(__file__)), "input_sha256": inputs,
              "checkpoint_sha256": spec["sha256"], "model_config": payload["model_config"],
              "catalog_sha256": payload["catalog_sha256"],
              "vocabulary_sha256": payload["vocabulary_sha256"],
              "metadata_snapshot": metadata.snapshot_id, "label_meta": label_meta,
              "training_experiment": payload["experiment"], "records": records,
              "aggregate": {"errors": error_n, "controls": control_n,
                            "games": len({p["game_id"] for p in positions}),
                            "classes": dict(Counter(p["self_class"] for p in positions))}}
    dq.write_once(out, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(result["aggregate"]))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=AUDIT_ROOT)
    parser.add_argument("--phase", choices=("reconstruct", "training", "diagnostics"), default="reconstruct")
    args = parser.parse_args()
    PRIVATE = args.output_dir.resolve()
    if not PRIVATE.is_relative_to(AUDIT_ROOT.resolve()):
        parser.error("output must remain inside the ignored audit directory")
    if args.phase == "training":
        training_audit()
    elif args.phase == "diagnostics":
        diagnostic_audit()
    else:
        run()
