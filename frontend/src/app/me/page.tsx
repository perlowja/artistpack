"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, APIError } from "@/lib/api-client";
import { useSession, clearSession } from "@/lib/session";
import type { ArtistOut, MeOut } from "@/lib/api-types";
import { ApiErrorBanner } from "@/components/ApiErrorBanner";

export default function MePage() {
  const router = useRouter();
  const session = useSession();
  const [me, setMe] = useState<MeOut | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [savingMe, setSavingMe] = useState(false);
  const [error, setError] = useState<APIError | null>(null);

  // Artist form state — only the fields the dashboard can edit per the API.
  const [newArtistPublicId, setNewArtistPublicId] = useState("");
  const [newArtistName, setNewArtistName] = useState("");
  const [creatingArtist, setCreatingArtist] = useState(false);
  const [artists, setArtists] = useState<ArtistOut[]>([]);
  const [editingArtist, setEditingArtist] = useState<string | null>(null);
  const [artistDraft, setArtistDraft] = useState<Partial<ArtistOut>>({});
  const [savingArtist, setSavingArtist] = useState(false);

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      if (!session) return;
      setError(null);
      try {
        const meOut = await api.me(session.token, signal);
        setMe(meOut);
        setDisplayName(meOut.display_name ?? "");
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
              message: err instanceof Error ? err.message : "Failed to load profile.",
            }),
          );
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

  // Load the artist profiles for editing.
  useEffect(() => {
    if (!session || !me) return;
    const controller = new AbortController();
    (async () => {
      try {
        const loaded: ArtistOut[] = [];
        for (const summary of me.artists) {
          const full = await api
            .patchArtist === undefined
            ? null
            : null;
          // We use the public read endpoint here (no auth required).
          const res = await fetch(
            `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1"}/artists/${encodeURIComponent(summary.public_id)}`,
            { signal: controller.signal },
          );
          if (res.ok) {
            loaded.push((await res.json()) as ArtistOut);
          }
        }
        setArtists(loaded);
      } catch {
        /* swallow */
      }
    })();
    return () => controller.abort();
  }, [session, me]);

  async function onSaveMe(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session) return;
    setSavingMe(true);
    setError(null);
    try {
      const updated = await api.patchMe(session.token, {
        display_name: displayName,
      });
      setMe(updated);
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
      setSavingMe(false);
    }
  }

  async function onCreateArtist(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session) return;
    if (!/^[a-z0-9][a-z0-9-]*$/.test(newArtistPublicId)) {
      setError(
        new APIError({
          status: 0,
          code: "validation",
          message:
            "Artist public_id must start with a letter or digit and contain only lowercase letters, digits, and dashes.",
        }),
      );
      return;
    }
    if (newArtistName.trim().length === 0) {
      setError(
        new APIError({
          status: 0,
          code: "validation",
          message: "Artist name is required.",
        }),
      );
      return;
    }
    setCreatingArtist(true);
    setError(null);
    try {
      const created = await api.createArtist(session.token, {
        public_id: newArtistPublicId,
        name: newArtistName.trim(),
      });
      setArtists((prev) => [...prev, created]);
      setNewArtistName("");
      setNewArtistPublicId("");
      // Refresh me so the new artist shows up in /me.artists[]
      await refresh();
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
      setCreatingArtist(false);
    }
  }

  async function onSaveArtist(publicId: string) {
    if (!session) return;
    setSavingArtist(true);
    setError(null);
    try {
      const updated = await api.patchArtist(session.token, publicId, {
        name: (artistDraft.name as string | undefined) ?? undefined,
        bio: (artistDraft.bio as string | undefined) ?? undefined,
        website: (artistDraft.website as string | undefined) ?? undefined,
        patreon: (artistDraft.patreon as string | undefined) ?? undefined,
        support_url: (artistDraft.support_url as string | undefined) ?? undefined,
      });
      setArtists((prev) =>
        prev.map((a) => (a.public_id === publicId ? updated : a)),
      );
      setEditingArtist(null);
      setArtistDraft({});
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
      setSavingArtist(false);
    }
  }

  if (!session) return <p className="loading">Redirecting…</p>;
  if (!me && !error) return <p className="loading">Loading profile…</p>;

  return (
    <div className="stack">
      <h1>Your profile</h1>
      {error ? <ApiErrorBanner error={error} /> : null}

      {me ? (
        <form className="card stack" onSubmit={onSaveMe} data-testid="me-form">
          <div>
            <label>User ID</label>
            <div className="muted">
              <code>{me.id}</code>
            </div>
          </div>
          <div>
            <label>Email</label>
            <div className="muted">{me.email ?? "(none)"}</div>
          </div>
          <div>
            <label>Role</label>
            <div>
              <span className="tag">{me.role}</span>
            </div>
          </div>
          <div>
            <label htmlFor="display_name">Display name</label>
            <input
              id="display_name"
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </div>
          <div className="btn-row">
            <button type="submit" disabled={savingMe} data-testid="me-save">
              {savingMe ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      ) : null}

      <section className="card stack" data-testid="artists-section">
        <h2 style={{ margin: 0 }}>Artist profiles</h2>
        <p className="muted" style={{ margin: 0 }}>
          Artist profiles are the public-facing identity you publish under.
          One user can own several (for collaboration, separate names, etc.).
        </p>

        {artists.length === 0 ? (
          <div className="notice">No artist profiles yet. Create one below.</div>
        ) : (
          <ul className="stack" style={{ listStyle: "none", padding: 0 }}>
            {artists.map((a) => (
              <li key={a.public_id} className="card" data-testid="artist-row">
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <div>
                    <strong>{a.name}</strong>{" "}
                    <span className="muted">@{a.public_id}</span>
                  </div>
                  <div className="btn-row">
                    {editingArtist === a.public_id ? (
                      <>
                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={() => {
                            setEditingArtist(null);
                            setArtistDraft({});
                          }}
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          disabled={savingArtist}
                          onClick={() => onSaveArtist(a.public_id)}
                        >
                          {savingArtist ? "Saving…" : "Save"}
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => {
                          setEditingArtist(a.public_id);
                          setArtistDraft({
                            name: a.name,
                            bio: a.bio ?? "",
                            website: a.website ?? "",
                            patreon: a.patreon ?? "",
                            support_url: a.support_url ?? "",
                          });
                        }}
                      >
                        Edit
                      </button>
                    )}
                  </div>
                </div>
                {editingArtist === a.public_id ? (
                  <div className="stack" style={{ marginTop: "0.75rem" }}>
                    <div>
                      <label htmlFor={`name-${a.public_id}`}>Name</label>
                      <input
                        id={`name-${a.public_id}`}
                        type="text"
                        value={(artistDraft.name as string) ?? ""}
                        onChange={(e) =>
                          setArtistDraft((d) => ({ ...d, name: e.target.value }))
                        }
                      />
                    </div>
                    <div>
                      <label htmlFor={`bio-${a.public_id}`}>Bio</label>
                      <textarea
                        id={`bio-${a.public_id}`}
                        value={(artistDraft.bio as string) ?? ""}
                        onChange={(e) =>
                          setArtistDraft((d) => ({ ...d, bio: e.target.value }))
                        }
                      />
                    </div>
                    <div>
                      <label htmlFor={`website-${a.public_id}`}>Website</label>
                      <input
                        id={`website-${a.public_id}`}
                        type="url"
                        value={(artistDraft.website as string) ?? ""}
                        onChange={(e) =>
                          setArtistDraft((d) => ({
                            ...d,
                            website: e.target.value,
                          }))
                        }
                      />
                    </div>
                    <div>
                      <label htmlFor={`patreon-${a.public_id}`}>Patreon</label>
                      <input
                        id={`patreon-${a.public_id}`}
                        type="url"
                        value={(artistDraft.patreon as string) ?? ""}
                        onChange={(e) =>
                          setArtistDraft((d) => ({
                            ...d,
                            patreon: e.target.value,
                          }))
                        }
                      />
                    </div>
                    <div>
                      <label htmlFor={`support-${a.public_id}`}>Support URL</label>
                      <input
                        id={`support-${a.public_id}`}
                        type="url"
                        value={(artistDraft.support_url as string) ?? ""}
                        onChange={(e) =>
                          setArtistDraft((d) => ({
                            ...d,
                            support_url: e.target.value,
                          }))
                        }
                      />
                    </div>
                  </div>
                ) : (
                  <div className="muted" style={{ marginTop: "0.5rem" }}>
                    {a.bio ? a.bio : <em>No bio</em>}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}

        <form className="stack" onSubmit={onCreateArtist} data-testid="new-artist-form">
          <h3 style={{ margin: 0 }}>Create a new artist profile</h3>
          <div>
            <label htmlFor="new-artist-public-id">Public ID</label>
            <input
              id="new-artist-public-id"
              type="text"
              required
              minLength={1}
              pattern="^[a-z0-9][a-z0-9-]*$"
              value={newArtistPublicId}
              onChange={(e) => setNewArtistPublicId(e.target.value)}
              placeholder="e.g. nova-ashworth"
            />
            <p className="muted" style={{ margin: "0.25rem 0 0" }}>
              Lowercase letters, digits, and dashes. Cannot be changed later.
            </p>
          </div>
          <div>
            <label htmlFor="new-artist-name">Display name</label>
            <input
              id="new-artist-name"
              type="text"
              required
              minLength={1}
              value={newArtistName}
              onChange={(e) => setNewArtistName(e.target.value)}
            />
          </div>
          <div className="btn-row">
            <button type="submit" disabled={creatingArtist}>
              {creatingArtist ? "Creating…" : "Create artist"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}