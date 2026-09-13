# ArtistPack REST API — v1 design

Backend: FastAPI (see `docs/tech-decisions.md` for why). REST, not GraphQL
— nothing about this API's access patterns (list/filter/paginate a handful
of resource types) benefits from GraphQL's flexibility enough to justify
its added client and server complexity.

## Conventions

- Base path: `/api/v1`.
- Pagination: **cursor-based**, not offset. Every list endpoint accepts
  `?cursor=` and `?limit=` (default 25, max 100) and returns
  `{"items": [...], "next_cursor": "..."|null}`. Offset pagination drifts
  under concurrent writes on a feed that's actively growing; cursor
  pagination doesn't.
- Every pack/artist/feed object in a response includes its own canonical
  manifest URL (`manifest_url` field) — per the source doc's explicit
  requirement that API responses must let a client jump straight to the
  authoritative YAML.
- Errors: `{"error": {"code": "...", "message": "...", "details": {...}}}`,
  HTTP status matches the error class (400 validation, 401/403 auth,
  404 not found, 409 conflict, 422 semantic validation e.g. schema-valid
  but fails a publish-policy gate).
- All timestamps ISO-8601 UTC.

## Public endpoints (no auth required)

```text
GET /api/v1/artists
GET /api/v1/artists/{artist_id}
GET /api/v1/artists/{artist_id}/packs

GET /api/v1/packs
GET /api/v1/packs/{pack_id}

GET /api/v1/artworks/{artwork_id}

GET /api/v1/feeds
GET /api/v1/feeds/{feed_id}

GET /api/v1/search
```

### Filters (query params, apply to the relevant list endpoints)

```text
artist, tag, category, orientation, aspect_ratio, resolution, license,
updated_since
```

`orientation` and `aspect_ratio` are derived server-side from each
artwork's `original.width`/`height` at ingest time (stored, not computed
per-request) so filtering doesn't require decoding every artwork's
manifest on every search.

### `GET /api/v1/search`

Free-text query (`?q=`) plus any of the filters above. Backed by
PostgreSQL full-text search for MVP — no separate search infrastructure
until query volume or relevance needs justify one (YAGNI, matches the
doc's own instruction not to over-build ahead of real usage).

## Authenticated endpoints (artist dashboard)

```text
POST   /api/v1/auth/oauth/{provider}/callback     # google | github
GET    /api/v1/me
PATCH  /api/v1/me

POST   /api/v1/artists                            # create artist profile
PATCH  /api/v1/artists/{artist_id}
POST   /api/v1/artists/{artist_id}/avatar

POST   /api/v1/packs                              # create draft pack
PATCH  /api/v1/packs/{pack_id}
DELETE /api/v1/packs/{pack_id}                     # only while draft
POST   /api/v1/packs/{pack_id}/publish             # the C2PA + validation gate lives here
POST   /api/v1/packs/{pack_id}/unpublish

POST   /api/v1/packs/{pack_id}/artworks             # upload artwork (multipart)
PATCH  /api/v1/packs/{pack_id}/artworks/{artwork_id}
DELETE /api/v1/packs/{pack_id}/artworks/{artwork_id}
POST   /api/v1/packs/{pack_id}/artworks/{artwork_id}/regenerate-derivatives
POST   /api/v1/packs/{pack_id}/artworks/{artwork_id}/provenance/sign  # artist-gated C2PA step, docs/architecture.md

GET    /api/v1/packs/{pack_id}/validation           # current validation-error list for the dashboard
```

### `POST /api/v1/packs/{pack_id}/publish` — the gate

This is where `docs/architecture.md`'s two-tier validation becomes code.
Request succeeds (200) only when:

1. The generated manifest passes `schema/pack.schema.json` (structural).
2. Every artwork's `provenance.c2pa` is `true` with a verified signature —
   either the artist's own preserved/extended credentials or one produced
   by `POST .../provenance/sign` (policy, artistpack.org-specific).
3. `rights.license` is a recognized value (standard SPDX id or the
   ArtistPack Display License string).
4. Every artwork has non-empty `attribution.display_name`.

A failed publish returns 422 with a `details.errors[]` list mirroring what
`GET .../validation` already showed the artist in the dashboard — the
artist should never see a publish failure they weren't already warned
about.

## Moderation/admin endpoints

```text
GET    /api/v1/admin/reports
POST   /api/v1/admin/packs/{pack_id}/suspend
POST   /api/v1/admin/packs/{pack_id}/reinstate
GET    /api/v1/admin/audit-log
```

Restricted to `moderator`/`administrator` roles (`docs/database-schema.md`
§`users.role`). Content removal never deletes the underlying audit trail —
see `docs/architecture.md`'s moderation principle (source doc §28).

## Caching

Public GET endpoints set `ETag` (hash of the response body) and honor
`If-None-Match`; list endpoints additionally set
`Cache-Control: public, max-age=60` (short — feeds change) while
individual pack/artist/artwork objects use `max-age=300` once published
(publishing itself invalidates via a version-bump in `manifest_url`, not
cache-busting headers).
