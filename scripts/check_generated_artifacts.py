"""Rebuild the pinned source-derived Standard artifacts and fail if any committed output differs."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from standard_profile import ROOT, load_profile, profile_path

BUILDERS = ("build_standard_profile",)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path)
    args = parser.parse_args()
    profile = load_profile(args.profile)
    outputs = {profile_path(profile, key) for key in ("roots", "catalog")}
    before = {path: path.read_bytes().replace(b"\r\n", b"\n") if path.exists() else None for path in outputs}
    environment = {**os.environ, "MANAMIND_STANDARD_PROFILE": str(profile["_path"])}
    for script in BUILDERS:
        subprocess.run([sys.executable, str(ROOT / "scripts" / (script + ".py"))], cwd=ROOT, env=environment, check=True)
    changed = [str(path) for path, content in before.items() if not path.exists() or path.read_bytes().replace(b"\r\n", b"\n") != content]
    if changed:
        raise SystemExit("Generated outputs were stale:\n" + "\n".join(sorted(changed)))
    print(f"{len(outputs)} pinned outputs reproduced from the pinned HearthstoneJSON snapshot.")


if __name__ == "__main__":
    main()
