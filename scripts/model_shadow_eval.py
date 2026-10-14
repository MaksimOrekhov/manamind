"""MODEL-SHADOW-EVAL-1: how well did Policy v2, the retrained v2 and Policy v3 predict the player's real actions?

Reads the model-shadow journal(s) from ``--model-shadow`` live sessions, re-imports every journaled match from its
completed Power.log (``data/raw/collected/<match id[:16]>.log``) with the existing Policy importer in memory, pairs each
shadow decision with the player's confirmed action (match id + options_id + state_hash + full ordered menu must agree)
and reports Top-1 / Top-3 / MRR per model and per match, Demon Hunter category breakdowns and model disagreements.
Training matches of every checkpoint are excluded as TRAINING_OVERLAP. Read-only: nothing is trained, no log, journal or
dataset is modified, the report goes to a NEW file.

  python scripts/model_shadow_eval.py                                  # journals under data/raw/live, console report
  python scripts/model_shadow_eval.py --out reports/model_shadow_eval_1/eval.json --examples 8
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.integrations.powerlog.policy_import import PolicyImportError, extract_match  # noqa: E402
from manamind.policy_shadow.analysis import read_journal  # noqa: E402
from manamind.policy_shadow.evaluation import MatchLabels, evaluate, render  # noqa: E402
from manamind.training.policy_checkpoint import load_policy_checkpoint  # noqa: E402

CARDS = ROOT / "data/cards/standard_current_enUS.json"
MODEL_ORDER = ("policy_v2", "retrained_v2", "policy_v3")


def checkpoint_paths() -> dict[str, Path]:
    import run_manamind
    return {"policy_v2": run_manamind.POLICY_V2_CHECKPOINT, "retrained_v2": run_manamind.RETRAINED_V2_CHECKPOINT,
            "policy_v3": run_manamind.POLICY_V3_CHECKPOINT}


def training_games(paths: dict[str, Path], frozen_split: Path | None) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Matches each checkpoint trained or was selected on (train + validation + test), read from the checkpoint itself.

    Also returns the SHA-256 of the very bytes that were parsed, to be compared with the digest in the shadow journal.
    """
    result, digests = {}, {}
    for name, path in paths.items():
        if not Path(path).is_file():
            raise SystemExit(f"checkpoint for {name} not found: {path} (needed to prove the matches are independent)")
        data = Path(path).read_bytes()
        digests[name] = hashlib.sha256(data).hexdigest()
        _, _, payload = load_policy_checkpoint(io.BytesIO(data), device="cpu")
        groups = payload.get("experiment", {}).get("split", {}).get("game_ids", {})
        result[name] = {game for games in groups.values() for game in games}
    if frozen_split is not None and frozen_split.is_file():
        frozen = json.loads(frozen_split.read_text(encoding="utf-8"))
        result["frozen_split_v3"] = {g for games in frozen.get("game_ids", {}).values() for g in games}
    return result, digests


def card_names(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    cards = payload.get("cards", []) if isinstance(payload, dict) else payload
    return {c.get("id") or c.get("card_id"): (c.get("name") if isinstance(c.get("name"), str) else (c.get("name") or {}).get("enUS"))
            for c in cards if isinstance(c, dict) and (c.get("id") or c.get("card_id"))}


def import_matches(match_ids: set[str], raw_dir: Path, catalog: CardCatalog, *,
                   prepare_actions: bool = False) -> dict[str, MatchLabels]:
    labels = {}
    for match in sorted(match_ids):
        path = raw_dir / f"{match[:16]}.log"
        if not path.is_file():
            continue
        try:
            examples, summary = extract_match(path.read_text(encoding="utf-8").splitlines(), catalog,
                                              prepare_actions=prepare_actions)
            labels[match] = MatchLabels.from_import(examples, summary)
        except PolicyImportError as error:
            labels[match] = MatchLabels(import_error=error.reason)
    return labels


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--journal", type=Path, nargs="*",
                        help="model-shadow journals; default: <data-root>/raw/live/prediction_journal.model_shadow*.jsonl")
    parser.add_argument("--data-root", type=Path, default=ROOT / "data")
    parser.add_argument("--raw-dir", type=Path, help="completed Power.log files; default: <data-root>/raw/collected")
    parser.add_argument("--prediction-journal", type=Path,
                        help="Policy journal that explains decisions without a shadow row; default: <data-root>/raw/live/prediction_journal.jsonl")
    parser.add_argument("--match", nargs="*", help="only these match ids (prefixes allowed)")
    parser.add_argument("--self-class", default="DEMONHUNTER", help="class of the category breakdown")
    parser.add_argument("--examples", type=int, default=6, help="model-disagreement examples to list")
    parser.add_argument("--out", type=Path, help="write the full report here (a NEW file)")
    parser.add_argument("--prepare-actions", action="store_true",
                        help="experimental: label Prepare cards' PLAY_CARD / PREPARE_CARD roots (use with run_manamind.py --prepare-actions)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    live = args.data_root / "raw/live"
    paths = args.journal or sorted(live.glob("prediction_journal.model_shadow*.jsonl"))
    if not paths:
        print("no model-shadow journal found; play with run_manamind.py --model-shadow first")
        return 1
    if args.out is not None and args.out.exists():
        print(f"{args.out} exists; choose a new file (results are never overwritten)")
        return 1
    rows = read_journal(paths)
    if args.match:
        rows = [r for r in rows if any(str(r.get("match_id", "")).startswith(m) for m in args.match)]
    catalog = CardCatalog.from_json(CARDS)
    raw_dir = args.raw_dir or args.data_root / "raw/collected"
    matches = {r["match_id"] for r in rows if r.get("event") == "MODEL_SHADOW" and "match_id" in r}
    labels = import_matches(matches, raw_dir, catalog, prepare_actions=args.prepare_actions)
    models = [m for m in MODEL_ORDER if any(e.get("name") == m for r in rows for e in r.get("models", []))]
    games, digests = training_games(checkpoint_paths(), args.data_root / "processed_policy_v3/frozen_split.json")
    prediction_path = args.prediction_journal or live / "prediction_journal.jsonl"
    prediction_rows = read_journal([prediction_path]) if prediction_path.is_file() else None
    report = evaluate(rows, labels, models, training_games=games, checkpoints=digests, prediction_rows=prediction_rows,
                      names=card_names(CARDS), examples=args.examples, self_class=args.self_class)
    report["inputs"] = {"journals": [p.name for p in map(Path, paths)], "raw_dir": str(raw_dir),
                        "importer_summaries": {m[:8]: {"labeled": len(lab.examples), "skipped": len(lab.skipped),
                                                       "import_error": lab.import_error} for m, lab in sorted(labels.items())}}
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
