"""Recompute audit metrics and normalized program agreement; no semantic-gold claim."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
from pathlib import Path

from author_first_pass import ROOT, write
from measure import read
from manamind.card_metadata import CardMetadata

REPO = ROOT.parents[1]


def load_conformance():
    spec = importlib.util.spec_from_file_location("independent_opus_conformance", REPO / "reports/card_ir_v02/conformance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_cases(CardMetadata.load())[1]


def canonical_program(doc):
    """Compare encoded programs, not dependencies, evidence or actual game behavior.

    Only documented defaults, local handle renaming and non-operative annotations
    are normalized. No operation or condition is removed as 'equivalent'.
    """
    def normalize(node, names):
        if isinstance(node, list):
            return [normalize(n, names) for n in node]
        if not isinstance(node, dict):
            return node
        out = {}
        for key, value in node.items():
            if key in ("span", "dep", "resolved"):
                continue
            if key == "at" and value == "CURRENT":
                continue
            if key == "zone" and value == "PLAY":
                continue
            if key == "n" and value == 1 and node.get("pick") == "RANDOM":
                continue
            if key == "count" and value == 1:
                continue
            out[key] = names.get(value, value) if key in ("bind", "as", "ref", "var") else normalize(value, names)
        return out

    abilities = []
    for ability in doc["abilities"]:
        names = {}
        if "target" in ability:
            names[ability["target"]["bind"]] = "entity0"

        def collect(node):
            if isinstance(node, dict):
                if "as" in node and node["as"] not in names:
                    names[node["as"]] = f"entity{len(names)}"
                for value in node.values():
                    collect(value)
            elif isinstance(node, list):
                for value in node:
                    collect(value)
        collect(ability)
        abilities.append(normalize(ability, names))
    return dict(abilities=abilities, keywords=normalize(doc.get("keywords", []), {}),
                unexpressed=[g["span"] for g in doc.get("unexpressed", [])])


def leaf_changes(a, b, path=""):
    if type(a) is type(b) and isinstance(a, dict):
        return sum(leaf_changes(a[k], b[k], f"{path}/{k}") if k in a and k in b else 1 for k in a.keys() | b.keys())
    if type(a) is type(b) and isinstance(a, list):
        return sum(leaf_changes(x, y, f"{path}/{i}") for i, (x, y) in enumerate(zip(a, b))) + abs(len(a) - len(b))
    return int(a != b)


def build():
    raw = read(ROOT / "raw_baseline/measurement.json")
    final = read(ROOT / "final_baseline/measurement.json")
    before = read(ROOT / "negatives_before.json")
    after = read(ROOT / "negatives_after.json")
    corrections = read(ROOT / "corrections.json")
    source_docs = {}
    sources = {}
    for path in sorted((REPO / "reports/card_ir_v02/examples").glob("*.json")):
        if path.stem != "gap_bindings":
            source_docs[path.stem] = read(path)
            sources[path.stem] = path.relative_to(REPO).as_posix()
    for case in load_conformance():
        if case["name"] in ("Nascent Bolt: draw only if the target survives", "Waggle Pick: return with the full-hand rule acknowledged"):
            source_docs[case["doc"]["card_id"]] = case["doc"]
            sources[case["doc"]["card_id"]] = "reports/card_ir_v02/conformance.py: " + case["name"]
    source_docs["JAIL_118"] = read(REPO / "reports/card_ir_b1_independent_review/diagnostics.json")["counterfactual"]["JAIL_118"]["declaration"]
    sources["JAIL_118"] = "reports/card_ir_b1_independent_review/diagnostics.json: counterfactual.JAIL_118 (v0.1)"
    source_docs["CORE_BT_921"] = read(REPO / "reports/card_ir_stage_b1/final/CORE_BT_921.json")
    sources["CORE_BT_921"] = "reports/card_ir_stage_b1/final/CORE_BT_921.json (inherited v0.1; no new Opus declaration)"
    rows = []
    for card_id in read(ROOT / "protocol.json")["order"]:
        initial = read(ROOT / "raw" / f"{card_id}.json")
        corrected = read(ROOT / "final" / f"{card_id}.json")
        other = source_docs.get(card_id)
        comparison = dict(source=sources.get(card_id, "Opus v0.2 forecast only; no authored Ultraxion v0.2 declaration"),
                          comparable=other is not None, normalized_program_equal=(canonical_program(corrected) == canonical_program(other)) if other else None,
                          json_equal=(corrected == other) if other else None,
                          scope="Encoded program/partial fragment only; evidence, dependencies and correctness excluded")
        rows.append(dict(card_id=card_id, raw=raw["cards"][card_id], final=final["cards"][card_id],
                         corrections=[c for c in corrections if c["card_id"] == card_id],
                         changed=initial != corrected, leaf_changes=leaf_changes(initial, corrected),
                         comparison=comparison))
    comparable = [r for r in rows if r["comparison"]["comparable"]]
    errors = [c for c in corrections if c["category"] == "AUTHOR_ERROR"]
    v02before, v02after = (read(ROOT / f"v02_{phase}.json") for phase in ("before", "after"))
    metrics = dict(
        first_pass=raw["summary"], final=final["summary"],
        expressibility=dict(effect_skeleton_without_unexpressed=10, missing_structural_mechanism_cards=["CATA_497", "CATA_585"],
                            opus_potential_complete=9, independent_accepted_complete=6,
                            explanation="Three additional PARTIAL labels (Aviana, Spellweaver, Fury) reflect conservative rule/evidence policy, not three new missing syntax constructs. Hound remains PARTIAL for unqualified split in both v0.2 authorships."),
        author_errors=dict(unit="One documented error group per affected card; not per JSON leaf", total=len(errors),
                           structural_caught=1, missed_evidence_or_scope_omissions=2,
                           independent_gameplay_accuracy=None),
        corrections=dict(changed_cards=sum(r["changed"] for r in rows), rounds=1, groups=len(corrections),
                         leaf_operations=sum(r["leaf_changes"] for r in rows), evidence_clarifications=2,
                         runner_path_bug="Fixed relative/absolute path mismatch after raw commit; raw declarations unaffected, not an authoring error"),
        adversarial_before=before["summary"], adversarial_after=after["summary"],
        adversarial_wrong_total=37, adversarial_missed_before=24, adversarial_missed_after=17,
        adversarial_false_complete_before=15, adversarial_false_complete_after=12,
        structural_valid_semantic_negatives=dict(total=27, accepted_before=18, accepted_after=13),
        normalized_program_agreement=dict(comparable=len(comparable), equal=sum(r["comparison"]["normalized_program_equal"] for r in comparable),
                                          json_equal=sum(r["comparison"]["json_equal"] for r in comparable),
                                          independent_opus_authored_counterparts=10, inherited_historical_counterparts=1,
                                          not_comparable=["CATA_497"],
                                          semantic_correctness_agreement=None,
                                          caveat="Equivalent chosen hypotheses/partial fragments are included. This is not eleven confirmed full card semantics or independent proof."),
        v02_regression=dict(conformance_before=v02before["conformance"]["passed"], conformance_after=v02after["conformance"]["passed"],
                            historical_declarations=v02after["history"],
                            old_mutations_before=v02before["mutations"]["detected"], old_mutations_after=v02after["mutations"]["detected"], old_mutations_total=44))
    paths = [ROOT / "negative_cases.json", ROOT / "protocol.json", ROOT / "raw_bindings.json", ROOT / "final_bindings.json"]
    paths += list((REPO / "src/manamind/card_ir").glob("*.py"))
    return dict(id="CARD-IR-V02-INDEPENDENT-VALIDATION", base_sha="ec67dcbba91869bb01417476b3fcd7badab58466",
                raw_commit="498b52d", baseline_commit="1fb02d8", validator_fix_commit="a898db1", metrics=metrics, cards=rows,
                artifacts=dict(card_comparison="CARD_COMPARISON.md", validator_audit="VALIDATOR_AUDIT.md",
                               verification="verification.json", history="history_reproduction.json",
                               raw_hashes="raw_manifest.json", raw_bindings="raw_bindings.json", final_bindings="final_bindings.json",
                               before="negatives_before.json", after="negatives_after.json", frozen_cases="negative_cases.json",
                               later_diagnostics=["contract_probes.json", "extra_contract_probes.json"]),
                current_hashes={p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)},
                recommendation="NO-GO", recommendation_scope="Mass automatic compilation and using FULL_DEP as a semantic gate; bounded manual research can resume only with separate authorization and review gates",
                next_18="Separate task after evidence/scope and adversarial semantic review gates; not started",
                torch_s2="Defer. First test generalization on the next bounded, independently reviewed batch after gates; one-card S2 does not address current false acceptance.",
                semantic_gold_accuracy=None, population_false_acceptance_rate=None,
                limitations=["Single in-session author, not blinded to task's known issues or normative examples in prose; raw committed before prior declarations/fixtures.",
                             "No external game-rule research or execution; disputed rules remain explicitly unknown, user observations have USER_OBSERVED provenance.",
                             "Adversarial corpus selected after Opus comparison; not a random or protected holdout. Cases include combined faults.",
                             "One equivalent mutation excluded from error count. Three malformed semantic probes rejected for unrelated shape/binding errors do not prove semantic detection.",
                             "Agreement measured on normalized encoded programs, not actual Hearthstone outcomes.",
                             "Before snapshots remain immutable; source fixes do not retroactively improve first-pass metrics."])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write(args.output, build())
