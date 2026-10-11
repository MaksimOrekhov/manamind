"""Build display-only RU/EN names. Never changes the model's Standard catalog.

Inputs: full cards.json from the build/locale URLs in the committed manifest.
No network access: download those two files explicitly before reproducing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(inputs: dict[str, Path], sources: dict) -> dict:
    names = {}
    for locale, path in inputs.items():
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sources[locale]["sha256"]:
            raise ValueError(f"Source hash mismatch: {locale}")
        for card in json.loads(raw):
            if card.get("id") and card.get("name"):
                names.setdefault(card["id"], {})[locale] = card["name"]
    return {"schema": "manamind.card_names/1", "build": 253932, "sources": sources,
            "names": dict(sorted(names.items()))}


def serialize(payload: dict) -> str:
    # One record per line keeps this generated all-entity snapshot reviewable and compact.
    header = json.dumps({k: v for k, v in payload.items() if k != "names"}, ensure_ascii=False, indent=2)
    rows = ["    " + json.dumps(k, ensure_ascii=False) + ": " + json.dumps(v, ensure_ascii=False)
            for k, v in payload["names"].items()]
    return header[:-2] + ',\n  "names": {\n' + ",\n".join(rows) + "\n  }\n}\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ru", type=Path, required=True)
    parser.add_argument("--en", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pinned = json.loads((ROOT / "data/localization/card_names_253932.json").read_text(encoding="utf-8"))
    payload = build({"enUS": args.en, "ruRU": args.ru}, pinned["sources"])
    args.output.write_text(serialize(payload), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
