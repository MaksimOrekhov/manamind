"""Strict loader for versioned finite pool manifests used by ManaEngine."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_POOL_FIELDS = {
    "pool_id", "schema_version", "contract_version", "format_profile_id", "as_of_date",
    "predicate", "card_ids", "count", "sorted_membership_sha256", "metadata_snapshot",
    "membership_status", "dependency_status", "training_eligible", "exclusions",
    "predicate_rules_fingerprint",
}
_PREDICATE_FIELDS = {"kind", "school", "base_cost", "class_policy"}
_PREDICATES = {"STANDARD_SPELL_SCHOOL", "STANDARD_SPELL_BASE_COST"}
_CLASS_POLICIES = {"ANY_CLASS", "NON_NEUTRAL_CLASS"}
_MEMBERSHIP = {"CANDIDATE", "MEMBERSHIP_REVIEWED"}
_DEPENDENCY = {"OPEN", "DEPENDENCY_CLOSED"}
_EXCLUSION_CATEGORIES = {
    "QUEST", "RUNE", "NON_GENERATABLE", "CLASS_POLICY", "NEUTRAL_POLICY",
    "EVENT_POLICY", "ALIAS", "BAN", "OTHER",
}
_EXCLUSION_STATUSES = {"REVIEWED_EXCLUDED", "UNRESOLVED"}
_CARD_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class PoolExclusionRecord:
    category: str
    status: str
    card_ids: tuple[str, ...]
    rationale: str
    evidence_ref: str


@dataclass(frozen=True)
class PoolManifestDocument:
    pool_id: str
    schema_version: int
    contract_version: int
    format_profile_id: str
    as_of_date: str
    predicate_kind: str
    school: str
    base_cost: int
    class_policy: str
    card_ids: tuple[str, ...]
    count: int
    sorted_membership_sha256: str
    metadata_snapshot_id: str
    metadata_snapshot_sha256: str
    membership_status: str
    dependency_status: str
    training_eligible: bool
    exclusions: tuple[PoolExclusionRecord, ...]
    predicate_rules_fingerprint: str

    def to_native(self, native: Any) -> Any:
        manifest = native.PoolManifest()
        manifest.pool_id = self.pool_id
        manifest.schema_version = self.schema_version
        manifest.contract_version = self.contract_version
        manifest.format_profile_id = self.format_profile_id
        manifest.as_of_date = self.as_of_date
        manifest.metadata_snapshot_id = self.metadata_snapshot_id
        manifest.metadata_snapshot_sha256 = self.metadata_snapshot_sha256
        manifest.card_ids = list(self.card_ids)
        manifest.count = self.count
        manifest.sorted_membership_sha256 = self.sorted_membership_sha256
        manifest.predicate_rules_fingerprint = self.predicate_rules_fingerprint
        manifest.membership_status = getattr(native.PoolMembershipStatus, self.membership_status)
        manifest.dependency_status = getattr(native.PoolDependencyStatus, self.dependency_status)
        manifest.training_eligible = self.training_eligible
        predicate = native.PoolPredicate()
        predicate.kind = getattr(native.PoolPredicateKind, self.predicate_kind)
        predicate.school = self.school
        predicate.base_cost = self.base_cost
        predicate.class_policy = getattr(native.PoolClassPolicy, self.class_policy)
        manifest.predicate = predicate
        exclusions = []
        for source in self.exclusions:
            exclusion = native.PoolExclusion()
            exclusion.category = getattr(native.PoolExclusionKind, source.category)
            exclusion.status = getattr(native.PoolExclusionStatus, source.status)
            exclusion.card_ids = list(source.card_ids)
            exclusion.rationale = source.rationale
            exclusion.evidence_ref = source.evidence_ref
            exclusions.append(exclusion)
        manifest.exclusions = exclusions
        return manifest


def membership_hash(card_ids: tuple[str, ...] | list[str]) -> str:
    return hashlib.sha256(("\n".join(card_ids) + "\n").encode("utf-8")).hexdigest()



@dataclass(frozen=True)
class DarkGiftOptionManifestDocument:
    manifest_id: str
    source_metadata_id: str
    source_metadata_sha256: str
    candidate_option_ids: tuple[str, ...]
    launch_reviewed_option_ids: tuple[str, ...]
    candidate_membership_sha256: str
    launch_reviewed_membership_sha256: str
    def to_native(self, native: Any) -> Any:
        manifest = native.DarkGiftOptionManifest()
        manifest.manifest_id = self.manifest_id
        manifest.source_metadata_id = self.source_metadata_id
        manifest.source_metadata_sha256 = self.source_metadata_sha256
        manifest.candidate_option_ids = list(self.candidate_option_ids)
        manifest.launch_reviewed_option_ids = list(self.launch_reviewed_option_ids)
        manifest.candidate_membership_sha256 = self.candidate_membership_sha256
        manifest.launch_reviewed_membership_sha256 = self.launch_reviewed_membership_sha256
        manifest.runtime_membership_status = native.DarkGiftRuntimeMembershipStatus.UNRESOLVED
        manifest.sampler_status = native.DarkGiftSamplerStatus.UNVERIFIED
        manifest.training_eligible = False
        return manifest

def load_dark_gift_option_manifest(manifest_path: str | Path, metadata_path: str | Path) -> DarkGiftOptionManifestDocument:
    """Load the bounded launch-review option set without claiming runtime admission."""
    raw = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    fields = {"schema_version", "contract_version", "manifest_id", "source_metadata",
              "candidate_option_ids", "launch_reviewed_option_ids",
              "runtime_membership_status", "sampler_status", "execution_support_status",
              "training_eligible", "candidate_membership_sha256", "launch_reviewed_membership_sha256"}
    if not isinstance(raw, dict) or set(raw) != fields or raw["schema_version"] != 1 or raw["contract_version"] != 1:
        raise ValueError("Dark Gift option manifest schema mismatch")
    metadata = raw["source_metadata"]
    if not isinstance(metadata, dict) or set(metadata) != {"id", "sha256"}:
        raise ValueError("Dark Gift source metadata identity is invalid")
    digest = hashlib.sha256(Path(metadata_path).read_bytes()).hexdigest()
    if metadata["sha256"] != digest or not _SHA256.fullmatch(str(metadata["sha256"])):
        raise ValueError("Dark Gift option metadata identity mismatch")
    candidates = raw["candidate_option_ids"]
    reviewed = raw["launch_reviewed_option_ids"]
    for name, ids in (("candidates", candidates), ("launch-reviewed", reviewed)):
        if not isinstance(ids, list) or ids != sorted(set(ids)) or any(not isinstance(v, str) or not _CARD_ID.fullmatch(v) for v in ids):
            raise ValueError(f"Dark Gift {name} identities must be sorted, unique card IDs")
    if len(candidates) != 12 or len(reviewed) != 10 or not set(reviewed).issubset(candidates):
        raise ValueError("Dark Gift candidate/launch-reviewed set sizes do not match the reviewed contract")
    if raw["runtime_membership_status"] != "UNRESOLVED" or raw["sampler_status"] != "UNVERIFIED" or raw["execution_support_status"] != "SCOPED_EXPERIMENTAL" or raw["training_eligible"] is not False:
        raise ValueError("Dark Gift uncertainty/training status cannot be promoted by this loader")
    if raw["candidate_membership_sha256"] != membership_hash(candidates) or raw["launch_reviewed_membership_sha256"] != membership_hash(reviewed):
        raise ValueError("Dark Gift option membership hash mismatch")
    rows = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    if not isinstance(rows, dict) or not isinstance(rows.get("cards"), list):
        raise ValueError("Dark Gift option metadata must contain a cards array")
    metadata_ids = {row.get("id") for row in rows["cards"] if isinstance(row, dict)}
    if not set(reviewed).issubset(metadata_ids):
        raise ValueError("launch-reviewed Dark Gift option is missing from pinned identity metadata")
    return DarkGiftOptionManifestDocument(raw["manifest_id"], metadata["id"], metadata["sha256"],
        tuple(candidates), tuple(reviewed), raw["candidate_membership_sha256"], raw["launch_reviewed_membership_sha256"])

def _predicate_fingerprint(document: dict[str, Any]) -> str:
    predicate = document["predicate"]
    metadata = document["metadata_snapshot"]
    lines = [
        f"schema={document['schema_version']}",
        f"contract={document['contract_version']}",
        f"pool={document['pool_id']}",
        f"profile={document['format_profile_id']}",
        f"as_of={document['as_of_date']}",
        f"predicate={predicate['kind']}",
        f"school={predicate['school'] or ''}",
        f"base_cost={-1 if predicate['base_cost'] is None else predicate['base_cost']}",
        f"class_policy={predicate['class_policy']}",
        f"metadata_id={metadata['id']}",
        f"metadata_sha256={metadata['sha256']}",
        f"membership={document['sorted_membership_sha256']}",
    ]
    for exclusion in document["exclusions"]:
        lines.append(
            f"exclusion={exclusion['category']}|{exclusion['status']}|"
            f"{exclusion['rationale']}|{exclusion['evidence_ref']}"
        )
        lines.extend(f"id={card_id}" for card_id in exclusion["card_ids"])
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


@lru_cache(maxsize=4)
def _metadata_by_id(path: str) -> dict[str, dict[str, Any]]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("pinned metadata snapshot must be a card list")
    return {row["id"]: row for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)}


def _validate_membership_predicate(ids: list[str], predicate: dict[str, Any], metadata_path: str) -> None:
    metadata = _metadata_by_id(metadata_path)
    for card_id in ids:
        row = metadata.get(card_id)
        if row is None:
            raise ValueError(f"pool member is absent from pinned metadata: {card_id}")
        if not row.get("collectible") or row.get("type") != "SPELL":
            raise ValueError(f"pool member is not a collectible spell: {card_id}")
        if predicate["kind"] == "STANDARD_SPELL_SCHOOL" and str(row.get("spellSchool", "")).upper() != predicate["school"].upper():
            raise ValueError(f"pool member does not match spell-school predicate: {card_id}")
        if predicate["kind"] == "STANDARD_SPELL_BASE_COST" and row.get("cost") != predicate["base_cost"]:
            raise ValueError(f"pool member does not match base-cost predicate: {card_id}")
        if predicate["class_policy"] == "NON_NEUTRAL_CLASS" and row.get("cardClass") == "NEUTRAL":
            raise ValueError(f"pool member does not match class predicate: {card_id}")

def load_pool_manifest(
    manifest_path: str | Path,
    *,
    expected_profile_id: str,
    expected_as_of_date: str,
    metadata_snapshot_path: str | Path,
    standard_roots_path: str | Path,
    expected_metadata_snapshot_id: str,
) -> PoolManifestDocument:
    """Load a manifest only when its versions, hashes and pinned metadata match."""
    raw = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != _POOL_FIELDS:
        raise ValueError("unknown or missing pool manifest fields")
    if raw["schema_version"] != 1:
        raise ValueError("unknown pool manifest schema version")
    if raw["contract_version"] != 1:
        raise ValueError("unknown pool manifest contract version")
    if raw["format_profile_id"] != expected_profile_id or raw["as_of_date"] != expected_as_of_date:
        raise ValueError("pool manifest format profile identity mismatch")
    predicate = raw["predicate"]
    if not isinstance(predicate, dict) or set(predicate) != _PREDICATE_FIELDS:
        raise ValueError("pool predicate has unknown or missing fields")
    if predicate["kind"] not in _PREDICATES or predicate["class_policy"] not in _CLASS_POLICIES:
        raise ValueError("unknown typed pool predicate or class policy")
    if predicate["kind"] == "STANDARD_SPELL_SCHOOL":
        if not isinstance(predicate["school"], str) or not predicate["school"] or predicate["base_cost"] is not None or predicate["class_policy"] != "ANY_CLASS":
            raise ValueError("invalid spell-school predicate parameters")
    elif not isinstance(predicate["base_cost"], int) or isinstance(predicate["base_cost"], bool) or not 0 <= predicate["base_cost"] <= 10 or predicate["school"] is not None:
        raise ValueError("invalid spell base-cost predicate parameters")
    ids = raw["card_ids"]
    if not isinstance(ids, list) or any(not isinstance(card_id, str) or not _CARD_ID.fullmatch(card_id) for card_id in ids):
        raise ValueError("pool membership must contain canonical card IDs")
    if ids != sorted(set(ids)):
        raise ValueError("pool membership must be sorted and unique")
    if raw["count"] != len(ids):
        raise ValueError("pool manifest count mismatch")
    if raw["sorted_membership_sha256"] != membership_hash(ids):
        raise ValueError("pool manifest membership hash mismatch")
    _validate_membership_predicate(ids, predicate, str(Path(metadata_snapshot_path).resolve()))
    roots_document = json.loads(Path(standard_roots_path).read_text(encoding="utf-8"))
    if roots_document.get("format") != "STANDARD" or roots_document.get("as_of_date") != expected_as_of_date:
        raise ValueError("pinned Standard roots identity mismatch")
    standard_ids = {row.get("card_id") for row in roots_document.get("roots", []) if isinstance(row, dict)}
    if len(standard_ids) != roots_document.get("root_count"):
        raise ValueError("pinned Standard roots count mismatch")
    if hashlib.sha256("\n".join(sorted(standard_ids)).encode("utf-8")).hexdigest() != roots_document.get("root_membership_sha256"):
        raise ValueError("pinned Standard roots membership hash mismatch")
    if raw["metadata_snapshot"].get("id") != expected_metadata_snapshot_id:
        raise ValueError("pool manifest metadata snapshot ID mismatch")
    if not set(ids).issubset(standard_ids):
        raise ValueError("pool membership contains an ID outside the pinned Standard roots")
    snapshot = raw["metadata_snapshot"]
    if not isinstance(snapshot, dict) or set(snapshot) != {"id", "sha256"} or not _SHA256.fullmatch(str(snapshot["sha256"])):
        raise ValueError("invalid metadata snapshot identity")
    actual_snapshot_hash = hashlib.sha256(Path(metadata_snapshot_path).read_bytes()).hexdigest()
    if snapshot["sha256"] != actual_snapshot_hash:
        raise ValueError("pool manifest metadata identity mismatch")
    if raw["membership_status"] not in _MEMBERSHIP or raw["dependency_status"] not in _DEPENDENCY:
        raise ValueError("invalid pool membership/dependency status")
    if not isinstance(raw["training_eligible"], bool):
        raise ValueError("training_eligible must be boolean")
    if raw["training_eligible"] and (raw["membership_status"] != "MEMBERSHIP_REVIEWED" or raw["dependency_status"] != "DEPENDENCY_CLOSED"):
        raise ValueError("training eligibility requires reviewed membership and dependency closure")
    if not isinstance(raw["exclusions"], list):
        raise ValueError("pool exclusions must be a list")
    exclusions = []
    for exclusion in raw["exclusions"]:
        fields = {"category", "status", "card_ids", "rationale", "evidence_ref"}
        if not isinstance(exclusion, dict) or set(exclusion) != fields:
            raise ValueError("pool exclusion has unknown or missing fields")
        if exclusion["category"] not in _EXCLUSION_CATEGORIES or exclusion["status"] not in _EXCLUSION_STATUSES:
            raise ValueError("unknown pool exclusion category/status")
        excluded_ids = exclusion["card_ids"]
        if not isinstance(excluded_ids, list) or excluded_ids != sorted(set(excluded_ids)) or any(not _CARD_ID.fullmatch(value) for value in excluded_ids):
            raise ValueError("pool exclusion IDs must be canonical, sorted and unique")
        if not isinstance(exclusion["rationale"], str) or not exclusion["rationale"] or not isinstance(exclusion["evidence_ref"], str):
            raise ValueError("pool exclusion rationale/evidence identity is invalid")
        if exclusion["status"] == "REVIEWED_EXCLUDED" and set(ids).intersection(excluded_ids):
            raise ValueError("reviewed excluded identity also appears in pool membership")
        exclusions.append(PoolExclusionRecord(exclusion["category"], exclusion["status"], tuple(excluded_ids), exclusion["rationale"], exclusion["evidence_ref"]))
    if not _SHA256.fullmatch(str(raw["predicate_rules_fingerprint"])) or raw["predicate_rules_fingerprint"] != _predicate_fingerprint(raw):
        raise ValueError("pool predicate/rules fingerprint mismatch")
    return PoolManifestDocument(
        pool_id=raw["pool_id"], schema_version=raw["schema_version"], contract_version=raw["contract_version"],
        format_profile_id=raw["format_profile_id"], as_of_date=raw["as_of_date"], predicate_kind=predicate["kind"],
        school=predicate["school"] or "", base_cost=-1 if predicate["base_cost"] is None else predicate["base_cost"],
        class_policy=predicate["class_policy"], card_ids=tuple(ids), count=raw["count"],
        sorted_membership_sha256=raw["sorted_membership_sha256"], metadata_snapshot_id=snapshot["id"],
        metadata_snapshot_sha256=snapshot["sha256"], membership_status=raw["membership_status"],
        dependency_status=raw["dependency_status"], training_eligible=raw["training_eligible"],
        exclusions=tuple(exclusions), predicate_rules_fingerprint=raw["predicate_rules_fingerprint"],
    )
