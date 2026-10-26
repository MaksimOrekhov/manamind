"""Mutation test of the pre-engine checks: which plausible authoring errors do the validator and the lint catch?

For every declaration and every operator, the first applicable site (depth-first order) is mutated once; the mutant
is then validated and linted. A mutant may be semantically equivalent to the original (e.g. swapping two steps that
commute); rates are therefore lower bounds of what a check can see, and "undetected" is not always an error.

    python -I reports/card_ir_pilot_1/mutants.py --output reports/card_ir_pilot_1/mutants.json
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterator

ROOT = Path(__file__).resolve().parents[2]
PILOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from manamind.card_ir import validate_declaration  # noqa: E402
from manamind.card_ir.lint import lint_declaration  # noqa: E402
from manamind.card_metadata import CardMetadata  # noqa: E402

VALUE_KEYS = {"amount", "attack", "health", "count", "reduce", "set", "n", "turns", "goal", "spell_damage"}
FLIPS = {
    "side": {"FRIENDLY": "ENEMY", "ENEMY": "FRIENDLY", "ANY": "ENEMY"},
    "pick": {"ALL": "RANDOM", "RANDOM": "ALL", "CHOSEN": "RANDOM"},
    "timing": {"AFTER": "WHENEVER", "WHENEVER": "AFTER", "AT": "AFTER", "WHEN": "AFTER"},
    "op": {"DEAL_DAMAGE": "RESTORE_HEALTH", "RESTORE_HEALTH": "DEAL_DAMAGE", "DESTROY": "SILENCE", "SILENCE": "DESTROY"},
}
ORDER = ["NUMBER", "MARK_DROP", "MARK_ADD", "SIDE", "PICK", "ZONE", "TIMING", "OP_SWAP", "SEQ_SWAP", "STEP_DROP",
         "EXCLUDE_DROP", "REF_TO_SELF", "KEYWORD_SWAP", "ABILITY_DROP", "DEP_DROP", "STATUS_OPTIMISTIC"]


def walk(node: Any, path: tuple = ()) -> Iterator[tuple[tuple, Any]]:
    """Depth-first (path, node) pairs."""
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, path + (index,))


def get(doc: Any, path: tuple) -> Any:
    for step in path:
        doc = doc[step]
    return doc


def put(doc: Any, path: tuple, value: Any) -> None:
    get(doc, path[:-1])[path[-1]] = value


def first(doc: dict, test: Callable[[tuple, Any], bool]) -> tuple | None:
    for path, node in walk(doc["abilities"], ("abilities",)):
        if test(path, node):
            return path
    return None


def mutate(doc: dict, operator: str) -> tuple[dict, str] | None:
    """Return (mutant, site) or None when the operator does not apply."""
    m = copy.deepcopy(doc)
    if operator == "NUMBER":
        path = first(m, lambda p, n: isinstance(n, int) and not isinstance(n, bool) and p and p[-1] in VALUE_KEYS)
        if path is None:
            return None
        put(m, path, get(m, path) + 1)
    elif operator == "MARK_DROP":
        path = first(m, lambda p, n: isinstance(n, dict) and "mark" in n)
        if path is None:
            return None
        put(m, path, get(m, path)["n"])
    elif operator == "MARK_ADD":
        path = first(m, lambda p, n: isinstance(n, int) and p and p[-1] == "amount")
        if path is None:
            return None
        put(m, path, {"n": get(m, path), "mark": "$"})
    elif operator in ("SIDE", "PICK", "TIMING", "OP_SWAP"):
        key = {"SIDE": "side", "PICK": "pick", "TIMING": "timing", "OP_SWAP": "op"}[operator]
        path = first(m, lambda p, n: p and p[-1] == key and n in FLIPS[key])
        if path is None:
            return None
        put(m, path, FLIPS[key][get(m, path)])
    elif operator == "ZONE":
        path = first(m, lambda p, n: p and p[-1] == "zone")
        if path is None:
            return None
        zone = get(m, path)
        swap = {"HAND": "PLAY", "DECK": "HAND", "PLAY": "HAND"}
        put(m, path, [swap[zone[0]], *zone[1:]] if isinstance(zone, list) else swap[zone])
    elif operator in ("SEQ_SWAP", "STEP_DROP"):
        path = first(m, lambda p, n: isinstance(n, dict) and isinstance(n.get("seq"), list))
        if path is None:
            return None
        steps = get(m, path)["seq"]
        if operator == "SEQ_SWAP":
            steps[0], steps[1] = steps[1], steps[0]
        elif len(steps) > 2:
            steps.pop()
        else:
            put(m, path, steps[0]) if path != ("abilities",) else None
    elif operator == "EXCLUDE_DROP":
        path = first(m, lambda p, n: isinstance(n, dict) and "exclude" in n and "pick" in n)
        if path is None:
            return None
        del get(m, path)["exclude"]
    elif operator == "REF_TO_SELF":
        path = first(m, lambda p, n: p and p[-1] == "to" and isinstance(n, dict) and "ref" in n)
        if path is None:
            return None
        put(m, path, "SELF")
    elif operator == "KEYWORD_SWAP":
        path = first(m, lambda p, n: p and p[-1] == "keywords" and isinstance(n, list) and n)
        if path is None:
            return None
        keywords = get(m, path)
        keywords[0] = "TAUNT" if keywords[0] != "TAUNT" else "RUSH"
    elif operator == "ABILITY_DROP":
        if not m["abilities"]:
            return None
        m["abilities"].pop()
        path = ("abilities", len(m["abilities"]))
    elif operator == "DEP_DROP":
        if not m["dependencies"]:
            return None
        m["dependencies"].pop(0)
        path = ("dependencies", 0)
    elif operator == "STATUS_OPTIMISTIC":
        better = {"PARTIAL": "FULL_DEP", "FULL_DEP": "FULL"}
        if m["status"] not in better:
            return None
        m["status"] = better[m["status"]]
        path = ("status",)
    else:
        raise ValueError(operator)
    return m, ".".join(str(step) for step in path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; refusing to overwrite")
    meta = CardMetadata.load()
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((PILOT / "declarations").glob("*.json"))]
    for doc in docs:
        if validate_declaration(doc, meta).errors or lint_declaration(doc):
            raise SystemExit(f"{doc['card_id']}: the original must validate and lint clean")

    stats: dict[str, Counter] = {operator: Counter() for operator in ORDER}
    undetected: dict[str, list[str]] = {operator: [] for operator in ORDER}
    for doc in docs:
        for operator in ORDER:
            result = mutate(doc, operator)
            if result is None:
                continue
            mutant, site = result
            if mutant == doc:
                continue
            by_validator = bool(validate_declaration(mutant, meta).errors)
            by_lint = bool(lint_declaration(mutant))
            layer = "validator" if by_validator else ("lint_only" if by_lint else "undetected")
            stats[operator]["mutants"] += 1
            stats[operator][layer] += 1
            if layer == "undetected":
                undetected[operator].append(f"{doc['card_id']} {site}")
    table = {}
    for operator in ORDER:
        count = stats[operator]
        n = count["mutants"]
        table[operator] = {
            "mutants": n, "validator": count["validator"], "lint_only": count["lint_only"],
            "undetected": count["undetected"],
            "detected_share": round((count["validator"] + count["lint_only"]) / n, 3) if n else None,
            "undetected_examples": undetected[operator],
        }
    total = Counter()
    for count in stats.values():
        total.update(count)
    payload = {
        "declarations": len(docs), "operators": ORDER, "table": table,
        "total": {"mutants": total["mutants"], "validator": total["validator"], "lint_only": total["lint_only"],
                  "undetected": total["undetected"]},
        "caveat": ("lint anchors were tuned to zero warnings on these same declarations; detection on new cards must be "
                   "measured separately. Some mutants are semantically equivalent to the original."),
    }
    args.output.write_bytes((json.dumps(payload, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    for operator, row in table.items():
        print(f"{operator:18} n={row['mutants']:3} validator={row['validator']:3} lint_only={row['lint_only']:3} "
              f"undetected={row['undetected']:3}")
    print("total", payload["total"])


if __name__ == "__main__":
    main()
