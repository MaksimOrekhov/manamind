"""Validate manual exports and optionally compare two independent reviewers; no fit."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from manamind.training.action_preferences import validate_annotations  # noqa: E402
from manamind.training.policy_checkpoint import identity  # noqa: E402


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("annotations", type=Path)
    parser.add_argument("--second", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists(): raise ValueError("Fresh validation directory required")
    pack, first = read(args.pack), read(args.annotations)
    if pack.get("schema") != "manamind.action_preference_pack/1": raise ValueError("Wrong pack schema")
    result = validate_annotations(pack, first)
    summary = {"strict_preferences": len(result["strict_preferences"]), "equivalences": len(result["aspect_equivalences"]),
               "abstentions": len(result["abstentions"]), "unlabelled": result["unlabelled"], "ready_for_training": False}
    if args.second:
        second = read(args.second)
        if second.get("reviewer") == first.get("reviewer") or second.get("independent_review") is not True:
            raise ValueError("Different independent second reviewer required")
        verified_second = validate_annotations(pack, second)
        a = {x["pair_id"]: x["initial"] for x in first["annotations"]}
        b = {x["pair_id"]: x["initial"] for x in second["annotations"]}
        counts = Counter()
        disagreements = []
        for pid in sorted(a.keys() & b.keys()):
            if a[pid]["aspect"] != b[pid]["aspect"]:
                counts["different_aspects"] += 1
            elif a[pid]["result"] == b[pid]["result"]:
                counts["same_result_same_aspect"] += 1
            else:
                counts["disagreed_same_aspect"] += 1
                disagreements.append(pid)
        summary["second_review"] = {"counts": dict(counts), "disagreement_pair_ids": disagreements,
                                    "warning": "Agreement is not proof of optimality; review shared biases and confidence."}
        result["second"] = verified_second
    summary["pack_sha256"] = identity(pack)
    args.out.mkdir(parents=True)
    for filename, payload in (("validated_annotations.json", result), ("summary.json", summary)):
        with (args.out / filename).open("x", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
