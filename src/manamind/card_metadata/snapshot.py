"""Read-only access to pinned full HearthstoneJSON snapshots (collectible and non-collectible records).

This layer is independent of the model catalog: it never reads ``data/cards/standard_current_enUS.json`` or a
checkpoint, and nothing in the model, encoder or LIVE path imports it. A record in a snapshot proves only that the
client data defines the ID. It does not prove that the card is legal in a format or that any engine supports it.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "card_metadata"
MANIFEST_NAME = "manifest.json"
SCHEMA_VERSION = 1

# Record kinds that a player can have in hand or on the board; other types are enchantments, skins, modes.
GAMEPLAY_TYPES = frozenset({"MINION", "SPELL", "WEAPON", "LOCATION", "HERO", "HERO_POWER"})
COSTED_TYPES = frozenset({"MINION", "SPELL", "WEAPON", "LOCATION"})
# Tags that describe behaviour rather than a plain keyword; a card with one of them and no text is suspicious.
EFFECT_TAGS = frozenset({
    "BATTLECRY", "DEATHRATTLE", "COMBO", "OUTCAST", "SECRET", "QUEST", "SIDE_QUEST", "TRIGGER_VISUAL",
    "INSPIRE", "OVERLOAD", "SPELLBURST", "FRENZY", "TRADEABLE", "ECHO", "DISCOVER", "ADAPT", "CHOOSE_ONE",
    "START_OF_GAME", "AURA", "IMMUNE", "FORGETFUL", "INFUSE", "TITAN", "COLOSSAL", "DORMANT",
})

_TAG = re.compile(r"<[^>]+>")
_NUMBER_MARK = re.compile(r"[$#](?=\d)")
_SPACE = re.compile(r"\s+")
_PLACEHOLDER = re.compile(r"to be revealed|\bTBD\b|\bPLACEHOLDER\b|\[PH\]|\bDNT\b", re.IGNORECASE)
_TEMPLATE_VALUE = re.compile(r"\{\d+\}")
# Build 254477 and later inject a bare "&" after "</b>", a comma or a period before a space/newline (323 records,
# all collectible; 6 older records carry only a legitimate " & "). It is a layout marker, not display text.
_LAYOUT_MARKER = re.compile(r"(?<=[A-Za-z0-9>,.:])&(?=\s|$)")
# Ten records of build 254477 and later end in a debug tag such as "~GAMEPLAY ASPROXY CORE EX1 323" (spaces are NBSP).
_DEBUG_MARKER = re.compile(r"\s*~GAMEPLAY\s+ASPROXY[^\n]*$")


class SnapshotError(ValueError):
    """The manifest, a snapshot file or its recorded identity is invalid."""


class SnapshotIntegrityError(SnapshotError):
    """The bytes of a snapshot file do not match the SHA-256 pinned in the manifest."""


class AmbiguousCardId(LookupError):
    """More than one record carries the requested ID; a caller must not pick one silently."""

    def __init__(self, card_id: str, count: int) -> None:
        super().__init__(f"{card_id!r} has {count} records in the snapshot")
        self.card_id = card_id
        self.count = count


class Status(str, Enum):
    FOUND = "FOUND"
    MISSING = "MISSING"
    AMBIGUOUS = "AMBIGUOUS"


def strip_text_artifacts(text: Any) -> str:
    """Raw card text without the injected ``&`` layout marker and trailing debug tag (HTML is left intact)."""
    return _DEBUG_MARKER.sub("", _LAYOUT_MARKER.sub("", text)) if isinstance(text, str) else ""


def plain_text(text: Any) -> str:
    """Card text without markup: no HTML tags, no layout marker, no leading ``[x]``, no ``$``/``#`` marks."""
    if not isinstance(text, str):
        return ""
    text = _TAG.sub("", strip_text_artifacts(text).replace("\u00a0", " "))
    text = _NUMBER_MARK.sub("", text)
    if text.startswith("[x]"):
        text = text[3:]
    return _SPACE.sub(" ", text).strip()


@dataclass(frozen=True)
class SnapshotInfo:
    snapshot_id: str
    build: int
    patch: str | None
    locale: str
    file: str
    raw_sha256: str
    raw_bytes: int
    record_count: int
    source_url: str
    retrieved_at_utc: str
    equivalent_builds: tuple[int, ...]
    role: str
    notes: str


