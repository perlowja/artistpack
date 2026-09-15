/**
 * Shared TypeScript types mirroring the Pydantic schemas in
 * `backend/app/schemas/__init__.py`. These are the shapes we expect to
 * receive from the API; the backend is the source of truth
 * (see `docs/api-design.md`).
 */

export interface ErrorBody {
  code: string;
  message: string;
  details?: unknown;
}

export interface ErrorEnvelope {
  error: ErrorBody;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface ArtistSummary {
  id: string;
  public_id: string;
  name: string;
  avatar_url?: string | null;
  website?: string | null;
}

export interface ArtistOut {
  id: string;
  public_id: string;
  name: string;
  bio?: string | null;
  avatar_url?: string | null;
  website?: string | null;
  patreon?: string | null;
  support_url?: string | null;
  socials?: Record<string, string | null> | null;
  links: { kind: string; url: string }[];
  manifest_url: string;
  created_at: string;
  updated_at: string;
}

export interface ArtistCreateIn {
  public_id: string;
  name: string;
  bio?: string;
  website?: string;
  patreon?: string;
  support_url?: string;
  socials?: Record<string, string | null>;
}

export interface ArtistPatchIn {
  name?: string;
  bio?: string;
  website?: string;
  patreon?: string;
  support_url?: string;
  socials?: Record<string, string | null>;
}

export interface PackSummary {
  id: string;
  public_id: string;
  title: string;
  description?: string | null;
  current_version?: string | null;
  status?: string | null;
  manifest_url: string;
  artist: ArtistSummary;
}

export interface PackOut {
  id: string;
  public_id: string;
  title: string;
  description?: string | null;
  current_version?: string | null;
  status?: string | null;
  manifest_url: string;
  manifest_sha256?: string | null;
  artist: ArtistSummary;
  created_at: string;
  updated_at: string;
}

export interface PackCreateIn {
  public_id: string;
  title: string;
  description?: string;
  /** public_id of the artist who owns this pack (query param on the real endpoint) */
  artist_public_id: string;
}

export interface PackPatchIn {
  title?: string;
  description?: string;
}

export interface ArtworkVariantOut {
  file: string;
  sha256: string;
  width: number;
  height: number;
  mime_type?: string | null;
  url: string;
}

export interface ArtworkOut {
  id: string;
  public_id: string;
  title: string;
  description?: string | null;
  original_file: string;
  original_sha256: string;
  width: number;
  height: number;
  mime_type: string;
  orientation: string;
  aspect_ratio: string;
  license?: string | null;
  attribution_name: string;
  attribution_url?: string | null;
  tags: string[];
  variants: ArtworkVariantOut[];
  pack_id: string;
  pack_public_id: string;
  manifest_url: string;
  display?: Record<string, unknown> | null;
  palette?: Record<string, unknown> | null;
  created_at: string;
}

export interface ArtworkPatchIn {
  title?: string;
  description?: string;
  tags?: string[];
  attribution_url?: string;
}

export interface MeOut {
  id: string;
  email?: string | null;
  display_name?: string | null;
  role: string;
  artists: ArtistSummary[];
}

export interface MePatchIn {
  display_name?: string;
}

export interface OAuthCallbackIn {
  code: string;
  state: string;
  redirect_uri: string;
}

export interface OAuthCallbackOut {
  user: MeOut;
  token: string;
  expires_in: number;
}

export interface PublishError {
  path: string;
  message: string;
}

export interface PublishValidationOut {
  pack_id: string;
  version: string;
  errors: PublishError[];
}

export interface PublishOut {
  pack_id: string;
  version: string;
  status: string;
  published_at: string;
  manifest_sha256: string;
}

export type OAuthProvider = "google" | "github";