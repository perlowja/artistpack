import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  ArtworkUploadForm,
  validateImageClient,
} from "@/components/ArtworkUploadForm";

function makeFile(name: string, type: string, size: number): File {
  // Construct a File whose `size` and `type` we control. We don't need
  // real bytes — validateImageClient only reads metadata.
  const bytes = new Uint8Array(Math.min(size, 16));
  const f = new File([bytes], name, { type });
  Object.defineProperty(f, "size", { configurable: true, value: size });
  return f;
}

describe("validateImageClient", () => {
  it("accepts a JPEG under the size cap", () => {
    const f = makeFile("a.jpg", "image/jpeg", 1024);
    expect(validateImageClient(f).ok).toBe(true);
  });

  it("accepts a PNG under the size cap", () => {
    const f = makeFile("a.png", "image/png", 1024);
    expect(validateImageClient(f).ok).toBe(true);
  });

  it("accepts a WebP under the size cap", () => {
    const f = makeFile("a.webp", "image/webp", 1024);
    expect(validateImageClient(f).ok).toBe(true);
  });

  it("rejects an unsupported MIME", () => {
    const f = makeFile("a.gif", "image/gif", 1024);
    const v = validateImageClient(f);
    expect(v.ok).toBe(false);
    expect(v.message).toMatch(/JPEG.*PNG.*WebP/);
  });

  it("rejects a file with no MIME type", () => {
    const f = makeFile("a.bin", "", 1024);
    expect(validateImageClient(f).ok).toBe(false);
  });

  it("rejects a file over the size cap", () => {
    const f = makeFile("big.jpg", "image/jpeg", 26 * 1024 * 1024);
    const v = validateImageClient(f);
    expect(v.ok).toBe(false);
    expect(v.message).toMatch(/max is/i);
  });
});

describe("ArtworkUploadForm rendering", () => {
  it("keeps the submit button disabled until all required fields are filled with valid values", () => {
    render(<ArtworkUploadForm token="t" packPublicId="demo" onUploaded={() => {}} />);

    const submit = screen.getByTestId("upload-submit") as HTMLButtonElement;
    // Initially disabled (no file, no fields).
    expect(submit.disabled).toBe(true);

    // Fill in metadata, but still no file.
    fireEvent.change(screen.getByTestId("upload-public-id"), {
      target: { value: "dawn" },
    });
    fireEvent.change(screen.getByTestId("upload-title"), {
      target: { value: "Dawn over Kyoto" },
    });
    fireEvent.change(screen.getByTestId("upload-attribution-name"), {
      target: { value: "Nova Ashworth" },
    });
    expect(submit.disabled).toBe(true);

    // Pick a valid file.
    const file = makeFile("dawn.jpg", "image/jpeg", 1024);
    fireEvent.change(screen.getByTestId("upload-file"), {
      target: { files: [file] },
    });
    expect(submit.disabled).toBe(false);

    // Pick an invalid file — submit must disable again, and the inline
    // error message must show.
    const badFile = makeFile("big.jpg", "image/jpeg", 26 * 1024 * 1024);
    fireEvent.change(screen.getByTestId("upload-file"), {
      target: { files: [badFile] },
    });
    expect(submit.disabled).toBe(true);
    expect(screen.getByText(/max is/i)).toBeInTheDocument();

    // Bad MIME.
    const gifFile = makeFile("a.gif", "image/gif", 1024);
    fireEvent.change(screen.getByTestId("upload-file"), {
      target: { files: [gifFile] },
    });
    expect(submit.disabled).toBe(true);
  });

  it("shows a preview element after a valid file is selected", () => {
    render(<ArtworkUploadForm token="t" packPublicId="demo" onUploaded={() => {}} />);

    // Initially no preview.
    expect(screen.queryByTestId("upload-preview")).toBeNull();

    const file = makeFile("dawn.jpg", "image/jpeg", 1024);
    fireEvent.change(screen.getByTestId("upload-file"), {
      target: { files: [file] },
    });

    expect(screen.getByTestId("upload-preview")).toBeInTheDocument();
  });
});