@dataclass(frozen=True)
class Lookup:
    card_id: str
    status: Status
    snapshot_id: str
    record: Mapping[str, Any] | None = None
    candidates: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class CardDescription:
    """Typed view of one record. Missing values stay ``None``; nothing is invented."""

    card_id: str
    snapshot_id: str
    dbf_id: int | None
    name: str | None
    card_type: str | None
    card_class: str | None
    classes: tuple[str, ...]
    card_set: str | None
    rarity: str | None
    collectible: bool
    cost: int | None
    attack: int | None
    health: int | None
    durability: int | None
    armor: int | None
    races: tuple[str, ...]
    spell_school: str | None
    mechanics: tuple[str, ...]
    referenced_tags: tuple[str, ...]
    text: str
    plain_text: str
    is_token: bool
    flags: tuple[str, ...]


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _tuple(value: Any) -> tuple[str, ...]:
    return tuple(item for item in value if isinstance(item, str)) if isinstance(value, list) else ()


def quality_flags(record: Mapping[str, Any]) -> tuple[str, ...]:
    """Independent, informational data-quality flags. They never hide or repair a record."""
    flags: list[str] = []
    card_type = _str(record.get("type"))
    if card_type is None:
        flags.append("MISSING_TYPE")
    if not _str(record.get("name")):
        flags.append("MISSING_NAME")
    gameplay = card_type in GAMEPLAY_TYPES
    if gameplay and not _str(record.get("cardClass")):
        flags.append("MISSING_CLASS")
    if card_type in COSTED_TYPES and _int(record.get("cost")) is None:
        flags.append("MISSING_COST")
    if card_type == "MINION" and (_int(record.get("attack")) is None or _int(record.get("health")) is None):
        flags.append("MISSING_STATS")
    if card_type == "WEAPON" and (_int(record.get("attack")) is None or _int(record.get("durability")) is None):
        flags.append("MISSING_STATS")
    text = record.get("text")
    if gameplay and not plain_text(text):
        flags.append("EMPTY_TEXT")
        if EFFECT_TAGS & set(_tuple(record.get("mechanics"))):
            flags.append("EMPTY_TEXT_WITH_EFFECT_TAG")
    if isinstance(text, str):
        if _PLACEHOLDER.search(text):
            flags.append("PLACEHOLDER_TEXT")
        if _TEMPLATE_VALUE.search(text):
            flags.append("TEMPLATE_VALUE_IN_TEXT")
        if "@" in text:
            flags.append("MULTI_STATE_TEXT")
        if _LAYOUT_MARKER.search(text):
            flags.append("LAYOUT_MARKER_IN_TEXT")
        if _DEBUG_MARKER.search(text):
            flags.append("DEBUG_MARKER_IN_TEXT")
        if "�" in text:
            flags.append("REPLACEMENT_CHARACTER_IN_TEXT")
    return tuple(flags)


def describe_record(record: Mapping[str, Any], snapshot_id: str) -> CardDescription:
    card_type = _str(record.get("type"))
    collectible = record.get("collectible") is True
    races = _tuple(record.get("races")) or _tuple([record.get("race")] if record.get("race") else [])
    text = record.get("text") if isinstance(record.get("text"), str) else ""
    return CardDescription(
        card_id=str(record["id"]), snapshot_id=snapshot_id, dbf_id=_int(record.get("dbfId")), name=_str(record.get("name")),
        card_type=card_type, card_class=_str(record.get("cardClass")), classes=_tuple(record.get("classes")),
        card_set=_str(record.get("set")), rarity=_str(record.get("rarity")), collectible=collectible,
        cost=_int(record.get("cost")), attack=_int(record.get("attack")), health=_int(record.get("health")),
        durability=_int(record.get("durability")), armor=_int(record.get("armor")), races=races,
        spell_school=_str(record.get("spellSchool")), mechanics=_tuple(record.get("mechanics")),
        referenced_tags=_tuple(record.get("referencedTags")), text=text, plain_text=plain_text(text),
        is_token=(not collectible) and card_type in {"MINION", "SPELL", "WEAPON", "LOCATION"},
        flags=quality_flags(record),
    )


