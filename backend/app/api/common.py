"""Common HTTP helpers: ETag, Cache-Control, link/manifest URL builders."""

from __future__ import annotations

import hashlib

from fastapi import Response


def weak_etag(body: bytes | str) -> str:
    """Compute a weak ETag (W/) for the given body.

    ``docs/api-design.md`` §Caching: public GET endpoints set
    ``ETag`` (hash of the response body) and honor ``If-None-Match``.
    Weak ETag is correct here because byte-level equivalence is
    semantically what we mean — two equivalent JSON serializations
    should match.
    """

    if isinstance(body, str):
        body = body.encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()[:32]
    return f'W/"{digest}"'


def apply_cache(response: Response, body: bytes | str, *, max_age: int) -> str:
    """Compute the ETag, set Cache-Control + ETag on ``response``, return the ETag.

    ``docs/api-design.md``: list endpoints set ``max-age=60`` (short —
    feeds change); individual pack/artist/artwork objects set
    ``max-age=300`` once published.
    """

    etag = weak_etag(body)
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = f"public, max-age={max_age}"
    return etag


def cached_response_or_304(
    body: bytes,
    *,
    max_age: int,
    if_none_match: str | None,
):
    """Return either a ``Response(status_code=304)`` or the body bytes.

    Sets ``ETag`` and ``Cache-Control`` headers in both cases. Used by
    the public GET endpoints to honor ``If-None-Match`` per
    ``docs/api-design.md`` §Caching.
    """

    etag = weak_etag(body)
    if if_none_match:
        # Accept either ``W/"..."`` or ``"..."`` form.
        for raw in if_none_match.split(","):
            candidate = raw.strip()
            if candidate == "*" or candidate == etag or candidate == etag.removeprefix("W/"):
                return Response(
                    status_code=304,
                    content=b"",
                    headers={"ETag": etag, "Cache-Control": f"public, max-age={max_age}"},
                )
    return Response(
        status_code=200,
        content=body,
        media_type="application/json",
        headers={"ETag": etag, "Cache-Control": f"public, max-age={max_age}"},
    )


def artist_manifest_url(base_url: str, public_id: str) -> str:
    return f"{base_url.rstrip('/')}/artists/{public_id}/artist.yaml"


def pack_manifest_url(base_url: str, artist_public_id: str, pack_public_id: str) -> str:
    return f"{base_url.rstrip('/')}/packs/{artist_public_id}/{pack_public_id}/pack.yaml"


def artwork_url(base_url: str, artwork_id: str) -> str:
    return f"{base_url.rstrip('/')}/artworks/{artwork_id}"


def feed_manifest_url(base_url: str, public_id: str) -> str:
    return f"{base_url.rstrip('/')}/feeds/{public_id}/feed.yaml"


__all__ = [
    "weak_etag",
    "apply_cache",
    "cached_response_or_304",
    "artist_manifest_url",
    "pack_manifest_url",
    "artwork_url",
    "feed_manifest_url",
]

