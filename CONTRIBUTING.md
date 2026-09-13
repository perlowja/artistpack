# Contributing to ArtistPack

ArtistPack is pre-MVP. The specification, schema, and initial reference
implementation are being built in the order described in
`docs/mvp-plan.md` — please read that before proposing a large change, so
effort isn't spent on something already sequenced for later or already
ruled out as a non-goal in `docs/architecture.md`.

## Ground rules

- **Format independence first.** Nothing in `spec/` or `schema/` may
  become dependent on artistpack.org-specific behavior. If a change only
  makes sense assuming the web application exists, it belongs in `web/` or
  `registry/`, not `spec/`.
- **Artists are not engineers.** Any change to the artist-facing dashboard
  (`web/`) that surfaces raw YAML, raw JSON Schema errors, or manifest
  internals to an artist is a bug, not a feature — see `docs/architecture.md`
  §5.
- **No blockchain, tokens, or NFTs.** This is a hard non-goal, not an
  oversight to be "fixed" later.
- **Attribution is load-bearing.** Any change that makes it easier to
  strip, hide, or bypass artist attribution/provenance metadata will be
  rejected regardless of its stated purpose.
- **Unknown optional manifest fields must be ignored, not rejected**, by
  every parser and validator, per the compatibility rule in
  `spec/artistpack-0.1.md`. Unknown *required* capabilities
  (`requires:` entries) must fail clearly, not silently.

## Development workflow

1. Check `docs/mvp-plan.md` for where a task sits in the build sequence.
2. Schema/spec changes: add or update the matching fixture under
   `examples/`, and confirm `schema/*.schema.json` still validates it.
3. Code changes: this repo is a monorepo (see `README.md`); keep changes
   scoped to the component(s) they actually touch.
4. Every PR that touches `spec/` or `schema/` needs a fixture
   demonstrating the change, per `docs/mvp-plan.md`'s CI validation list.

## Commit / PR conventions

- Conventional-commit style subject lines (`type(scope): summary`).
- No AI-attribution footers on commits authored as ArtistPack maintainers
  work (this mirrors the zeroclaw-labs convention this project's
  maintainer already follows elsewhere) — human contributors should credit
  themselves normally.
- Sign your own commits with your own identity; DCO is not currently
  required but may be added before 1.0.

## Reporting issues

Security issues: see `SECURITY.md` — do not open a public issue for a
vulnerability. Everything else: open a GitHub or GitLab issue (whichever
mirror you're working from) with enough detail to reproduce.
