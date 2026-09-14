# MVP milestone plan

## Task sequence

Ordered per the product brief's own §59, with one task inserted (Task 0)
and ownership assigned per the fleet's code-escalation ladder — Claude
handles architecture-level work directly; implementation goes to zoder
first, escalating only if genuinely needed.

| # | Task | Owner | Status |
|---|---|---|---|
| 0 | Read Singularity's actual current Artist Pack implementation before writing any migration doc | Claude (direct) | **Done** — `docs/migration-from-singularity.md` |
| 1 | `docs/architecture.md` | Claude (direct) | **Done** |
| 2 | `spec/artistpack-0.1.md` | Claude (direct) | **Done** |
| 3 | `schema/{artist,pack,feed}.schema.json` | Claude (direct) | **Done**, fixtures validate |
| 4 | `examples/{minimal,full,feed}/` fixtures | Claude (direct) | **Done**, validated against schema |
| 5 | Rust SDK (parse/validate/verify/cache) | zoder, rung 1 (local models) | Not started |
| 6 | CLI validator (`artistpack validate pack.yaml` must work) | zoder, rung 1 | Not started |
| 7 | Minimal API/backend (FastAPI, `docs/api-design.md`) | zoder → Codex if complexity warrants | **Done** — `backend/` (FastAPI + SQLAlchemy + Alembic; 58 pytest tests covering publish-gate 4 checks, pagination, filters, ETag, OAuth stub, ingest, audit-log, unpublish) |
| 8 | Artist dashboard (Next.js) | zoder → Codex | Not started |
| 9 | Image processing pipeline, **including the C2PA signing gate** — no longer deferrable, see `docs/tech-decisions.md` | zoder → Codex | Not started |
| 10 | Public registry/feed | After 7–9 land | Not started |
| 11 | Connect Singularity (`ArtistPackManager` second backend, `docs/migration-from-singularity.md`) or a simple standalone Linux client | After SDK (5) exists | Not started |

Windows/macOS clients are explicitly **not** started until this vertical
slice (artist upload → manifest → storage → registry feed → client
discovery → download → verification → wallpaper display → attribution)
works end-to-end on Linux, per the brief's own instruction.

## MVP scope (what "done" means for the vertical slice)

**Server:** PostgreSQL, OAuth, artist profiles, pack creation, image
upload, per-artwork metadata entry, derivative generation, C2PA signing
gate (mandatory, artist-gated — this is new relative to the original
brief's MVP scope, see `docs/tech-decisions.md`), manifest generation,
public artist/pack pages, public feed, S3-compatible storage, pack
validation.

**SDK:** parse feed, parse pack, validate schema, download assets, verify
SHA-256, verify C2PA signatures, cache locally, return attribution
metadata.

**Client:** subscribe to feed, download pack, display available artwork,
set wallpaper, rotate wallpaper, show artist/title, open artist URL.
Singularity integration preferred as validation of the format (per the
brief); a standalone Linux client only if that integration stalls.

## Phase Two (explicitly deferred, not forgotten)

Stronger manifest/feed signing (Sigstore/minisign/Ed25519), Windows
client, macOS client, GNOME/KDE integration, richer search, self-hosted
feed tooling, `.apack` archive support, Git registry mirror
(`docs/tech-decisions.md`), C2PA trust-list application
(`docs/architecture.md`).

## Phase Three (not scoped in detail yet)

Decentralized registry federation, artist verification levels beyond
`unverified`/`verified_email`, featured curators, gallery/museum feeds,
broader desktop-environment adoption, marketplace-free artist support
mechanisms.

## Founding artists

Two independent artists were identified in the original brief as founding
participants for creator-facing feedback (attribution, licensing,
cropping, redistribution policy, support links, portfolio discovery,
artist controls, provenance). Per the operator's explicit instruction,
their real names are withheld from every document in this repository
until their participation is confirmed directly with them — see
`GOVERNANCE.md`. All fixtures and examples in this repository use
entirely fictional artist names (`Nova Ashworth`, `Kai Renshaw`) for
exactly this reason, not as a stylistic choice.

## What blocks moving from Task 4 to Task 5

Nothing technical — schema and fixtures are complete and validated. The
remaining gate is procedural: this design should get a final read-through
(`docs/superpowers/specs/2026-09-13-artistpack-org-design.md`) before
Task 5 work is dispatched, per the brainstorming process this design
followed.
