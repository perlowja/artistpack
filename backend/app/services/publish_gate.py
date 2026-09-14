"""The publish gate — see ``docs/api-design.md`` §"`POST .../publish` — the gate".

The doc specifies four checks:

    1. The generated manifest passes ``schema/pack.schema.json``.
    2. Every artwork's ``provenance.c2pa`` is ``true`` with a verified signature.
    3. ``rights.license`` is a recognized value.
    4. Every artwork has non-empty ``attribution.display_name``.

In this MVP implementation:

* Check 1 — **real**: ``app.services.schema_validate.validate_pack_manifest``.
* Check 2 — **partial**: for MVP we check that every artwork has a
  ``provenance_records`` row with ``verification_status == 'verified'``.
  Actual C2PA **signature verification** is **Task 9 per ``docs/mvp-plan.md``
  and is explicitly out of scope here** — see the task brief. The signing
  service and trust-list application live elsewhere; what this gate
  enforces is "the row exists with the right status", which is exactly
  the contract the artist-facing ``POST .../provenance/sign`` endpoint
  (also Task 9) would populate.
* Check 3 — **real**: against the ``licenses`` table.
* Check 4 — **real**: empty ``attribution.display_name`` per-artwork.

The function returns a list of ``{"path", "message"}`` errors; the
caller maps them to a 422 with ``details.errors`` per the doc.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    License,
    Pack,
    PackVersion,
    ProvenanceVerificationStatus,
)
from app.services.licenses import is_recognized_license_id
from app.services.schema_validate import validate_pack_manifest


async def check_pack_publishable(
    session: AsyncSession, pack: Pack, pack_version: PackVersion
) -> list[dict[str, str]]:
    """Return a list of publish-gate errors; empty list means pass."""

    # Defensive: the pack must match the version's pack.
    if pack_version.pack_id != pack.id:
        return [{"path": "pack", "message": "pack_version.pack_id mismatch with pack.id"}]

    # Refresh to ensure relationships are loaded.
    await session.refresh(pack, attribute_names=["artist"])
    await session.refresh(pack_version, attribute_names=["artworks"])
    for art in pack_version.artworks:
        await session.refresh(art, attribute_names=["variants", "provenance"])

    manifest = pack_version.manifest

    errors: list[dict[str, str]] = []

    # ---- Check 1: structural validation -------------------------------------
    schema_errors = await asyncio.to_thread(validate_pack_manifest, manifest)
    for e in schema_errors:
        errors.append(
            {
                "path": f"manifest.{e['path']}",
                "message": f"schema validation: {e['message']}",
            }
        )

    # ---- Check 3: rights.license is recognized ------------------------------
    rights_license = (manifest.get("rights") or {}).get("license")
    if not rights_license or not is_recognized_license_id(rights_license):
        errors.append(
            {
                "path": "rights.license",
                "message": f"unrecognized license {rights_license!r}; "
                "publish gate accepts SPDX ids or artistpack-display-license-1.0",
            }
        )
    # Also: a pack_version that overrides rights per-artwork via the
    # License catalog should keep that license in the catalog. We check
    # the DB-bound rows here as the secondary guard.
    override_license_ids = {
        art.license_id for art in pack_version.artworks if art.license_id is not None
    }
    if override_license_ids:
        rows = (
            await session.execute(
                select(License.spdx_or_custom_id).where(License.id.in_(override_license_ids))
            )
        ).all()
        for spdx_id, in rows:
            if not is_recognized_license_id(spdx_id):
                errors.append(
                    {
                        "path": "artworks[].license",
                        "message": f"artwork override license {spdx_id!r} is not in the catalog",
                    }
                )

    # ---- Check 4: every artwork has non-empty attribution.display_name -----
    for art in pack_version.artworks:
        if not (art.attribution_name or "").strip():
            errors.append(
                {
                    "path": f"artworks[{art.public_id}].attribution.display_name",
                    "message": "attribution.display_name must be non-empty",
                }
            )

    # ---- Check 2: every artwork has verified provenance ---------------------
    # **Boundary:** real C2PA signature verification is Task 9. Here we
    # check the row exists with verification_status == 'verified' — which
    # is the *contract* the signing service must satisfy. A draft pack
    # with no provenance records will fail here until the artist runs
    # ``POST .../provenance/sign`` (also Task 9, not yet implemented).
    for art in pack_version.artworks:
        prov = art.provenance
        if prov is None:
            errors.append(
                {
                    "path": f"artworks[{art.public_id}].provenance.c2pa",
                    "message": "no provenance_records row attached; sign via "
                    "POST .../provenance/sign (Task 9) before publishing",
                }
            )
            continue
        if prov.verification_status != ProvenanceVerificationStatus.verified:
            errors.append(
                {
                    "path": f"artworks[{art.public_id}].provenance.verification_status",
                    "message": (
                        f"provenance_records.verification_status is "
                        f"{prov.verification_status.value!r}, expected 'verified'"
                    ),
                }
            )

    return errors


__all__ = ["check_pack_publishable"]
