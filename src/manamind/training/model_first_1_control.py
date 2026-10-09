"""Integrity and leakage checks for the frozen MODEL-FIRST-1 test corpus."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from manamind.live.snapshot import canonical_json

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOCK = ROOT / "configs/model_first_1_control_lock.json"


def normalized_sha256(path: Path) -> str:
    """Hash text files independently of the checkout's LF/CRLF convention."""
    contents = Path(path).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(contents).hexdigest()


def _action_key(action: dict) -> str:
    """Canonical action meaning without protocol/entity handles."""
    return canonical_json({key: value for key, value in action.items() if key != "entity_id"})


def scenario_content_fingerprint(row: dict) -> str:
    """Fingerprint exact state plus an order-independent semantic legal menu."""
    content = {
        "state": row["state"],
        "legal_actions": sorted(_action_key(action) for action in row["legal_actions"]),
    }
    return hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()


def verify_frozen_control(
    lock_path: Path = DEFAULT_LOCK,
) -> tuple[set[str], set[str], set[str], set[str]]:
    """Verify the control file and return identities plus exact-content fingerprints."""
    lock_path = Path(lock_path)
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if set(lock) != {"schema_version", "baseline_path", "sha256", "scenario_ids", "family_ids",
                     "template_ids", "content_fingerprints"}:
        raise ValueError("Invalid MODEL-FIRST-1 control lock schema")
    if lock["schema_version"] != 2:
        raise ValueError("Unsupported MODEL-FIRST-1 control lock version")
    baseline = (ROOT / lock["baseline_path"]).resolve()
    if normalized_sha256(baseline) != lock["sha256"]:
        raise ValueError("Frozen MODEL-FIRST-1 control baseline has changed")
    rows = [json.loads(line) for line in baseline.read_text(encoding="utf-8").splitlines() if line.strip()]
    scenario_ids = {row["scenario_id"] for row in rows}
    family_ids = {row["family_id"] for row in rows}
    template_ids = {row["template_id"] for row in rows}
    content_fingerprints = {scenario_content_fingerprint(row) for row in rows}
    if (scenario_ids != set(lock["scenario_ids"]) or family_ids != set(lock["family_ids"])
            or template_ids != set(lock["template_ids"])
            or content_fingerprints != set(lock["content_fingerprints"])
            or any(row.get("split") != "test" for row in rows)):
        raise ValueError("Frozen MODEL-FIRST-1 control identity or split does not match its lock")
    return scenario_ids, family_ids, template_ids, content_fingerprints


def validate_no_control_overlap(rows: list[dict], lock_path: Path = DEFAULT_LOCK) -> None:
    """Fail if candidate train/validation data includes a frozen test case or family."""
    frozen_ids, frozen_families, frozen_templates, frozen_content = verify_frozen_control(lock_path)
    candidate_ids = {row.get("scenario_id") for row in rows}
    candidate_families = {row.get("family_id") for row in rows}
    candidate_templates = {row.get("template_id") for row in rows}
    candidate_content = {scenario_content_fingerprint(row) for row in rows}
    id_overlap = frozen_ids & candidate_ids
    family_overlap = frozen_families & candidate_families
    template_overlap = frozen_templates & candidate_templates
    content_overlap = frozen_content & candidate_content
    if id_overlap or family_overlap or template_overlap or content_overlap:
        raise ValueError(
            "Training/validation data overlaps frozen MODEL-FIRST-1 test control: "
            f"scenario_ids={sorted(id_overlap)}, family_ids={sorted(family_overlap)}, "
            f"template_ids={sorted(template_overlap)}, "
            f"content_fingerprints={sorted(content_overlap)}"
        )
