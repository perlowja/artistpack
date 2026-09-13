# ArtistPack Architecture

## Purpose

ArtistPack is an open, operating-system-neutral distribution standard for
independent visual artists. It generalizes a simpler, apt-package-based
"Artist Pack" mechanism already shipping in Singularity (the NCZ-OS desktop
environment) into a format-first standard usable independently of any one
website, desktop environment, or vendor. See
`docs/migration-from-singularity.md` for exactly what exists today and how
it maps onto this design.

Core philosophy: *artists provide the art, ArtistPack provides the
distribution, the artist gets the audience.* Every architectural decision
below is a consequence of taking that sentence seriously — in particular,
the requirement that the artist's identity, licensing terms, and signed
provenance travel with the artwork through every layer, and that no layer
can silently drop them.

## Non-goals

ArtistPack is deliberately **not**: an NFT platform, an AI image generation
platform, an AI-generated-image detector, an ad network, a stock-photo
licensing marketplace, a social network, an image scraper, a centralized
requirement for using the file format, a DRM system, or a blockchain
project. No crypto/tokens/NFTs. No engagement-maximizing recommendation
algorithm. No automatic ingestion of images from other sites — every
artwork enters the system because an artist (or, for migrated NCZ-curated
content, the curation pipeline acting as a declared publisher) explicitly
uploaded it.

## The eight components

1. **ArtistPack Specification** (`spec/`) — the versioned manifest formats
   (`artist.yaml`, `pack.yaml`, `feed.yaml`). Must remain usable by anyone
   self-hosting a `pack.yaml` at a URL of their choosing, with zero
   dependency on artistpack.org's existence.
2. **ArtistPack Registry** (`registry/`) — the discovery/feed API
   artistpack.org exposes over its own published packs. A registry is a
   convenience layer over the spec, never a gatekeeper the spec depends on.
3. **ArtistPack.org Web Application** (`web/`) — the publishing interface
   (artist dashboard) and public browsing surface. This is the only layer
   allowed to enforce *policy* (e.g. "C2PA is required to publish here") on
   top of the *format*, which stays permissive — see "Two-tier validation"
   below.
4. **ArtistPack SDK** (`sdk/`) — canonical Rust implementation of
   parse/validate/verify/cache. Every other consumer (CLI, desktop clients,
   future language bindings) is built on this, not a reimplementation.
5. **Client Applications / OS Integrations** (`cli/`, `clients/`) — the
   desktop wallpaper rotator and OS-specific adapters (Singularity, GNOME,
   KDE, later macOS/Windows).
6. **Public Feeds** — plain HTTP/CDN-servable YAML/JSON, independent of
   artistpack.org's own infrastructure once published.
7. **Provenance / Signing** — C2PA Content Credentials, required (see
   below), plus future manifest/feed signing (Sigstore/minisign/Ed25519 —
   deferred past v0.1, SHA-256 hashing is the v0.1 integrity floor).
8. **Storage/CDN** — S3-compatible object storage behind an abstraction
   that also supports a local filesystem backend for development.

## Trust boundaries

```text
                          ┌─────────────────────────┐
                          │   artistpack.org (web)   │
                          │  policy: what's required │
                          │  to PUBLISH to registry   │
                          └────────────┬─────────────┘
                                       │ generates
                                       ▼
   artist's own site   ┌───────────────────────────────┐   registry mirrors/
   (self-hosted)  ────▶│   ArtistPack manifest (YAML)   │◀── indexes, never
   pack.yaml            │  format: spec/, schema/         │   the only path
                          └────────────┬─────────────────┘
                                       │ fetched + verified by
                                       ▼
                          ┌─────────────────────────┐
                          │   ArtistPack SDK (Rust)   │
                          │  hash + C2PA verification │
                          │  independent of the origin │
                          └────────────┬─────────────┘
                                       │
                                       ▼
                          ┌─────────────────────────┐
                          │  CLI / Desktop clients    │
                          └─────────────────────────┘
```

The load-bearing property: **a self-hosted `pack.yaml` that artistpack.org
has never seen must validate and display correctly in any compliant
client.** The SDK's verification logic must never special-case
artistpack.org's own URLs.

