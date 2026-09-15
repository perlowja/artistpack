"use client";

import { useState } from "react";
import { api, APIError } from "@/lib/api-client";
import type { ArtworkOut } from "@/lib/api-types";
import { ApiErrorBanner } from "@/components/ApiErrorBanner";

interface Props {
  token: string;
  packPublicId: string;
  artwork: ArtworkOut;
  onUpdated: (artwork: ArtworkOut) => void;
  onDeleted: () => void;
}

/**
 * Per-artwork card: edit metadata (title / description / attribution URL),
 * delete the artwork, regenerate derivatives, and run the explicit
 * C2PA provenance-sign step (artist-gated, Task 9 boundary).
 */
export function ArtworkEditForm(props: Props) {
  const a = props.artwork;
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(a.title);
  const [description, setDescription] = useState(a.description ?? "");
  const [attributionUrl, setAttributionUrl] = useState(a.attribution_url ?? "");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [signing, setSigning] = useState(false);
  const [error, setError] = useState<APIError | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  async function onSave(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const updated = await api.patchArtwork(
        props.token,
        props.packPublicId,
        a.public_id,
        {
          title,
          description,
          attribution_url: attributionUrl || undefined,
        },
      );
      props.onUpdated(updated);
      setEditing(false);
    } catch (err) {
      if (err instanceof APIError) setError(err);
      else
        setError(
          new APIError({
            status: 0,
            code: "unknown",
            message: err instanceof Error ? err.message : "Failed to save.",
          }),
        );
    } finally {
      setSaving(false);
    }
  }

  async function onDelete() {
    if (
      !confirm(
        `Delete artwork "${a.public_id}"? This is irreversible while the pack is in draft.`,
      )
    )
      return;
    setDeleting(true);
    setError(null);
    try {
      await api.deleteArtwork(props.token, props.packPublicId, a.public_id);
      props.onDeleted();
    } catch (err) {
      if (err instanceof APIError) setError(err);
      else
        setError(
          new APIError({
            status: 0,
            code: "unknown",
            message: err instanceof Error ? err.message : "Failed to delete.",
          }),
        );
    } finally {
      setDeleting(false);
    }
  }

  async function onRegenerate() {
    setRegenerating(true);
    setError(null);
    setInfo(null);
    try {
      const r = await api.regenerateDerivatives(
        props.token,
        props.packPublicId,
        a.public_id,
      );
      setInfo(
        `Derivative regeneration enqueued (job ${r.job_id}, status ${r.status}).${
          r.hint ? " " + r.hint : ""
        }`,
      );
    } catch (err) {
      if (err instanceof APIError) setError(err);
      else
        setError(
          new APIError({
            status: 0,
            code: "unknown",
            message:
              err instanceof Error ? err.message : "Failed to enqueue job.",
          }),
        );
    } finally {
      setRegenerating(false);
    }
  }

  async function onSignProvenance() {
    if (
      !confirm(
        `Run C2PA signing for "${a.public_id}"? This is the artist-gated provenance step (docs/tech-decisions.md). In this Task 7 build the signing service is stubbed and will return 501 c2pa_sign_not_implemented.`,
      )
    )
      return;
    setSigning(true);
    setError(null);
    setInfo(null);
    try {
      await api.signProvenance(props.token, props.packPublicId, a.public_id);
      setInfo("C2PA signing complete.");
    } catch (err) {
      if (err instanceof APIError) setError(err);
      else
        setError(
          new APIError({
            status: 0,
            code: "unknown",
            message:
              err instanceof Error ? err.message : "Failed to sign provenance.",
          }),
        );
    } finally {
      setSigning(false);
    }
  }

  // Show the first variant as the preview. Real thumbnails are Task 9.
  const previewUrl = a.variants[0]?.url ?? null;

  return (
    <div className="artwork-card stack" data-testid="artwork-card">
      {previewUrl ? (
        <img
          src={previewUrl}
          alt={`Preview of ${a.title}`}
          className="image-thumb"
          data-testid="artwork-thumb"
        />
      ) : (
        <div
          className="image-thumb"
          aria-label="No preview"
          style={{
            aspectRatio: `${a.width || 16} / ${a.height || 9}`,
            background: "var(--code-bg)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--muted)",
            fontSize: "0.8rem",
          }}
        >
          {a.width}×{a.height} {a.mime_type}
        </div>
      )}

      <div>
        <strong>{a.title}</strong>{" "}
        <span className="muted">
          @{a.public_id} · {a.width}×{a.height} · {a.orientation}
        </span>
      </div>
      {a.description ? (
        <div className="muted" style={{ fontSize: "0.9rem" }}>
          {a.description}
        </div>
      ) : null}
      <div className="muted" style={{ fontSize: "0.85rem" }}>
        Attribution: {a.attribution_name}
        {a.attribution_url ? ` (${a.attribution_url})` : ""}
      </div>

      {error ? <ApiErrorBanner error={error} /> : null}
      {info ? (
        <div className="info-banner" data-testid="artwork-info">
          {info}
        </div>
      ) : null}

      {editing ? (
        <form className="stack" onSubmit={onSave}>
          <div>
            <label htmlFor={`title-${a.id}`}>Title</label>
            <input
              id={`title-${a.id}`}
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor={`desc-${a.id}`}>Description</label>
            <textarea
              id={`desc-${a.id}`}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor={`attr-${a.id}`}>Attribution URL</label>
            <input
              id={`attr-${a.id}`}
              type="url"
              value={attributionUrl}
              onChange={(e) => setAttributionUrl(e.target.value)}
            />
          </div>
          <div className="btn-row">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setEditing(false);
                setTitle(a.title);
                setDescription(a.description ?? "");
                setAttributionUrl(a.attribution_url ?? "");
              }}
            >
              Cancel
            </button>
            <button type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      ) : (
        <div className="btn-row">
          <button
            type="button"
            className="btn-secondary"
            onClick={() => setEditing(true)}
            data-testid={`edit-${a.public_id}`}
          >
            Edit metadata
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={onRegenerate}
            disabled={regenerating}
            data-testid={`regen-${a.public_id}`}
          >
            {regenerating ? "Enqueuing…" : "Regenerate derivatives"}
          </button>
          <button
            type="button"
            onClick={onSignProvenance}
            disabled={signing}
            data-testid={`sign-${a.public_id}`}
            title="Run the C2PA signing step explicitly (artist-gated)."
          >
            {signing ? "Signing…" : "Sign C2PA provenance"}
          </button>
          <button
            type="button"
            className="btn-danger"
            onClick={onDelete}
            disabled={deleting}
            data-testid={`delete-${a.public_id}`}
          >
            {deleting ? "Deleting…" : "Delete"}
          </button>
        </div>
      )}
    </div>
  );
}