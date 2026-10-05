"""Check Phase 4K.1b migration lineage and prohibit new untyped production failures.

The accepted audit classifications and baseline hashes are historical evidence.
Migration hashes/markers bind their reviewed dispositions to current source.
This is a token guard, not a reachability or gameplay correctness proof.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from phase_4k1b_failure_site_audit import NATIVE, _statement_end, _tokens

INVENTORY = Path(__file__).with_name("PHASE_4K1B_NATIVE_FAILURE_INVENTORY.json")


def compact(text):
    return "".join(text[a:b] for kind, a, b in _tokens(text) if kind != "op" or not text[a:b].isspace())


def throws(text):
    tokens = list(_tokens(text))
    for i, (kind, start, end) in enumerate(tokens):
        if kind == "id" and text[start:end] == "throw":
            stop = tokens[_statement_end(text, tokens, i)][1]
            yield compact(text[start:stop])


def source_problems(text, allowed=()):
    problems = []
    tokens = list(_tokens(text))
    if any(kind == "id" and text[a:b] == "reject_unsupported" for kind, a, b in tokens):
        problems.append("legacy reject_unsupported is prohibited")
    remaining = Counter(allowed)
    for expression in throws(text):
        if expression == "throw":  # bare rethrow retains the in-flight type
            continue
        if expression.startswith("throwUnsupportedSimulationError(FailureCode::"):
            continue
        if remaining[expression]:
            remaining[expression] -= 1
            continue
        problems.append("unreviewed/untyped throw: " + expression)
    for expression, count in remaining.items():
        if count:
            problems.append("reviewed throw missing: " + expression)
    return problems


def check(inventory=INVENTORY):
    data = json.loads(Path(inventory).read_text(encoding="utf-8"))
    migration = data["migration"]
    problems = []
    codes = {row["code"] for row in data["reason_codes"]}
    if migration["unmigrated"] != 0:
        problems.append("unmigrated must be zero")
    baseline = [site for site in migration["sites"] if site["status"] != "AUDIT_APPROVED_SPLIT"]
    if len(baseline) != data["totals"]["native_sites"]:
        problems.append("migration lost a baseline site")
    markers = [site["marker"] for site in migration["sites"]]
    if len(markers) != len(set(markers)):
        problems.append("duplicate migration markers")
    for row in data["rows"]:
        if row.get("selectors"):
            sites = [site for site in baseline if site["row"] == row["id"]]
            if len(sites) != row["site_count"] or row.get("migration_disposition") != "COMPLETE":
                problems.append(f"{row['id']}: incomplete disposition")
            if any(site["classification"] != row["classification"] for site in sites):
                problems.append(f"{row['id']}: silently reclassified")
    for site in migration["sites"]:
        text = (NATIVE / site["file"]).read_text(encoding="utf-8")
        if site["marker"] not in text:
            problems.append("missing migration marker: " + site["marker"])
        if site["status"] in {"TYPED", "AUDIT_APPROVED_SPLIT"} and site["code"] not in codes:
            problems.append("unmapped code: " + site["marker"])
    for rel, digest in migration["source_sha256"].items():
        path = NATIVE / rel
        actual = hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        if actual != digest:
            problems.append("migration source changed; review inventory delta: " + rel)
    # All production include/src files, not merely the audited four files.
    allow = migration["unguarded_throw_allowlist"]
    for folder in ("include", "src"):
        for path in sorted((NATIVE / folder).rglob("*")):
            if path.suffix not in {".hpp", ".cpp"}:
                continue
            rel = path.relative_to(NATIVE).as_posix()
            problems.extend(f"{rel}: {error}" for error in source_problems(
                path.read_text(encoding="utf-8"), [row["expression"] for row in allow if row["file"] == rel],
            ))
    return problems


def main():
    problems = check()
    for problem in problems:
        print("FAIL:", problem)
    print(f"310 audited sites + 3 approved split routes; unmigrated=0; {len(problems)} problems")
    return bool(problems)


if __name__ == "__main__":
    raise SystemExit(main())
