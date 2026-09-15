import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { APIError, apiFetch, api, DEFAULT_API_BASE_URL } from "@/lib/api-client";
import type {
  PublishOut,
  PublishValidationOut,
  MeOut,
} from "@/lib/api-types";

/**
 * The dashboard surfaces backend errors as `APIError` instances with the
 * envelope shape mandated by `docs/api-design.md`:
 *   {"error": {"code", "message", "details"}}.
 * These tests pin down that behavior at the client level.
 */

function envelope(code: string, message: string, details?: unknown): unknown {
  return { error: { code, message, details } };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("apiFetch error handling", () => {
  let originalFetch: typeof fetch;
  let lastUrl: string | null = null;
  let lastInit: RequestInit | null = null;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    lastUrl = null;
    lastInit = null;
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      lastUrl = typeof input === "string" ? input : input.toString();
      lastInit = init ?? null;
      return jsonResponse({}, 200);
    }) as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("resolves relative paths against the configured base URL", async () => {
    await apiFetch("/me");
    expect(lastUrl).toBe(`${DEFAULT_API_BASE_URL}/me`);
  });

  it("attaches Authorization header when given a token", async () => {
    await apiFetch("/me", { token: "abc.def.ghi" });
    const headers = (lastInit?.headers ?? {}) as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer abc.def.ghi");
  });

  it("serializes JSON body and sets Content-Type", async () => {
    await apiFetch("/me", {
      method: "PATCH",
      token: "t",
      body: { display_name: "New" },
    });
    expect(lastInit?.body).toBe(JSON.stringify({ display_name: "New" }));
    const headers = (lastInit?.headers ?? {}) as Record<string, string>;
    expect(headers["Content-Type"]).toBe("application/json");
  });

  it("surfaces an APIError whose details come straight from the backend envelope", async () => {
    globalThis.fetch = (async () =>
      jsonResponse(
        envelope("publish_validation_failed", "Pack failed the publish gate.", {
          errors: [
            { path: "rights.license", message: "unrecognized license 'foo'" },
          ],
        }),
        422,
      )) as typeof fetch;

    try {
      await apiFetch("/packs/p/publish", { method: "POST", token: "t" });
      throw new Error("expected throw");
    } catch (err) {
      expect(err).toBeInstanceOf(APIError);
      const apiErr = err as APIError;
      expect(apiErr.status).toBe(422);
      expect(apiErr.code).toBe("publish_validation_failed");
      expect(apiErr.details).toEqual({
        errors: [
          { path: "rights.license", message: "unrecognized license 'foo'" },
        ],
      });
    }
  });

  it("maps network failures to APIError with code network_error", async () => {
    globalThis.fetch = (async () => {
      throw new TypeError("Failed to fetch");
    }) as typeof fetch;

    try {
      await apiFetch("/me");
      throw new Error("expected throw");
    } catch (err) {
      expect(err).toBeInstanceOf(APIError);
      const apiErr = err as APIError;
      expect(apiErr.status).toBe(0);
      expect(apiErr.code).toBe("network_error");
    }
  });

  it("returns undefined for 204 No Content responses", async () => {
    globalThis.fetch = (async () =>
      new Response(null, { status: 204 })) as typeof fetch;

    const result = await apiFetch("/packs/p", { method: "DELETE", token: "t" });
    expect(result).toBeUndefined();
  });
});

describe("typed endpoint wrappers", () => {
  let originalFetch: typeof fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("validation() returns the parsed response", async () => {
    const fixture: PublishValidationOut = {
      pack_id: "p",
      version: "0.0.1",
      errors: [
        { path: "rights.license", message: "unrecognized" },
      ],
    };
    globalThis.fetch = (async () =>
      jsonResponse(fixture)) as typeof fetch;
    const result = await api.validation("t", "p");
    expect(result.errors).toEqual(fixture.errors);
  });

  it("publish() throws on 422 with the publish-gate error list", async () => {
    globalThis.fetch = (async () =>
      jsonResponse(
        envelope("publish_validation_failed", "Pack failed the publish gate.", {
          errors: [
            { path: "artworks[a].provenance.c2pa", message: "missing" },
          ],
        }),
        422,
      )) as typeof fetch;
    try {
      await api.publish("t", "p");
      throw new Error("expected throw");
    } catch (err) {
      expect(err).toBeInstanceOf(APIError);
      const apiErr = err as APIError;
      expect(apiErr.code).toBe("publish_validation_failed");
      expect(apiErr.details).toEqual({
        errors: [{ path: "artworks[a].provenance.c2pa", message: "missing" }],
      });
    }
  });

  it("publish() resolves with the typed PublishOut on 200", async () => {
    const fixture: PublishOut = {
      pack_id: "p",
      version: "1.0.0",
      status: "published",
      published_at: "2026-09-14T12:00:00Z",
      manifest_sha256:
        "0000000000000000000000000000000000000000000000000000000000000000",
    };
    globalThis.fetch = (async () =>
      jsonResponse(fixture)) as typeof fetch;
    const result = await api.publish("t", "p");
    expect(result.pack_id).toBe("p");
    expect(result.status).toBe("published");
  });

  it("me() returns the typed MeOut", async () => {
    const fixture: MeOut = {
      id: "u-1",
      email: "a@b.co",
      display_name: "A",
      role: "user",
      artists: [],
    };
    globalThis.fetch = (async () =>
      jsonResponse(fixture)) as typeof fetch;
    const result = await api.me("t");
    expect(result.role).toBe("user");
    expect(result.artists).toEqual([]);
  });
});