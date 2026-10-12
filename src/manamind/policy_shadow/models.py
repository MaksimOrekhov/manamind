"""Loading of experimental Policy checkpoints for the model shadow: pinned SHA-256, runtime catalog, no side effects."""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path

from manamind.training.policy_checkpoint import identity, load_policy_checkpoint

_SHA256 = re.compile(r"[0-9a-f]{64}")


class ModelUnavailable(ValueError):
    """A checkpoint the shadow refuses to use; ``reason`` is a stable code (no path, no exception text)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ExperimentalModel:
    name: str                 # stable label written to the journal, e.g. "retrained_v2" or "policy_v3"
    sha256: str
    schema: str
    architecture: str
    parameters: int
    catalog_sha256: str
    policy: object
    encoder: object
    representation: int


def load_experimental(name: str, path: Path, expected_sha256: str, catalog) -> ExperimentalModel:
    """Verify the pinned digest of the exact bytes that are then parsed, the strict schema and the runtime catalog."""
    if not isinstance(expected_sha256, str) or _SHA256.fullmatch(expected_sha256) is None:
        raise ModelUnavailable("CHECKPOINT_IDENTITY_MISMATCH")
    try:
        data = Path(path).read_bytes()
    except OSError:
        raise ModelUnavailable("CHECKPOINT_UNREADABLE") from None
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ModelUnavailable("CHECKPOINT_IDENTITY_MISMATCH")
    try:
        policy, encoder, payload = load_policy_checkpoint(io.BytesIO(data), device="cpu")
    except Exception:  # torch / pickle errors may carry file content
        raise ModelUnavailable("CHECKPOINT_INCOMPATIBLE") from None
    if identity(catalog.to_dict()) != payload["catalog_sha256"]:
        raise ModelUnavailable("RUNTIME_CATALOG_MISMATCH")
    policy.eval()
    for parameter in policy.parameters():
        parameter.requires_grad_(False)
    from manamind.models.policy_inputs import representation_of
    return ExperimentalModel(
        name=name, sha256=expected_sha256, schema=payload["schema"],
        architecture=payload["model_config"]["architecture"],
        parameters=sum(p.numel() for p in policy.parameters()), catalog_sha256=payload["catalog_sha256"],
        policy=policy, encoder=encoder, representation=representation_of(policy))


def load_models(specs, catalog, *, reserved_sha256: set[str] | frozenset[str] = frozenset()):
    """Load ``(name, path, sha256)`` specs independently: one bad checkpoint never disables the others.

    Returns ``(models, failures)`` where ``failures`` maps the name to a stable reason code. A checkpoint equal to an
    already used one (including the pinned primary) is refused, so the comparison always has distinct models.
    """
    models, failures, used = [], {}, set(reserved_sha256)
    for name, path, sha256 in specs:
        if name in {m.name for m in models} or name in failures:
            failures[name] = "DUPLICATE_NAME"
            continue
        if sha256 in used:
            failures[name] = "DUPLICATE_CHECKPOINT"
            continue
        try:
            models.append(load_experimental(name, path, sha256, catalog))
            used.add(sha256)
        except ModelUnavailable as error:
            failures[name] = error.reason
        except Exception:
            failures[name] = "CHECKPOINT_INCOMPATIBLE"
    return models, failures
