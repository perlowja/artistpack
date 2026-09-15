/**
 * API client. The base URL is read from `NEXT_PUBLIC_API_BASE_URL` and
 * defaults to the backend's local dev address — see `docs/api-design.md`
 * for the surface this dashboard is a client of and `backend/app/api/v1/`
 * for the live implementation.
 */

import type {
  ArtworkOut,
  ArtworkPatchIn,
  ArtistCreateIn,
  ArtistOut,
  ArtistPatchIn,
  ErrorEnvelope,
  MeOut,
  MePatchIn,
  OAuthCallbackIn,
  OAuthCallbackOut,
  OAuthProvider,
  PackCreateIn,
  PackOut,
  PackPatchIn,
  Page,
  PublishOut,
  PublishValidationOut,
} from "./api-types";

export const DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1";

export function getApiBaseUrl(): string {
  // `NEXT_PUBLIC_*` is statically inlined by Next.js at build time, which
  // is exactly what we want here — a build-time default that operators can
  // override via env without code changes.
  const fromEnv = process.env.NEXT_PUBLIC_API_BASE_URL;
  return (fromEnv && fromEnv.length > 0 ? fromEnv : DEFAULT_API_BASE_URL).replace(
    /\/+$/,
    "",
  );
}

export class APIError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(opts: {
    status: number;
    code: string;
    message: string;
    details?: unknown;
  }) {
    super(opts.message);
    this.name = "APIError";
    this.status = opts.status;
    this.code = opts.code;
    this.details = opts.details;
  }
}

export interface FetchOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  /** When set, sent as `multipart/form-data`. Object values are coerced to strings. */
  formData?: FormData;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

/**
 * Resolve a relative URL (e.g. ``/api/v1/me``) against the configured base.
 * For an absolute URL we return it as-is — useful when `manifest_url`s in
 * API responses point to a different host.
 */
export function resolveUrl(pathOrUrl: string): string {
  if (/^https?:\/\//.test(pathOrUrl)) return pathOrUrl;
  const base = getApiBaseUrl();
  if (pathOrUrl.startsWith("/")) return `${base}${pathOrUrl}`;
  return `${base}/${pathOrUrl}`;
}

/**
 * Build the headers for an authenticated request. The session token is
 * kept in localStorage so it survives across tabs but is per-device.
 * Server components don't see it; we only call this from client code.
 */
export function authHeaders(token: string | null | undefined): Record<string, string> {
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

export async function apiFetch<T = unknown>(
  pathOrUrl: string,
  opts: FetchOptions & { token?: string | null } = {},
): Promise<T> {
  const url = resolveUrl(pathOrUrl);
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...authHeaders(opts.token ?? null),
    ...(opts.headers ?? {}),
  };

  let body: BodyInit | undefined;
  if (opts.formData) {
    // Don't set Content-Type; the browser adds the correct multipart
    // boundary. Setting it manually would strip the boundary.
    body = opts.formData;
  } else if (opts.body !== undefined) {
    body = JSON.stringify(opts.body);
    headers["Content-Type"] = "application/json";
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: opts.method ?? (body ? "POST" : "GET"),
      headers,
      body,
      signal: opts.signal,
      credentials: "include",
    });
  } catch (err) {
    // Network-layer failure — no response to inspect.
    const message =
      err instanceof Error ? err.message : "Network request failed.";
    throw new APIError({
      status: 0,
      code: "network_error",
      message,
    });
  }

  if (response.status === 204) {
    // No content — caller's responsibility to type as void.
    return undefined as T;
  }

  const text = await response.text();
  let parsed: unknown = undefined;
  if (text.length > 0) {
    try {
      parsed = JSON.parse(text);
    } catch {
      // Non-JSON response (e.g. a proxy error page).
      if (!response.ok) {
        throw new APIError({
          status: response.status,
          code: `http_${response.status}`,
          message: text.slice(0, 500),
        });
      }
      throw new APIError({
        status: response.status,
        code: "invalid_response",
        message: "Server returned a non-JSON body.",
      });
    }
  }

  if (!response.ok) {
    const envelope = parsed as ErrorEnvelope | undefined;
    if (envelope && envelope.error) {
      throw new APIError({
        status: response.status,
        code: envelope.error.code,
        message: envelope.error.message,
        details: envelope.error.details,
      });
    }
    throw new APIError({
      status: response.status,
      code: `http_${response.status}`,
      message: `Request failed with status ${response.status}.`,
    });
  }

  return parsed as T;
}

// --- High-level endpoint wrappers ------------------------------------------

