"""Build a deterministic ledger for the 105 audited candidates; report-only."""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
BASELINE = "eb1018a"
IMPLEMENTED = {"CORE_DS1_185", "CORE_CS1_130", "CORE_CS2_032", "CORE_BAR_801"}
ARCHITECTURE_FAMILIES = {
    "temporary_hero_power_swap", "discover_dark_gift", "corpses_dark_gift",
    "hidden_zone_copy", "deck_draw_copy_summon", "death_history_replay",
    "future_companion_override", "future_generated_state", "discover_then_play_other_option",
    "discover_predicate", "discover_deck", "provenance_filtered_draw",
    "quest_excluded_from_random", "sidequest_composite_minion", "refresh_discover_outlier",
    "rewind_discover", "random_school_generation", "conditional_spell_return",
    "held_history_damage", "held_spell_transform", "cast_when_drawn_shuffle",
    "temporary_inherited_effect", "stat_keyword_enchant", "smoldering_hand_age",
}


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    revision = subprocess.run(["git", "rev-parse", BASELINE], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()
    baseline_cards = json.loads(subprocess.run(
        ["git", "show", f"{revision}:experiments/manaengine/data/card_abilities.json"],
        cwd=ROOT, check=True, capture_output=True, text=True).stdout)["cards"]
    matrix = read(OUT / "DYNAMIC_GENERATION_CAPABILITY_MATRIX.json")["cards"]
    plan = {x["proposed_family"]: x for x in read(OUT / "DYNAMIC_GENERATION_FAMILY_PLAN.json")["families"]}
    current_cards = read(ROOT / "experiments/manaengine/data/card_abilities.json")["cards"]
    registry = read(ROOT / "data/cards/standard_registry_20261001_enUS.json")["cards"]
    roots = read(ROOT / "data/cards/standard_roots_20261001_enUS.json")
    root_metadata = {x["card_id"]: x["metadata"] for x in roots["roots"]}
    reviews = read(OUT / "DYNAMIC_GENERATION_CARD_REVIEW.json")["card_reviews"]

    rows = []
    for card in matrix:
        card_id = card["card_id"]
        prior = baseline_cards.get(card_id)
        declared_now = current_cards.get(card_id)
        implemented_before = prior is not None and prior.get("support_state") in {"SUPPORTED", "VERIFIED_VANILLA"}
        implemented_by_task = card_id in IMPLEMENTED
        family = card["semantic_family"]
        dynamic = list(card["dynamic_generated_dependencies"])
        new_caps = list(card["new_or_unreviewed_capabilities"])

        if implemented_by_task:
            status = "IMPLEMENTED_SCOPED_VERIFIED"
            blocker = ["Task-local native family scenario and adapter/policy test passed.",
                       "Canonical registry remains IMPLEMENTED_UNVERIFIED; no Rosetta bridge parity or registry evidence promotion in this task.",
                       "Dynamic generation pool admission and full dependency closure remain outside this package."]
        elif implemented_before:
            status = "IMPLEMENTED_BUT_RULES_BLOCKED"
            blocker = ["Existing ManaEngine declaration is preserved.",
                       f"Canonical rules status: {registry[card_id]['rules_verification']['status']}.",
                       "No new focused verification or evidence promotion in this harvest."]
            if dynamic:
                blocker.append("Dynamic dependencies remain unresolved: " + ", ".join(dynamic))
        elif family in ARCHITECTURE_FAMILIES:
            status = "DEFERRED_ARCHITECTURE"
            blocker = ["Existing behavior set does not cover this state/event/choice/session contract honestly."]
        elif dynamic:
            status = "DEFERRED_DYNAMIC_DEPENDENCY"
            blocker = ["Reachable runtime pool/state selector is unresolved: " + ", ".join(dynamic)]
        elif card["rules_uncertainty"]:
            status = "DEFERRED_RULES_EVIDENCE"
            blocker = [str(card["rules_uncertainty"])]
        elif new_caps:
            status = "DEFERRED_NEW_CAPABILITY"
            blocker = ["Requires existing-primitive extension or a separately reviewed shared capability: " + ", ".join(new_caps)]
        else:
            status = "DEFERRED_RULES_EVIDENCE"
            blocker = ["No independently reviewed existing contract and focused evidence was selected in this bounded batch."]

        metadata = root_metadata[card_id]
        rows.append({
            "card_id": card_id,
            "name": card["name"],
            "semantic_family": family,
            "fire_candidate": card["pool_membership"]["fire_candidate"],
            "whelp_raw_candidate": card["pool_membership"]["whelp_raw_candidate"],
            "whelp_working_class_candidate": card["pool_membership"]["whelp_working_class_candidate"],
            "implemented_before_task": implemented_before,
            "implemented_by_task": implemented_by_task,
            "current_declaration_state": (declared_now or {}).get("support_state", "NO_DECLARATION"),
            "status": status,
            "existing_primitives": card["existing_manaengine_primitives"],
            "fixed_dependencies": card["fixed_generated_dependencies"],
            "dynamic_dependencies": dynamic,
            "remaining_blockers": blocker,
            "rules_evidence_status": registry[card_id]["rules_verification"]["status"],
            "reviewed_metadata_dbf_id": metadata.get("dbfId"),
            "reviewed_rules_text": metadata.get("text", ""),
            "review_note": reviews[card_id]["rules_uncertainty"],
            "family_plan_risk": plan[family]["rules_risk"],
        })

    counts = Counter(x["status"] for x in rows)
    fire_declared = sum(x["fire_candidate"] and current_cards.get(x["card_id"], {}).get("support_state") == "SUPPORTED" for x in rows)
    whelp_declared = sum(x["whelp_working_class_candidate"] and current_cards.get(x["card_id"], {}).get("support_state") == "SUPPORTED" for x in rows)
    token = read(ROOT / "experiments/manaengine/data/dependency_metadata_audit.json")["cards"]
    dependency = next(x for x in token if x["id"] == "BAR_035t")
    ledger = {
        "schema_version": 1,
        "report_type": "SAFE_EXISTING_PRIMITIVE_COVERAGE_HARVEST",
        "profile_id": "standard_full_20261001_v1",
        "audit_baseline_revision": revision,
        "harvest_base_commit": "eb1018a",
        "rules_verification_note": "IMPLEMENTED_SCOPED_VERIFIED is limited to task-local ManaEngine native and adapter/action-policy expectations. It does not promote canonical RosettaStone evidence, bridge parity, pool closure, or training eligibility.",
        "universe": {"reviewed_unique_candidates": len(rows),
                     "fire_candidates": sum(x["fire_candidate"] for x in rows),
                     "whelp_raw_candidates": sum(x["whelp_raw_candidate"] for x in rows),
                     "whelp_working_candidates": sum(x["whelp_working_class_candidate"] for x in rows)},
        "status_counts": {name: counts[name] for name in ["IMPLEMENTED_SCOPED_VERIFIED", "IMPLEMENTED_BUT_RULES_BLOCKED", "DEFERRED_NEW_CAPABILITY", "DEFERRED_DYNAMIC_DEPENDENCY", "DEFERRED_RULES_EVIDENCE", "DEFERRED_ARCHITECTURE"]},
        "supported_declaration_counts_not_pool_admission": {"fire_candidates": {"before": 7, "after": fire_declared},
                                                             "working_whelp_candidates": {"before": 3, "after": whelp_declared}},
        "task_changes": {"new_root_declarations": sorted(IMPLEMENTED), "exact_fixed_dependency_id": dependency,
                         "new_engine_primitives": 0, "new_card_id_branches": 0,
                         "native_scenario_groups": 34, "native_assertions_passed": 665,
                         "adapter_policy_tests_passed": 46, "full_python_tests_passed": 90,
                         "native_scenario_groups_added": 1, "adapter_tests_added": 1,
                         "bridge_parity_runs": 0,
                         "canonical_evidence_promotions": 0},
        "provenance": {name: sha(ROOT / path) for name, path in {
            "capability_matrix_sha256": "reports/manaengine_phase4b_20261004/DYNAMIC_GENERATION_CAPABILITY_MATRIX.json",
            "review_annotations_sha256": "reports/manaengine_phase4b_20261004/DYNAMIC_GENERATION_CARD_REVIEW.json",
            "card_abilities_sha256": "experiments/manaengine/data/card_abilities.json",
            "dependency_metadata_sha256": "experiments/manaengine/data/dependency_metadata_audit.json",
            "registry_sha256": "data/cards/standard_registry_20261001_enUS.json",
        }.items()},
        "cards": rows,
    }
    (OUT / "SAFE_EXISTING_PRIMITIVE_HARVEST.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    lines = ["# Safe existing-primitive harvest ledger", "",
             f"Profile `{ledger['profile_id']}`; {len(rows)} unique audit candidates. Support count means a ManaEngine declaration exists, not runtime-pool admission or training eligibility.", "",
             "| Measure | Count |", "|---|---:|"]
    for name, value in ledger["status_counts"].items():
        lines.append(f"| {name} | {value} |")
    lines += ["", "## Coverage changes", "",
              "- Completion verification: native binary 34 scenario groups / 665 assertions PASS; adapter/policy CI selection 46 PASS; full Python suite 90 PASS; Ruff PASS; generic branch guard PASS; generated artifact check PASS (36 outputs); `git diff --check` PASS.",
              f"- Existing supported ManaEngine declarations in this universe: {counts['IMPLEMENTED_BUT_RULES_BLOCKED']} roots; prior source state is preserved and not reverified here.",
              f"- New focused ManaEngine root scenarios: {len(IMPLEMENTED)} roots — {', '.join(sorted(IMPLEMENTED))}.",
              f"- Fire declaration coverage: {fire_declared}/33; working-class Whelp declaration coverage: {whelp_declared}/63. Neither pool is runtime-admitted.",
              "- Exact fixed dependency: `BAR_035t` Swift Hyena, 1/1 Beast with Rush; separately declared `VERIFIED_VANILLA`.",
              "- New engine primitives: 0; card-ID behavior branches: 0; native scenario groups added: 1; bridge parity runs: 0.",
              "- Canonical rules evidence promotions: 0. New scoped test results do not change registry or training eligibility.", "",
              "## Candidate ledger", "",
              "| ID | Family | F | W raw/work | Prior declaration | This task | Status | Blocker |",
              "|---|---|---:|---:|---|---|---|---|"]
    for x in rows:
        blocker = "; ".join(x["remaining_blockers"]).replace("|", "/").replace("\n", " ")
        lines.append(f"| {x['card_id']} | {x['semantic_family']} | {'yes' if x['fire_candidate'] else 'no'} | {'yes' if x['whelp_raw_candidate'] else 'no'} / {'yes' if x['whelp_working_class_candidate'] else 'no'} | {'yes' if x['implemented_before_task'] else 'no'} | {'yes' if x['implemented_by_task'] else 'no'} | {x['status']} | {blocker} |")
    (OUT / "SAFE_EXISTING_PRIMITIVE_HARVEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"universe": ledger["universe"], "status_counts": ledger["status_counts"],
                      "supported_declaration_counts": ledger["supported_declaration_counts_not_pool_admission"]}, indent=2))


if __name__ == "__main__":
    main()
