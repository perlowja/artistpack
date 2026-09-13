# ArtistPack.org — architectural design record

**Status:** design complete, pending final user review before
transitioning to an implementation plan (writing-plans skill).
**Path:** architectural (new project, new subsystems, no existing repo).
**Source:** `ArtistPack.org Technical Handoff.md` (user-provided, 220
sections) plus three rounds of live refinement in this session.

This document is the record of what was decided and why. The actual
deliverables it produced are the other files in this repository:
`docs/architecture.md`, `spec/artistpack-0.1.md`, `schema/*.schema.json`,
`examples/`, `docs/api-design.md`, `docs/database-schema.md`,
`docs/security-model.md`, `docs/tech-decisions.md`,
`docs/migration-from-singularity.md`, `docs/mvp-plan.md`.

## Classification

Architectural. This is a brand-new project — no existing repository, no
existing flow to change — so "bounded" never applied, and the handoff
doc's own scope (spec + registry + web app + SDK + CLI + clients) is
exactly the kind of multi-component system the brainstorming process
exists for.

## Clarifying questions asked and answered

1. **What should happen with the handoff doc right now?** → Full
   deliverable per the doc's own §64 ("First Deliverable Expected from
   Claude"): architecture proposal, repo structure, manifest design, JSON
   Schema, REST API design, PostgreSQL schema, trust/security model, MVP
   milestone plan, tech decisions with rationale, migration strategy.
2. **Where should the project live?** → `gitlab.com/ncz-os/artistpack`
   (GitLab, canonical), with a new Buildkite pipeline under the existing
   `ncz-os` Buildkite organization, per the user's explicit instruction.
3. **Monorepo or polyrepo?** → Monorepo. The user's own stated constraint
   ("one Buildkite pipeline") made this close to a forced move rather than
   a close call — see `docs/tech-decisions.md`.
4. **GitHub mirror?** → Yes, from day one: ARGONAS (bare mirror) → GitLab
   (canonical) → GitHub (`perlowja/artistpack`, mirror), matching this
   fleet's standing push-order convention.
5. **Founding-artist names (Nova Ashworth/Kai Renshaw are the fictional
   stand-ins used throughout this repo) — real or placeholder?** →
   Placeholder. Two real people were named in the original brief as
   founding artists; the user had not yet confirmed their participation
   directly, so every document and fixture in this repository uses
   fictional names instead. This is why `examples/` never references the
   brief's original example artist by name.

## Approaches considered

### Registry model: PostgreSQL-only vs. Postgres+Git hybrid

The brief itself raised this as an open question (its own §36,
"Investigate"). Considered:

- **A. Postgres-only, generated feed endpoints** (chosen for v0.1) —
  simplest, one persistence mechanism to keep consistent while the schema
  is still likely to change.
- **B. Postgres as operational store + generated Git mirror** — real
  benefits (transparency, reproducibility, easy external mirroring) but
  adds a second persistence mechanism to keep in sync before the core
  publish flow is even proven. The brief's own Phase Two list (§57)
  already places this there independently of this session's reasoning —
  deferring it isn't overriding the brief, it's following its own
  sequencing.

**Decision: A now, B in Phase 2.** See `docs/tech-decisions.md`.

### C2PA requirement: three rounds of refinement, not one decision

This is the part of the design that actually changed shape during the
conversation, so it's recorded as a sequence rather than a single
decision:

1. **Brief's own MVP guidance:** don't block launch on full C2PA signing
   (§56) — implement it after the basic end-to-end system works.
2. **Round 1 (Claude's initial proposal):** keep `rights`/`attribution`/
   `provenance` optional at the schema level, required only by
   artistpack.org's publish endpoint — a two-tier model, C2PA itself still
   effectively optional-forever in practice.
3. **User correction, informed by real evidence:** "the Singularity
   artist pack spec may not be sufficient currently, as it doesn't have
   C2PA or metadata per image, we may need to improve the spec." This
   prompted actually reading Singularity's current implementation
   (`docs/migration-from-singularity.md`) rather than continuing to reason
   from the brief's own "treat as prior art" assumption — confirmed the
   gap was real and exactly as described: pack-level metadata only, zero
   C2PA, license field frequently absent even in the newer OCS path.
4. **Round 2 (user directive):** make C2PA mandatory outright, overriding
   the brief's own MVP guidance. Claude flagged the concrete costs (moves
   `c2pa-rs` integration and signing-key custody into the MVP critical
   path; self-signed cert won't validate against public C2PA verifiers
   until a Phase 3 trust-list application) rather than silently agreeing
   or silently implementing without surfacing the trade-off.
5. **Round 3 (final, user refinement):** "make C2PA a artist-gated
   requirement" — mandatory, but the requirement is satisfied through the
   artist's own visible, consented publish-flow action (preserve an
   artist's existing Content Credentials if present, or explicit opt-in to
   artistpack.org signing), never injected silently server-side. This is
   the version implemented in `docs/architecture.md` and reflected in
   `schema/pack.schema.json`'s conditional requirement
   (`c2pa: true` requires `manifest_file`).