export const api = {
  /** Start an OAuth flow against the backend. The backend's stub provider
   * returns `oauth_not_implemented` (see `backend/app/auth/oauth.py`); the
   * UI must surface this visibly, not silently work around it. */
  oauthCallback(
    provider: OAuthProvider,
    body: OAuthCallbackIn,
    signal?: AbortSignal,
  ): Promise<OAuthCallbackOut> {
    return apiFetch<OAuthCallbackOut>(
      `/auth/oauth/${provider}/callback`,
      { method: "POST", body, signal },
    );
  },

  me(token: string, signal?: AbortSignal): Promise<MeOut> {
    return apiFetch<MeOut>("/me", { token, signal });
  },
  patchMe(token: string, body: MePatchIn, signal?: AbortSignal): Promise<MeOut> {
    return apiFetch<MeOut>("/me", { method: "PATCH", body: body, token, signal });
  },

  createArtist(
    token: string,
    body: ArtistCreateIn,
    signal?: AbortSignal,
  ): Promise<ArtistOut> {
    return apiFetch<ArtistOut>("/artists", { method: "POST", body, token, signal });
  },
  patchArtist(
    token: string,
    artistId: string,
    body: ArtistPatchIn,
    signal?: AbortSignal,
  ): Promise<ArtistOut> {
    return apiFetch<ArtistOut>(`/artists/${encodeURIComponent(artistId)}`, {
      method: "PATCH",
      body,
      token,
      signal,
    });
  },

  /** Dashboard-only listing: list *own* packs via the public list endpoint,
   *  filtered by `artist=`. Public list works without auth. */
  listArtistPacks(
    artistPublicId: string,
    signal?: AbortSignal,
  ): Promise<Page<PackOut>> {
    const q = new URLSearchParams({ artist: artistPublicId, limit: "100" });
    return apiFetch<Page<PackOut>>(`/packs?${q.toString()}`, { signal });
  },
  getPack(packPublicId: string, signal?: AbortSignal): Promise<PackOut> {
    return apiFetch<PackOut>(`/packs/${encodeURIComponent(packPublicId)}`, {
      signal,
    });
  },
  createPack(
    token: string,
    body: PackCreateIn,
    signal?: AbortSignal,
  ): Promise<PackOut> {
    // The backend takes ``artist_public_id`` as a *query* parameter on
    // ``POST /api/v1/packs`` even though ``public_id`` is part of the JSON
    // body — see ``backend/app/api/v1/packs.py``::create_pack.
    const { artist_public_id, ...jsonPayload } = body;
    const q = new URLSearchParams({ artist_public_id });
    return apiFetch<PackOut>(`/packs?${q.toString()}`, {
      method: "POST",
      body: jsonPayload,
      token,
      signal,
    });
  },
  patchPack(
    token: string,
    packPublicId: string,
    body: PackPatchIn,
    signal?: AbortSignal,
  ): Promise<PackOut> {
    return apiFetch<PackOut>(`/packs/${encodeURIComponent(packPublicId)}`, {
      method: "PATCH",
      body,
      token,
      signal,
    });
  },
  deletePack(token: string, packPublicId: string, signal?: AbortSignal): Promise<void> {
    return apiFetch<void>(`/packs/${encodeURIComponent(packPublicId)}`, {
      method: "DELETE",
      token,
      signal,
    });
  },

  validation(
    token: string,
    packPublicId: string,
    signal?: AbortSignal,
  ): Promise<PublishValidationOut> {
    return apiFetch<PublishValidationOut>(
      `/packs/${encodeURIComponent(packPublicId)}/validation`,
      { token, signal },
    );
  },
  publish(
    token: string,
    packPublicId: string,
    signal?: AbortSignal,
  ): Promise<PublishOut> {
    return apiFetch<PublishOut>(
      `/packs/${encodeURIComponent(packPublicId)}/publish`,
      { method: "POST", token, signal },
    );
  },
  unpublish(
    token: string,
    packPublicId: string,
    signal?: AbortSignal,
  ): Promise<PackOut> {
    return apiFetch<PackOut>(
      `/packs/${encodeURIComponent(packPublicId)}/unpublish`,
      { method: "POST", token, signal },
    );
  },

  // Artworks

  uploadArtwork(
    token: string,
    packPublicId: string,
    formData: FormData,
    signal?: AbortSignal,
  ): Promise<ArtworkOut> {
    return apiFetch<ArtworkOut>(
      `/packs/${encodeURIComponent(packPublicId)}/artworks`,
      { method: "POST", formData, token, signal },
    );
  },
  patchArtwork(
    token: string,
    packPublicId: string,
    artworkPublicId: string,
    body: ArtworkPatchIn,
    signal?: AbortSignal,
  ): Promise<ArtworkOut> {
    return apiFetch<ArtworkOut>(
      `/packs/${encodeURIComponent(packPublicId)}/artworks/${encodeURIComponent(artworkPublicId)}`,
      { method: "PATCH", body, token, signal },
    );
  },
  deleteArtwork(
    token: string,
    packPublicId: string,
    artworkPublicId: string,
    signal?: AbortSignal,
  ): Promise<void> {
    return apiFetch<void>(
      `/packs/${encodeURIComponent(packPublicId)}/artworks/${encodeURIComponent(artworkPublicId)}`,
      { method: "DELETE", token, signal },
    );
  },
  regenerateDerivatives(
    token: string,
    packPublicId: string,
    artworkPublicId: string,
    signal?: AbortSignal,
  ): Promise<{ job_id: string; status: string; hint?: string }> {
    return apiFetch<{ job_id: string; status: string; hint?: string }>(
      `/packs/${encodeURIComponent(packPublicId)}/artworks/${encodeURIComponent(artworkPublicId)}/regenerate-derivatives`,
      { method: "POST", token, signal },
    );
  },
  /** C2PA sign endpoint. The backend stub returns 501
   *  ``c2pa_sign_not_implemented`` — the dashboard must call this as its
   *  own explicit action (artist-gated per docs/tech-decisions.md). */
  signProvenance(
    token: string,
    packPublicId: string,
    artworkPublicId: string,
    signal?: AbortSignal,
  ): Promise<unknown> {
    return apiFetch<unknown>(
      `/packs/${encodeURIComponent(packPublicId)}/artworks/${encodeURIComponent(artworkPublicId)}/provenance/sign`,
      { method: "POST", token, signal },
    );
  },
};

export { APIError as APIError_ };