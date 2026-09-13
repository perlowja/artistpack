# Trust and security model

See `SECURITY.md` for how to report a vulnerability. This document
describes the model, not the reporting process.

## Threat model summary

Treat every submitted artifact as adversarial until validated: images,
YAML, URLs, artist descriptions, social links, C2PA payloads, and (once
`.apack` archive upload exists) archive contents. The upload pipeline is
the single highest-value attack surface in this system — it's the only
place an untrusted party can get bytes into artistpack.org's storage and
database.

## Upload pipeline guards

1. **MIME sniffing by content, never by file extension.** A `.jpg`
   extension proves nothing.
2. **Decompression-bomb protection** — reject any image whose decoded
   pixel dimensions exceed a hard cap before full decode, not after.
3. **Dimension and file-size limits**, enforced before any processing
   touches the file.
4. **Safe YAML parsing only** — no arbitrary tag construction, ever.
   Generated manifests use a restricted-tag loader/dumper on both ends.
5. **EXIF/IPTC policy, not blanket deletion**: GPS coordinates, camera
   serial numbers, and private comments are stripped by default;
   copyright/artist/title/ArtistPack-URL/C2PA metadata is preserved
   unless the artist explicitly opts out. See §47 of the original product
   brief — "do not assume metadata should simply be deleted" applies
   here as a security-adjacent privacy decision, not just a UX one.
6. **`.apack` archive guards (built now, even though archive upload ships
   later)**: path-traversal, zip-bomb, and symlink-attack protection are
   written as part of the storage-write path from day one — retrofitting
   them under deadline pressure once archive upload actually ships is the
   failure mode this avoids.
7. **Rate limiting, CSRF protection, OAuth state validation, XSS
   protection, and external-link/URL sanitation** apply to every
   authenticated write endpoint in `docs/api-design.md`, not just upload.

## C2PA signing key custody

The self-issued MVP signing certificate (`docs/architecture.md` §"C2PA:
mandatory, artist-gated") is a secret with real blast radius — anyone who
obtains the private key can forge provenance assertions for content that
was never actually published through artistpack.org. It is generated,
stored, and rotated following the same operational discipline as any
other fleet secret: never committed to this repository, never logged, and
tracked in whatever secret-management system the deployment environment
actually uses once the signing service is built (this repository does not
yet contain that service — see `docs/mvp-plan.md`).

## Authentication and authorization

- OAuth (Google/GitHub, `docs/api-design.md`) is authentication only.
  ArtistPack maintains its own internal `users.id`/`artists.id` —
  authorization decisions never key off a provider's own user ID directly,
  so revoking or changing an OAuth connection can never silently change
  who owns what inside ArtistPack.
- RBAC roles (`user`, `artist`, `moderator`, `administrator`) gate the
  admin/moderation endpoints in `docs/api-design.md`. An `artist` role
  controls only their own `artists`/`packs` rows — there is no
  cross-artist write path in the API short of the moderation endpoints.

## Client-side trust (SDK)

The SDK (`sdk/`) is the actual trust boundary for every consumer — CLI,
desktop clients, and any future third-party client. Two independent
checks, both mandatory, neither optional:

1. **SHA-256 verification** of every downloaded file against the value
   in its manifest, regardless of transport (HTTPS doesn't substitute for
   this — TLS proves the bytes weren't altered in transit from *whatever
   server sent them*, not that the server itself wasn't compromised or
   malicious).
2. **C2PA signature verification** for any artwork the client's UI
   presents as having "verified provenance." Presence of a `provenance`
   block is not verification — a client that skips the actual signature
   check and shows a "verified" badge anyway is a security bug matching
   the C2PA misuse pattern the source brief explicitly warns against
   (never claim to prove authorship or human origin beyond what the
   manifest actually asserts).

Atomic install (`docs/architecture.md`'s data-flow diagram: staging
directory → atomic activation) exists specifically so a partially
downloaded or partially verified pack is never mistaken for a complete,
trusted one.

## Desktop client privilege boundaries

`docs/migration-from-singularity.md` documents a concrete precedent worth
generalizing: Singularity's existing `ArtistPackManager` resolves its
privileged install helper from a **fixed, compiled-in absolute path**,
never via `$PATH` lookup, specifically because a `$PATH`-based resolution
would let anything writing to an earlier `$PATH` directory (commonly
user-writable, e.g. `~/.local/bin`) achieve local privilege escalation
when that helper is invoked via `pkexec`. Any future ArtistPack desktop
client that shells out to a privileged helper for wallpaper installation
must follow the identical pattern — this is not a Singularity-specific
quirk, it's the correct general answer to "a Vala/Rust/whatever client
needs to run one root-owned script," and should be treated as a
reviewable requirement, not a nice-to-have.

## What's explicitly not attempted

No AI-generated-image detection (`docs/architecture.md`'s non-goals).
Malware scanning on uploaded images is "if practical" per the source
brief, not a hard MVP requirement — flagged here so it's a known,
deliberate gap rather than an oversight.
