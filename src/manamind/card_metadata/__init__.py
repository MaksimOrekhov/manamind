"""Independent full-card metadata layer (research tools and future components, not the model catalog)."""

from .snapshot import (
    AmbiguousCardId,
    CardDescription,
    CardMetadata,
    Lookup,
    SnapshotError,
    SnapshotInfo,
    SnapshotIntegrityError,
    Status,
    plain_text,
    strip_text_artifacts,
    quality_flags,
    read_manifest,
)

__all__ = [
    "AmbiguousCardId", "CardDescription", "CardMetadata", "Lookup", "SnapshotError", "SnapshotInfo",
    "SnapshotIntegrityError", "Status", "plain_text", "quality_flags", "read_manifest",
    "strip_text_artifacts",
]
