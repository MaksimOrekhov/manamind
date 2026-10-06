import json
from pathlib import Path
import subprocess
import sys


def test_new_dated_profile_builds_without_python_source_edits(tmp_path):
    profile = json.loads(Path("configs/standard_profile.json").read_text(encoding="utf-8"))
    scope = json.loads(Path(profile["scope"]).read_text(encoding="utf-8"))
    scope["as_of_date"] = "2026-10-02"
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(json.dumps(scope), encoding="utf-8")
    profile.update({"profile_id": "test_standard_20261002", "registry_id": "test_registry_20261002", "as_of_date": "2026-10-02", "scope": str(scope_path), "roots": str(tmp_path / "roots.json"), "catalog": str(tmp_path / "catalog.json"), "engine_overlay": str(tmp_path / "overlay.json"), "registry": str(tmp_path / "registry.json"), "reports": str(tmp_path / "reports"), "verification_evidence": []})
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    for script in ("build_standard_profile", "build_standard_registry"):
        subprocess.run([sys.executable, "scripts/" + script + ".py", "--profile", str(profile_path)], check=True, capture_output=True)
    registry = json.loads(Path(profile["registry"]).read_text(encoding="utf-8"))
    assert registry["registry_id"] == "test_registry_20261002"
    assert registry["snapshot"]["as_of_date"] == "2026-10-02"
    assert registry["computed_admission"]["profile_id"] == "test_standard_20261002"
    catalog = json.loads(Path(profile["catalog"]).read_text(encoding="utf-8"))
    overlay = json.loads(Path(profile["engine_overlay"]).read_text(encoding="utf-8"))
    assert {row["id"] for row in catalog["cards"]} == set(registry["cards"])
    assert overlay == catalog["cards"]
    before = Path(profile["registry"]).read_bytes()
    subprocess.run([sys.executable, "scripts/build_standard_registry.py", "--profile", str(profile_path)], check=True, capture_output=True)
    assert Path(profile["registry"]).read_bytes() == before


def test_observation_source_identity_covers_the_shared_power_log_package(tmp_path, monkeypatch):
    sys.path.insert(0, "scripts")
    import standard_profile as sp

    assert "src/manamind/integrations/powerlog" in sp.OBSERVATION_SOURCE_ROOTS
    assert not any("manamind/live" in root for root in sp.OBSERVATION_SOURCE_ROOTS)
    for root in sp.OBSERVATION_SOURCE_ROOTS:
        assert (sp.ROOT / root).exists()

    seen = {}
    real = sp.tree_digest
    monkeypatch.setattr(sp, "tree_digest", lambda directory, roots: seen.setdefault(roots, real(directory, roots)))
    profile = json.loads(Path("configs/standard_profile.json").read_text(encoding="utf-8"))
    sp.execution_identity(profile)
    assert sp.OBSERVATION_SOURCE_ROOTS in seen  # execution_identity hashes exactly this set

    # Any change inside the package changes the digest (deterministic, private-log free).
    package = tmp_path / "src/manamind/integrations/powerlog"
    package.mkdir(parents=True)
    (package / "visible_state.py").write_text("A = 1\n", encoding="utf-8")
    roots = ("src/manamind/integrations/powerlog",)
    before = real(tmp_path, roots)
    (package / "visible_state.py").write_text("A = 2\n", encoding="utf-8")
    assert real(tmp_path, roots) != before
    (package / "exporter.py").write_text("B = 1\n", encoding="utf-8")
    assert real(tmp_path, roots) != before
