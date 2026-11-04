"""Bytes in, text out (architecture 5.5, plan WP10.1)."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["SUPPORTED_MIME", "ExtractionError", "extract_text"]


class ExtractionError(Exception):
    """A document's text could not be read out of its bytes."""


@dataclass(frozen=True, slots=True)
class Format:
    """One accepted upload, and the extensions people actually use for it."""

    mime: str
    extensions: tuple[str, ...]


MARKDOWN = Format("text/markdown", (".md", ".markdown"))
PLAIN = Format("text/plain", (".txt", ".text"))
PDF = Format("application/pdf", (".pdf",))

SUPPORTED_MIME: tuple[str, ...] = (MARKDOWN.mime, PLAIN.mime, PDF.mime)

#: Below this, a "successful" extraction has almost certainly found nothing — a scanned PDF.
MIN_USEFUL_CHARACTERS = 20


def extract_text(payload: bytes, *, mime: str, filename: str | None = None) -> str:
    """The document's text, or ``ExtractionError`` saying why there is none."""
    resolved = _resolve(mime, filename)
    text = _from_pdf(payload) if resolved is PDF else _decode(payload)

    if len(text.strip()) < MIN_USEFUL_CHARACTERS:
        raise ExtractionError(
            "No readable text was found in this file. If it is a scanned PDF, "
            "the pages are images and need OCR before they can be indexed."
        )
    return text


def _resolve(mime: str, filename: str | None) -> Format:
    """Trust the extension over the browser's guess, and refuse the unknown."""
    for candidate in (MARKDOWN, PLAIN, PDF):
        if mime == candidate.mime:
            return candidate
    lowered = (filename or "").lower()
    for candidate in (MARKDOWN, PLAIN, PDF):
        if any(lowered.endswith(extension) for extension in candidate.extensions):
            return candidate
    raise ExtractionError(
        f"{mime or 'that file type'} cannot be indexed yet. "
        "Markdown, plain text and PDFs with a text layer can be."
    )


def _decode(payload: bytes) -> str:
    # `utf-8-sig` first, and the order is the whole point.
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    # Cannot fail, and will mangle rather than raise.
    return payload.decode("latin-1", errors="replace")


def _from_pdf(payload: bytes) -> str:
    """The text layer, page by page, with pages separated by a blank line."""
    import io

    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(payload))
        pages = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as error:
        raise ExtractionError(f"This PDF could not be read: {error}") from error
    except Exception as error:
        # pypdf raises a wide and undocumented range on malformed files.
        raise ExtractionError("This PDF could not be read.") from error

    return "\n\n".join(page.strip() for page in pages if page.strip())
