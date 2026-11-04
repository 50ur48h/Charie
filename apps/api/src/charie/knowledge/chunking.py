"""Turning a document into passages worth retrieving (architecture 5.5)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from charie.llm.base import estimate_tokens

__all__ = ["Chunk", "chunk_document", "split_sections"]

#: The target size, in estimated tokens.
TARGET_TOKENS = 700

#: A chunk shorter than this is merged into the next one within the same section.
MIN_TOKENS = 40

#: How much of the previous chunk a continuation repeats.
OVERLAP_PARAGRAPHS = 1

#: Markdown ATX headings. Setext (`===` underlines) is deliberately not handled.
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")

#: A blank line, however much whitespace it carries.
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")

#: Fenced code, which must not be split by the heading scanner.
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True, slots=True)
class Section:
    """A run of text under one heading trail."""

    headings: tuple[str, ...]
    text: str


@dataclass(frozen=True, slots=True)
class Chunk:
    """One passage, as it will be stored and retrieved."""

    seq: int
    text: str
    headings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def token_estimate(self) -> int:
        return estimate_tokens(self.text)


def split_sections(document: str) -> list[Section]:
    """Break a document at its headings, keeping the trail to each."""
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []
    body: list[str] = []
    in_fence = False

    def flush() -> None:
        text = "\n".join(body).strip()
        body.clear()
        if text:
            sections.append(Section(headings=tuple(title for _, title in stack), text=text))

    for line in document.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            body.append(line)
            continue
        match = None if in_fence else _HEADING.match(line)
        if match is None:
            body.append(line)
            continue
        flush()
        depth, title = len(match.group(1)), match.group(2).strip()
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if title:
            stack.append((depth, title))

    flush()
    return sections


def chunk_document(document: str, *, target_tokens: int = TARGET_TOKENS) -> list[Chunk]:
    """The whole pipeline: sections, then length, then a gap-free ``seq``."""
    chunks: list[Chunk] = []
    for section in split_sections(document):
        for text in _split_by_length(section.text, target_tokens):
            chunks.append(Chunk(seq=len(chunks), text=text, headings=section.headings))
    return chunks


def _split_by_length(text: str, target_tokens: int) -> list[str]:
    """One section's text, cut on paragraph boundaries near the target size."""
    if estimate_tokens(text) <= target_tokens:
        return [text]

    paragraphs = [part.strip() for part in _PARAGRAPH_BREAK.split(text) if part.strip()]
    out: list[str] = []
    current: list[str] = []
    size = 0
    for paragraph in paragraphs:
        cost = estimate_tokens(paragraph)
        if current and size + cost > target_tokens:
            out.append("\n\n".join(current))
            # The overlap: the tail of what was just emitted opens the next chunk.
            current = current[-OVERLAP_PARAGRAPHS:]
            size = sum(estimate_tokens(part) for part in current)
        current.append(paragraph)
        size += cost
    if current:
        out.append("\n\n".join(current))

    return _merge_stragglers(out)


def _merge_stragglers(chunks: list[str]) -> list[str]:
    """Fold a too-small trailing chunk back into its predecessor."""
    if len(chunks) > 1 and estimate_tokens(chunks[-1]) < MIN_TOKENS:
        tail = chunks.pop()
        chunks[-1] = f"{chunks[-1]}\n\n{tail}"
    return chunks
