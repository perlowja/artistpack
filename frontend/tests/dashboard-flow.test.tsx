/**
 * End-to-end-ish flow: log in, list packs, view a pack, see validation,
 * and publish — all against an in-test mocked API.
 *
 * This isn't a "true" Playwright browser test against a running backend
 * (which would also need a real Postgres + OAuth adapter); it's a
 * Vitest+RTL flow that wires every component together against a
 * deterministic mock and asserts the user-visible behavior of the
 * dashboard at a higher level than the per-component tests.
 */

// Mock next/navigation once for the whole file. Per-test overrides would
// require vi.mock hoisting gymnastics that fight Vitest's loader; a single
// stable stub is fine because we always use replace/push as no-ops.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";

const routerStub = { replace: vi.fn(), push: vi.fn() };
vi.mock("next/navigation", () => ({
  useRouter: () => routerStub,
  usePathname: () => "/login",
}));

import LoginPage from "@/app/login/page";
import PacksListPage from "@/app/packs/page";
import PackDetailPage from "@/app/packs/[packPublicId]/page";
import { saveSession, loadSession } from "@/lib/session";

afterEach(() => {
  cleanup();
  routerStub.replace.mockReset();
  routerStub.push.mockReset();
  if (typeof window !== "undefined") {
    window.localStorage.clear();
  }
});

/**
 * Helper: mock the global fetch so we can return different responses
 * for different URLs. Routes are matched longest-prefix first so a
 * generic `/api/v1/packs` rule doesn't shadow `/api/v1/packs/foo`.
 */
function mockFetch(
  routes: Record<string, () => Response | Promise<Response>>,
): void {
  const sortedPrefixes = Object.keys(routes).sort(
    (a, b) => b.length - a.length,
  );
  globalThis.fetch = (async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : (input as Request).url;
    for (const prefix of sortedPrefixes) {
      if (url.includes(prefix)) {
        return routes[prefix]();
      }
    }
    return new Response(
      JSON.stringify({
        error: { code: "not_found", message: `No mock for ${url}` },
      }),
      { status: 404, headers: { "Content-Type": "application/json" } },
    );
  }) as typeof fetch;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("dashboard end-to-end flow (mocked API)", () => {
  it("login page surfaces oauth_not_implemented from the stub provider", async () => {
    mockFetch({
      "/api/v1/auth/oauth/google/callback": () =>
        json(
          {
            error: {
              code: "oauth_not_implemented",
              message:
                "OAuth exchange for provider=google is a stub. Implement app.auth.oauth.<Google|GitHub>Provider before going live.",
              details: { provider: "google" },
            },
          },
          400,
        ),
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText(/Authorization code/i), {
      target: { value: "abc" },
    });
    fireEvent.change(screen.getByLabelText(/^State$/i), {
      target: { value: "xyz" },
    });
    fireEvent.change(screen.getByLabelText(/Redirect URI/i), {
      target: { value: "https://example.com/cb" },
    });

    fireEvent.click(screen.getByTestId("login-submit"));

    // The stub error must surface as a visible banner — the dashboard
    // does NOT silently work around the missing implementation.
    await waitFor(() => {
      expect(screen.getByTestId("api-error")).toHaveTextContent(
        /oauth_not_implemented/,
      );
    });
  });

  it("successful login stores the session and navigates to /me", async () => {
    mockFetch({
      // The login form defaults to `google` as the provider.
      "/api/v1/auth/oauth/google/callback": () =>
        json({
          user: {
            id: "u-1",
            email: "a@b.co",
            display_name: "A",
            role: "user",
            artists: [],
          },
          token: "fake-token-123",
          expires_in: 3600,
        }),
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText(/Authorization code/i), {
      target: { value: "abc" },
    });
    fireEvent.change(screen.getByLabelText(/^State$/i), {
      target: { value: "xyz" },
    });
    fireEvent.change(screen.getByLabelText(/Redirect URI/i), {
      target: { value: "https://example.com/cb" },
    });

    fireEvent.click(screen.getByTestId("login-submit"));

    await waitFor(() => {
      expect(routerStub.replace).toHaveBeenCalledWith("/me");
    });
    const stored = loadSession();
    expect(stored?.token).toBe("fake-token-123");
    expect(stored?.expiresAt).toBeGreaterThan(Date.now());
  });

  it("packs list shows an empty state for users with no packs", async () => {
    saveSession({
      token: "t",
      displayName: "A",
      expiresAt: Date.now() + 60_000,
    });

    mockFetch({
      "/api/v1/me": () =>
        json({
          id: "u-1",
          email: "a@b.co",
          display_name: "A",
          role: "user",
          artists: [{ id: "ar-1", public_id: "nova", name: "Nova" }],
        }),
      "/api/v1/packs": () =>
        json({ items: [], next_cursor: null }),
    });

    render(<PacksListPage />);

    await waitFor(() => {
      expect(screen.getByTestId("pack-list")).toBeInTheDocument();
    });
    expect(
      screen.getByText(/haven\u2019t created any packs yet/i),
    ).toBeInTheDocument();
  });

  it("pack detail renders validation checklist + a disabled publish button when checks fail", async () => {
    saveSession({
      token: "t",
      displayName: "A",
      expiresAt: Date.now() + 60_000,
    });

    mockFetch({
      "/api/v1/packs/autumn-light": () =>
        json({
          id: "p-1",
          public_id: "autumn-light",
          title: "Autumn Light",
          description: "demo",
          current_version: "0.0.1",
          status: "draft",
          manifest_url: "https://example.com/manifest",
          artist: { id: "ar-1", public_id: "nova", name: "Nova" },
          created_at: "2026-09-14T12:00:00Z",
          updated_at: "2026-09-14T12:00:00Z",
        }),
      "/api/v1/packs/autumn-light/validation": () =>
        json({
          pack_id: "autumn-light",
          version: "0.0.1",
          errors: [
            { path: "rights.license", message: "unrecognized license 'foo'" },
          ],
        }),
    });

    render(<PackDetailPage params={{ packPublicId: "autumn-light" }} />);

    await waitFor(() => {
      expect(screen.getByTestId("validation-panel")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId("validation-summary")).toHaveAttribute(
        "data-all-ok",
        "false",
      );
    });
    const btn = screen.getByTestId("publish-button") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("pack detail enables publish when validation passes", async () => {
    saveSession({
      token: "t",
      displayName: "A",
      expiresAt: Date.now() + 60_000,
    });

    mockFetch({
      "/api/v1/packs/autumn-light": () =>
        json({
          id: "p-1",
          public_id: "autumn-light",
          title: "Autumn Light",
          description: "demo",
          current_version: "0.0.1",
          status: "draft",
          manifest_url: "https://example.com/manifest",
          artist: { id: "ar-1", public_id: "nova", name: "Nova" },
          created_at: "2026-09-14T12:00:00Z",
          updated_at: "2026-09-14T12:00:00Z",
        }),
      "/api/v1/packs/autumn-light/validation": () =>
        json({
          pack_id: "autumn-light",
          version: "0.0.1",
          errors: [],
        }),
    });

    render(<PackDetailPage params={{ packPublicId: "autumn-light" }} />);

    await waitFor(() => {
      expect(screen.getByTestId("validation-summary")).toHaveAttribute(
        "data-all-ok",
        "true",
      );
    });
    const btn = screen.getByTestId("publish-button") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });
});

beforeEach(() => {
  // No-op: per-test mocks do their own setup.
});