This sequence is preserved here because a future contributor reading only
`docs/architecture.md` would see the final state without understanding
that it deliberately overrides the brief's own stated MVP guidance, or
why — which matters if anyone is later tempted to "fix" it back toward
the original optional-C2PA plan.

### GRAEAE consult: attempted, failed, proceeded on direct judgment

Per this fleet's standing architecture-review process, a GRAEAE consult
was submitted before finalizing the remaining open tech-selection
questions (backend framework, worker queue, registry model). All 8
configured muses returned authentication errors
(`x-api-key header is required`, malformed `Bearer` header) — a total
service failure, not a partial/low-consensus result. This was consistent
with the GitLab CI pipeline for `ncz-os/graeae` itself failing the same
day, per the session's own build-watch feed — almost certainly the same
root cause, and not something to debug mid-task here. Per the fail-safe
principle (a missing/failed advisory input never blocks progress, and
never silently grants permission to skip judgment either), the remaining
decisions were made directly and are documented with explicit rationale
in `docs/tech-decisions.md` rather than presented as GRAEAE-validated
when they weren't.

## Design sections (see the referenced files for full detail)

1. **Architecture** — `docs/architecture.md`. Eight components, explicit
   trust boundary (a self-hosted `pack.yaml` artistpack.org has never seen
   must validate identically to a registered one), two-tier validation
   (schema vs. registry policy) as the resolution to the schema-must-stay-
   permissive vs. registry-must-guarantee-provenance tension.
2. **Repository structure** — monorepo, `gitlab.com/ncz-os/artistpack`.
3. **Manifest design** — `spec/artistpack-0.1.md`. Per-artwork metadata
   (not just per-pack) is the core addition relative to what Singularity
   has today; required `provenance` object with conditional
   `manifest_file` requirement when `c2pa: true`.
4. **JSON Schema** — `schema/{artist,pack,feed}.schema.json`, Draft
   2020-12, validated against all six fixtures in `examples/` using
   `jsonschema` (Python) via `uv run` — all pass.
5. **REST API design** — `docs/api-design.md`. Cursor pagination
   throughout; the publish endpoint is where the C2PA gate becomes code.
6. **PostgreSQL schema** — `docs/database-schema.md`. Artworks belong to
   immutable `pack_versions` (not mutable `packs` directly) so a published
   version is reproducible; `manifest_sha256` is a generated/triggered
   column specifically to prevent DB/YAML drift.
7. **Trust/security model** — `docs/security-model.md`. Generalizes a real
   precedent found in Singularity's own code (fixed-path privilege
   escalation guard in `ArtistPackManager`) as a requirement for any
   future ArtistPack desktop client, not just a Singularity quirk.
8. **MVP milestone plan** — `docs/mvp-plan.md`. Task 0 (read Singularity's
   real implementation) inserted ahead of the brief's own Task 1;
   ownership mapped to the fleet's code-escalation ladder.
9. **Tech decisions with rationale** — `docs/tech-decisions.md`.
10. **Migration strategy** — `docs/migration-from-singularity.md`, grounded
    in the actual current Vala implementation and OCS design spec, not the
    brief's untested "treat as prior art" assumption.

## Spec self-review

- **Placeholder scan:** no TBD/TODO markers in any produced document.
  Two items are explicitly named as open/unresolved rather than
  placeholder-filled: (a) whether `ncz-wallpaper-ocs`'s CLI already
  supports the operations `docs/migration-from-singularity.md` assumes —
  flagged as a real unknown to confirm during Task 5/11 implementation,
  not glossed over; (b) the ArtistPack Display License's exact legal
  wording (`ARTWORK-LICENSES.md`) is explicitly marked as a drafting
  basis pending real legal review, not a finished instrument.
- **Internal consistency:** the C2PA requirement is stated identically
  across `docs/architecture.md`, `spec/artistpack-0.1.md` §9,
  `schema/pack.schema.json`'s conditional requirement, and
  `docs/api-design.md`'s publish-gate description — checked pairwise
  during authoring, not just asserted here.
- **Scope check:** focused enough for one implementation plan covering
  Tasks 5–6 (SDK + CLI) as the next concrete unit of work; Tasks 7–11
  depend on those landing first and would be their own subsequent plans.
- **Ambiguity check:** the one place two readings were possible —
  whether mandatory C2PA applies retroactively to already-published
  Singularity content — is resolved explicitly in
  `docs/migration-from-singularity.md`'s closing section: it doesn't,
  because nothing has been published to artistpack.org yet.

## Next step

Per the brainstorming skill's architectural path: this document goes to
the user for review, then Task 5 (Rust SDK) implementation planning
begins via the writing-plans skill — targeting zoder (rung 1 of the
fleet's code-escalation ladder) as the author, not Claude directly, per
the fleet's orchestrator-not-worker operating principle.
