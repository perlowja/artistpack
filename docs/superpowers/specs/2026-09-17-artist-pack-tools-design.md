# Artist Pack Tools — design

Status: approved by operator 2026-09-17, ready for implementation plan.
GRAEAE consultations: `b8e120a5d6c94c559bc0ea80b49d7ce6` (tech stack),
`bymo5dstn`-sourced follow-up (distribution/onboarding) — both HTTP-fallback
consults against `http://192.168.207.67:5002/v1/consultations` (MCP
`graeae_consult` was down this session).

## Goal

A non-developer Mac/Windows creative professional (photographer,
illustrator, wallpaper artist) drops raw image files into a folder and
works conversationally with an AI coding agent (Claude Code, Codex CLI,
ChatGPT, or equivalent) to produce a complete, schema-valid ArtistPack
pack — `pack.yaml` + `artist.yaml` + resized variants + a built
`.pak.gz` — without hand-writing YAML, without touching a raw terminal
error, and without needing to already be a developer.

## Explicitly OUT of scope for this spec (real, tracked follow-ons)

- **Signed native installer app** ("ArtistPack Starter" — notarized
  `.dmg`/`.pkg` for macOS, signed `.msi` for Windows). Needs an Apple
  Developer account, a notarization pipeline, and a Windows
  code-signing certificate — real ongoing infra/cost, not a coding
  task. Revisit once the CLI + guide have real usage and we know
  whether artists actually get stuck at "install an agent CLI."
- **Hosted web builder** (`artistpack.org/create` — upload images in a
  browser, no local install at all). A natural extension of the
  existing `backend/`/`frontend/` (Tasks 7/8), genuinely the easiest
  path per GRAEAE, but a distinct project with its own UI/backend work.
- **Claude Code / Codex / ChatGPT-specific wrapper packages** (a real
  Claude Skill plugin-marketplace entry, a Codex-specific skill config,
  a ChatGPT Custom GPT + Action bridge). The portable `AGENT_GUIDE.md`
  is the v1 answer for all three; per-agent wrappers are a cheap
  follow-on once the guide's content has stabilized against real use.

This spec covers only: the new CLI subcommands, the bundled image tool
integration, the C2PA signing ceremony, `AGENT_GUIDE.md`, and the
human-facing `README.md`.

## Architecture

```
artist's folder
  images/                 <- artist drops raw files here, nothing else required
  AGENT_GUIDE.md           <- shipped alongside the CLI, agent reads this
  README.md                <- human-facing, artist reads this once
  (bundled tool dir)/
      artistpack           <- the CLI binary
      vips-tools/          <- bundled libvips CLI binaries (per-OS)

Agent (Claude Code / Codex / ChatGPT, etc.)
  reads AGENT_GUIDE.md
  drives the CLI via subcommands, JSON in/out only
  translates every CLI error into a plain-language question or explanation
  asks the artist only for information only the artist can provide
    (attribution name, license choice, tags, alt text, whether images
     are the artist's own to license, C2PA identity if signing)

artistpack CLI (Rust, extends sdk/ + cli/ from Tasks 5-9)
  scan-dir        -> candidate originals + hashes/dimensions/mime
  derive-variants -> shells to bundled vips tool, writes resized files
  draft           -> renders pack.yaml/artist.yaml from an answers JSON
  validate         (existing)
  sign-c2pa       -> local, artist-gated C2PA signing ceremony
  build-pak        (existing)
```

Every new subcommand is **JSON in, JSON out** (`--json` on stdout,
human text is not parsed by the agent) — this is the "artist-safe
diagnostics" boundary: the CLI's job is to turn a raw I/O or format
error into a structured `{"error": {"code", "message", "hint"}}` the
agent can turn into a plain sentence, never a Rust panic or a bare
stack trace reaching the artist.

## New CLI subcommands

### `artistpack scan-dir <path> --json`

