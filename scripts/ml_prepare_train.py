"""ML-PREPARE-TRAIN-1: train Policy v2/v3 with and without the Prepare-aware corpus (behavior cloning, bounded CPU).

Groups (``configs/ml_prepare_train_1/experiment.json``, registered before any run):
  prepare_v2 / prepare_v3  all decisions of the train matches (action schema 1 and 2), checkpoint semantic schema 2
  control_v2 / control_v3  the same matches, schema-1 decisions only, ordinary semantic-schema-1 checkpoint

The split is the one in ``split_plan.json``: train -> training, validation -> epoch selection, test_seen -> final
descriptive diagnostics (written as the checkpoint's "test" part). ``fresh_holdout`` is never read: its match files are
not opened, only listed by name to prove they are disjoint from the other parts.

  python scripts/ml_prepare_train.py train --group prepare_v3 --seed 42
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from manamind.training.policy_checkpoint import identity  # noqa: E402
from manamind.training.real_policy import validate_example  # noqa: E402

CORPUS = ROOT / "data/processed_policy_prepare_1"
OUTPUT = ROOT / "data/processed_policy_prepare_train_1"
EXPERIMENT = ROOT / "configs/ml_prepare_train_1/experiment.json"
PART_NAMES = {"train": "train", "validation": "validation", "test": "test_seen"}  # checkpoint part -> plan part
V3_ONLY = ("heads", "entity_layers", "menu_layers")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_plan(corpus: Path = CORPUS) -> dict:
    """The corpus split plan, checked for internal consistency and for matching the match files on disk."""
    plan = json.loads((corpus / "split_plan.json").read_text(encoding="utf-8"))
    parts = plan["parts"]
    if set(parts) != {"train", "validation", "test_seen", "fresh_holdout"}:
        raise ValueError("Unexpected split plan parts")
    flat = [g for ids in parts.values() for g in ids]
    if len(flat) != len(set(flat)) or any(not ids for ids in parts.values()):
        raise ValueError("Split plan parts overlap or are empty")
    if plan["split_sha256"] != identity({"algorithm": plan["algorithm"], "seed": plan["seed"], "parts": parts}):
        raise ValueError("Split plan identity mismatch")
    on_disk = {p.stem for p in (corpus / "dataset").glob("*.jsonl")}
    if on_disk != set(flat):
        raise ValueError("Split plan does not cover the dataset files exactly")
    return plan


def read_match(corpus: Path, game_id: str) -> list[dict]:
    path = corpus / "dataset" / f"{game_id}.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows or {r["game_id"] for r in rows} != {game_id}:
        raise ValueError("Match file does not hold exactly its own match")
    for row in rows:
        validate_example(row, allow_prepare=True)
    return rows


def load_parts(corpus: Path = CORPUS, plan: dict | None = None) -> tuple[dict, dict]:
    """Rows of train/validation/test_seen keyed by checkpoint part name; fresh_holdout files are never opened."""
    plan = plan or load_plan(corpus)
    parts = {name: [r for g in plan["parts"][source] for r in read_match(corpus, g)]
             for name, source in PART_NAMES.items()}
    for rows in parts.values():
        rows.sort(key=lambda r: r["decision_id"])
    return parts, plan


def schema1_only(parts: dict) -> dict:
    """The control data: every decision whose menu has no Prepare root (exactly the earlier action schema 1 rows)."""
    reduced = {name: [r for r in rows if r["action_schema_version"] == 1] for name, rows in parts.items()}
    for name, rows in reduced.items():
        if not rows or any(a["type"] == "PREPARE_CARD" for r in rows for a in r["legal_actions"]):
            raise ValueError(f"Control {name} part is empty or still holds Prepare")
    return reduced


def build_split(parts: dict, plan: dict) -> dict:
    """The checkpoint's split record. Its "test" part is the plan's test_seen; fresh_holdout ids are only reserved."""
    split = {"algorithm": plan["algorithm"], "seed": plan["seed"],
             "game_ids": {name: sorted({r["game_id"] for r in rows}) for name, rows in parts.items()},
             "reserved_game_ids": sorted(plan["parts"]["fresh_holdout"]), "plan_sha256": plan["split_sha256"],
             "part_names": PART_NAMES}
    split["dataset_sha256"] = identity(sorted((r for rows in parts.values() for r in rows),
                                              key=lambda r: r["decision_id"]))
    expected = {n: sorted(plan["parts"][s]) for n, s in PART_NAMES.items()}
    if split["game_ids"] != expected:
        raise ValueError("A part lost or gained a match")
    return split


def group_config(base_path: Path, architecture: str, seed: int) -> dict:
    base = json.loads(Path(base_path).read_text(encoding="utf-8-sig"))["base"]
    config = {**base, "architecture": architecture, "seed": seed}
    if architecture == "v2":
        for key in V3_ONLY:
            config.pop(key)
    return config


def train(group: str, seed: int, output_root: Path, corpus: Path = CORPUS, experiment_path: Path = EXPERIMENT,
          max_epochs: int | None = None) -> dict:
    import train_policy_v3 as trainer

    experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
    spec = experiment["groups"][group]
    parts, plan = load_parts(corpus)
    if spec["data"] == "schema1_only":
        parts = schema1_only(parts)
    split = build_split(parts, plan)
    config = group_config(ROOT / experiment["base_config"], spec["architecture"], seed)
    if max_epochs is not None:  # smoke runs only; a real run must keep the registered configuration
        config["max_epochs"] = max_epochs
    output = Path(output_root) / f"{group}_seed{seed}"
    result = trainer.run(corpus / "dataset", corpus / "split_plan.json", ROOT / "data/cards/standard_current_enUS.json",
                         output, config, label=output.name, allow_prepare=spec["allow_prepare"],
                         prepared=(parts, split),
                         ablate_prepare_feature=spec.get("ablate_prepare_feature", False))
    provenance = {"group": group, "seed": seed, "spec": spec, "experiment_sha256": sha256_file(experiment_path),
                  "split_plan_sha256": plan["split_sha256"], "dataset_sha256": split["dataset_sha256"],
                  "decisions": {name: len(rows) for name, rows in parts.items()},
                  "matches": {name: len(ids) for name, ids in split["game_ids"].items()},
                  "prepare_in_menu": {name: sum(r["action_schema_version"] == 2 for r in rows)
                                      for name, rows in parts.items()},
                  "prepare_chosen": {name: sum(r["legal_actions"][r["chosen_action_index"]]["type"] == "PREPARE_CARD"
                                               for r in rows) for name, rows in parts.items()},
                  "match_file_sha256": {g: sha256_file(corpus / "dataset" / f"{g}.jsonl")
                                        for ids in split["game_ids"].values() for g in ids},
                  "ablate_prepare_feature": spec.get("ablate_prepare_feature", False), "fresh_holdout_opened": False, "checkpoint_sha256": result["checkpoint_sha256"]}
    with (output / "provenance.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(provenance, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("train")
    one.add_argument("--group", required=True)
    one.add_argument("--seed", type=int, required=True)
    one.add_argument("--output", type=Path, default=OUTPUT)
    one.add_argument("--experiment", type=Path, default=EXPERIMENT, help="registered experiment definition")
    one.add_argument("--max-epochs", type=int, default=None, help="smoke runs only")
    args = parser.parse_args()
    result = train(args.group, args.seed, args.output, experiment_path=args.experiment, max_epochs=args.max_epochs)
    print(json.dumps({k: result[k] for k in ("label", "selected_epoch", "epochs_run", "parameters", "training_seconds",
                                             "best_validation_cross_entropy")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
