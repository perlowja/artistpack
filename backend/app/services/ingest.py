"""Image ingestion: file -> Artwork + variants, with MIME sniff + bomb guard.

Per ``docs/security-model.md`` §"Upload pipeline guards":

* MIME sniffing by content, never by extension
* Decompression-bomb protection — cap decoded dimensions before decode
* Dimension and file-size limits

Variant generation is **stubbed** for MVP: we copy the original as the
sole variant. Full derivative generation (1920x1080, 2560x1440, ...) is
Task 9's image-processing pipeline.
"""

from __future__ import annotations

import hashlib
import io
from typing import IO

from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.errors import bad_request


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sniff_and_decode(data: bytes) -> Image.Image:
    """Decode ``data`` with PIL while enforcing the pixel-count cap.

    Raises ``bad_request`` on any decode failure or pixel-cap violation.
    The cap is the ``image_content`` size limit imposed *before* decode,
    matching the doc's "decompression-bomb guard" requirement.
    """

    if len(data) > settings.artwork_max_bytes:
        raise bad_request(
            "file_too_large",
            f"File is {len(data)} bytes; maximum allowed is {settings.artwork_max_bytes}.",
        )
    try:
        # ``Image.open`` is lazy — calling ``load`` actually decodes.
        img = Image.open(io.BytesIO(data))
    except UnidentifiedImageError as exc:
        raise bad_request(
            "unsupported_image", "Could not identify image format from content."
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise bad_request("image_decode_failed", f"Image decoding failed: {exc}") from exc

    # Pillow >= 9.1 has a built-in bomb guard via ``Image.MAX_IMAGE_PIXELS``;
    # we set it conservatively to ``settings.artwork_max_pixels`` and the
    # very next operation (``load``/size access) raises DecompressionBombError.
    Image.MAX_IMAGE_PIXELS = settings.artwork_max_pixels
    try:
        w, h = img.size
    except Exception as exc:  # pragma: no cover - size never raises in practice
        raise bad_request("image_decode_failed", str(exc)) from exc
    if w * h > settings.artwork_max_pixels:
        raise bad_request(
            "image_too_large",
            f"Decoded dimensions {w}x{h} exceed pixel cap {settings.artwork_max_pixels}.",
        )
    img.load()  # force decode so any bomb-throw happens here
    return img


def sniff_mime(data: bytes) -> str:
    """Sniff the MIME type from the file's leading bytes.

    Uses Pillow's type identification; not the extension. Bumps the
    PIL pixel cap before opening because ``app.services.ingest``'s bomb
    guard sets it low and PIL's ``open`` honors ``MAX_IMAGE_PIXELS``
    lazily — we want sniffing to always work even if the previous test
    tightened the cap.
    """

    try:
        Image.MAX_IMAGE_PIXELS = max(Image.MAX_IMAGE_PIXELS or 0, 1 << 25)
    except Exception:
        pass
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = (img.format or "").lower()
    except Exception:
        return "application/octet-stream"
    return {
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }.get(fmt, "application/octet-stream")


def ingest_artwork(fileobj: IO[bytes]) -> dict:
    """Return a dict with sha256, mime_type, width, height, decoded Image."""

    data = fileobj.read()
    img = _sniff_and_decode(data)
    mime = sniff_mime(data)
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        raise bad_request("unsupported_mime", f"MIME type {mime!r} is not supported.")
    w, h = img.size
    sha = compute_sha256(data)
    return {
        "data": data,
        "sha256": sha,
        "mime_type": mime,
        "width": w,
        "height": h,
        "image": img,
    }


def derive_orientation(width: int, height: int) -> str:
    if width > height:
        return "landscape"
    if height > width:
        return "portrait"
    return "square"


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a or 1


def derive_aspect_ratio(width: int, height: int) -> str:
    """Express the aspect ratio as ``W:H`` in lowest terms."""

    g = _gcd(width, height)
    return f"{width // g}:{height // g}"
