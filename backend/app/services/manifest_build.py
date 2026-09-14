"""Build the canonical manifest dict for a ``PackVersion``.

The dict shape returned here is what gets served as ``pack.yaml`` and
what ``schema/pack.schema.json`` is validated against. It must round-trip
through the SDK's ``Pack::from_yaml_str`` — see ``sdk/src/types.rs``.
"""

from __future__ import annotations

from typing import Any

from app.db.models import Artwork, Pack, PackVersion


def build_pack_manifest(pack: Pack, pack_version: PackVersion) -> dict[str, Any]:
    """Return the pack.yaml-shaped dict for ``pack_version``."""

    return {
        "artistpack": "0.1",
        "pack": {
            "id": pack.public_id,
            "title": pack.title,
            "version": pack_version.version,
            **({"description": pack.description} if pack.description else {}),
        },
        "artist": {
            "id": pack.artist.public_id,
            "name": pack.artist.name,
            **({"bio": pack.artist.bio} if pack.artist.bio else {}),
            **({"website": pack.artist.website} if pack.artist.website else {}),
        },
        "rights": {
            "copyright": f"Copyright {pack_version.created_at.year} {pack.artist.name}",
            "license": "artistpack-display-license-1.0",
            "attribution_required": True,
        },
        "artworks": [_artwork_entry(art) for art in pack_version.artworks],
    }


def _artwork_entry(art: Artwork) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": art.public_id,
        "title": art.title,
        **({"description": art.description} if art.description else {}),
        "original": {
            "file": art.original_file,
            "sha256": art.original_sha256,
            "width": art.width,
            "height": art.height,
            "mime_type": art.mime_type,
        },
        "variants": [
            {
                "file": v.file,
                "sha256": v.sha256,
                "width": v.width,
                "height": v.height,
                **({"mime_type": v.mime_type} if v.mime_type else {}),
            }
            for v in art.variants
        ],
        "attribution": {
            "display_name": art.attribution_name,
            **({"url": art.attribution_url} if art.attribution_url else {}),
        },
        "provenance": {
            "c2pa": art.provenance is not None,
            **(
                {"manifest_file": art.provenance.manifest_file}
                if art.provenance and art.provenance.manifest_file
                else {}
            ),
        },
    }
    return out