Walks `<path>` non-recursively (v1: flat directory only — a nested
folder structure is a `hint`-level warning, not a scope this spec
covers) for image files (jpg/jpeg/png/webp — the same formats
`schema/pack.schema.json`'s `mime_type` already anticipates). For each
file: SHA-256 (`hash::sha256_hex_of_file`, already exists), MIME type
(sniffed from content, not extension — a `infer`-crate-class check,
not a trust-the-extension check), width/height (via the `image` crate
already available as a light dependency — this is dimension-reading
only, not the resize path, so it does not need libvips).

Output:
```json
{
  "candidates": [
    {
      "file": "sunset-1.jpg",
      "sha256": "…",
      "mime_type": "image/jpeg",
      "width": 5472,
      "height": 3648
    }
  ],
  "warnings": ["skipped subdirectory: drafts/ (not scanned)"]
}
```

No pack-shape decisions happen here (no artwork IDs, no grouping) —
that is the agent's conversational job with the artist, informed by
this raw list.

### `artistpack derive-variants <draft.json> --sizes <spec> --json`

Takes a draft (see `draft` below, or an intermediate shape before the
final `pack.yaml` exists) naming one or more originals and a size spec
(e.g. `--sizes 3840x2160,1920x1080`), and for each (original, size)
pair:

1. Shells out to the bundled `vips-tools` binary (`vipsthumbnail` or
   `vips resize`, whichever gives correct aspect-ratio-preserving
   output most directly — decide at implementation time against real
   libvips CLI docs, not guessed here) to produce the resized file
   alongside the original.
2. Recomputes SHA-256/width/height of the produced file
   (`hash::sha256_hex_of_file` + the `image` crate again, on the
   OUTPUT this time — never trust what the resize tool claims it
   produced, verify from disk like everything else in this codebase
   does).
3. Returns the new variant's `{file, sha256, width, height, mime_type}`
   in the same `ImageRef` shape `sdk/src/types.rs` already defines, so
   the agent can drop it straight into a draft's `variants[]`.

A resize failure (corrupt input, unsupported color space — CMYK TIFFs
are a real named example from the GRAEAE consult) returns a structured
error with a `hint` field written in plain artist-facing language
("This file looks like a CMYK TIFF, which we can't resize yet — try
exporting it as sRGB JPEG or PNG first"), not the bundled tool's raw
stderr.

### `artistpack draft --from <answers.json> -o pack.yaml --json`

Takes a single JSON document the agent assembles from (a)
`scan-dir`/`derive-variants` output and (b) the artist's conversational
answers (title, per-artwork attribution/tags/alt-text/license, pack-level
copyright/license, artist profile fields), and renders `pack.yaml` +
`artist.yaml` — byte-for-byte deterministic given the same input (no
hidden defaults beyond what `spec/artistpack-0.1.md`/the schemas
already default, e.g. `attribution_required: true`).

This is pure rendering — it does NOT re-verify hashes (that already
happened in `scan-dir`/`derive-variants`) and does NOT run
`validate_pack` itself (the agent calls `validate` as a separate,
visible step, so a validation failure is its own clear moment in the
conversation, not buried inside `draft`'s output).

### `artistpack sign-c2pa <pack.yaml> --json`

The explicit, artist-gated local signing ceremony (GRAEAE's
recommended flow, adopted as-is):

1. Refuses to run non-interactively without an explicit
   `--identity <label>` the artist has already set up (this spec does
   NOT design the local-key-material setup flow itself — Keychain-backed
   on macOS, cert-store/CNG-backed on Windows — that is real, separate,
   security-sensitive work belonging to its own spec once this ships;
   v1's `sign-c2pa` targets whatever local identity/cert the official
   `c2pa`/`c2patool` tooling already knows how to use on this machine,
   and errors clearly, with a link to upstream's own setup docs, when
   none exists).
2. Prints/returns EXACTLY what will be signed and with which identity
   before doing anything, so the agent can relay it to the artist in
   plain language and get an explicit yes before re-invoking with
   `--confirm`.
3. Invokes the real `c2pa`/`c2patool` (crate `c2pa`, repo
   `contentauth/c2pa-rs`, MIT OR Apache-2.0 — confirmed via GRAEAE
   against the official Content Authenticity Initiative/C2PA Joint
   Development Foundation tooling, not a reimplementation) to produce
   the artwork's C2PA manifest, writes it alongside the artwork,
   updates `pack.yaml`'s `provenance.manifest_file` to point at it.
4. Never sends private key material anywhere — this is a purely local
   operation. The backend/registry side (Task 9's original scope) only
   ever verifies and displays an already-signed manifest; it does not
   sign on the artist's behalf by default. This closes Task 9's
   self-distribution half; the centralized/managed-account signing
   path (if ever needed) is separate, deferred, out of this spec.

Signing is optional at pack-creation time — a pack with
`provenance.c2pa: false` is schema-valid and buildable; the artist can
run `sign-c2pa` later and rebuild.

## `AGENT_GUIDE.md` — content outline

Plain markdown, **no tool-specific syntax** (no Claude tool-call XML, no
Codex-specific config) — just prose instructions plus literal shell
commands any tool-calling agent can execute. Sections:

1. **What you're building** — one paragraph, the end state (`output/*.pak.gz`).
2. **The tools you have** — the exact path to the bundled `artistpack`
   binary relative to this file, and that every subcommand takes
   `--json` and must be parsed as JSON, never as human text.
3. **The exact sequence** — `scan-dir` → conversational Q&A → grouping
   originals/variants → `derive-variants` (only if the artist wants
   additional sizes beyond their originals) → `draft` → `validate` →
   (optional) `sign-c2pa` → `build-pak`. Written as an explicit
   numbered flow, not left for the agent to improvise the order.
4. **What to ask the artist, and when** — a checklist: attribution
   display name, per-artwork title, tags, alt text, whether they're the
   rights holder, which license (point at
   `schema/pack.schema.json`'s enumerated/known license strings),
   whether they want C2PA signing now or later. One question at a time,
   plain language, no schema jargon exposed to the artist.
5. **Error handling contract** — every subcommand's JSON error shape,
   and the instruction: never show the artist raw JSON or a stack
   trace; always translate to one plain sentence plus, if there's a
   `hint` field, that hint.
6. **When to stop and ask a human** — cases the guide can't fully
   script (an ambiguous file that might be a duplicate, a `sign-c2pa`
   identity error) get an explicit "stop, explain, ask" instruction
   rather than the agent guessing.

## `README.md` — content outline (human-facing, not the agent's)

Per GRAEAE's phrasing, adopted directly:

```md
# Make Your ArtistPack

You do not need to code.

1. Put your images in the `images/` folder.
2. Open your AI assistant (Claude Code, Codex, or similar).
3. Paste this prompt:

   > Read AGENT_GUIDE.md in this folder and follow it exactly.
   > Start by scanning images/, then help me fill in the details,
   > validate the pack, and build the final .pak.gz.

4. Answer the assistant's questions about your artwork.
5. Find your finished pack in `output/`.

## If you don't have an AI coding assistant yet

We recommend Claude Code. Install it from Anthropic's official guide:
https://docs.anthropic.com/en/docs/claude-code/getting-started
You'll sign in with your Claude account — you do not need to know how
to code.
```

Plus a short "what is C2PA / do I need to sign now" paragraph, and a
"what if something goes wrong" pointer back to the agent (never a raw
troubleshooting/CLI-flags section aimed at the artist directly).

## Testing

- Every new subcommand gets the same real-fixture-based test style
  already established in `sdk/src/pak.rs`/`sdk/tests/fixtures.rs` — real
  temp directories, real files, real computed hashes, no mocking.
- `derive-variants` needs the bundled `vips` tool present in the test
  environment (CI must stage it, same per-arch bundling this spec
  requires for real distribution — resolve exact CI staging in the
  implementation plan, not guessed here).
- `sign-c2pa` tests run against a locally-generated throwaway test
  identity/cert (never a real one), verifying the manifest round-trips
  through `c2pa`'s own verification — do not hand-roll a fake C2PA
  manifest shape independent of the real crate.
- `AGENT_GUIDE.md`/`README.md` are content, not code — reviewed by a
  real read-through against the actual CLI's current `--help` output
  and JSON shapes before each release, not unit-tested.

## Open questions for the implementation plan (not resolved here)

1. Exact bundled-libvips acquisition mechanism per OS (build from
   source vs. redistribute upstream prebuilt binaries — check libvips'
   own license/redistribution terms, LGPL implications for bundling).
2. Exact `vips` CLI invocation for aspect-ratio-preserving resize
   (`vipsthumbnail` vs `vips resize` vs `vips thumbnail`) — pick against
   real libvips CLI docs during implementation, not guessed here.
3. Local C2PA identity/cert setup UX (Keychain/cert-store-backed signer
   helper) is real, separate work this spec deliberately does not
   design — `sign-c2pa` in v1 only needs to detect and use whatever
   identity the official tooling already supports, erroring clearly
   when none exists.
