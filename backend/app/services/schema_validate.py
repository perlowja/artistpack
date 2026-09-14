"""JSON-Schema validation of the manifest formats.

Loads ``schema/{pack,artist,feed}.schema.json`` from the repo root and
exposes thin ``validate_*`` wrappers that return a list of error
``{"path", "message"}`` dicts (the same shape the publish gate's 422
response uses). The schema files are the authoritative source per
``spec/artistpack-0.1.md`` §0 — they're never edited from this codebase.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from app.core.config import settings


@lru_cache(maxsize=1)
def _load_schema(name: str) -> dict[str, Any]:
    path: Path = settings.schema_dir / name
    if not path.exists():
        raise FileNotFoundError(
            f"Schema file not found at {path}. "
            "Set ARTISTPACK_SCHEMA_DIR or run from the repo root."
        )
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(_load_schema(name))


def _format_path(absolute_path) -> str:
    parts = [str(p) for p in list(absolute_path) if p != ""]
    if not parts:
        return "<root>"
    return ".".join(parts) if len(parts) > 1 else parts[0]


def _format_errors(errors) -> list[dict[str, str]]:
    return [{"path": _format_path(e.absolute_path), "message": e.message} for e in errors]


def validate_pack_manifest(manifest: dict[str, Any]) -> list[dict[str, str]]:
    """Validate ``manifest`` against ``schema/pack.schema.json``."""

    errors = sorted(_validator("pack.schema.json").iter_errors(manifest), key=lambda e: list(e.absolute_path))
    return _format_errors(errors)


def validate_artist_manifest(manifest: dict[str, Any]) -> list[dict[str, str]]:
    errors = sorted(_validator("artist.schema.json").iter_errors(manifest), key=lambda e: list(e.absolute_path))
    return _format_errors(errors)


def validate_feed_manifest(manifest: dict[str, Any]) -> list[dict[str, str]]:
    errors = sorted(_validator("feed.schema.json").iter_errors(manifest), key=lambda e: list(e.absolute_path))
    return _format_errors(errors)
