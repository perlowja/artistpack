# Technology decisions and rationale

GRAEAE consult was attempted before finalizing these (per this project's
standing architecture-review process) and failed outright — all 8
configured muses returned auth errors (`x-api-key header is required` /
malformed `Bearer` header), consistent with the GRAEAE service itself
having a broken deploy at the time (its own GitLab CI pipeline was failing
the same day). Decisions below were made directly, mostly by adopting
what the source product brief already specified rather than re-litigating
settled choices, and are flagged individually where they required real
judgment rather than just following the brief.

## Repository structure: monorepo

**Decision:** one repository (`gitlab.com/ncz-os/artistpack`), one
Buildkite pipeline, internal layout `spec/ schema/ web/ registry/ sdk/
cli/ clients/ docs/ examples/ tests/ infrastructure/`.

**Why:** the brief allowed either; the deciding constraint was operational
— one Buildkite pipeline was the explicit ask, and a single early-stage
maintainer plus AI-agent-assisted development benefits far more from
atomic cross-component commits (a schema change and its fixture update
landing together, a spec change and the SDK code that implements it in
one PR) than from the isolation a polyrepo buys. Splitting later, once
components have independent release cadences and separate maintainer
teams, is cheap; merging six existing repos back together later is not.

## Backend: FastAPI + PostgreSQL + Arq

**Decision:** Python/FastAPI backend, PostgreSQL database, **Arq** as the
async worker queue for the image-processing/C2PA-signing pipeline.

**Why FastAPI+PostgreSQL:** already the brief's own stated MVP preference
(§16) — good schema handling via Pydantic, async support, fast to iterate
on with a small team. Not re-litigated; a Rust backend was the brief's
alternative but explicitly deprioritized developer speed under "developer
speed matters more than theoretical performance" in the same section.

**Why Arq over Celery/Dramatiq/RQ:** the brief asked for "the smallest
reliable option" among Celery/Dramatiq/RQ/Arq. Arq is async-native and
sits on the same asyncio runtime as FastAPI itself, needing only Redis as
infrastructure — no separate broker daemon class the way Celery needs
(RabbitMQ or Redis plus Celery's own worker/beat processes). Dramatiq and
RQ are both reasonable second choices; Arq was picked specifically because
the backend is already committed to async FastAPI, and running the worker
on the same async primitives avoids a second concurrency model in the
codebase.

## SDK: Rust (canonical)

**Decision:** the canonical ArtistPack SDK is Rust; CLI and desktop
clients are built on it; language bindings (Python/C/Swift/.NET) come
later, not at MVP.

**Why:** already the brief's own stated choice, justified by the actual
constraint that matters most here — three planned desktop targets (Linux,
macOS, Windows) plus a CLI all need the same parse/verify/cache logic with
no runtime dependency, which rules out anything requiring a VM (JVM,
CLR-without-native-AOT) or an interpreter shipped alongside the binary.
`c2pa-rs` (the reference C2PA implementation) being Rust-native is a
second, independently sufficient reason once C2PA became mandatory
(`docs/architecture.md`) — the signing/verification path and the SDK can
share the same crate ecosystem instead of bridging languages at that
boundary.

## Frontend: Next.js + TypeScript

**Decision:** as specified in the brief; SvelteKit was the brief's own
listed alternative and wasn't chosen because there's no team-experience or
ecosystem reason to deviate from the more conventional choice for an
image-heavy, SEO-relevant, server-rendered public site plus an
authenticated dashboard — exactly Next.js's home turf.

## Registry model: PostgreSQL-only for v0.1, no Git mirror yet

**Decision:** the registry is backed by PostgreSQL with generated
JSON/YAML feed endpoints. The "Git repository as source of truth" hybrid
the brief raises as something to "investigate" (its own §36) is
**deferred to Phase 2** — the brief's own Phase Two list (§57) already
places "Git registry mirror" there, so this isn't overriding the brief,
it's following its own sequencing rather than pulling that work forward.

**Why defer:** the hybrid buys transparency, reproducibility, and easy
external mirroring — real benefits, but ones that matter once there's a
real corpus of published packs and a community that wants to audit/mirror
it. Building it before the core publish flow is proven adds a second
persistence mechanism (Postgres + generated Git commits) to keep
consistent while the schema and publish gate are still likely to change.
YAGNI, per the brief's own stated principle.

## C2PA: mandatory, artist-gated (operator decision, evolved across three rounds)

**Decision path**, recorded because the reasoning at each step matters
more than the final state alone: the brief's own MVP guidance (§56) said
not to block launch on full C2PA signing. The operator first directed
C2PA to be made mandatory outright — overriding that MVP guidance — after
confirming (by reading Singularity's actual current implementation, see
`docs/migration-from-singularity.md`) that the existing "prior art" this
project is meant to generalize has *no* C2PA and *no* per-image metadata
at all, meaning ArtistPack has to be a real upgrade, not a reformatting of
what already exists. The operator then refined "mandatory" to
**artist-gated**: the requirement is enforced at the artist's own publish
action (a visible, consented dashboard step), not injected silently by
the server on every upload regardless of artist intent. See
`docs/architecture.md`'s C2PA section for the resulting mechanism, and
`docs/security-model.md` for the signing-key custody consequences.

**Cost this decision accepts, stated plainly:** C2PA signing infrastructure
(`c2pa-rs` integration, a signing keypair, key custody, eventual C2PA
trust-list application) moves from a Phase 2 nice-to-have into the MVP
critical path. This is a deliberate trade of MVP timeline against product
integrity — the operator's call, not a technical necessity independent of
the product's stated purpose (provenance and attribution are literally why
ArtistPack exists, per `docs/architecture.md`'s opening philosophy).

## Storage: S3-compatible behind an abstraction

**Decision:** as the brief specifies — Cloudflare R2 as the default
production target, MinIO or local filesystem for development, behind an
interface neither the Rust SDK's cache logic nor the Python backend's
ingest pipeline hard-codes a specific provider into.

**Why:** avoids AWS lock-in the brief explicitly warns against, and the
abstraction cost is low (a handful of methods: put, get, generate a
signed URL) relative to the flexibility it buys for self-hosters, who by
`docs/architecture.md`'s own trust-boundary requirement must be able to
run their own storage entirely outside artistpack.org's infrastructure.
