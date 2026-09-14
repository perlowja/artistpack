"""Initial license catalog seed.

The doc says the ``licenses`` table holds the canonical SPDX ids plus
the ArtistPack Display License string. This module is the seed invoked
at startup (and in tests) to populate the canonical catalog.

The list is deliberately short and curated — adding SPDX ids is a
deliberate act, not something that happens implicitly. The publish gate
verifies pack manifests against this catalog.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import License


# SPDX-style ids we accept on pack manifests as recognized licenses.
# The ArtistPack Display License is the project-specific custom id.
SEED_LICENSES: list[dict[str, object]] = [
    {
        "spdx_or_custom_id": "artistpack-display-license-1.0",
        "name": "ArtistPack Display License 1.0",
        "url": "https://artistpack.org/licenses/display-1.0",
        "is_custom": True,
    },
    {
        "spdx_or_custom_id": "CC0-1.0",
        "name": "Creative Commons Zero 1.0 Universal",
        "url": "https://spdx.org/licenses/CC0-1.0.html",
        "is_custom": False,
    },
    {
        "spdx_or_custom_id": "CC-BY-4.0",
        "name": "Creative Commons Attribution 4.0 International",
        "url": "https://spdx.org/licenses/CC-BY-4.0.html",
        "is_custom": False,
    },
    {
        "spdx_or_custom_id": "CC-BY-SA-4.0",
        "name": "Creative Commons Attribution-ShareAlike 4.0 International",
        "url": "https://spdx.org/licenses/CC-BY-SA-4.0.html",
        "is_custom": False,
    },
    {
        "spdx_or_custom_id": "CC-BY-NC-4.0",
        "name": "Creative Commons Attribution-NonCommercial 4.0 International",
        "url": "https://spdx.org/licenses/CC-BY-NC-4.0.html",
        "is_custom": False,
    },
    {
        "spdx_or_custom_id": "CC-BY-NC-SA-4.0",
        "name": "Creative Commons Attribution-NonCommercial-ShareAlike 4.0",
        "url": "https://spdx.org/licenses/CC-BY-NC-SA-4.0.html",
        "is_custom": False,
    },
]


async def seed_licenses(session: AsyncSession) -> None:
    existing = {
        row[0]
        for row in (await session.execute(select(License.spdx_or_custom_id))).all()
    }
    for entry in SEED_LICENSES:
        if entry["spdx_or_custom_id"] in existing:  # type: ignore[operator]
            continue
        session.add(License(**entry))  # type: ignore[arg-type]
    await session.commit()


def is_recognized_license_id(spdx_or_custom_id: str) -> bool:
    """Pure-Python check used by the publish gate before a DB round-trip."""

    return any(entry["spdx_or_custom_id"] == spdx_or_custom_id for entry in SEED_LICENSES)
