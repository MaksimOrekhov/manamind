"""CARD-IR-EXECUTION-PILOT-1 runner: execute scenarios and mutations, write RESULTS.json.

    set MANAMIND_MANAENGINE_BUILD=<build>/python   (built ManaEngine extension)
    python reports/card_ir_execution_pilot_1/pilot.py            # writes RESULTS.json
    python reports/card_ir_execution_pilot_1/pilot.py --check    # compares a fresh run with RESULTS.json

Expected values live in scenarios.py and were written by hand; this file only executes and compares. The legacy run
(B0) uses ManaEngine's own unchanged declarations and is a compatibility check, not a source of truth.
"""
from __future__ import annotations

import argparse
import ast
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from manamind.card_ir.engine_translate import TranslationRefused, translate  # noqa: E402
from manamind.card_ir.strict_v02 import validate_strict_v02  # noqa: E402
from manamind.card_ir.vocabulary_v02 import RULES_V02  # noqa: E402
from manamind.card_metadata import CardMetadata  # noqa: E402
from manamind.integrations.manaengine import (  # noqa: E402
    ManaEngineSession, SimulationOutcome, UnsupportedSimulationError, attempt_action,
)
from engine_bridge import build_catalog, compile_declaration, start_session  # noqa: E402
from scenarios import CARDS, FILLER, MUTATION_SCENARIOS, MUTATIONS, SCENARIOS, SETUPS, Scenario  # noqa: E402

RESULTS = HERE / "RESULTS.json"
TRACE_EVENTS = {"FRIENDLY_MINIONS_BUFF", "RANDOM_SPELL_DISCARDED", "RANDOM_SPELL_DISCARD_EMPTY"}
CODE_FILES = ("src/manamind/card_ir/engine_translate.py", "reports/card_ir_execution_pilot_1/engine_bridge.py")
CARD_ID = re.compile(r"^[A-Z][A-Z0-9]*_[A-Za-z0-9_]+$")


def declarations() -> dict[str, dict]:
    return {card: json.loads((HERE / "declarations" / f"{card}.json").read_text(encoding="utf-8")) for card in CARDS}


class NoLegalAction(LookupError):
    pass


def _target_label(action: dict) -> str:
    if action.get("target_entity_id", -1) < 0:
        return "NONE"
    side = "SELF" if action["target_is_self"] else "OPP"
    return f"{side}_HERO" if action["target_is_hero"] else f"{side}_MINION:{action['target_card_id']}"


def _wanted(target: Any) -> str:
    if target is None:
        return "NONE"
    if isinstance(target, tuple):
        return f"{target[0]}:{target[1]}"
    return target


def resolve(session: ManaEngineSession, step: tuple) -> dict:
    if step[0] == "end":
        return {"type": "END_TURN"}
    kind = {"play": "PLAY_CARD", "attack": "ATTACK"}[step[0]]
    for action in session.legal_actions():
        source = action.get("card_id") if kind == "PLAY_CARD" else action.get("source_card_id")
        if action["type"] == kind and source == step[1] and _target_label(action) == _wanted(step[2]):
            return action
    raise NoLegalAction(f"no legal {step}")


def targets_of(session: ManaEngineSession, card: str) -> list[str]:
    return sorted(_target_label(a) for a in session.legal_actions() if a["type"] == "PLAY_CARD" and a["card_id"] == card)


def snapshot(state) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for side, player in (("SELF", state.self_player), ("OPP", state.opponent)):
        for name in ("hero_health", "armor", "max_mana", "available_mana", "overloaded_mana", "pending_overload",
                     "deck_size", "hand_size"):
            out[f"{side}.{name}"] = getattr(player, name)
        out[f"{side}.board"] = [f"{b.card.card_id} {b.current_attack}/{b.current_health}/{b.max_health}"
                                for b in player.board]
    out["SELF.hand"] = [card.card_id for card in state.self_hand]
    return out


def diff(before: dict, after: dict) -> dict[str, list]:
    return {key: [before[key], after[key]] for key in before if before[key] != after[key]}


