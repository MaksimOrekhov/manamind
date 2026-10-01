"""Build configured native consumers and record their source/binary identities."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from standard_profile import ROOT, execution_identity, load_profile


def cache_value(cache: Path, key: str) -> str:
    for line in cache.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(key + ":"):
            return line.split("=", 1)[1]
    raise ValueError(f"Missing {key} in {cache}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path)
    args = parser.parse_args()
    profile = load_profile(args.profile)
    before = execution_identity(profile)
    core = ROOT / "vendor/RosettaStone/build-mana-py312"
    bridge = ROOT / "integrations/rosettastone/build"
    cmake = cache_value(bridge / "CMakeCache.txt", "CMAKE_COMMAND")
    commands = [[cmake, "--build", str(core), "--target", "RosettaStone", "UnitTests"], [cmake, "--build", str(bridge), "--target", "mana_rosetta_bridge"]]
    log = []
    for command in commands:
        if sys.platform == "win32":
            compiler = Path(cache_value(bridge / "CMakeCache.txt", "CMAKE_CXX_COMPILER"))
            vcvars = compiler.parents[6] / "Auxiliary/Build/vcvars64.bat"
            build_command = f'call "{vcvars}" >nul && ' + subprocess.list2cmdline(command)
            invocation = f'cmd.exe /d /s /c "{build_command}"'
        else:
            invocation = command
        result = subprocess.run(invocation, capture_output=True, text=True, errors="replace", check=False)
        log.append(result.stdout + result.stderr)
        (bridge / "review_native_build.log").write_text("\n".join(log), encoding="utf-8")
        if result.returncode:
            raise SystemExit(f"Native build failed; see {bridge / 'review_native_build.log'}")
    if execution_identity(profile) != before:
        raise SystemExit("Sources changed during build; identity was not recorded")
    sys.path.insert(0, str(ROOT))
    from scripts.verification_evidence import artifact_identities
    document = {"schema_version": 1, "execution_identity": before, "artifacts": artifact_identities(), "build_result": "PASS", "commands": commands}
    output = bridge / "execution_identity.json"
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"Native build identity recorded: {output}")


if __name__ == "__main__":
    main()
