# Artwork licensing — read this before assuming anything about rights

**The Apache-2.0 license in `LICENSE` covers the code in this repository
only.** It does not, and cannot, grant any rights to artwork published,
referenced, cached, or distributed through ArtistPack. This separation is a
core product principle (see `docs/architecture.md`), not a legal
technicality — the whole point of ArtistPack is that artists never lose
ownership of their work by using it.

## What an artist grants

Every artwork published through ArtistPack carries an explicit `rights`
block in its manifest (`spec/artistpack-0.1.md`), naming one of:

1. **A standard open license** the artist chose themselves — `CC BY`,
   `CC BY-NC`, `CC BY-NC-ND`, or another SPDX-identifiable license string.
2. **The ArtistPack Display License** — a narrow, purpose-built permission
   for artists who want their work shown as desktop/lock-screen imagery
   without granting broad reuse rights:

   > The artist grants permission for ArtistPack-compatible software to
   > download, cache, resize, and — only where `display.allow_crop` is
   > explicitly `true` — crop the selected artwork, solely for the purpose
   > of displaying it as desktop or lock-screen imagery. Ownership remains
   > with the artist at all times. No right to redistribute the artwork
   > outside ArtistPack-compatible delivery, to modify it for any other
   > purpose, or to use it commercially is granted unless stated separately
   > in the artist's own license field.

   This is a permission for a specific technical use, not a copyright
   transfer, and not a general reuse license. It has not yet had a formal
   legal review — treat the wording above as a drafting basis, not a
   finished legal instrument, until that review happens.

## What no one may assume

- Absence of a `rights.license` field is never silent permission — the
  schema requires it, and a manifest without one fails validation.
- Redistribution outside ArtistPack-compatible clients is **not** granted
  by default under either the Display License or most standard licenses
  artists are likely to choose (`CC BY-NC`, `CC BY-NC-ND` explicitly forbid
  it; even plain `CC BY` requires attribution ArtistPack clients must
  preserve).
- Code-license terms (patent grant, NOTICE requirements, warranty
  disclaimer) do not apply to artwork. Do not cite `LICENSE` when
  discussing what a consumer of a pack is allowed to do with the images
  in it.

## Repository contents this rule applies to

Any artwork committed into `examples/` for testing purposes is either
synthetic/generated placeholder content created for this repository, or
explicitly public-domain/permissively-licensed reference material with its
own license noted next to it. Real, artist-owned artwork is never committed
into this repository — it is stored and served from `storage/` (see
`docs/architecture.md`), and its rights are declared in its own manifest,
not inherited from this file or from `LICENSE`.