def _session(setup_id: str, catalog) -> ManaEngineSession:
    setup = SETUPS[setup_id]
    pad = lambda cards: [*cards, *([FILLER] * (30 - len(cards)))]  # noqa: E731
    deck1, deck2 = pad(setup.deck1), pad(setup.deck2)
    if catalog is None:
        session = ManaEngineSession(deck1, deck2, player1_class="MAGE", player2_class="MAGE", shuffle=False)
    else:
        session = start_session(catalog, deck1, deck2, player1_class="MAGE", player2_class="MAGE")
    for step in setup.script:
        session.apply_action(resolve(session, step))
    return session


def _failure_code(attempt) -> str:
    failure = attempt.diagnostics.native_failure if attempt.diagnostics else None
    return failure.code if failure is not None else str(attempt.reason.value if attempt.reason else "")


def execute(scenario: Scenario, catalog) -> dict[str, Any]:
    """Run one scenario on a catalog (None = legacy ManaEngine declarations). Never raises for game outcomes."""
    record: dict[str, Any] = {}
    try:  # a position the engine cannot represent is refused before any tested action
        parent = _session(scenario.setup, catalog)
        if scenario.expected_targets is not None:
            record["legal_targets"] = targets_of(parent, scenario.card)
        before = snapshot(parent.observation("PLAYER1"))
    except UnsupportedSimulationError as exc:
        return {"outcome": f"UNSIMULATABLE:{exc.failure.code if exc.failure else 'UNTYPED'}", "stage": "position",
                "parent_unchanged": True}
    if scenario.expected_trace is not None:
        parent.set_diagnostic_trace(True)
    trace_start = len(parent.diagnostic_trace)
    session, state = parent, None
    try:
        for step in scenario.action:
            attempt = attempt_action(session, resolve(session, step), perspective="PLAYER1")
            if attempt.outcome != SimulationOutcome.COMPLETED:
                record["outcome"] = f"{attempt.outcome.value}:{_failure_code(attempt)}"
                break
            session, state = attempt.child, attempt.state
        else:
            record["outcome"] = "COMPLETED"
    except NoLegalAction:
        record["outcome"] = "NO_LEGAL_ACTION"
    except UnsupportedSimulationError as exc:
        record["outcome"] = f"UNSIMULATABLE:{exc.failure.code if exc.failure else 'UNTYPED'}"
    after_parent = snapshot(parent.observation("PLAYER1"))
    record["parent_unchanged"] = after_parent == before and parent.is_valid
    if record["outcome"] == "COMPLETED" and state is not None:
        after = snapshot(state)
        record["changes"] = diff(before, after)
        if scenario.mode == "fields":
            record["after_fields"] = {key: after[key] for key in (scenario.expected_changes or {})}
        record["evidence_constraints"] = list(state.evidence_constraints)
        record["training_eligible"] = session.training_eligible
        if scenario.expected_trace is not None:
            record["trace"] = [event.split()[0] for event in session.diagnostic_trace[trace_start:]
                               if event.split()[0] in TRACE_EVENTS]
    return record


def judge(scenario: Scenario, record: dict[str, Any]) -> list[str]:
    """Differences between the hand-written expectation and the observed record (empty = pass)."""
    problems = []
    if record.get("outcome") != scenario.expected_outcome:
        problems.append(f"outcome {record.get('outcome')} != {scenario.expected_outcome}")
    if scenario.expected_targets is not None and record.get("legal_targets") != sorted(scenario.expected_targets):
        problems.append(f"legal targets {record.get('legal_targets')} != {sorted(scenario.expected_targets)}")
    if not record.get("parent_unchanged", False):
        problems.append("parent session changed")
    if record.get("outcome") == "COMPLETED" and scenario.action:
        changes = {key: value[1] for key, value in record["changes"].items()}
        options = scenario.expected_any or ((scenario.expected_changes or {}),)

        def matches(expected):
            if scenario.mode == "fields":  # listed fields must hold after the action, changed or not
                return record["after_fields"] == expected
            return changes == expected
        if not any(matches(option) for option in options):
            problems.append(f"changes {changes} != expected {options if len(options) > 1 else options[0]}")
        if record.get("evidence_constraints") or record.get("training_eligible"):
            problems.append("unexpected evidence debt or training eligibility")
    if scenario.expected_trace is not None and record.get("trace") != list(scenario.expected_trace):
        problems.append(f"trace {record.get('trace')} != {list(scenario.expected_trace)}")
    return problems


