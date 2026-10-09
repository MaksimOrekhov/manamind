"""Guards the MODEL-FIRST-MIGRATION-1 decision: RosettaStone is not an active dependency."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_ROOTS = ("src", "scripts", "tests", "experiments/manaengine/scripts", "experiments/manaengine/tests", ".github", "pyproject.toml")
SELF = Path(__file__).resolve()
FORBIDDEN = re.compile(r"integrations[./]rosettastone|vendor/RosettaStone|MANAMIND_ROSETTA|mana_rosetta_bridge|submodules:\s*recursive", re.I)


def test_no_submodules_or_vendored_engine():
    assert not (ROOT / ".gitmodules").exists()
    assert not (ROOT / "vendor" / "RosettaStone").exists()
    assert not (ROOT / "integrations" / "rosettastone").exists()
    assert not (ROOT / "src/manamind/integrations/rosettastone").exists()
    tracked = subprocess.run(["git", "ls-files", "-s"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert not [line for line in tracked.splitlines() if line.startswith("160000")], "gitlink (submodule) found"


def test_active_code_and_ci_do_not_reference_rosettastone():
    hits = []
    for name in ACTIVE_ROOTS:
        base = ROOT / name
        for path in ([base] if base.is_file() else base.rglob("*")):
            if not path.is_file() or path == SELF or "__pycache__" in path.parts or "build-" in path.as_posix():
                continue
            if path.suffix not in {".py", ".yml", ".yaml", ".toml", ".txt", ".cmake", ".cpp", ".h", ".hpp"}:
                continue
            if FORBIDDEN.search(path.read_text(encoding="utf-8", errors="ignore")):
                hits.append(path.relative_to(ROOT).as_posix())
    assert not hits, hits
