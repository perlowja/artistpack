# ArtistPack

An open distribution standard for independent digital artists. Artists
publish once and make selected artwork discoverable as desktop and
lock-screen imagery across Linux, macOS, Windows, and other environments —
while preserving attribution, licensing, and a verifiable, signed chain of
provenance back to the creator.

> Artists provide the art. We provide the distribution. The artist gets the
> audience.

Think RSS for visual artists, delivered directly to operating-system
desktops — not another anonymous wallpaper scraper or centralized content
silo.

## What this is not

Not an NFT platform, not an AI image generator or detector, not an ad
network, not a stock-photo marketplace, not a social network, not an image
scraper, not DRM, not blockchain. See `docs/architecture.md` for the full
non-goals list and the reasoning behind each.

## Repository layout

```text
spec/           ArtistPack format specification (versioned, OS-neutral)
schema/         JSON Schema for artist.yaml / pack.yaml / feed.yaml
web/            artistpack.org backend (FastAPI) + frontend (Next.js)
registry/       Discovery API / feed generation
sdk/            Canonical Rust SDK (parse, validate, verify, cache)
cli/            `artistpack` command-line tool, built on the SDK
clients/        Desktop rotator + OS integrations (Singularity, GNOME, KDE, …)
docs/           Architecture, API design, DB schema, security model, MVP plan
examples/       Fixture packs/artists/feeds for tests and documentation
tests/          Cross-component fixtures and integration tests
infrastructure/ Deployment / CI / database migration definitions
```

## Status

Pre-MVP. Specification and schema are being drafted first; no code has been
written yet. See `docs/mvp-plan.md` for the build order and
`docs/superpowers/specs/2026-09-13-artistpack-org-design.md` for the full
design record.

## License

Code is licensed under Apache-2.0 (`LICENSE`). **Artwork contributed to or
distributed through ArtistPack is never covered by the code license** — see
`ARTWORK-LICENSES.md`. This distinction is deliberate and non-negotiable.

## First reference consumer

[Singularity](https://github.com/singularityos-lab) (the desktop environment
used by NCZ-OS) already ships a simpler, apt-package-based Artist Pack
mechanism. ArtistPack generalizes that concept; Singularity becomes the
first reference consumer of the resulting spec, not its owner. See
`docs/migration-from-singularity.md`.
