# ArtistPack package format — `.pak.gz`, not `.deb`

Draft for discussion with Mirko Brombin (singularityos-lab) — the "apt
config"/package-format piece referenced in
`docs/migration-from-singularity.md` section 3. Not yet implemented; this
document is the spec to review before writing the shared build tool.

**Naming note**: working name `.pak.gz` (ArtistPack), placeholder — needs a
real collision check against existing extensions before this lands
anywhere real.

## Why not `.deb`

The initial draft of this document specced a real `.deb` for Debian-family
Linux, reasoning that reusing dpkg's integrity/atomic-install/removal
semantics was "for sanity" cheaper than reinventing them, with the SDK's
own cache mechanism (`sdk/src/cache.rs`) covering everything else
(non-Debian Linux, eventually Windows/Mac).

That fell apart under two real objections raised in review:

1. **Windows and macOS don't use `.deb` either.** A "Debian-family gets
   `.deb`, everyone else gets something else" split was never actually
   heading toward one universal answer — it was heading toward at least
   three (`.deb`, a bare SDK-cache path, and eventually whatever
   Windows/macOS need), which is worse than picking one format and using
   it everywhere.
2. **The SDK already reimplements everything `.deb` was buying.**
   `cache.rs` already does streaming SHA-256 verify, staged→atomic-activate
   install, and clean replace-on-reinstall — tested, working, used
   regardless of platform. So "reuse dpkg to avoid reinventing atomic
   install" wasn't actually true; that work already exists and ships on
   every platform via the SDK. The only thing genuinely `.deb`-specific
   that would be lost is `dpkg -l`/apt discoverability — a real but small
   gap, cheaper to solve with a local index than to fork the whole
   packaging strategy over.

**Decision: one package format, used on every platform, including
NCZ-OS/Debian.** No per-OS packaging fork.

## Format: a single archive, same layout everywhere

`.pak.gz` is `tar.gz` of exactly this directory layout — no control/data
split, no maintainer scripts, no dpkg-specific machinery, because there's
nothing here that needs any of that (pure content, zero compiled code,
zero real dependency graph):

```
pack.yaml              # exact bytes as published
artist.yaml
artworks/
    <artwork.id>.<ext>                        # original
    <artwork.id>-<width>x<height>.<ext>        # each variant beyond original
c2pa/
    <artwork.id>.c2pa   # reserved for provenance.manifest_file content
                        # once Task 9 (C2PA signing gate) lands -- not
                        # populated yet, directory exists so the layout
                        # doesn't need a breaking change later
```

This is the exact payload a `.deb` would have carried under the previous
draft, just archived directly instead of wrapped in `ar`/`dpkg-deb`
framing that bought nothing here.

## Feed standard, modeled on apt's `Packages`/`Release` — not apt itself

Reuse and extend what's already built (`spec/artistpack-0.1.md`,
`schema/feed.schema.json`), rather than adopting apt's actual index
format wholesale. The load-bearing property to borrow from
`Packages`/`Release`: **the feed is a tamper-evident index of installable
artifacts, not just a list of manifest URLs to dereference and hope.**

Add to each feed entry:

- `pak_url` — where to fetch the archive
- `pak_sha256` — hash of the archive itself (in addition to the
  per-artwork hashes already inside `pack.yaml`, which the client
  re-verifies after extraction regardless — this is a fast pre-download
  integrity/corruption check, not a replacement for the per-file checks)
- `pak_size` — byte size, for progress/preflight

Signing (apt's `Release`→`InRelease` GPG model, equivalent here) stays
Phase Two per `docs/mvp-plan.md` ("stronger manifest/feed signing —
Sigstore/minisign/Ed25519") — SHA-256 is the v0.1 integrity floor per the
architecture doc; feed-level signing is a real, separate piece of work,
not bundled into this decision.

## Install mechanism — SDK, one new step in front of what already exists

1. Fetch `.pak.gz` (or use an already-cached copy if `pak_sha256` matches).
2. Verify `pak_sha256` against the downloaded archive (fast fail before
   spending time on extraction).
3. Extract to a staging directory.
4. **Everything from here is already built and tested** — run
   `hash.rs`'s per-artwork `verify` against every extracted file's
   declared `sha256` in `pack.yaml`, then `cache.rs`'s existing
   staging→atomic-activate flow (already handles clean
   reactivation/replace). No new verification or atomicity logic needed,
   only the extraction step in front of it.

## Discoverability — the one real gap `.deb` would have closed for free

No package-manager database exists to query, so the SDK needs its own
local index of installed packs: a flat JSON (or SQLite, if query needs
grow) file the cache maintains alongside the staged content —
`{pack_id, artist_id, version, installed_at, source_feed}` per entry.
Small, new, but bounded — this is the one piece of real net-new work this
decision adds versus the `.deb` draft, in exchange for not forking the
packaging strategy per OS.

## Build tool — same "who builds it" model as before

Unchanged from the previous draft: one shared tool (proposed `artistpack
build-pak <pack.yaml>` CLI subcommand, alongside the existing `validate`
one), usable either by artistpack.org's backend (centralized path) or by
an artist running it themselves (self-distribution path — the path
NCZ-OS's own existing pipeline is now framed as an instance of, per
`docs/migration-from-singularity.md` section 3, **unchanged, not touched
by this decision**: NCZ-OS keeps shipping its real `.deb`s through
`ncz-apt` exactly as it does today until this tool exists and
`build-wallpaper-contrib-deb.sh` is migrated to call it, at which point
NCZ-OS's own packages would also become `.pak.gz`s like everything else —
not before).

**Mandatory build-time integrity check** (unchanged from the previous
draft, still applies): the tool must recompute SHA-256 of every staged
artwork file and hard-fail on any mismatch against the manifest's
declared hash, before the archive is produced — the same check
`sdk/src/hash.rs::verify` does client-side, run server-side too so a
stale/tampered manifest can't ship.

## Open questions for Mirko

1. Real extension/name for `.pak.gz` — collision check needed.
2. Exact shape of the local installed-pack index (flat JSON vs SQLite) —
   depends on how `singularity-shell`'s eventual consumer wants to query
   it (a settings-page list, a `Provides`-style lookup, etc.) — worth
   designing together rather than guessing the consumer's needs.
3. Same open question as the previous draft, still unresolved: no
   `artist.email` field exists in `schema/artist.schema.json` for a
   contactable-maintainer-style record — worth adding regardless of
   packaging format, but doesn't block this decision either way.

## Cross-references

- `docs/migration-from-singularity.md` section 3 — the two-path
  distribution decision (centralized vs. self-distribution) this format
  serves; NCZ-OS's current `.deb` pipeline stays untouched by this
  decision until the shared tool actually exists.
- `docs/architecture.md` — OS-neutral format principle this decision
  extends to the install artifact itself, not just the manifest.
- `sdk/src/cache.rs`, `sdk/src/hash.rs` — the primitives this format's
  install mechanism reuses directly rather than reimplementing.
