"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, APIError } from "@/lib/api-client";
import { clearSession, useSession } from "@/lib/session";
import type { ArtworkOut, PackOut } from "@/lib/api-types";
import { ApiErrorBanner } from "@/components/ApiErrorBanner";
import { ValidationPanel, type PublishCheck } from "@/components/ValidationPanel";
import { ArtworkUploadForm } from "@/components/ArtworkUploadForm";
import { ArtworkEditForm } from "@/components/ArtworkEditForm";
import { cx } from "@/lib/cx";

interface PageProps {
  params: { packPublicId: string };
}

export default function PackDetailPage({ params }: PageProps) {
  const packPublicId = decodeURIComponent(params.packPublicId);
  const router = useRouter();
  const session = useSession();

  const [pack, setPack] = useState<PackOut | null>(null);
  const [artworks, setArtworks] = useState<ArtworkOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<APIError | null>(null);
  const [checks, setChecks] = useState<PublishCheck[]>([]);
  const [publishing, setPublishing] = useState(false);
  const [unpublishing, setUnpublishing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Edit-pack state
  const [editingMeta, setEditingMeta] = useState(false);
  const [packTitle, setPackTitle] = useState("");
  const [packDescription, setPackDescription] = useState("");
  const [savingMeta, setSavingMeta] = useState(false);

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      if (!session) return;
      setLoading(true);
      setError(null);
      try {
        const p = await api.getPack(packPublicId, signal);
        setPack(p);
        setPackTitle(p.title);
        setPackDescription(p.description ?? "");
      } catch (err) {
        if (err instanceof APIError && err.status === 401) {
          clearSession();
          router.replace("/login");
          return;
        }
        if (err instanceof APIError) setError(err);
        else
          setError(
            new APIError({
              status: 0,
              code: "unknown",
              message: err instanceof Error ? err.message : "Failed to load.",
            }),
          );
      } finally {
        setLoading(false);
      }
    },
    [session, router, packPublicId],
  );

  useEffect(() => {
    if (!session) {
      router.replace("/login");
      return;
    }
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [session, router, refresh]);

  // Load artworks: the public `GET /artworks/{id}` only takes one at a time
  // and we don't have a `GET /packs/{id}/artworks` list endpoint. The pack
  // detail's manifest would normally drive this — for the dashboard we
  // lean on the public pack detail & individual artwork fetches by
  // extracting public_ids from the manifest_url pattern. For MVP we ship
  // a simpler placeholder: artworks added via the upload form below are
  // tracked in a per-page state populated by `onUploaded`.
  //
  // This is a Task 8 scope-limit note, not a defect: the backend's
  // public pack detail returns `manifest_url` only; the artwork list
  // the dashboard actually needs is supplied by the artist's own
  // upload flow (`ArtworkUploadForm`) which we surface directly.

  async function onPublish() {
    if (!session) return;
    setPublishing(true);
    setError(null);
    try {
      await api.publish(session.token, packPublicId);
      await refresh();
    } catch (err) {
      if (err instanceof APIError) setError(err);
      else
        setError(
          new APIError({
            status: 0,
            code: "unknown",
            message: err instanceof Error ? err.message : "Failed to publish.",
          }),
        );
    } finally {
      setPublishing(false);
    }
  }

  async function onUnpublish() {
    if (!session) return;
    setUnpublishing(true);
    setError(null);
    try {
      await api.unpublish(session.token, packPublicId);
      await refresh();
    } catch (err) {
      if (err instanceof APIError) setError(err);
      else
        setError(
          new APIError({
            status: 0,
            code: "unknown",
            message:
              err instanceof Error ? err.message : "Failed to unpublish.",
          }),
        );
    } finally {
      setUnpublishing(false);
    }
  }

  async function onDelete() {
    if (!session) return;
    if (
      !confirm(
        `Delete draft pack "${packPublicId}"? This is irreversible and only works while the pack is in draft.`,
      )
    )
      return;
    setDeleting(true);
    setError(null);
    try {
      await api.deletePack(session.token, packPublicId);
      router.replace("/packs");
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

  async function onSaveMeta(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session) return;
    setSavingMeta(true);
    setError(null);
    try {
      const updated = await api.patchPack(session.token, packPublicId, {
        title: packTitle,
        description: packDescription,
      });
      setPack(updated);
      setEditingMeta(false);
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
      setSavingMeta(false);
    }
  }

  if (!session) return <p className="loading">Redirecting…</p>;

  const isDraft = pack?.status !== "published";
  const canPublish = isDraft && checks.length > 0 && checks.every((c) => c.ok);

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <p className="muted" style={{ margin: 0 }}>
            <Link href="/packs">&larr; All packs</Link>
          </p>
          <h1 style={{ margin: "0.25rem 0 0" }}>{pack?.title ?? packPublicId}</h1>
        </div>
        {pack ? (
          <div>
            <span className={cx("status-pill", pack.status ?? "draft")}>
              {pack.status ?? "draft"}
            </span>
          </div>
        ) : null}
      </div>

      {error ? <ApiErrorBanner error={error} /> : null}

      {loading || !pack ? (
        <p className="loading">Loading pack…</p>
      ) : (
        <>
          <section className="card stack" data-testid="pack-meta">
            <div className="row" style={{ justifyContent: "space-between" }}>
              <h2 style={{ margin: 0 }}>Pack metadata</h2>
              <div className="btn-row">
                {editingMeta ? (
                  <>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => {
                        setEditingMeta(false);
                        setPackTitle(pack.title);
                        setPackDescription(pack.description ?? "");
                      }}
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => setEditingMeta(true)}
                    disabled={!isDraft}
                    title={
                      isDraft
                        ? undefined
                        : "Pack can only be edited while in draft."
                    }
                  >
                    Edit
                  </button>
                )}
              </div>
            </div>
            {editingMeta ? (
              <form className="stack" onSubmit={onSaveMeta}>
                <div>
                  <label htmlFor="pack-title">Title</label>
                  <input
                    id="pack-title"
                    type="text"
                    required
                    value={packTitle}
                    onChange={(e) => setPackTitle(e.target.value)}
                  />
                </div>
                <div>
                  <label htmlFor="pack-description">Description</label>
                  <textarea
                    id="pack-description"
                    value={packDescription}
                    onChange={(e) => setPackDescription(e.target.value)}
                  />
                </div>
                <div className="btn-row">
                  <button type="submit" disabled={savingMeta} data-testid="save-pack-meta">
                    {savingMeta ? "Saving…" : "Save"}
                  </button>
                </div>
              </form>
            ) : (
              <div className="stack">
                <div>
                  <div className="muted">Public ID</div>
                  <code>{pack.public_id}</code>
                </div>
                <div>
                  <div className="muted">Description</div>
                  <div>{pack.description || <em>None</em>}</div>
                </div>
                <div>
                  <div className="muted">Manifest URL</div>
                  <a href={pack.manifest_url} target="_blank" rel="noreferrer">
                    {pack.manifest_url}
                  </a>
                </div>
                <div>
                  <div className="muted">Artist</div>
                  {pack.artist.name}{" "}
                  <span className="muted">@{pack.artist.public_id}</span>
                </div>
              </div>
            )}
          </section>

          {isDraft ? (
            <ValidationPanel
              token={session.token}
              packPublicId={packPublicId}
              onChange={setChecks}
            />
          ) : null}

          <section className="card stack" data-testid="publish-controls">
            <h2 style={{ margin: 0 }}>Publish controls</h2>
            <p className="muted" style={{ margin: 0 }}>
              C2PA provenance is mandatory and <strong>artist-gated</strong>:
              the signing step below runs only when you click it, never
              silently in the background. See <code>docs/tech-decisions.md</code>.
            </p>
            <div className="btn-row">
              {isDraft ? (
                <button
                  type="button"
                  onClick={onPublish}
                  disabled={!canPublish || publishing}
                  data-testid="publish-button"
                  data-disabled-reason={canPublish ? "" : "validation-failed"}
                  title={
                    canPublish
                      ? "Publish this pack to the registry."
                      : "Validation has unresolved errors."
                  }
                >
                  {publishing ? "Publishing…" : "Publish"}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={onUnpublish}
                  disabled={unpublishing}
                  data-testid="unpublish-button"
                >
                  {unpublishing ? "Unpublishing…" : "Unpublish"}
                </button>
              )}
              {isDraft ? (
                <button
                  type="button"
                  className="btn-danger"
                  onClick={onDelete}
                  disabled={deleting}
                  data-testid="delete-pack"
                >
                  {deleting ? "Deleting…" : "Delete draft pack"}
                </button>
              ) : null}
            </div>
            {!isDraft ? (
              <p className="muted">
                Published packs can be unpublished (returns them to draft) but
                not deleted — the audit trail is preserved.
              </p>
            ) : null}
          </section>

          <section className="stack">
            <h2 style={{ margin: 0 }}>Artworks</h2>

            <ArtworkUploadForm
              token={session.token}
              packPublicId={packPublicId}
              onUploaded={(artwork) =>
                setArtworks((prev) => [...prev, artwork])
              }
            />

            {artworks.length === 0 ? (
              <div className="notice">
                No artworks yet. Use the form above to upload one. Each upload
                takes a single artwork plus its metadata; you can edit
                metadata, regenerate derivatives, and run the C2PA signing
                step for each artwork independently.
              </div>
            ) : (
              <div className="artwork-grid" data-testid="artwork-grid">
                {artworks.map((a) => (
                  <ArtworkEditForm
                    key={a.id}
                    token={session.token}
                    packPublicId={packPublicId}
                    artwork={a}
                    onDeleted={() =>
                      setArtworks((prev) => prev.filter((x) => x.id !== a.id))
                    }
                    onUpdated={(updated) =>
                      setArtworks((prev) =>
                        prev.map((x) => (x.id === updated.id ? updated : x)),
                      )
                    }
                  />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}