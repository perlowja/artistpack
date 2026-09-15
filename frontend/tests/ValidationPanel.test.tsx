import { describe, expect, it } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { classifyErrors, ValidationPanel } from "@/components/ValidationPanel";
import type { PublishValidationOut } from "@/lib/api-types";

describe("classifyErrors", () => {
  it("treats a zero-error response as all-pass", () => {
    const validation: PublishValidationOut = {
      pack_id: "p",
      version: "0.0.1",
      errors: [],
    };
    const checks = classifyErrors(validation.errors);
    expect(checks).toHaveLength(4);
    expect(checks.every((c) => c.ok)).toBe(true);
  });

  it("classifies structural schema errors", () => {
    const checks = classifyErrors([
      { path: "manifest.pack.id", message: "must be string" },
    ]);
    const structural = checks.find((c) => c.id === "structural");
    expect(structural).toBeDefined();
    expect(structural!.ok).toBe(false);
    expect(structural!.errors[0].path).toBe("manifest.pack.id");
    // Other checks unaffected
    const others = checks.filter((c) => c.id !== "structural");
    expect(others.every((c) => c.ok)).toBe(true);
  });

  it("classifies C2PA provenance errors", () => {
    const checks = classifyErrors([
      {
        path: "artworks[dawn].provenance.c2pa",
        message: "no provenance_records row attached",
      },
      {
        path: "artworks[dawn].provenance.verification_status",
        message: "expected 'verified'",
      },
    ]);
    const c2pa = checks.find((c) => c.id === "c2pa");
    expect(c2pa).toBeDefined();
    expect(c2pa!.ok).toBe(false);
    expect(c2pa!.errors).toHaveLength(2);
  });

  it("classifies license errors", () => {
    const checks = classifyErrors([
      {
        path: "rights.license",
        message: "unrecognized license 'foo'",
      },
    ]);
    const license = checks.find((c) => c.id === "license");
    expect(license!.ok).toBe(false);
    expect(license!.errors[0].path).toBe("rights.license");
  });

  it("classifies per-artwork license overrides as license errors", () => {
    const checks = classifyErrors([
      {
        path: "artworks[].license",
        message: "artwork override license 'CC-BY-NC-2.0' is not in the catalog",
      },
    ]);
    const license = checks.find((c) => c.id === "license");
    expect(license!.ok).toBe(false);
  });

  it("classifies attribution errors", () => {
    const checks = classifyErrors([
      {
        path: "artworks[dawn].attribution.display_name",
        message: "attribution.display_name must be non-empty",
      },
    ]);
    const attribution = checks.find((c) => c.id === "attribution");
    expect(attribution!.ok).toBe(false);
    expect(attribution!.errors[0].path).toBe(
      "artworks[dawn].attribution.display_name",
    );
  });

  it("classifies a mixed pass/fail response correctly", () => {
    const validation: PublishValidationOut = {
      pack_id: "p",
      version: "0.0.1",
      errors: [
        // structural OK (no manifest.* error)
        { path: "rights.license", message: "unrecognized license 'BAD'" },
        { path: "artworks[a].provenance.c2pa", message: "missing provenance" },
        { path: "artworks[a].attribution.display_name", message: "must be non-empty" },
      ],
    };
    const checks = classifyErrors(validation.errors);
    const structural = checks.find((c) => c.id === "structural")!;
    const license = checks.find((c) => c.id === "license")!;
    const c2pa = checks.find((c) => c.id === "c2pa")!;
    const attribution = checks.find((c) => c.id === "attribution")!;
    expect(structural.ok).toBe(true);
    expect(license.ok).toBe(false);
    expect(c2pa.ok).toBe(false);
    expect(attribution.ok).toBe(false);
  });
});

describe("ValidationPanel rendering", () => {
  it("renders all four checks and marks each with the right pass/fail icon", async () => {
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
      render(<ValidationPanel token="t" packPublicId="demo" />);
      await waitFor(() => {
        expect(screen.getByTestId("check-structural")).toHaveAttribute(
          "data-ok",
          "true",
        );
      });
      expect(screen.getByTestId("check-license")).toHaveAttribute(
        "data-ok",
        "false",
      );
      expect(screen.getByTestId("check-c2pa")).toHaveAttribute(
        "data-ok",
        "false",
      );
      expect(screen.getByTestId("check-attribution")).toHaveAttribute(
        "data-ok",
        "false",
      );
      // The summary banner should report remaining errors.
      expect(screen.getByTestId("validation-summary")).toHaveAttribute(
        "data-all-ok",
        "false",
      );
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});