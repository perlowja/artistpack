# ArtistPack backend

FastAPI service implementing `docs/api-design.md` (Task 7 of `docs/mvp-plan.md`).
This package is the minimal MVP backend:

- **DB layer**: SQLAlchemy models for every entity in `docs/database-schema.md`,
  Alembic migrations. `pack_versions.manifest_sha256` is implemented as a real
  Postgres trigger in the initial migration, plus a Python-side recompute on
  every save as a portable invariant for tests/dev.
- **Public endpoints**: artists, packs, artworks, feeds, search — cursor
  pagination, the spec'd error envelope, ETag/Cache-Control caching headers.
- **Authenticated endpoints**: OAuth callback stubs (Google/GitHub — token
  exchange lives behind a clearly-marked adapter), artist profile CRUD,
  pack CRUD, artwork upload (multipart, local-disk storage behind a swappable
  interface).
- **Publish gate**: checks 1, 3, 4 from `docs/api-design.md` §"`POST .../publish`
  — the gate" implemented for real. Check 2 is reduced to "every artwork has
  `provenance_records.verification_status == 'verified'`" — actual C2PA
  signing/verification is **Task 9** and is intentionally not stubbed here
  beyond verifying the row exists.

## Scope notes (from the task brief)

- C2PA signing/verification itself is **out of scope** — see
  `app/services/publish_gate.py` for the explicit boundary comment.
- OAuth provider HTTP exchanges are **stubs** — see `app/auth/oauth.py`.
- Storage backend is **local disk**; the `Storage` interface in
  `app/storage/base.py` is the swap point for S3/R2 in Phase 2.
- Frontend (Task 8), image processing pipeline (Task 9), and Sigstore/Sigstore
  manifest signing are explicitly not implemented here.

## Run

```bash
cd backend
python3 -m pip install -e ".[dev]"
export ARTISTPACK_DATABASE_URL="sqlite+aiosqlite:///./artistpack.db"  # dev default
export ARTISTPACK_STORAGE_DIR="./storage"                             # dev default
alembic upgrade head
uvicorn app.main:app --reload
```

## Test

```bash
cd backend
python3 -m pytest
```

The test suite runs against an in-memory SQLite database via
SQLAlchemy's ``StaticPool`` (see ``tests/conftest.py``) — production
targets Postgres via the ``ARTISTPACK_DATABASE_URL``
``postgresql+psycopg://...`` URL, and the Postgres-only
``manifest_sha256`` integrity trigger is exercised by the migration
``alembic/versions/0002_manifest_sha256_trigger.py``. SQLite tests
verify the same invariant via the application's
``recompute_manifest_sha256`` helper called before every commit.
