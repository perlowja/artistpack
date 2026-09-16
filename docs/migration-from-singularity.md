# Migration from Singularity's existing Artist Pack mechanism

This document is grounded in the actual current implementation, read
directly rather than assumed from the product brief's "treat it as prior
art" instruction. Source files, as of 2026-09-13:

- `singularity-shell/src/core/artist_pack_manager.vala` — the manager
  class itself.
- `singularity-shell/src/components/sidebar/pages/desktop_page.vala` —
  Desktop settings UI integration.
- `singularity-ocs/docs/superpowers/specs/2026-09-04-wallpaper-pack-browser-ocs-design.md`
  — the design spec for the OCS browse/import + curated-pack-catalog UI
  built on top of this manager.

## What actually exists today

**Curated packs are `.deb` packages, not manifests.** A "curated Artist
Pack" is a Debian package (`ncz-wallpapers-<id>`), distributed via an apt
repository from a trusted-source allowlist
(`dev.sinty.desktop.artist-pack-apt-sources`, a GSettings key), installed
via `pkexec` + PolicyKit calling a fixed-path root helper
(`ncz-wallpaper-pack-install`). Inventory comes from a second fixed-path
helper (`ncz-wallpaper-pack-inventory`) that returns a JSON array of
`{package, title, summary, version, source, installed}` — **metadata at
the package level only.** There is no per-image title, description, tags,
rights, attribution, or provenance anywhere in this path. A pack's
"artist" is whatever string a human put in the package's summary/catalog
entry; nothing enforces it, validates it, or links it to anything
verifiable.

**A second, newer, looser mechanism exists for OCS imports**, unrelated to
the apt path: one-click imports from the OCS (Open Collaboration Services)
browser write a `pack.json` per imported item under
`~/.local/share/backgrounds/<id>/`, carrying `origin: "ocs"` and
best-effort provenance (uploader, provider, and a license string that is
frequently absent — the OCS design doc explicitly treats "no license
stated" as a distinct, honestly-labeled state rather than defaulting to
an empty/misleading value). This is closer in spirit to a real manifest
than the apt path, but it is ad hoc, not schema-validated, and not the
shape this specification defines.

**A `.pack.json` migration was already anticipated and explicitly
deferred** in Singularity's own design doc — `.collection` stays
authoritative there for now. This project's `pack.yaml` is not the same
thing as that anticipated `.pack.json`, but it answers the same felt need
from inside the Singularity codebase, which is a useful signal that this
gap was visible from both directions independently.

**No C2PA. No mandatory per-image license/attribution.** Confirmed by
reading the code, not assumed — this is the concrete gap that justified
making C2PA mandatory in `docs/architecture.md` rather than accepting the
brief's original "don't block launch on it" MVP guidance: generalizing
what Singularity has today, without improving it, would ship a spec no
better than what already exists.

## Migration mechanics (concrete, not aspirational)

### 1. Curated packs: generate a real manifest at build time

`build/build-wallpaper-contrib-deb.sh` (in `cix-installer`, not this
repository) already builds the `.deb` and, per the OCS design doc's own
recommendation, is expected to generate a `catalog.json` alongside it.
Add one step: **generate a real `pack.yaml`** (sha256 each bundled image,
populate `rights`/`attribution` from whatever structured data the build
already has) and route every artwork through the C2PA signing gate
(`docs/architecture.md`) before that step completes. Bundle the resulting
manifest inside the `.deb` at `/usr/share/ncz-wallpapers/<id>/pack.yaml`.

The manifest becomes the source of truth; the `.deb` and `catalog.json`
become derived artifacts generated from it, not independent formats to
keep in sync by hand. This is additive to the existing pipeline — nothing
about the apt distribution mechanism, the PolicyKit install flow, or the
existing `ArtistPackManager` class needs to change for this step alone.

### 2. OCS imports: point the newest format at the real schema

