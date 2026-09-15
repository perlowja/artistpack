# ArtistPack dashboard

Task 8 of `docs/mvp-plan.md`. Next.js (App Router) + TypeScript dashboard
that talks to the FastAPI backend at `backend/`.

This package was added as part of the MVP vertical slice; the public-facing
browsing site, image-processing pipeline, and C2PA signing service are
separate future tasks (Tasks 9, 10) and intentionally not included here.

## Layout

```
src/
  app/                     Next.js App Router routes
    layout.tsx              Root layout (TopNav + main)
    page.tsx                Landing — redirect to /me or /login
    login/page.tsx          OAuth-callback form (POSTs to backend)
    me/page.tsx             Profile view/edit, artist profiles CRUD
    packs/page.tsx          Pack list + create draft
    packs/[packPublicId]/   Pack detail: metadata, validation, publish,
                            artworks, artwork upload/edit/sign
  components/               Reusable UI pieces
    TopNav.tsx              Header with sign-in / sign-out
    ApiErrorBanner.tsx      Surfaces backend errors with code/message/details
    ValidationPanel.tsx     The four publish-gate checks, live
    ArtworkUploadForm.tsx   Image upload with client-side preview
    ArtworkEditForm.tsx     Per-artwork edit / delete / regen / sign
  lib/                      Cross-cutting helpers
    api-types.ts            Pydantic-mirroring TypeScript types
    api-client.ts           Typed fetch wrapper + endpoint methods
    session.ts              localStorage-backed session token
    cx.ts                   Tiny className joiner
tests/                      Vitest + RTL tests (see Testing below)
```

## Running

```sh
npm ci
npm run build
npm test
```

For local development against a running backend:

```sh
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1 npm run dev
```

The dashboard calls the backend at `NEXT_PUBLIC_API_BASE_URL` (default
`http://localhost:8000/api/v1`, matching the local FastAPI default). The
backend's `POST /api/v1/auth/oauth/{provider}/callback` is currently a
stub that returns `oauth_not_implemented` (see `backend/app/auth/oauth.py`);
the dashboard wires to the real endpoint shape and surfaces that error
visibly rather than faking success client-side.

## Testing

39 tests across 5 files:

- `tests/api-client.test.ts` — envelope parsing, network-error mapping,
  204 handling, typed wrappers for `me` / `validation` / `publish`.
- `tests/ValidationPanel.test.tsx` — `classifyErrors` over a mixed
  pass/fail response, plus rendering the four-check checklist with the
  correct pass/fail icons.
- `tests/PublishButton.test.tsx` — publish-disabled logic for every
  interesting state (already published, validation pending, any failing
  check, all-green), plus panel rendering for both all-OK and failing
  states.
- `tests/ArtworkUploadForm.test.tsx` — `validateImageClient` over MIME
  types and size cap, plus the submit-disabled state as fields and a
  valid file are filled in.
- `tests/dashboard-flow.test.tsx` — end-to-end-ish login / packs-list /
  pack-detail flows against a deterministic mocked API, including the
  stub OAuth failure path.

The mix is Vitest + React Testing Library for unit/component tests and
"flow" tests that wire multiple components together against a mocked
backend — there's no real backend dependency, no Playwright browser, and
no DB. We deliberately did not add a separate Playwright layer here
because there's no real backend to point it at yet (Task 7's stub
backend; full integration is Task 9+).

## What's intentionally NOT here

- The public-facing artist / pack browsing pages (separate future task).
- Real OAuth flow — backend has only `StubOAuthProvider`; dashboard wires
  to the real endpoint shape and surfaces the stub failure.
- Image processing, derivative generation, real C2PA signing — all Task 9.
- A real backend runtime; the dashboard expects to talk to `backend/` over
  HTTP. `npm run dev` will start it pointing at `localhost:8000`.