# ArtistPack Specification 0.1

**Status:** Draft. Format version `"0.1"`. This document defines the
ArtistPack manifest formats independent of artistpack.org or any other
implementation — see `docs/architecture.md` for why that independence is
architecturally load-bearing.

Normative JSON Schema for every format defined here lives in `schema/` and
is authoritative over this prose wherever the two disagree; this document
exists to explain *why* the schema is shaped the way it is.

## 1. Terminology

- **Artist** — the individual or organization who created and owns the
  artwork. Identified by a stable `artist.id`, never by display name.
- **Pack** — a versioned, titled collection of one or more artworks
  published together, described by a `pack.yaml` manifest.
- **Artwork** — a single piece of art within a pack, with its own
  metadata, rights, attribution, and provenance, independent of the pack's.
- **Variant** — a derivative of an artwork's original file at a specific
  resolution, generated for display.
- **Feed** — a list of pack URLs, described by a `feed.yaml` manifest,
  subscribable by clients.
- **Manifest** — any of the three YAML documents this spec defines
  (`artist.yaml`, `pack.yaml`, `feed.yaml`).
- **Registry** — a service (canonically artistpack.org, but not
  necessarily) that indexes and serves manifests it did not necessarily
  author.
- **Capability** — an optional behavior a manifest can declare via
  `requires:`, letting an older client fail clearly instead of
  misinterpreting new mandatory structure it doesn't understand (§8).

## 2. Format versioning

`artistpack: "0.1"` (or `artistpack_feed: "0.1"` in a feed manifest) is
required at the top of every manifest. Format version and pack version
(`pack.version`, e.g. `"1.2.0"`) are independent axes — bumping a pack's
own semver has nothing to do with which format major version it targets.

A compliant client **must** reject a manifest declaring a future major
format version it does not understand, and **should** attempt best-effort
parsing of a manifest declaring an older minor version within the same
major version, ignoring unknown optional fields per §8.

## 3. Identifiers

`pack.id`, `artist.id`, and `feed.id` are stable, reverse-DNS-style
strings (e.g. `org.artistpack.novaashworth.worlds`) chosen once and never
reused for different content. They are the only safe join key across
manifests, database rows, and deep links (§ Browser Protocol, deferred
past v0.1 but the ID shape is chosen with it in mind). Display names
(`pack.title`, `artist.name`) are mutable; identifiers are not.

## 4. `artist.yaml`

Describes an artist independent of any specific pack. See
`schema/artist.schema.json` for the normative shape;
`examples/full/artist.yaml` for a complete example.

Required top-level fields: `artistpack` (format version), `artist.id`,
`artist.name`. Everything else — `bio`, `avatar`, `website`, `support.*`,
`socials.*`, `packs` (a list of pack manifest URLs this artist publishes)
— is optional at the format level; an artistpack.org artist profile page
requires more of these fields to be *filled in*, but that's a registry
publish-policy decision (`docs/architecture.md` §Two-tier validation), not
a schema requirement.

## 5. `pack.yaml`

The core manifest. Required top-level sections: `artistpack`, `pack`,
`artist`, `rights`, `artworks` (a non-empty array).

### 5.1 `rights` (pack-level defaults)

```yaml
rights:
  copyright: "Copyright 2026 <name>"
  license: "artistpack-display-license-1.0"   # or an SPDX-style id, e.g. "CC-BY-4.0"
  attribution_required: true
```

