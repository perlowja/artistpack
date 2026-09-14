"""Canonical manifest serialization + SHA-256 recomputation.

Per ``docs/database-schema.md`` (and the design note it links):

    a ``pack_versions`` row must never silently drift from the YAML
    it represents

The hard guarantee in production is a Postgres trigger (see the
Alembic migration ``0001_initial.py``). Tests/dev on SQLite use the
same canonical serialization here, called from the application before
the row is committed, so the invariant holds regardless of backend.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _canonicalize(obj: Any) -> Any:
    """Produce the canonical manifest representation for hashing.

    * Sort keys at every object level so field ordering doesn't change
      the hash.
    * Drop ``None`` values so optional-omitted vs optional-explicit-null
      representations hash identically. The spec's JSON Schema already
      treats these as equivalent for required-optional fields.
    * Keep the structure nested (manifest is a dict, artworks is a list,
      etc.) — we hash the *content*, not a flattened bag.
    """

    if isinstance(obj, dict):
        return {
            k: _canonicalize(v)
            for k, v in sorted(obj.items())
            if v is not None
        }
    if isinstance(obj, list):
        return [_canonicalize(v) for v in obj]
    return obj


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    """Return the canonical serialized bytes (UTF-8 JSON) for ``manifest``."""

    canonical = _canonicalize(manifest)
    return json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,  # belt-and-suspenders: keys are already sorted above
        allow_nan=False,
    ).encode("utf-8")


def compute_manifest_sha256(manifest: dict[str, Any]) -> str:
    """Compute the SHA-256 of the canonical manifest bytes, lowercase hex."""

    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def recompute_and_set(pack_version) -> None:
    """Update ``pack_version.manifest_sha256`` from ``pack_version.manifest``.

    Callers should invoke this right before commit. Returns the value
    that was set so callers can assert it.
    """

    pack_version.manifest_sha256 = compute_manifest_sha256(pack_version.manifest)
    return pack_version.manifest_sha256
