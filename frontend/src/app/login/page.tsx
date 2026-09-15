"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, APIError } from "@/lib/api-client";
import { saveSession } from "@/lib/session";
import type { OAuthProvider } from "@/lib/api-types";
import { ApiErrorBanner } from "@/components/ApiErrorBanner";

const PROVIDERS: OAuthProvider[] = ["google", "github"];

/**
 * Login page. The real flow is an OAuth redirect from the artist's
 * provider, which lands them back here on ``/login?code=&state=`` where
 * the dashboard POSTs to ``/api/v1/auth/oauth/{provider}/callback``.
 *
 * For Task 8 we ship the **full UI flow** against the stubbed backend:
 * the artist fills in the `code` / `state` / `redirect_uri` they got from
 * their provider (or, in dev, anything they want), picks the provider,
 * and the dashboard hits the real endpoint shape. The backend stub
 * returns ``oauth_not_implemented`` — we surface that visibly rather than
 * faking success client-side.
 */
export default function LoginPage() {
  const router = useRouter();
  const [provider, setProvider] = useState<OAuthProvider>("google");
  const [code, setCode] = useState("");
  const [state, setState] = useState("");
  const [redirectUri, setRedirectUri] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<APIError | null>(null);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.oauthCallback(provider, {
        code: code.trim(),
        state: state.trim(),
        redirect_uri: redirectUri.trim(),
      });
      saveSession({
        token: result.token,
        displayName: result.user.display_name ?? result.user.email ?? null,
        expiresAt: Date.now() + result.expires_in * 1000,
      });
      router.replace("/me");
    } catch (err) {
      if (err instanceof APIError) {
        setError(err);
      } else {
        setError(
          new APIError({
            status: 0,
            code: "unknown",
            message:
              err instanceof Error ? err.message : "Unknown error.",
          }),
        );
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="stack">
      <h1>Sign in</h1>
      <p className="muted">
        Sign in with the OAuth provider you used for your ArtistPack account.
        The dashboard exchanges the authorization code for a session token;
        a stubbed backend will return <span className="kbd">oauth_not_implemented</span>
        &mdash; see <code>backend/app/auth/oauth.py</code>. The UI surfaces that
        as a visible error rather than pretending success.
      </p>

      {error ? <ApiErrorBanner error={error} /> : null}

      <form className="card stack" onSubmit={onSubmit} data-testid="login-form">
        <div>
          <label htmlFor="provider">Provider</label>
          <select
            id="provider"
            value={provider}
            onChange={(e) => setProvider(e.target.value as OAuthProvider)}
          >
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="code">Authorization code</label>
          <input
            id="code"
            type="text"
            required
            minLength={1}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="from the OAuth provider redirect"
            autoComplete="off"
          />
        </div>
        <div>
          <label htmlFor="state">State</label>
          <input
            id="state"
            type="text"
            required
            minLength={1}
            value={state}
            onChange={(e) => setState(e.target.value)}
            placeholder="anti-CSRF state value"
            autoComplete="off"
          />
        </div>
        <div>
          <label htmlFor="redirect_uri">Redirect URI</label>
          <input
            id="redirect_uri"
            type="url"
            required
            minLength={1}
            value={redirectUri}
            onChange={(e) => setRedirectUri(e.target.value)}
            placeholder="https://dashboard.example.com/oauth/callback"
          />
        </div>
        <div className="btn-row">
          <button type="submit" disabled={submitting} data-testid="login-submit">
            {submitting ? "Signing in…" : `Sign in with ${provider}`}
          </button>
        </div>
      </form>
    </div>
  );
}