Every artwork inherits these unless it declares its own `rights` block
(§5.2) — a pack may bundle artworks under different licenses, e.g. a
retrospective mixing `CC BY` pieces with pieces under the ArtistPack
Display License. `attribution_required: false` is legal (some open
licenses don't require it) but attribution metadata (§5.3) must still be
*present* in the manifest even when display of it isn't mandatory — a
client is always allowed to show it.

### 5.2 `artworks[]` — required per-artwork fields

This is the field set the existing Singularity Artist Pack mechanism does
not have today (it carries metadata at the pack level only — see
`docs/migration-from-singularity.md`), and is the reason this
specification exists rather than just reusing what shipped there.

```yaml
artworks:
  - id: "city-001"                    # required, stable within the pack
    title: "..."                      # required
    description: "..."                # optional
    original:                         # required
      file: "images/city-001.jpg"
      sha256: "..."                   # required — integrity floor, §7
      width: 7680
      height: 4320
      mime_type: "image/jpeg"
    variants: [ ... ]                 # required, non-empty — see §6
    tags: [ ... ]                     # optional
    rights: { ... }                   # optional — overrides pack-level rights (§5.1)
    attribution:                      # required
      display_name: "Nova Ashworth"
      url: "https://..."
    provenance:                       # required — see §9, never optional
      c2pa: true
      manifest_file: "provenance/city-001.c2pa"
    display:                          # optional
      crop_mode: "smart"              # "smart" | "center" | "none"
      focal_point: { x: 0.5, y: 0.5 }
      allow_crop: true
      allow_scale: true
    accessibility:                    # optional, but strongly encouraged
      alt_text: "..."
```

`attribution` is required per-artwork (not just per-pack) because a pack
mixing multiple contributing artists — a curated collection, a
collaboration — must not let a client fall back to the pack's own
`artist` block for an artwork that has a different actual creator. Most
single-artist packs will simply repeat the same `attribution` on every
artwork; that repetition is the cost of correctness for the mixed case.

### 5.3 `compatibility`

```yaml
compatibility:
  wallpaper: true
  lock_screen: true
```

Declares which display surfaces the pack's `display` hints were designed
for. Optional; absence means "assume wallpaper only."

## 6. Variants and resolution strategy

Every artwork must declare at least one `variants[]` entry in addition to
its `original`. A variant carries the same shape as `original` minus
`mime_type` (inherited). Recommended baseline resolution set: `1920x1080`,
`2560x1440`, `3440x1440`, `3840x2160`, `5120x2880`, plus the 16:10 set
(`2560x1600`, `2880x1800`, `3840x2400`) where the source supports it.
Publishers must never upscale — a variant's dimensions must not exceed
`original`'s. Clients select the smallest variant that is greater than or
equal to their target resolution; if none qualifies, they fall back to
`original` and scale/crop locally per the artwork's `display` hints.
Images are never stretched to fit — `display.crop_mode` governs how a
mismatched aspect ratio is resolved, never a non-uniform scale.

## 7. Integrity

Every `original` and every `variants[]` entry requires `sha256`. A client
**must** verify the hash of any downloaded file against the manifest
before treating it as valid, independent of whether the manifest itself
came from a source the client already trusts (§ SDK responsibilities,
`docs/architecture.md`). Manifest-level and feed-level signing
(Sigstore/minisign/Ed25519) is out of scope for v0.1; the schema is
designed so a `signature:` block can be added to any manifest in a future
minor version without breaking v0.1 parsers (§8).

## 8. Capability negotiation and forward compatibility

```yaml
requires:
  - artistpack.wallpaper
  - artistpack.provenance.c2pa
```

An optional top-level array on `pack.yaml`. A client that does not
recognize an entry in `requires:` **must** refuse to fully process that
pack and **should** tell the user why, rather than silently degrading.
Unknown fields *outside* `requires:` (i.e. ordinary schema extensions)
must always be ignored by parsers, never treated as an error — this is
what lets the format add new optional structure across minor versions
without breaking every existing client. `artistpack.provenance.c2pa` is
listed here as an example of a *future* optional capability string, for
packs that want to advertise something a client might not understand yet
— it is not how v0.1 expresses its own mandatory C2PA requirement, which
is a registry publish-policy matter (`docs/architecture.md`), not a
format-level capability flag.

## 9. Provenance — mandatory field, policy-gated requirement

The `provenance` object (§5.2) is a **required** field in every artwork
entry at the schema level — a manifest missing it is not valid v0.1. What
varies by policy, not by schema, is whether `provenance.c2pa` is
`true` with a real, signature-valid `manifest_file`, versus a
placeholder pending signing. artistpack.org's publish gate requires the
former (`docs/architecture.md` §"C2PA: mandatory, artist-gated"); a
self-hosted pack that never intends to register with any public registry
is schema-valid either way, but any client that surfaces "verified
provenance" UI must check the actual signature, never just the presence
of the field.

## 10. `feed.yaml`

```yaml
artistpack_feed: "0.1"
feed:
  id: "org.artistpack.featured"
  title: "ArtistPack Featured"
  description: "Featured independent artists."
  updated: "2026-09-13T18:00:00Z"
packs:
  - url: "https://artistpack.org/packs/nova-ashworth/worlds/pack.yaml"
```

Feeds are plain lists of pack URLs, independent of artistpack.org — any
site can publish `artistpack-feed.yaml` and any compliant client can
subscribe to it (`docs/architecture.md`'s self-hosting requirement applies
identically to feeds). A feed's own `updated` timestamp lets a client
short-circuit re-fetching every referenced pack when nothing changed
(§ Feed Update Behavior, `docs/mvp-plan.md`).

## 11. Compatibility rule (post-1.0)

Once ArtistPack 1.0 ships, this format must not casually break. Unknown
optional fields are always ignored (§8); unknown required capabilities
always fail clearly (§8); a pack targeting a future major version is
rejected outright rather than partially misinterpreted (§2). Nothing in
v0.1 is final in the sense of "can never be extended" — it is final in the
sense that every extension must be additive.
