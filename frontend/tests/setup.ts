import "@testing-library/jest-dom/vitest";

// Polyfill fetch — vitest's happy-dom env provides it but the
// Response.json path uses it for round-tripping in tests.
if (typeof globalThis.fetch === "undefined") {
  // No-op stub; individual tests install their own fetch mock.
  globalThis.fetch = (() =>
    Promise.resolve(
      new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }),
    )) as typeof fetch;
}

// Stub matchMedia — components don't use it, but jsdom/happy-dom sometimes
// has it missing.
if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

// Stub URL.createObjectURL so the upload form's preview doesn't blow up
// in happy-dom, which lacks it. Tests that exercise preview behavior
// will override it themselves.
if (typeof URL.createObjectURL !== "function") {
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: () => "blob:test",
  });
}
if (typeof URL.revokeObjectURL !== "function") {
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: () => {},
  });
}