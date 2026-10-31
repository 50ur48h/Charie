"""Upload validation: names, types, size and readable bytes (P08.2).

Pure checks live here so the API stays thin; failures raise ApiError with
plain-English messages and never leave partial rows behind.
"""

import os

from fastapi import UploadFile

from charie.shared.errors import ApiError

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB per file, checked while streaming.
ALLOWED_TYPES = ("docx", "pdf", "pptx", "xlsx", "md", "txt")


def clean_name(name: str | None) -> str:
    """A safe display name: no folders, only printable characters."""
    base = os.path.basename(name or "").strip()
    cleaned = "".join(char for char in base if char.isprintable())
    return cleaned[:200] or "upload"


def file_type_of(file_name: str) -> str:
    """The lowercase extension, or empty when there is none."""
    return file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""


def check_type(file_type: str, file_name: str) -> None:
    """Refuse anything Charie can't read, naming what it can."""
    if file_type not in ALLOWED_TYPES:
        raise ApiError(
            400,
            "unsupported_file",
            f"{file_name} can't be added. Charie reads Word, PDF, PowerPoint, Excel, "
            "Markdown and text files.",
        )


async def read_bytes(upload: UploadFile, file_name: str) -> bytes:
    """Stream the upload, refusing oversized and empty files as it goes."""
    data = bytearray()
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        data += chunk
        if len(data) > MAX_UPLOAD_BYTES:
            raise ApiError(
                413,
                "file_too_big",
                f"{file_name} is too big. Each file can be up to 50 MB.",
            )
    if not data:
        raise ApiError(400, "empty_file", f"{file_name} is empty.")
    return bytes(data)


def check_bytes(file_type: str, data: bytes, file_name: str) -> None:
    """Refuse files whose first bytes don't match their extension."""
    if file_type == "pdf" and not data.startswith(b"%PDF"):
        raise ApiError(400, "unreadable_file", f"{file_name} can't be added.")
    if file_type in ("docx", "pptx", "xlsx") and not data.startswith(b"PK\x03\x04"):
        raise ApiError(400, "unreadable_file", f"{file_name} can't be added.")
    if file_type in ("md", "txt"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise ApiError(400, "unreadable_file", f"{file_name} can't be added.") from None