## Two-tier validation: format vs. registry policy

This is the single most important architectural decision in this design,
because it resolves what would otherwise be a contradiction: the *format*
must stay permissive enough for an artist to self-host a minimal pack (and
for the existing, C2PA-less, per-pack-only-metadata Singularity content to
have a real migration path — see `docs/migration-from-singularity.md`),
while artistpack.org's own registry must guarantee every artwork it lists
publicly carries verified attribution and signed provenance.

| Layer | Enforces | Example |
|---|---|---|
| **JSON Schema** (`schema/`) | Structural correctness only | `pack.id` is a required string; `rights` is a required object |
| **artistpack.org publish gate** (`web/`) | Product/trust policy | `provenance.c2pa` must be present and signature-valid before the Publish action succeeds |

A pack can be schema-valid and still be rejected by artistpack.org's
publish endpoint. This is intentional, not a bug: the schema defines what a
*compliant ArtistPack manifest looks like*, the registry defines what
*artistpack.org is willing to list publicly*. A self-hosted, non-registered
pack only ever has to satisfy the schema.

## C2PA: mandatory, artist-gated

C2PA provenance is **required to publish through artistpack.org**, and the
requirement is gated at the artist's own publish action, not injected
silently on their behalf:

- If the artist's original upload already carries valid Content
  Credentials, the pipeline verifies them and **extends** them with
  ArtistPack's own assertions (publishing source, timestamp, derivative
  hashes) — it never overwrites or discards an artist's existing
  credentials.
- If it doesn't, the artist is offered — and must explicitly accept —
  artistpack.org signing on their behalf. This is a visible, consented
  step in the dashboard (a validation error blocks Publish until it's
  satisfied), not a background operation the artist never sees.
- The same gate applies uniformly to system-curated content: the NCZ-OS
  build pipeline that generates `pack.yaml` for existing curated Singularity
  packs (`docs/migration-from-singularity.md`) acts as the "publishing
  artist" for that content and must pass the identical gate. There is no
  special-cased exemption for first-party content.
- C2PA proves *provenance assertions* (who published what, when, from what
  original hash). It does **not** prove or claim "this image is
  objectively human-made." An artist may separately assert
  `creation.artist_declares_human_created: true` in their manifest — that
  is an assertion the artist makes, not something C2PA or ArtistPack
  verifies. ArtistPack does not implement AI-detection scoring of any kind.
- For MVP, signing uses a self-issued ArtistPack certificate. Manifests
  signed this way are fully verifiable by the ArtistPack SDK (which trusts
  its own signing key as a first-party anchor) but will not yet validate
  against public, general-purpose C2PA verifiers (e.g. Content Credentials
  Verify) until ArtistPack applies for inclusion in a C2PA-conformant trust
  list — a Phase 3 item (`docs/mvp-plan.md`), not an MVP blocker.

## Data flow: an artwork's life cycle

```text
artist upload
    │  (MIME sniff, dimension/size caps, decompression-bomb guard)
    ▼
derivative generation (thumbnails, resolution set, SHA-256 per file)
    │
    ▼
C2PA signing gate  ──── blocks here until satisfied ────┐
    │ satisfied                                          │
    ▼                                                     │
manifest generation (pack.yaml / artist.yaml)             │
    │                                                     │
    ▼                                                     │
storage (S3-compatible; object keys mirror the manifest   │
    structure documented in docs/database-schema.md)      │
    │                                                     │
    ▼                                                     │
registry feed (generated, cursor-paginated)                │
    │                                                     │
    ▼                                                     │
client discovery → download → SDK verification ◀──────────┘
    │  (hash + C2PA check; independent of origin)
    ▼
wallpaper display + artist attribution surfaced in client UI
```

Never leave a pack partially installed on the client side: downloads land
in a staging directory and are atomically activated only after every hash
and signature check passes (`docs/mvp-plan.md`, SDK responsibilities).

## Governance of this document

Architectural or trust-boundary changes to this document require the same
review this design itself went through: see
`docs/superpowers/specs/2026-09-13-artistpack-org-design.md` for the full
decision record, including the alternatives considered and rejected for
each of the choices above.
