"""Split document markdown into ordered sections (P08.3).

Every heading starts a new section; pipe and HTML tables (the Azure
Layout shape) are never cut mid-row. An oversized table splits by row
groups with its headers repeated and a continuation note. Page ranges
are tracked only when the text marks page breaks (a form feed);
otherwise they stay unknown instead of guessed.
"""

import re
from dataclasses import dataclass, field

MAX_SECTION_CHARS = 6000  # Well under the embedding input limit.
CONTINUATION_NOTE = "> (continued from the previous section)"

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_TABLE_OPEN = re.compile(r"<table(\s[^>]*)?>", re.IGNORECASE)
_THEAD = re.compile(r"<thead\b.*?</thead>", re.IGNORECASE | re.DOTALL)
_TR = re.compile(r"<tr\b.*?</tr>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class SectionDraft:
    """One section ready to store: its path, text and page range."""

    heading_path: str | None
    text: str
    page_from: int | None
    page_to: int | None


@dataclass
class _Open:
    """The section being built: its heading stack and text pieces."""

    stack: list[tuple[int, str]] = field(default_factory=list)
    pieces: list[str] = field(default_factory=list)
    length: int = 0
    first_page: int | None = None
    last_page: int | None = None


def split_sections(markdown: str, *, page_count: int) -> list[SectionDraft]:
    """Split markdown into sections, keeping tables whole."""
    text = (markdown or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return []
    parts = text.split("\f")
    known_pages = len(parts) > 1 or page_count == 1
    sections: list[SectionDraft] = []
    current = _Open()

    def close() -> None:
        if not current.pieces:
            return
        path = " > ".join(title for _, title in current.stack) or None
        body = "\n\n".join(current.pieces).strip()
        if body:
            sections.append(
                SectionDraft(
                    heading_path=path,
                    text=body,
                    page_from=current.first_page,
                    page_to=current.last_page,
                )
            )
        current.pieces = []
        current.length = 0
        current.first_page = None
        current.last_page = None

    def note_page(page: int | None) -> None:
        if page is None:
            return
        if current.first_page is None:
            current.first_page = page
        current.last_page = page

    def push(piece: str, page: int | None) -> None:
        if current.pieces and current.length + 2 + len(piece) > MAX_SECTION_CHARS:
            close()
        current.pieces.append(piece)
        current.length += (2 if len(current.pieces) > 1 else 0) + len(piece)
        note_page(page)

    for number, part in enumerate(parts, start=1):
        if not part.strip():
            continue
        page = number if known_pages and len(parts) > 1 else (1 if known_pages else None)
        for block in _blocks(part):
            if block[0] == "heading":
                close()
                _, level, title = block
                while current.stack and current.stack[-1][0] >= level:
                    current.stack.pop()
                current.stack.append((level, title))
                push(f"{'#' * level} {title}", page)
            elif block[0] == "table":
                for piece in _table_pieces(block[1]):
                    push(piece, page)
            elif block[0] == "html_table":
                for piece in _html_table_pieces(block[1]):
                    push(piece, page)
            else:
                for piece in _prose_pieces(block[1]):
                    push(piece, page)
    close()
    return sections


def _blocks(part: str) -> list[tuple]:
    """Split a page into heading, table and prose blocks, in order."""
    blocks: list[tuple] = []
    prose: list[str] = []
    table: list[str] = []
    html: list[str] = []
    fenced = False

    def flush() -> None:
        if table:
            blocks.append(("table", list(table)))
            table.clear()
        if html:
            blocks.append(("html_table", "\n".join(html).strip()))
            html.clear()
        if prose:
            blocks.append(("prose", "\n".join(prose).strip()))
            prose.clear()

    for line in part.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fenced = not fenced
            flush()
            blocks.append(("prose", line))
            continue
        if fenced:
            prose.append(line)
            continue
        if html:
            html.append(line)
            if "</table>" in stripped.lower():
                flush()
            continue
        if _TABLE_OPEN.match(stripped):
            flush()
            html.append(line)
            if "</table>" in stripped.lower():
                flush()
            continue
        match = _HEADING.match(line)
        if match:
            flush()
            blocks.append(("heading", len(match.group(1)), match.group(2)))
        elif stripped.startswith("|"):
            if prose and not table:
                flush()
            table.append(line)
        elif not stripped:
            flush()
        else:
            if table:
                flush()
            prose.append(line)
    flush()
    return [block for block in blocks if block[0] != "prose" or block[1]]


def _table_pieces(lines: list[str]) -> list[str]:
    """One table, whole when it fits; row groups with headers when not."""
    whole = "\n".join(lines).strip()
    if len(whole) <= MAX_SECTION_CHARS:
        return [whole]
    header, body = _header_and_body(lines)
    head_size = len("\n".join(header))
    note_size = len(CONTINUATION_NOTE) + 2
    pieces: list[str] = []
    group: list[str] = []
    size = head_size

    def flush_group() -> None:
        if group:
            text = "\n".join([*header, *group])
            if pieces:
                text = f"{CONTINUATION_NOTE}\n\n{text}"
            pieces.append(text)
            group.clear()

    for row in body:
        budget = MAX_SECTION_CHARS - (note_size if pieces else 0)
        if size + 1 + len(row) > budget and group:
            flush_group()
            size = head_size
        group.append(row)
        size += 1 + len(row)
    flush_group()
    return pieces or [whole]


def _header_and_body(lines: list[str]) -> tuple[list[str], list[str]]:
    """The header rows (with the delimiter when there is one) and the rest."""
    if len(lines) >= 2 and _is_delimiter(lines[1]):
        return lines[:2], lines[2:]
    return lines[:1], lines[1:]


def _is_delimiter(line: str) -> bool:
    """A `| --- | --- |` style row: pipes, dashes, colons and spaces only."""
    stripped = line.strip()
    return len(stripped) >= 3 and "-" in stripped and set(stripped) <= set("|-: ")


def _html_table_pieces(text: str) -> list[str]:
    """An Azure Layout table, whole when it fits; row groups with headers when not."""
    whole = text.strip()
    if len(whole) <= MAX_SECTION_CHARS:
        return [whole]
    open_tag, header, body = _parse_html_table(whole)
    if not body:
        return _prose_pieces(whole)
    tail = "\n</table>"
    head_size = len(open_tag) + 1 + len(header) + len(tail)
    note_size = len(CONTINUATION_NOTE) + 2
    pieces: list[str] = []
    group: list[str] = []
    size = head_size

    def flush_group() -> None:
        if group:
            chunk = f"{open_tag}\n{header}\n" + "\n".join(group) + tail
            if pieces:
                chunk = f"{CONTINUATION_NOTE}\n\n{chunk}"
            pieces.append(chunk)
            group.clear()

    for row in body:
        budget = MAX_SECTION_CHARS - (note_size if pieces else 0)
        if size + 1 + len(row) > budget and group:
            flush_group()
            size = head_size
        group.append(row)
        size += 1 + len(row)
    flush_group()
    return pieces or [whole]


def _parse_html_table(text: str) -> tuple[str, str, list[str]]:
    """The opening tag, the header block and the body rows of one HTML table."""
    open_match = _TABLE_OPEN.search(text)
    open_tag = open_match.group(0) if open_match else "<table>"
    thead = _THEAD.search(text)
    if thead is not None:
        header = thead.group(0)
        body = _TR.findall(text[: thead.start()] + text[thead.end() :])
    else:
        rows = _TR.findall(text)
        header, body = (rows[0], rows[1:]) if rows else ("", [])
    return open_tag, header, body


def _prose_pieces(text: str) -> list[str]:
    """Prose that fits passes through; a giant paragraph hard-splits."""
    if len(text) <= MAX_SECTION_CHARS:
        return [text]
    budget = MAX_SECTION_CHARS - len(CONTINUATION_NOTE) - 2
    pieces = [text[0:MAX_SECTION_CHARS]]
    for start in range(MAX_SECTION_CHARS, len(text), budget):
        pieces.append(f"{CONTINUATION_NOTE}\n\n{text[start : start + budget]}")
    return pieces
