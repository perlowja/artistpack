"use client";

import { APIError } from "@/lib/api-client";

/**
 * Surfaces a backend `APIError` with its code, message, and a brief
 * rendering of any structured `details`. We deliberately *don't* try to
 * translate every error code into bespoke UI — the dashboard shows what
 * the server returned so a maintainer can correlate it against
 * `docs/api-design.md` and `backend/app/core/errors.py`.
 */
export function ApiErrorBanner({ error }: { error: APIError }) {
  return (
    <div className="error-banner" role="alert" data-testid="api-error">
      <strong>{error.code}</strong>
      <div>{error.message}</div>
      {error.details !== undefined && error.details !== null ? (
        <pre
          className="muted"
          style={{
            marginTop: "0.4rem",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {typeof error.details === "string"
            ? error.details
            : JSON.stringify(error.details, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}