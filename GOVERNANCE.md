# Governance

ArtistPack is pre-MVP. Governance is deliberately lightweight right now and
will formalize as the project and community grow — this document describes
the current state, not an aspirational end state that's already been
implemented.

## Current structure

- **Maintainer:** Jason Perlow (jperlow@gmail.com), acting as BDFL during
  the pre-MVP and MVP phases. All architectural and product decisions
  currently route through the maintainer.
- **Founding artists:** two independent artists have been identified as
  founding participants whose feedback shapes creator-facing decisions
  (attribution, licensing, cropping rules, redistribution policy, support
  links, portfolio discovery, artist controls, provenance). Their names
  are withheld from this document until their participation is formally
  confirmed with them directly — see `docs/mvp-plan.md`. Referred to
  generically as `founding-artist-1` and `founding-artist-2` in any
  interim documentation.

## Planned future structure

Once the project has real external contributors and published artists:

- **ArtistPack Technical Steering Committee** — technical direction for
  `spec/`, `schema/`, `sdk/`, `cli/`, `registry/`.
- **Artist Advisory Group** — creator-facing product decisions. Engineers
  do not unilaterally decide what artists need; see `CODE_OF_CONDUCT.md`.

Neither body exists yet. This section exists so the intent is on record
before it's needed, not because it is currently in effect.

## Decision-making principle

Engineering decisions default to the maintainer during pre-MVP. Anything
that changes what an artist grants, what a consumer of their work may do,
or how attribution is presented, requires artist-facing review before
being finalized — even while that review is informal (a direct
conversation with a founding artist) rather than a formal committee vote.
