"""Capture source card metadata and build a pinned Standard root-pool snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://api.hearthstonejson.com/v1/latest/enUS/cards.collectible.json"
DEFAULT_SCOPE = ROOT / "data/cards/standard_scope_20261001.json"
DEFAULT_ARCHIVE = ROOT / "data/cards/source_snapshots/cards_collectible_20261001_enUS.json"
DEFAULT_OUTPUT = ROOT / "data/cards/standard_roots_20261001_enUS.json"


def read_source(source_file: Path | None) -> tuple[bytes, str]:
    if source_file:
        return source_file.read_bytes(), str(source_file.resolve())
    request = Request(SOURCE_URL, headers={"User-Agent": "ManaMind Standard root snapshot builder"})
    with urlopen(request, timeout=60) as response:
        return response.read(), response.geturl()


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", type=Path, default=DEFAULT_SCOPE)
    parser.add_argument("--source-file", type=Path, help="Use a previously captured full collectible-card JSON array")
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    scope_bytes = args.scope.read_bytes()
    scope = json.loads(scope_bytes.decode("utf-8-sig"))
    if scope.get("format") != "STANDARD" or scope.get("as_of_date") != "2026-10-01":
        raise ValueError("This builder expects the approved STANDARD scope dated 2026-10-01")
    sets = scope.get("standard_sets")
    exceptions = scope.get("explicit_standard_card_ids")
    excluded_ids = scope.get("excluded_card_ids", [])
    if not isinstance(sets, list) or not sets or len(set(sets)) != len(sets):
        raise ValueError("standard_sets must contain unique set IDs")
    if not isinstance(exceptions, list) or len(set(exceptions)) != len(exceptions):
        raise ValueError("explicit_standard_card_ids must contain unique IDs")
    if not isinstance(excluded_ids, list) or len(set(excluded_ids)) != len(excluded_ids):
        raise ValueError("excluded_card_ids must contain unique IDs")
    if set(exceptions) & set(excluded_ids):
        raise ValueError("A card ID cannot be both an explicit root exception and an exclusion")

    source_bytes, resolved_source = read_source(args.source_file)
    source = json.loads(source_bytes.decode("utf-8-sig"))
    if not isinstance(source, list) or any(not isinstance(row, dict) for row in source):
        raise ValueError("Source must be a JSON array of card objects")
    source_ids = [row.get("id") for row in source]
    if any(not isinstance(card_id, str) or not card_id for card_id in source_ids):
        raise ValueError("Source has records without a card ID")
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Source has duplicate card IDs")
    by_id = {row["id"]: row for row in source}
    absent_sets = set(sets) - {row.get("set") for row in source}
    if absent_sets:
        raise ValueError(f"Approved set IDs missing from source: {sorted(absent_sets)}")
    absent_exceptions = set(exceptions) - set(by_id)
    if absent_exceptions:
        raise ValueError(f"Explicit exception IDs missing from source: {sorted(absent_exceptions)}")
    absent_exclusions = set(excluded_ids) - set(by_id)
    if absent_exclusions:
        raise ValueError(f"Explicit exclusion IDs missing from source: {sorted(absent_exclusions)}")
    invalid_exceptions = [card_id for card_id in exceptions if by_id[card_id].get("collectible") is not True]
    if invalid_exceptions:
        raise ValueError(f"Explicit root exceptions are not collectible: {sorted(invalid_exceptions)}")

    roots = []
    for card in source:
        if card.get("collectible") is not True or card.get("id") in excluded_ids:
            continue
        if card.get("set") in sets:
            reason = {"kind": "standard_set", "set_id": card["set"]}
        elif card.get("id") in exceptions:
            reason = {"kind": "explicit_card_exception", "exception_id": card["id"]}
        else:
            continue
        roots.append({"card_id": card["id"], "membership_reason": reason, "metadata": card})
    roots.sort(key=lambda item: item["card_id"])

    source_hash = hashlib.sha256(source_bytes).hexdigest()
    membership_hash = hashlib.sha256(
        "\n".join(item["card_id"] for item in roots).encode("utf-8")
    ).hexdigest()
    counts = Counter(item["membership_reason"].get("set_id", "EXPLICIT_EXCEPTION") for item in roots)
    output = {
        "schema_version": 1,
        "game": "Hearthstone",
        "format": "STANDARD",
        "as_of_date": scope["as_of_date"],
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "scope_file": str(args.scope.resolve()),
        "scope_sha256": hashlib.sha256(scope_bytes).hexdigest(),
        "source_name": "HearthstoneJSON collectible card metadata",
        "source_url": SOURCE_URL,
        "resolved_source": resolved_source,
        "source_archive": str(args.archive.resolve()),
        "source_sha256": source_hash,
        "source_record_count": len(source),
        "source_collectible_count": sum(row.get("collectible") is True for row in source),
        "standard_sets": sorted(sets),
        "explicit_standard_card_ids": sorted(exceptions),
        "excluded_card_ids": sorted(excluded_ids),
        "explicit_exclusions": scope.get("explicit_exclusions", []),
        "root_count": len(roots),
        "root_membership_sha256": membership_hash,
        "root_counts_by_set_or_exception": dict(sorted(counts.items())),
        "roots": roots,
        "sources": scope.get("sources", []),
        "validation": {
            "unique_source_ids": True,
            "all_scope_sets_present_in_source": True,
            "all_explicit_ids_present_and_collectible": True,
            "all_explicit_exclusion_ids_present": True,
            "no_explicit_exclusions_in_root_membership": not (set(excluded_ids) & {item["card_id"] for item in roots}),
            "all_roots_collectible": True
        }
    }
    output_bytes = (json.dumps(output, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    atomic_write(args.archive, source_bytes)
    atomic_write(args.output, output_bytes)
    print(f"Built {args.output}: {len(roots)} collectible roots")
    print(f"Archived source: {args.archive}")
    print(f"Source SHA-256: {source_hash}")
    print(f"Membership SHA-256: {membership_hash}")
    for set_id, count in sorted(counts.items()):
        print(f"  {set_id}: {count}")


if __name__ == "__main__":
    main()
