"""Service-layer modules (manifest, schema validation, ingest, publish gate)."""

from app.services.ingest import (
    derive_aspect_ratio,
    derive_orientation,
    ingest_artwork,
    sniff_mime,
)
from app.services.licenses import (
    SEED_LICENSES,
    is_recognized_license_id,
    seed_licenses,
)
from app.services.manifest_build import build_pack_manifest
from app.services.manifest_hash import (
    canonical_manifest_bytes,
    compute_manifest_sha256,
    recompute_and_set,
)
from app.services.publish_gate import check_pack_publishable
from app.services.schema_validate import (
    validate_artist_manifest,
    validate_feed_manifest,
    validate_pack_manifest,
)
from app.services.yaml_io import yaml_dump, yaml_load

__all__ = [
    "build_pack_manifest",
    "compute_manifest_sha256",
    "canonical_manifest_bytes",
    "recompute_and_set",
    "validate_pack_manifest",
    "validate_artist_manifest",
    "validate_feed_manifest",
    "ingest_artwork",
    "sniff_mime",
    "derive_orientation",
    "derive_aspect_ratio",
    "check_pack_publishable",
    "seed_licenses",
    "SEED_LICENSES",
    "is_recognized_license_id",
    "yaml_dump",
    "yaml_load",
]
