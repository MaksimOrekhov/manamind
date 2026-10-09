"""Integrity and leakage checks for the frozen MODEL-FIRST-1 test corpus."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOCK = ROOT / "configs/model_first_1_control_lock.json"


def verify_frozen_control(lock_path: Path = DEFAULT_LOCK) -> tuple[set[str], set[str], set[str]]:
    """Verify the committed control file and return scenario/family/template identities."""
    lock_path = Path(lock_path)
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if set(lock) != {"schema_version", "baseline_path", "sha256", "scenario_ids", "family_ids",
                     "template_ids"}:
        raise ValueError("Invalid MODEL-FIRST-1 control lock schema")
    if lock["schema_version"] != 1:
        raise ValueError("Unsupported MODEL-FIRST-1 control lock version")
    baseline = (ROOT / lock["baseline_path"]).resolve()
    if hashlib.sha256(baseline.read_bytes()).hexdigest() != lock["sha256"]:
        raise ValueError("Frozen MODEL-FIRST-1 control baseline has changed")
    rows = [json.loads(line) for line in baseline.read_text(encoding="utf-8").splitlines() if line.strip()]
    scenario_ids = {row["scenario_id"] for row in rows}
    family_ids = {row["family_id"] for row in rows}
    template_ids = {row["template_id"] for row in rows}
    if (scenario_ids != set(lock["scenario_ids"]) or family_ids != set(lock["family_ids"])
            or template_ids != set(lock["template_ids"])
            or any(row.get("split") != "test" for row in rows)):
        raise ValueError("Frozen MODEL-FIRST-1 control identity or split does not match its lock")
    return scenario_ids, family_ids, template_ids


def validate_no_control_overlap(rows: list[dict], lock_path: Path = DEFAULT_LOCK) -> None:
    """Fail if candidate train/validation data includes a frozen test case or family."""
    frozen_ids, frozen_families, frozen_templates = verify_frozen_control(lock_path)
    candidate_ids = {row.get("scenario_id") for row in rows}
    candidate_families = {row.get("family_id") for row in rows}
    candidate_templates = {row.get("template_id") for row in rows}
    id_overlap = frozen_ids & candidate_ids
    family_overlap = frozen_families & candidate_families
    template_overlap = frozen_templates & candidate_templates
    if id_overlap or family_overlap or template_overlap:
        raise ValueError(
            "Training/validation data overlaps frozen MODEL-FIRST-1 test control: "
            f"scenario_ids={sorted(id_overlap)}, family_ids={sorted(family_overlap)}, "
            f"template_ids={sorted(template_overlap)}"
        )
