"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, APIError } from "@/lib/api-client";
import { useSession, clearSession } from "@/lib/session";
import type { MeOut, PackOut } from "@/lib/api-types";
import { ApiErrorBanner } from "@/components/ApiErrorBanner";
import { cx } from "@/lib/cx";

export default function PacksListPage() {
  const router = useRouter();
  const session = useSession();
  const [me, setMe] = useState<MeOut | null>(null);
  const [packs, setPacks] = useState<PackOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<APIError | null>(null);

  // Create form state
  const [publicId, setPublicId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [artistPublicId, setArtistPublicId] = useState("");
  const [creating, setCreating] = useState(false);

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      if (!session) return;
      setLoading(true);
      setError(null);
      try {
        const meOut = await api.me(session.token, signal);
        setMe(meOut);
        const collected: PackOut[] = [];
        for (const summary of meOut.artists) {
          const res = await api.listArtistPacks(summary.public_id, signal);
          collected.push(...res.items);
        }
        setPacks(collected);
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
    [session, router],
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

  // Default the create form's artist to the first one the user owns.
  useEffect(() => {
    if (me && me.artists.length > 0 && !artistPublicId) {
      setArtistPublicId(me.artists[0].public_id);
    }
  }, [me, artistPublicId]);

  async function onCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session) return;
    if (!/^[a-z0-9.][a-z0-9.-]*$/.test(publicId)) {
      setError(
        new APIError({
          status: 0,
          code: "validation",
          message:
            "Pack public_id must start with a lowercase letter, digit, or dot and contain only lowercase letters, digits, dots, and dashes.",
        }),
      );
      return;
    }
    if (title.trim().length === 0) {
      setError(
        new APIError({
          status: 0,
          code: "validation",
          message: "Pack title is required.",
        }),
      );
      return;
    }
    if (!artistPublicId) {
      setError(
        new APIError({
          status: 0,
          code: "validation",
          message: "Pick an artist to own this pack.",
        }),
      );
      return;
    }
    setCreating(true);
    setError(null);
    try {
      const created = await api.createPack(session.token, {
        public_id: publicId,
        title: title.trim(),
        description: description.trim() || undefined,
        artist_public_id: artistPublicId,
      });
      router.push(`/packs/${encodeURIComponent(created.public_id)}`);
    } catch (err) {
      if (err instanceof APIError) setError(err);
      else
        setError(
          new APIError({
            status: 0,
            code: "unknown",
            message: err instanceof Error ? err.message : "Failed.",
          }),
        );
    } finally {
      setCreating(false);
    }
  }

  if (!session) return <p className="loading">Redirecting…</p>;

  return (
    <div className="stack">
      <h1>Packs</h1>
      {error ? <ApiErrorBanner error={error} /> : null}

      <section className="card stack" data-testid="pack-list">
        <h2 style={{ margin: 0 }}>Your packs</h2>
        {loading ? (
          <p className="loading">Loading packs…</p>
        ) : packs.length === 0 ? (
          <div className="notice">
            You haven&rsquo;t created any packs yet. Use the form below to make
            a draft. You&rsquo;ll be able to upload artworks and publish once
            it has at least one artwork with verified C2PA provenance.
          </div>
        ) : (
          <table className="simple">
            <thead>
              <tr>
                <th>Title</th>
                <th>Public ID</th>
                <th>Status</th>
                <th>Version</th>
                <th>Artist</th>
              </tr>
            </thead>
            <tbody>
              {packs.map((p) => (
                <tr key={p.public_id} data-testid="pack-row">
                  <td>
                    <Link
                      href={`/packs/${encodeURIComponent(p.public_id)}`}
                      data-testid="pack-link"
                    >
                      {p.title}
                    </Link>
                  </td>
                  <td>
                    <code>{p.public_id}</code>
                  </td>
                  <td>
                    <span className={cx("status-pill", p.status ?? "draft")}>
                      {p.status ?? "draft"}
                    </span>
                  </td>
                  <td>{p.current_version ?? "—"}</td>
                  <td>
                    {p.artist.name}{" "}
                    <span className="muted">@{p.artist.public_id}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {me && me.artists.length > 0 ? (
        <section className="card stack" data-testid="new-pack-form">
          <h2 style={{ margin: 0 }}>Create a draft pack</h2>
          <p className="muted" style={{ margin: 0 }}>
            A draft pack is invisible publicly until you publish it. Publish
            is gated by the four validation checks — see
            {" "}<code>docs/api-design.md</code>{" "}§&ldquo;the gate&rdquo;.
          </p>
          <form className="stack" onSubmit={onCreate}>
            <div>
              <label htmlFor="artist_public_id">Artist</label>
              <select
                id="artist_public_id"
                value={artistPublicId}
                onChange={(e) => setArtistPublicId(e.target.value)}
                required
              >
                {me.artists.map((a) => (
                  <option key={a.public_id} value={a.public_id}>
                    {a.name} (@{a.public_id})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="public_id">Public ID</label>
              <input
                id="public_id"
                type="text"
                required
                minLength={1}
                pattern="^[a-z0-9.][a-z0-9.-]*$"
                value={publicId}
                onChange={(e) => setPublicId(e.target.value)}
                placeholder="e.g. autumn-light"
              />
              <p className="muted" style={{ margin: "0.25rem 0 0" }}>
                Stable identifier used in the manifest URL.
              </p>
            </div>
            <div>
              <label htmlFor="title">Title</label>
              <input
                id="title"
                type="text"
                required
                minLength={1}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="description">Description</label>
              <textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div className="btn-row">
              <button type="submit" disabled={creating} data-testid="create-pack">
                {creating ? "Creating…" : "Create draft pack"}
              </button>
            </div>
          </form>
        </section>
      ) : (
        <div className="warning-banner">
          You need at least one artist profile before you can create packs.{" "}
          <Link href="/me">Create one on the Profile page.</Link>
        </div>
      )}
    </div>
  );
}