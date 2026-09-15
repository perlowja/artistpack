"use client";

import { useRef, useState } from "react";
import { api, APIError } from "@/lib/api-client";
import type { ArtworkOut } from "@/lib/api-types";
import { ApiErrorBanner } from "@/components/ApiErrorBanner";

interface Props {
  token: string;
  packPublicId: string;
  onUploaded: (artwork: ArtworkOut) => void;
}

const MAX_BYTES = 25 * 1024 * 1024; // 25 MiB — matches the backend's typical cap.
const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;

interface ClientValidation {
  ok: boolean;
  message?: string;
}

/**
 * Client-side validation for a chosen image. The backend re-validates
 * (MIME sniff, decompression-bomb guard, dimension cap per
 * `docs/security-model.md`); this exists so the user gets fast,
 * actionable feedback before the upload even starts.
 */
export function validateImageClient(file: File): ClientValidation {
  if (!ALLOWED_TYPES.includes(file.type as (typeof ALLOWED_TYPES)[number])) {
    return {
      ok: false,
      message: `Image must be JPEG, PNG, or WebP (got ${file.type || "unknown MIME"}).`,
    };
  }
  if (file.size > MAX_BYTES) {
    return {
      ok: false,
      message: `Image is ${(file.size / 1024 / 1024).toFixed(1)} MiB; max is ${MAX_BYTES / 1024 / 1024} MiB.`,
    };
  }
  return { ok: true };
}

export function ArtworkUploadForm(props: Props) {
  const [publicId, setPublicId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [attributionName, setAttributionName] = useState("");
  const [attributionUrl, setAttributionUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [clientValidation, setClientValidation] = useState<ClientValidation>({
    ok: true,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<APIError | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  function onFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0] ?? null;
    setFile(next);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(next ? URL.createObjectURL(next) : null);
    setClientValidation(next ? validateImageClient(next) : { ok: true });
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError(
        new APIError({
          status: 0,
          code: "validation",
          message: "Choose an image to upload.",
        }),
      );
      return;
    }
    const v = validateImageClient(file);
    if (!v.ok) {
      setError(
        new APIError({
          status: 0,
          code: "validation",
          message: v.message ?? "Invalid image.",
        }),
      );
      return;
    }
    if (!/^[a-z0-9][a-z0-9-]*$/.test(publicId)) {
      setError(
        new APIError({
          status: 0,
          code: "validation",
          message:
            "Artwork public_id must start with a lowercase letter or digit and contain only lowercase letters, digits, and dashes.",
        }),
      );
      return;
    }
    if (title.trim().length === 0) {
      setError(
        new APIError({
          status: 0,
          code: "validation",
          message: "Title is required.",
        }),
      );
      return;
    }
    if (attributionName.trim().length === 0) {
      setError(
        new APIError({
          status: 0,
          code: "validation",
          message: "Attribution display name is required (publish-gate check 4).",
        }),
      );
      return;
    }

    const fd = new FormData();
    fd.append("public_id", publicId);
    fd.append("title", title);
    if (description) fd.append("description", description);
    fd.append("attribution_name", attributionName);
    if (attributionUrl) fd.append("attribution_url", attributionUrl);
    fd.append("file", file);

    setSubmitting(true);
    setError(null);
    try {
      const created = await api.uploadArtwork(
        props.token,
        props.packPublicId,
        fd,
      );
      props.onUploaded(created);
      // Reset
      setPublicId("");
      setTitle("");
      setDescription("");
      setAttributionUrl("");
      setFile(null);
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
      setClientValidation({ ok: true });
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      if (err instanceof APIError) setError(err);
      else
        setError(
          new APIError({
            status: 0,
            code: "unknown",
            message: err instanceof Error ? err.message : "Upload failed.",
          }),
        );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      className="card stack"
      onSubmit={onSubmit}
      data-testid="upload-form"
    >
      <h3 style={{ margin: 0 }}>Upload an artwork</h3>
      <p className="muted" style={{ margin: 0 }}>
        Pick the image, fill in metadata, and upload. Client-side
        preview is local; the actual bytes only leave your browser when
        you click &ldquo;Upload&rdquo;.
      </p>

      {error ? <ApiErrorBanner error={error} /> : null}

      <div>
        <label htmlFor="upload-file">Image</label>
        <input
          id="upload-file"
          ref={fileInputRef}
          type="file"
          accept={ALLOWED_TYPES.join(",")}
          onChange={onFileChange}
          data-testid="upload-file"
        />
        {!clientValidation.ok ? (
          <p className="error-banner" style={{ marginTop: "0.5rem" }}>
            {clientValidation.message}
          </p>
        ) : null}
        {previewUrl ? (
          <img
            src={previewUrl}
            alt="Selected artwork preview"
            className="image-thumb"
            data-testid="upload-preview"
            style={{ marginTop: "0.5rem" }}
          />
        ) : null}
      </div>

      <div>
        <label htmlFor="upload-public-id">Public ID</label>
        <input
          id="upload-public-id"
          type="text"
          required
          pattern="^[a-z0-9][a-z0-9-]*$"
          value={publicId}
          onChange={(e) => setPublicId(e.target.value)}
          placeholder="e.g. dawn-over-kyoto"
          data-testid="upload-public-id"
        />
        <p className="muted" style={{ margin: "0.25rem 0 0" }}>
          Lowercase letters, digits, and dashes. Must be unique within the
          pack.
        </p>
      </div>
      <div>
        <label htmlFor="upload-title">Title</label>
        <input
          id="upload-title"
          type="text"
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          data-testid="upload-title"
        />
      </div>
      <div>
        <label htmlFor="upload-description">Description</label>
        <textarea
          id="upload-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <div>
        <label htmlFor="upload-attribution-name">Attribution display name</label>
        <input
          id="upload-attribution-name"
          type="text"
          required
          value={attributionName}
          onChange={(e) => setAttributionName(e.target.value)}
          placeholder="e.g. Nova Ashworth"
          data-testid="upload-attribution-name"
        />
        <p className="muted" style={{ margin: "0.25rem 0 0" }}>
          Required by publish-gate check 4. This is the byline shown on
          clients when the artwork is used.
        </p>
      </div>
      <div>
        <label htmlFor="upload-attribution-url">Attribution URL (optional)</label>
        <input
          id="upload-attribution-url"
          type="url"
          value={attributionUrl}
          onChange={(e) => setAttributionUrl(e.target.value)}
        />
      </div>
      <div className="btn-row">
        <button
          type="submit"
          disabled={
            submitting ||
            !file ||
            !clientValidation.ok ||
            !publicId ||
            !title ||
            !attributionName
          }
          data-testid="upload-submit"
        >
          {submitting ? "Uploading…" : "Upload"}
        </button>
      </div>
    </form>
  );
}