class Runner:
    def __init__(self) -> None:
        self.meta = CardMetadata.load()
        self.declared = declarations()
        self.specs = {card: compile_declaration(doc, self.meta) for card, doc in self.declared.items()}
        self._catalogs: dict[str, Any] = {}

    def catalog(self, replaced: dict[str, Any] | None = None):
        specs = dict(self.specs, **(replaced or {}))
        key = json.dumps({card: spec.declaration() for card, spec in sorted(specs.items())}, sort_keys=True)
        if key not in self._catalogs:
            self._catalogs[key] = build_catalog(specs.values())
        return self._catalogs[key]

    def run(self, scenario: Scenario) -> dict[str, Any]:
        row: dict[str, Any] = {"id": scenario.id, "card": scenario.card, "mechanic": scenario.mechanic,
                               "category": scenario.category, "setup": scenario.setup,
                               "setup_note": SETUPS[scenario.setup].note, "action": [list(map(str, s)) for s in scenario.action],
                               "ir": scenario.ir, "basis": scenario.basis,
                               "rules": {r: RULES_V02[r].basis for r in scenario.rules},
                               "expected_outcome": scenario.expected_outcome, "evidence": scenario.evidence}
        if scenario.expected_changes is not None or scenario.expected_any:
            row["expected_changes"] = scenario.expected_changes if not scenario.expected_any else list(scenario.expected_any)
            row["mode"] = scenario.mode
        if scenario.expected_targets is not None:
            row["expected_targets"] = sorted(scenario.expected_targets)
        if scenario.notes:
            row["notes"] = scenario.notes
        replaced = None
        if scenario.ir != "declared":
            mutation = MUTATIONS[scenario.ir]
            doc = copy.deepcopy(self.declared[mutation.card])
            mutation.change(doc)
            report = validate_strict_v02(doc, self.meta)
            row["mutation"] = {"class": mutation.klass, "description": mutation.description,
                               "validator": "ACCEPTED" if report.accepted and report.status == "FULL" else "REJECTED",
                               "expected_validator": scenario.expected_validator,
                               "validator_findings": [*report.errors, *report.warnings][:3]}
            try:  # computational-dependency probe: translate directly, bypassing the validator gate
                spec = translate(doc)
                row["mutation"]["steps"] = spec.declaration()
                replaced = {mutation.card: spec}
                catalog = self.catalog(replaced)
            except TranslationRefused as exc:
                row["record"] = {"outcome": f"REFUSED:{exc.code}", "refusal": str(exc)}
                row["differences"] = judge_refusal(scenario, row["record"])
                row["passed"] = not row["differences"]
                return row
        else:
            row["steps"] = self.specs[scenario.card].declaration()
            row["assumptions"] = list(self.specs[scenario.card].assumptions)
            catalog = self.catalog()
        row["record"] = execute(scenario, catalog)
        row["differences"] = judge(scenario, row["record"])
        if scenario.compare_legacy or scenario.ir != "declared":
            legacy = execute(scenario, None)
            row["legacy_record"] = legacy
            same = {k: legacy.get(k) for k in ("outcome", "changes", "legal_targets", "trace")} == \
                   {k: row["record"].get(k) for k in ("outcome", "changes", "legal_targets", "trace")}
            row["legacy_equal"] = same
        row["passed"] = not row["differences"]
        return row


def judge_refusal(scenario: Scenario, record: dict[str, Any]) -> list[str]:
    return [] if record["outcome"] == scenario.expected_outcome else \
        [f"outcome {record['outcome']} != {scenario.expected_outcome}"]