The OCS import pipeline's `pack.json` writer is the newest and least
entrenched of the two existing formats — the cheapest place to adopt the
real spec first, with the smallest blast radius if something needs
adjusting. Change it to write a schema-valid `pack.yaml` (single-artwork
pack is a legal, if minimal, `pack.yaml` per `spec/artistpack-0.1.md`)
instead of its current ad hoc shape, and route it through the same C2PA
gate — OCS-sourced content, given its already-weaker license provenance
("no license stated" is common per the design doc's own finding), is
exactly the content where a real provenance record adds the most value.

### 3. Feed-sourced packs install as real `.deb`s too (operator decision, 2026-09-16)

**Reverses the "no `.deb`, no apt repository at all" framing below** — kept
struck-through rather than deleted so the reasoning that got superseded is
still visible. Real, current decision: feed-sourced (self-hosted or
artistpack.org-centralized) packs ship as real `.deb` packages and install
through the same apt+PolicyKit mechanism as curated packs, not through a
parallel raw-file cache. Rationale: reuse the solved integrity/removal/
dependency semantics dpkg already provides rather than reinventing them in
a bespoke cache layer — "for sanity," in the operator's own words.

**Two distribution paths, one shared build mechanism — the client never
builds anything.** (operator, 2026-09-16, refining the above same day)

1. **Centralized**: artistpack.org's own backend builds a real `.deb` for
   every pack published to its registry, at publish time, and serves it
   alongside `pack.yaml` in the feed/registry response.
2. **Artist self-distribution**: an artist hosts their OWN pack
   independently of artistpack.org — no registry, no publish gate, no
   dependency on artistpack.org's existence (the same "zero dependency"
   property `docs/architecture.md`'s trust-boundary diagram already
   requires of the format itself, extended here to the install artifact).
   They build and host their own `.deb` the same way the centralized
   backend does.

**Both paths use the SAME build tool** — turning a validated `pack.yaml` +
its assets into a real, correctly-formed `.deb` (sha256-verified images,
the manifest bundled inside the package, a `.collection` file written,
porting the approach `cix-installer`'s
`build/build-wallpaper-contrib-deb.sh` already uses for NCZ's curated
packs). That tool belongs in this repo (`sdk/` or a new `artistpack
build-deb pack.yaml` CLI subcommand), not buried inside `cix-installer` —
it has to be usable standalone by a self-hosting artist who has never
heard of NCZ-OS, per the same self-hosting requirement that governs the
manifest format itself. `cix-installer`'s own script becomes (eventually)
a thin caller of this shared tool for NCZ's own curated packs, rather than
a second, divergent implementation.

The client (Singularity or any OS integration) never builds a `.deb`
itself in either path — it always just fetches one (from either source)
and installs it, same as it already does for curated packs today. This is
the "idempotent config" a distro needs: point at a feed URL, whichever of
the two paths produced it, and the client-side install mechanism is
identical either way.

**Status correction, live-verified 2026-09-16 (not assumed from this
doc's own 09-13 claim):** `ArtistPackManager` and the
`dev.sinty.desktop.artist-pack-apt-sources` GSettings key described above
as "already exists, solved problem" **no longer exist anywhere in current
`singularity-shell`** — a fresh clone + full-tree grep found zero hits.
They were superseded in the 3 days since this doc was written by the
wallpaper source-selector refactor (PR #25, merged) and the still-open OCS
browser PR #26 (`wallpaper_ocs.vala`, `wallpaper_provider.vala`) — both
HTTP/file-cache based, no apt/pkexec install path. **This means Task 11's
"extend the existing apt-based backend" premise needs re-verification
against whatever mechanism singularity-shell settles on
next** — either reviving an apt-install path (matching this section's
`.deb`-for-sanity decision) or wiring `.deb` install into the newer
OCS/provider architecture. Confirm the real current shape before writing
Task 11's client-side code; do not assume `artist_pack_manager.vala` is
there to extend.

~~The natural extension is a **second backend**, using the ArtistPack Rust~~
~~SDK to fetch, verify, and cache packs from an ArtistPack.org feed URL,~~
~~laid out under the same `~/.local/share/backgrounds/<id>/` + `.collection`~~
~~convention the wallpaper grid already reads (`docs/architecture.md`'s~~
~~"first reference consumer" principle). ... The new feed-based backend is~~
~~how third-party, non-NCZ artists reach Singularity users without needing~~
~~to be packaged into a `.deb` and pushed through an apt repository at~~
~~all.~~ This is Task 11 in `docs/mvp-plan.md`, scoped after the
backend/SDK exist (SDK now done, see `docs/mvp-plan.md`).

## What does NOT change as part of this migration

- The apt-based install flow, its PolicyKit policy, and its fixed-path
  privilege-escalation guard (`docs/security-model.md`) stay exactly as
  they are — they're a solved problem for on-distro curated content, not
  something this migration has any reason to touch.
- Nothing about this migration requires Singularity to depend on
  artistpack.org's availability — the feed-based backend consumes plain
  HTTP/YAML per `docs/architecture.md`'s self-hosting requirement, same as
  any other ArtistPack client.

## Open item, not yet resolved

Whether already-published curated packs need to be rebuilt/re-signed
retroactively once C2PA becomes mandatory, or whether the requirement only
binds going forward from the first build that includes step 1 above, is a
non-issue in practice: **nothing has been published to artistpack.org
yet** — this repository predates any real registry existing. There is no
backfill gap because there is nothing yet to backfill.
