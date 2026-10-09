import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROFILE = Path("configs/standard_profile.json")


def test_new_dated_profile_builds_catalog_without_python_source_edits(tmp_path):
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    scope = json.loads(Path(profile["scope"]).read_text(encoding="utf-8"))
    scope["as_of_date"] = "2026-10-02"
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(json.dumps(scope), encoding="utf-8")
    profile.update({"profile_id": "test_standard_20261002", "as_of_date": "2026-10-02", "scope": str(scope_path),
                    "roots": str(tmp_path / "roots.json"), "catalog": str(tmp_path / "catalog.json")})
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    subprocess.run([sys.executable, "scripts/build_standard_profile.py", "--profile", str(profile_path)], check=True, capture_output=True)
    catalog = json.loads(Path(profile["catalog"]).read_text(encoding="utf-8"))
    assert catalog["valid_as_of"] == "2026-10-02"
    assert catalog["profile_id"] == "test_standard_20261002"
    assert len(catalog["cards"]) == len(json.loads(Path(profile["roots"]).read_text(encoding="utf-8"))["roots"])


def test_committed_catalog_matches_pinned_snapshot_and_needs_no_vendored_engine():
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    assert not any("RosettaStone" in str(value) or "vendor/" in str(value) for key, value in profile.items() if key != "historical_registry")
    catalog = json.loads(Path(profile["catalog"]).read_text(encoding="utf-8"))
    roots = json.loads(Path(profile["roots"]).read_text(encoding="utf-8"))
    assert catalog["root_membership_sha256"] == roots["root_membership_sha256"]
    assert catalog["source_sha256"] == hashlib.sha256(Path(profile["metadata_snapshot"]).read_bytes()).hexdigest()
    assert [row["id"] for row in catalog["cards"]] == [item["metadata"]["id"] for item in roots["roots"]]
    assert not Path(".gitmodules").exists()


def test_historical_registry_is_marked_frozen_and_not_an_admission_gate():
    historical = json.loads(PROFILE.read_text(encoding="utf-8"))["historical_registry"]
    assert historical["status"] == "FROZEN_HISTORICAL_SNAPSHOT"
    registry = json.loads(Path(historical["path"]).read_text(encoding="utf-8"))
    assert registry["registry_id"] == historical["registry_id"]
