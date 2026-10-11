"""Optional read-only facts audit using the EXISTING unmerged Tactical Shadow checkout.

Run separately from the main runner so reference modules cannot replace production
imports in its process. No evaluate/rerank/L1/L2/L3 call and no future-state labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

REFERENCE = "600319b6b488eb0be32033d24bc375c27ae54bf9"
RAW_CONTENT = "2d2d995b9c0f5b82fb22f0b8a5353044e3889475a6867061d395c149b2cf006c"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow-reference", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--diagnostics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Refusing to overwrite results")
    rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=args.shadow_reference, capture_output=True, text=True, check=True).stdout.strip()
    if rev != REFERENCE:
        raise ValueError("Unexpected Tactical Shadow reference revision")
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", "src", "scripts"], cwd=args.shadow_reference, capture_output=True, check=True)
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "--", "src", "scripts"],
                               cwd=args.shadow_reference, capture_output=True, text=True, check=True).stdout
    if any(p.endswith(".py") for p in untracked.splitlines()):
        raise ValueError("Untracked Python files in reference checkout")
    # This process only loads the reviewed reference. Main diagnostics run separately.
    sys.path.insert(0, str(args.shadow_reference / "src"))
    from manamind.research.tactical_shadow_replay import collect_facts
    from manamind.tactical.heal_rules import assess_action, heal_sources, public_context
    from manamind.training.policy_checkpoint import identity
    from manamind.training.real_policy import load_examples

    diagnostics = json.loads(args.diagnostics.read_text(encoding="utf-8"))
    rows = load_examples(args.data_root / "processed_data_checkpoint_1_20261010/canonical")
    if identity(sorted(rows, key=lambda r: r["decision_id"])) != diagnostics["inputs"]["dataset"]:
        raise ValueError("Reference/diagnostics dataset mismatch")
    catalog = args.shadow_reference / "data/cards/standard_current_enUS.json"
    if hashlib.sha256(catalog.read_bytes()).hexdigest() != diagnostics["inputs"]["catalog"]:
        raise ValueError("Reference catalog mismatch")
    records = {r["id"]: r for r in json.loads(catalog.read_text(encoding="utf-8"))["cards"]}
    sources = heal_sources(list(records.values()))
    raw_paths = sorted((args.data_root / "raw").rglob("*.log"))
    raw_identity = identity(sorted(hashlib.sha256(p.read_bytes()).hexdigest() for p in raw_paths))
    if raw_identity != RAW_CONTENT:
        raise ValueError("Pinned raw content mismatch")
    facts, replay = collect_facts(args.data_root / "raw")
    if (replay["raw_log_files"], replay["replayed_matches"], len(facts)) != (93, 62, 2991):
        raise ValueError("Historical raw replay composition mismatch")
    if any(r["decision_id"] not in facts for r in rows):
        raise ValueError("Missing before-options facts")
    target_ids = {c["case_id"] for c in diagnostics["target_only_cases"]}
    selected = {c["case_id"]: c for c in diagnostics["target_only_cases"] + diagnostics["attack_arithmetic_cases"]}
    cases, states, pair_counts = [], Counter(), Counter()
    for row in rows:
        f = facts[row["decision_id"]]
        states[f.healing_does_damage] += 1
        cid = identity({"state": row["state"], "legal_actions": row["legal_actions"]})[:16]
        if cid not in selected:
            continue
        ctx = public_context(row["state"], records, f)
        record = {"case_id": cid, "target_only_cohort": cid in target_ids,
                  "healing_does_damage": f.healing_does_damage,
                  "window_complete": f.window_complete, "self_modifiers": list(f.self_modifiers),
                  "unknown_public_text": list(ctx.unknown_effectful + ctx.unknown_inert),
                  "rewrite_public_text": list(ctx.rewrite_public_text), "assessments": {}}
        for label in ("prediction", "player"):
            a = selected[cid][label]
            assessment = assess_action(0, row["state"], a, f, ctx, sources, records)
            record["assessments"][label] = None if assessment is None else {
                "outcome": assessment.outcome, "value": assessment.value,
                "amount": assessment.amount, "reasons": list(assessment.reasons)}
        record["flagged_entities"] = f.summary()["flagged_entities"]
        p, c = (record["assessments"][k] for k in ("prediction", "player"))
        values = {"GAIN_LETHAL": 0, "GAIN": 1, "NEUTRAL": 2, "HARM": 3}
        if p is None or c is None:
            status = "NOT_SUPPORTED_BY_EXISTING_HEAL_RULES"
        elif p["value"] not in values or c["value"] not in values:
            status = "EXISTING_RULES_ABSTAIN"
        elif values[c["value"]] < values[p["value"]]:
            status = "EXISTING_RULE_LOCAL_PREFERENCE_FOR_PLAYER_TARGET"
        elif values[c["value"]] == values[p["value"]]:
            status = "EXISTING_RULE_VALUES_TIED"
        else:
            status = "EXISTING_RULE_LOCAL_PREFERENCE_FOR_POLICY_TARGET"
        record["pair_status"] = status
        if cid in target_ids:
            pair_counts[status] += 1
        cases.append(record)
    if len(cases) != len(selected):
        raise ValueError("Missing or duplicate reference case")
    if identity(sorted(hashlib.sha256(p.read_bytes()).hexdigest() for p in raw_paths)) != raw_identity:
        raise ValueError("Raw inputs changed during replay")
    result = {"reference_commit": rev, "diagnostics_sha256": hashlib.sha256(args.diagnostics.read_bytes()).hexdigest(),
              "replay": replay, "healing_states": dict(sorted(states.items())),
              "raw_content_identity": raw_identity, "pair_status": dict(sorted(pair_counts.items())),
              "cases": sorted(cases, key=lambda c: c["case_id"])}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"healing_states": result["healing_states"], "cases": len(cases)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
