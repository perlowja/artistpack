"""``/api/v1`` route package."""

from app.api.v1 import artists, auth, feeds, moderation, packs, search

__all__ = [
    "artists",
    "auth",
    "feeds",
    "moderation",
    "packs",
    "search",
]