def _literal(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    return isinstance(node, (ast.Tuple, ast.List, ast.Set)) and any(_literal(item) for item in node.elts)


def static_card_check() -> dict[str, Any]:
    """C2: no card-ID-shaped string literal, and no card_id compared with a literal, in the translator and bridge."""
    findings = []
    for rel in CODE_FILES:
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and CARD_ID.match(node.value) \
                    and node.value.upper() == node.value and any(ch.isdigit() for ch in node.value):
                findings.append(f"{rel}:{node.lineno} literal {node.value!r}")
            if isinstance(node, ast.Compare):
                names = {n.attr if isinstance(n, ast.Attribute) else getattr(n, "id", None)
                         for n in ast.walk(node) if isinstance(n, (ast.Attribute, ast.Name))}
                if "card_id" in names and any(_literal(part) for part in (node.left, *node.comparators)):
                    findings.append(f"{rel}:{node.lineno} compares card_id with a literal")
    return {"files": list(CODE_FILES), "findings": findings, "passed": not findings}


def summarize(rows: list[dict], static: dict, real: dict | None) -> dict[str, Any]:
    scenario_rows = [r for r in rows if r["category"] != "mutation"]
    mutation_rows = [r for r in rows if r["category"] == "mutation"]
    executed_mutations = [r for r in mutation_rows if not r["record"]["outcome"].startswith("REFUSED")]
    # B1: a mutation that executes but reproduces the legacy result would mean the IR did not drive the computation.
    unexplained = [r["id"] for r in executed_mutations if r.get("legacy_equal")]
    ops = sorted({s["kind"] for r in scenario_rows if r["passed"] and r["record"].get("outcome") == "COMPLETED"
                  and r["action"] for s in r.get("steps", {}).get("effects", [])})
    criteria = {
        "C1_two_generic_operations": {"executed_engine_kinds": ops, "passed": len(ops) >= 2},
        "C2_no_card_specific_code": static,
        "C3_supported_scenarios_match": {"passed": all(r["passed"] for r in scenario_rows),
                                         "failed": [r["id"] for r in scenario_rows if not r["passed"]]},
        "C4_unsupported_blocked": {
            "cases": [r["id"] for r in rows if r["expected_outcome"].startswith(("REFUSED", "UNSIMULATABLE"))],
            "passed": all(r["passed"] for r in rows if r["expected_outcome"].startswith(("REFUSED", "UNSIMULATABLE")))},
        "C5_ir_controls_execution": {
            "mutations": len(mutation_rows),
            "executed_and_changed_vs_legacy": [r["id"] for r in executed_mutations if r.get("legacy_equal") is False],
            "refused": [r["id"] for r in mutation_rows if r["record"]["outcome"].startswith("REFUSED")],
            "identical_to_legacy_B1": unexplained,
            "passed": all(r["passed"] for r in mutation_rows) and not unexplained},
    }
    compat = [r for r in scenario_rows if "legacy_equal" in r]
    levels = {}
    for card in CARDS:
        mine = [r for r in scenario_rows if r["card"] == card]
        levels[card] = {
            "L1_validated": "FULL (strict v0.2, 0 errors, 0 warnings)",
            "L2_independent_semantic_review": "NONE_ON_RECORD",
            "L3_executes": f"{sum(r['passed'] for r in mine)}/{len(mine)} scenarios pass",
            "L4_independent_game_evidence": (real or {}).get("cards", {}).get(card, {}).get("verdict", "NOT_RUN"),
            "L5_training_admission": False,
        }
    return {
        "criteria": criteria,
        "b0_legacy_compatibility": {"compared": len(compat), "equal": sum(r["legacy_equal"] for r in compat),
                                    "different": [r["id"] for r in compat if not r["legacy_equal"]]},
        "evidence_levels": levels,
        "scenarios": {"total": len(scenario_rows), "passed": sum(r["passed"] for r in scenario_rows)},
        "mutations": {"total": len(mutation_rows), "passed": sum(r["passed"] for r in mutation_rows),
                      "validator_prediction_mismatch": [r["id"] for r in mutation_rows
                                                        if r["mutation"]["validator"] != r["mutation"]["expected_validator"]]},
    }


def build() -> dict[str, Any]:
    runner = Runner()
    rows = [runner.run(s) for s in (*SCENARIOS, *MUTATION_SCENARIOS)]
    real_path = HERE / "real_evidence.json"
    real = json.loads(real_path.read_text(encoding="utf-8")) if real_path.exists() else None
    return {
        "schema": "card_ir_execution_pilot_1/results-1",
        "protocol": "protocol.json",
        "translations": {card: {"steps": spec.declaration(), "keywords": list(spec.keywords),
                                "assumptions": list(spec.assumptions)} for card, spec in runner.specs.items()},
        "summary": summarize(rows, static_card_check(), real),
        "rows": rows,
        "real_evidence": real,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build(), indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    if args.check:
        same = RESULTS.read_text(encoding="utf-8") == text
        print("RESULTS.json reproduces" if same else "RESULTS.json differs from a fresh run")
        return 0 if same else 1
    RESULTS.write_bytes(text.encode("utf-8"))
    print(json.dumps(json.loads(text)["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
