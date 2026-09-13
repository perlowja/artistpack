# Security Policy

## Reporting a vulnerability

Do not open a public issue for a security vulnerability. Instead, email
the maintainer directly (see `GOVERNANCE.md` for current contact) with:

- A description of the issue and its impact.
- Steps to reproduce, or a proof of concept if you have one.
- Any suggested remediation, if you have one.

Expect an acknowledgment within a reasonable time; ArtistPack is a small,
pre-MVP project without a dedicated security team, so response times are
best-effort until that changes.

## Scope

Security-relevant surfaces, in priority order (see
`docs/security-model.md` for the full model):

1. **Upload pipeline** (`web/`) — MIME/type confusion, decompression
   bombs, path traversal, malicious YAML constructs, oversized images.
2. **C2PA signing/verification** (`sdk/`, `web/`) — a defect here can
   forge or falsify provenance claims, which is the entire trust surface
   ArtistPack exists to provide.
3. **Authentication** (`web/`) — OAuth flow correctness, session handling,
   internal ID stability.
4. **Feed/registry integrity** (`registry/`) — hash/signature
   verification in the SDK (`sdk/`) is the client-side backstop; a defect
   there means a compromised or malicious feed could serve altered content
   undetected.
5. **Desktop clients** (`clients/`) — privilege boundaries around wallpaper
   installation (see the precedent in Singularity's `ArtistPackManager`,
   referenced in `docs/migration-from-singularity.md`, for the kind of
   local-privilege-escalation class of bug this needs to avoid).

## Out of scope

Vulnerabilities requiring physical access to a user's already-compromised
machine, or in third-party dependencies with their own disclosure process
(report those upstream; let us know here only if ArtistPack's use of the
dependency makes the impact worse than upstream's own advisory states).
