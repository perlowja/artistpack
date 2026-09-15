/**
 * Publish-button disabled-state logic.
 *
 * The publish action on the pack detail page is governed by:
 *
 *   isDraft && checks.length > 0 && checks.every(c => c.ok)
 *
 * Where `checks` is the result of `classifyErrors(...)` on the
 * `GET /packs/{id}/validation` response. We exercise the same logic in
 * isolation here so the rules are tested independent of the page that
 * wires them up.
 */

import { describe, expect, it, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { classifyErrors, ValidationPanel, type PublishCheck } from "@/components/ValidationPanel";
import type { PublishValidationOut } from "@/lib/api-types";

afterEach(() => {
  cleanup();
});

function canPublish(isDraft: boolean, checks: PublishCheck[]): boolean {
  return isDraft && checks.length > 0 && checks.every((c) => c.ok);
}

describe("publish button disabled-state logic", () => {
  it("is disabled when the pack is already published", () => {
    const checks: PublishCheck[] = classifyErrors([]);
    expect(canPublish(false, checks)).toBe(false);
  });

  it("is disabled before validation has loaded (checks empty)", () => {
    expect(canPublish(true, [])).toBe(false);
  });

  it("is disabled when any check has unresolved errors", () => {
    const validation: PublishValidationOut = {
      pack_id: "p",
      version: "0.0.1",
      errors: [{ path: "rights.license", message: "unrecognized" }],
    };
    const checks = classifyErrors(validation.errors);
    expect(canPublish(true, checks)).toBe(false);
  });

  it("is enabled only when the pack is a draft AND every check is OK", () => {
    const validation: PublishValidationOut = {
      pack_id: "p",
      version: "0.0.1",
      errors: [],
    };
    const checks = classifyErrors(validation.errors);
    expect(canPublish(true, checks)).toBe(true);
  });

  it("disables when C2PA provenance is the only failing check", () => {
    const validation: PublishValidationOut = {
      pack_id: "p",
      version: "0.0.1",
      errors: [
        {
          path: "artworks[a].provenance.c2pa",
          message: "no provenance row",
        },
      ],
    };
    const checks = classifyErrors(validation.errors);
    const c2pa = checks.find((c) => c.id === "c2pa")!;
    expect(c2pa.ok).toBe(false);
    expect(canPublish(true, checks)).toBe(false);
  });

  it("disables when attribution is the only failing check", () => {
    const validation: PublishValidationOut = {
      pack_id: "p",
      version: "0.0.1",
      errors: [
        {
          path: "artworks[a].attribution.display_name",
          message: "must be non-empty",
        },
      ],
    };
    const checks = classifyErrors(validation.errors);
    expect(canPublish(true, checks)).toBe(false);
  });
});

describe("pack detail rendering — publish button", () => {
  it("disables publish and surfaces validation summary on unresolved errors", async () => {
    const fixture: PublishValidationOut = {
      pack_id: "demo",
      version: "0.0.1",
      errors: [
        { path: "rights.license", message: "unrecognized license 'BAD'" },
        { path: "artworks[a].provenance.c2pa", message: "missing" },
        { path: "artworks[a].attribution.display_name", message: "must be non-empty" },
      ],
    };

    const originalFetch = globalThis.fetch;
    globalThis.fetch = (() =>
      Promise.resolve(
        new Response(JSON.stringify(fixture), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )) as typeof fetch;

    try {
      let observed: PublishCheck[] | null = null;
      render(
        <ValidationPanel
          token="t"
          packPublicId="demo"
          onChange={(cs) => {
            observed = cs;
          }}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId("validation-summary")).toHaveAttribute(
          "data-all-ok",
          "false",
        );
      });

      expect(observed).not.toBeNull();
      const allOk = (observed as PublishCheck[]).every((c) => c.ok);
      expect(allOk).toBe(false);
      // canPublish requires isDraft && checks non-empty && allOk; with
      // allOk false the button would be disabled.
      expect(canPublish(true, observed as PublishCheck[])).toBe(false);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("enables publish when validation returns no errors", async () => {
    const fixture: PublishValidationOut = {
      pack_id: "demo",
      version: "0.0.1",
      errors: [],
    };

    const originalFetch = globalThis.fetch;
    globalThis.fetch = (() =>
      Promise.resolve(
        new Response(JSON.stringify(fixture), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )) as typeof fetch;

    try {
      let observed: PublishCheck[] | null = null;
      render(
        <ValidationPanel
          token="t"
          packPublicId="demo"
          onChange={(cs) => {
            observed = cs;
          }}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId("validation-summary")).toHaveAttribute(
          "data-all-ok",
          "true",
        );
      });

      const allOk = (observed as PublishCheck[]).every((c) => c.ok);
      expect(allOk).toBe(true);
      expect(canPublish(true, observed as PublishCheck[])).toBe(true);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});