"""Source-only regression guard for card-identity dispatch in generator code.

This detects common AST shapes, not semantic reuse or arbitrary Python dataflow.
Existing metadata/custom/routing exceptions are reviewed, structure-pinned data.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "configs/generator_branch_policy.json"
CARD_ID = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z][A-Z0-9]*)*_\d{2,}[A-Za-z0-9_]*")
IDENTITY_NAMES = {"card_id", "base_id", "cid"}
EXCEPTION_ROLES = {"METADATA_VALIDATION", "CUSTOM", "CUSTOM_ROUTING"}


def fingerprint(node: ast.AST) -> str:
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def literal_ids(node: ast.AST) -> set[str]:
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant)
            and isinstance(n.value, str) and CARD_ID.fullmatch(n.value)}


def identity(node: ast.AST, aliases: set[str]) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and (child.id in aliases or child.id.endswith("_card_id")):
            return True
        if isinstance(child, ast.Attribute) and child.attr == "card_id":
            return True
        if isinstance(child, ast.Subscript) and isinstance(child.slice, ast.Constant) and child.slice.value in {"card_id", "id"}:
            return True
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == "get" and child.args:
            if isinstance(child.args[0], ast.Constant) and child.args[0].value in {"card_id", "id"}:
                return True
    return False


def identity_value(node: ast.AST, aliases: set[str]) -> bool:
    """Direct ID aliases only; catalog.get(card_id) returns metadata, not an ID."""
    if isinstance(node, ast.Name):
        return node.id in aliases or node.id.endswith("_card_id")
    if isinstance(node, ast.Attribute):
        return node.attr == "card_id"
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        return node.slice.value in {"card_id", "id"}
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" and node.args:
        return isinstance(node.args[0], ast.Constant) and node.args[0].value in {"card_id", "id"}
    return False


class Inventory(ast.NodeVisitor):
    def __init__(self, path: str, tree: ast.Module):
        self.path = path
        self.scope = ["<module>"]
        self.aliases = set(IDENTITY_NAMES)
        self.constants: dict[str, set[str]] = {}
        self.findings: list[dict] = []
        self.covered_comparisons: set[int] = set()
        # Track literal allowlists/dispatch tables, including module constants.
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.constants[target.id] = literal_ids(node.value)

    def ids(self, node: ast.AST) -> set[str]:
        result = literal_ids(node)
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                result |= self.constants.get(child.id, set())
        return result

    def record(self, node: ast.AST, selector: ast.AST, kind: str) -> None:
        if identity(selector, self.aliases) or self.ids(selector):
            self.covered_comparisons.update(id(n) for n in ast.walk(selector) if isinstance(n, ast.Compare))
            self.findings.append({"path": self.path, "function": ".".join(self.scope[1:]) or "<module>",
                                  "kind": kind, "line": node.lineno,
                                  "card_ids": sorted(self.ids(selector)), "ast_sha256": fingerprint(node)})

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        old_aliases, old_constants = self.aliases, self.constants
        self.aliases, self.constants = set(old_aliases), dict(old_constants)
        self.scope.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self.scope.pop()
        self.aliases, self.constants = old_aliases, old_constants

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.constants[target.id] = self.ids(node.value)
                if identity_value(node.value, self.aliases):
                    self.aliases.add(target.id)
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self.record(node, node.test, "if")
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.record(node, node.test, "conditional_expression")
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        # Also catch comparisons inside assert/require and comprehension filters.
        if id(node) not in self.covered_comparisons:
            self.record(node, node, "identity_comparison")
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        if identity(node.subject, self.aliases) or self.ids(node):
            self.record(node, node, "match")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        # Ordinary card['card_id'] reads are not behavioral table dispatch.
        if identity(node.slice, self.aliases):
            self.record(node, node, "identity_lookup")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get" and node.args and identity(node.args[0], self.aliases):
            self.record(node, node, "identity_get_lookup")
        self.generic_visit(node)


def inventory(root: Path) -> list[dict]:
    paths = sorted(set((root / "scripts").glob("generate_*.py")) |
                   set((root / "scripts/card_rules").rglob("*.py")))
    findings = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = Inventory(path.relative_to(root).as_posix(), tree)
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings


def key(row: dict) -> tuple:
    return row["path"], row["function"], row["kind"], row["ast_sha256"]


def check_custom_ownership(root: Path, policy: dict) -> list[str]:
    errors = []
    rows = {}
    for path in sorted((root / "integrations/rosettastone/card_rules").glob("*.generated.json")):
        for card in json.loads(path.read_text(encoding="utf-8"))["cards"]:
            if card["card_id"] in rows:
                errors.append(f"Duplicate generated owner: {card['card_id']}")
            rows[card["card_id"]] = card
    custom_path = root / "scripts/card_rules/composition_ops.py"
    custom_ids = set()
    for node in ast.parse(custom_path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CUSTOM_EMITTER_CARD_IDS" for t in node.targets):
            custom_ids = set(ast.literal_eval(node.value))
    required = custom_ids | {cid for exception in policy["exceptions"] if exception["role"] == "CUSTOM"
                             for cid in exception["custom_card_ids"]}
    for cid in sorted(required):
        row = rows.get(cid)
        if row is None:
            errors.append(f"Custom emitter ID lacks a generated owner: {cid}")
        elif row.get("implementation_route") != "CUSTOM" or row.get("implementation_kind", "CUSTOM") != "CUSTOM":
            errors.append(f"Custom emitter ID is not classified CUSTOM: {cid}")
    return errors


def check(root: Path, policy: dict) -> list[str]:
    errors = []
    if policy.get("schema_version") != 1:
        return ["Unsupported generator branch policy schema"]
    exceptions = policy["exceptions"]
    allowed = {key(row): row for row in exceptions}
    if len(allowed) != len(exceptions):
        errors.append("Duplicate AST exception identity")
    for row in exceptions:
        if row["role"] not in EXCEPTION_ROLES or not row.get("reason"):
            errors.append(f"Invalid exception role/reason: {row['path']}:{row['function']}")
        if not isinstance(row.get("occurrences"), int) or row["occurrences"] < 1:
            errors.append(f"Invalid occurrence count: {row['path']}:{row['function']}")
        if row["role"] == "CUSTOM" and not row.get("custom_card_ids"):
            errors.append(f"CUSTOM exception lacks owner IDs: {row['path']}:{row['function']}")
    seen = Counter()
    for row in inventory(root):
        entry = allowed.get(key(row))
        if entry is None or entry["card_ids"] != row["card_ids"]:
            errors.append(f"Unreviewed card-identity logic: {row['path']}:{row['line']} "
                          f"{row['function']} ({row['kind']}; IDs={row['card_ids']}). "
                          "Use semantic parameters or reviewed CUSTOM/metadata ownership.")
        else:
            seen[key(row)] += 1
    for stale in set(allowed) - set(seen):
        errors.append(f"Stale AST exception: {stale[0]}:{stale[1]} ({stale[2]})")
    for identity_key, count in seen.items():
        if count != allowed[identity_key].get("occurrences"):
            errors.append(f"Changed AST occurrence count: {identity_key[0]}:{identity_key[1]} "
                          f"({identity_key[2]}; found {count})")
    errors.extend(check_custom_ownership(root, policy))
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--policy", type=Path, default=POLICY)
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    errors = check(args.root, policy)
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Generator identity guard: PASS ({len(policy['exceptions'])} reviewed AST exceptions; CUSTOM ownership checked)")


if __name__ == "__main__":
    main()