def read_manifest(root: Path = DEFAULT_ROOT) -> list[SnapshotInfo]:
    path = Path(root) / MANIFEST_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise SnapshotError(f"unsupported manifest schema in {path}")
    infos = []
    for entry in payload["snapshots"]:
        infos.append(SnapshotInfo(
            snapshot_id=entry["snapshot_id"], build=entry["build"], patch=entry.get("patch"), locale=entry["locale"],
            file=entry["file"], raw_sha256=entry["raw_sha256"], raw_bytes=entry["raw_bytes"],
            record_count=entry["record_count"], source_url=entry["source_url"],
            retrieved_at_utc=entry["retrieved_at_utc"], equivalent_builds=tuple(entry.get("equivalent_builds", ())),
            role=entry.get("role", ""), notes=entry.get("notes", ""),
        ))
    ids = [info.snapshot_id for info in infos]
    if len(set(ids)) != len(ids):
        raise SnapshotError("duplicate snapshot_id in manifest")
    return infos


class CardMetadata:
    """One pinned snapshot, loaded offline and verified against its manifest SHA-256. Read-only."""

    def __init__(self, info: SnapshotInfo, records: Iterable[Mapping[str, Any]]) -> None:
        self.info = info
        by_id: dict[str, list[Mapping[str, Any]]] = {}
        by_dbf: dict[int, list[str]] = {}
        for record in records:
            card_id = record.get("id") if isinstance(record, Mapping) else None
            if not isinstance(card_id, str) or not card_id:
                raise SnapshotError("record without a string id")
            by_id.setdefault(card_id, []).append(MappingProxyType(dict(record)))
            dbf = _int(record.get("dbfId"))
            if dbf is not None:
                by_dbf.setdefault(dbf, []).append(card_id)
        self._by_id = by_id
        self._by_dbf = by_dbf

    @classmethod
    def load(cls, snapshot_id: str | None = None, *, root: Path = DEFAULT_ROOT) -> "CardMetadata":
        """Load a snapshot by ID (default: the manifest's ``current`` one). Never touches the network."""
        infos = read_manifest(root)
        if snapshot_id is None:
            current = [info for info in infos if info.role == "current"]
            if len(current) != 1:
                raise SnapshotError("manifest must name exactly one snapshot with role 'current'")
            info = current[0]
        else:
            matches = [item for item in infos if item.snapshot_id == snapshot_id]
            if not matches:
                raise SnapshotError(f"unknown snapshot {snapshot_id!r}; known: {[item.snapshot_id for item in infos]}")
            info = matches[0]
        raw = gzip.decompress((Path(root) / info.file).read_bytes())
        digest = hashlib.sha256(raw).hexdigest()
        if digest != info.raw_sha256 or len(raw) != info.raw_bytes:
            raise SnapshotIntegrityError(f"{info.file}: sha256 {digest} does not match manifest {info.raw_sha256}")
        records = json.loads(raw.decode("utf-8"))
        if not isinstance(records, list) or len(records) != info.record_count:
            raise SnapshotIntegrityError(f"{info.file}: record count differs from manifest")
        return cls(info, records)

    @property
    def snapshot_id(self) -> str:
        return self.info.snapshot_id

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, card_id: object) -> bool:
        return card_id in self._by_id

    def ids(self) -> frozenset[str]:
        return frozenset(self._by_id)

    def ambiguous_ids(self) -> frozenset[str]:
        return frozenset(card_id for card_id, records in self._by_id.items() if len(records) > 1)

    def lookup(self, card_id: str) -> Lookup:
        records = self._by_id.get(card_id)
        if not records:
            return Lookup(card_id, Status.MISSING, self.snapshot_id)
        if len(records) > 1:
            return Lookup(card_id, Status.AMBIGUOUS, self.snapshot_id, candidates=tuple(records))
        return Lookup(card_id, Status.FOUND, self.snapshot_id, record=records[0])

    def get(self, card_id: str) -> Mapping[str, Any] | None:
        """The record, ``None`` when the ID is missing; raises ``AmbiguousCardId`` rather than choosing."""
        found = self.lookup(card_id)
        if found.status is Status.AMBIGUOUS:
            raise AmbiguousCardId(card_id, len(found.candidates))
        return found.record

    def describe(self, card_id: str) -> CardDescription | None:
        record = self.get(card_id)
        return None if record is None else describe_record(record, self.snapshot_id)

    def records(self) -> Iterable[Mapping[str, Any]]:
        for card_id in sorted(self._by_id):
            yield from self._by_id[card_id]

    def ids_for_dbf_id(self, dbf_id: int) -> tuple[str, ...]:
        """All IDs sharing a ``dbfId``. More than one means the numeric key is ambiguous."""
        return tuple(self._by_dbf.get(dbf_id, ()))
