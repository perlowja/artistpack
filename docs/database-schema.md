# ArtistPack PostgreSQL schema

PostgreSQL is the sole operational store for v0.1 — no Git-mirror registry
(see `docs/tech-decisions.md` for why that's deferred to Phase 2). UUIDs
internally; stable public slugs/IDs exist as separate columns because a
UUID is never a good public identifier (unguessable-but-meaningless vs.
the spec's own reverse-DNS-style `pack.id`/`artist.id`, which must be
human-chosen and stable — see `spec/artistpack-0.1.md` §3).

## Entities

```text
users                  -- OAuth-authenticated accounts; NOT the same as artists (spec §"one account may manage multiple artist identities")
oauth_accounts         -- provider + provider_user_id per user, supports multiple linked providers
artists                -- public artist profile; public_id = spec's artist.id
artist_links           -- website/patreon/socials, one row per link (not JSON) so they're individually queryable/validatable
packs                  -- pack shell; public_id = spec's pack.id
pack_versions          -- one row per published version; carries the generated manifest's own sha256 set
artworks               -- belongs to a pack_version (not to pack directly -- see note below)
artwork_variants       -- one row per resolution variant
tags
artwork_tags           -- join table
licenses               -- canonical license catalog (SPDX ids + the ArtistPack Display License)
feeds
feed_items             -- join: feed -> pack_version
provenance_records     -- one row per artwork's C2PA manifest: cert used, signed_at, verified_at, verification_status
publishing_jobs        -- async job tracking for the image pipeline (queued/running/failed/complete + error detail)
audit_log              -- append-only; FK'd from every mutating action below
```

**Why `artworks` belongs to `pack_versions`, not `packs` directly:** the
spec versions a pack as a whole (`pack.version`, semver), and an artwork's
metadata can change between versions without that being a new artwork
(re-titling, a corrected tag). Modeling artworks per-version means a
published `pack_version` is immutable and reproducible — re-fetching
`pack.yaml` for version `1.0.0` five years from now returns exactly what
was published, unaffected by later edits to version `1.1.0`. A `packs` row
is the mutable "current draft + version history" shell; a `pack_versions`
row is a frozen snapshot.

## Key columns

```sql
-- packs: mutable shell
packs (
  id            uuid primary key,
  public_id     text unique not null,   -- spec pack.id, e.g. org.artistpack.novaashworth.worlds
  artist_id     uuid not null references artists(id),
  current_draft_version_id uuid references pack_versions(id),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
)

-- pack_versions: immutable, one per published (or draft) version
pack_versions (
  id              uuid primary key,
  pack_id         uuid not null references packs(id),
  version         text not null,          -- semver, e.g. "1.0.0"
  manifest_sha256 text,                   -- generated column: hash of the canonical serialized manifest -- see note below
  status          text not null check (status in ('draft','pending_review','published','rejected','suspended')),
  published_at    timestamptz,            -- null while draft; set once, immutable after
  created_at      timestamptz not null default now(),
  unique (pack_id, version)
)

-- artworks: belongs to a specific pack_version
artworks (
  id                uuid primary key,
  pack_version_id   uuid not null references pack_versions(id),
  public_id         text not null,        -- spec artwork.id, unique within the pack version
  title             text not null,
  description       text,
  original_file     text not null,
  original_sha256   text not null,
  width             integer not null,
  height            integer not null,
  mime_type         text not null,
  orientation       text not null,        -- derived at ingest: 'landscape'|'portrait'|'square' (docs/api-design.md filters)
  aspect_ratio      text not null,        -- derived at ingest, e.g. '16:9'
  license_id        uuid references licenses(id),   -- null = inherits pack-level rights
  attribution_name  text not null,
  attribution_url   text,
  unique (pack_version_id, public_id)
)

provenance_records (
  id             uuid primary key,
  artwork_id     uuid not null references artworks(id),
  manifest_file  text not null,           -- storage key, not a DB blob -- see docs/architecture.md storage layer
  signed_by      text not null,           -- 'artist-provided' | 'artistpack-signing-service'
  signed_at      timestamptz not null,
  verified_at    timestamptz,
  verification_status text not null check (verification_status in ('pending','verified','failed')),
  unique (artwork_id)                     -- one active provenance record per artwork; re-signing creates a new artwork row via a new pack_version, not a mutated record
)

audit_log (
  id           uuid primary key,
  actor_user_id uuid references users(id),
  action       text not null,             -- e.g. 'pack.publish', 'pack.suspend', 'artwork.upload'
  target_type  text not null,
  target_id    uuid not null,
  detail       jsonb,
  created_at   timestamptz not null default now()
)
```

**`manifest_sha256` as a generated column, not a hand-maintained field:**
this is the guard called out in `docs/architecture.md`'s design record —
a `pack_versions` row must never silently drift from the YAML it
represents. Computed via a trigger that re-serializes the canonical
manifest on any change to the version or its artworks and stores the
resulting hash; a mismatch between this column and the actual served
`pack.yaml` is a bug to alert on, not a state that should ever be able to
occur silently.

**Why `provenance_records` is `unique (artwork_id)` rather than allowing a
history:** the spec treats an artwork's provenance as belonging to a
specific, immutable `pack_version` snapshot (see above) — if the artwork
needs re-signing, that happens as part of cutting a new pack version, which
creates a new `artworks` row (new `pack_version_id`), not by mutating the
provenance of an already-published, already-hashed version.

## Indexes worth calling out now (not exhaustive)

- `artists(public_id)`, `packs(public_id)` — unique, these are the join
  keys the whole public API filters on.
- `artworks(pack_version_id, orientation, aspect_ratio)` — composite,
  backs the `docs/api-design.md` filter set directly.
- `pack_versions(status, published_at)` — backs "recently published"
  feed generation without a full table scan.
- Full-text index (`tsvector`) over `packs.title`/`description` and
  `artworks.title`/`description`/tags for `GET /api/v1/search`.

## What's deliberately NOT in this schema yet

Signature/Sigstore key material, feed-level Git mirroring tables, and
multi-tenant organization support are all Phase 2/3 per
`docs/mvp-plan.md` — adding their tables now would be schema speculation
ahead of a design that doesn't exist yet.
