"""Pin a full (collectible + non-collectible) HearthstoneJSON build under data/card_metadata/.

The raw JSON bytes are hashed, then stored gzip-compressed with a fixed header; the manifest records the SHA-256 of the
raw bytes (the identity of the data), the build number, URL and retrieval time. Existing snapshot files are never
overwritten. ``--verify`` re-downloads a pinned build and compares it with the manifest without writing anything.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from manamind.card_metadata.snapshot import DEFAULT_ROOT, MANIFEST_NAME, SCHEMA_VERSION  # noqa: E402

URL_TEMPLATE = "https://api.hearthstonejson.com/v1/{build}/{locale}/cards.json"


def download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "ManaMind card metadata snapshot"})
    with urlopen(request, timeout=120) as response:
        return response.read()


def deterministic_gzip(raw: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, compresslevel=9, mtime=0) as stream:
        stream.write(raw)
    return buffer.getvalue()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def validate(raw: bytes) -> list[dict]:
    records = json.loads(raw.decode("utf-8"))
    if not isinstance(records, list) or not records or any(not isinstance(item, dict) for item in records):
        raise SystemExit("source is not a non-empty JSON list of objects")
    ids = [item.get("id") for item in records]
    if any(not isinstance(item, str) or not item for item in ids):
        raise SystemExit("source has a record without a string id")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=int, required=True)
    parser.add_argument("--locale", default="enUS")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--patch", help="Patch/build label from the data source, e.g. 37.0.0.255130")
    parser.add_argument("--role", choices=("current", "previous"), default="previous")
    parser.add_argument("--replace-current", action="store_true", help="Demote an existing 'current' snapshot")
    parser.add_argument("--equivalent-build", type=int, action="append", default=[],
                        help="Other build numbers whose published bytes were verified identical")
    parser.add_argument("--notes", default="")
    parser.add_argument("--verify", action="store_true", help="Re-download and compare with the manifest; write nothing")
    args = parser.parse_args()

    snapshot_id = f"hsjson_{args.build}_{args.locale}"
    url = URL_TEMPLATE.format(build=args.build, locale=args.locale)
    manifest_path = args.root / MANIFEST_NAME
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists()
                else {"schema_version": SCHEMA_VERSION, "snapshots": []})
    existing = {entry["snapshot_id"]: entry for entry in manifest["snapshots"]}

    raw = download(url)
    digest = hashlib.sha256(raw).hexdigest()
    records = validate(raw)

    if args.verify:
        entry = existing.get(snapshot_id)
        if entry is None:
            raise SystemExit(f"{snapshot_id} is not pinned")
        if entry["raw_sha256"] != digest:
            raise SystemExit(f"MISMATCH {snapshot_id}: source {digest} manifest {entry['raw_sha256']}")
        print(f"{snapshot_id}: source bytes match the manifest ({digest})")
        return
    if snapshot_id in existing:
        raise SystemExit(f"{snapshot_id} is already pinned; refusing to overwrite")

    current = [entry for entry in manifest["snapshots"] if entry.get("role") == "current"]
    if args.role == "current" and current:
        if not args.replace_current:
            raise SystemExit("a 'current' snapshot exists; pass --replace-current to demote it")
        for entry in current:
            entry["role"] = "previous"

    file_name = f"hearthstonejson_{args.build}_{args.locale}.json.gz"
    target = args.root / file_name
    if target.exists():
        raise SystemExit(f"{target} exists; refusing to overwrite")
    atomic_write_bytes(target, deterministic_gzip(raw))
    manifest["snapshots"].append({
        "snapshot_id": snapshot_id, "build": args.build, "patch": args.patch, "locale": args.locale, "file": file_name,
        "raw_sha256": digest, "raw_bytes": len(raw), "record_count": len(records), "source_url": url,
        "retrieved_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "equivalent_builds": sorted(args.equivalent_build), "role": args.role, "notes": args.notes,
    })
    manifest["snapshots"].sort(key=lambda entry: -entry["build"])
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    atomic_write_bytes(manifest_path, payload.encode("utf-8"))
    print(f"pinned {snapshot_id}: {len(records)} records, raw sha256 {digest}")


if __name__ == "__main__":
    main()
