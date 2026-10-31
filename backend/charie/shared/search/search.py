"""Three-way search: meaning, words and names, fused (P08.5).

Meaning is cosine distance over section/entry vectors, words is
PostgreSQL full-text search, names is trigram similarity over headings
and titles. Reciprocal-rank fusion (k=60) merges the channels; ties
break by stable ID. Removed and failed documents never appear in new
searches. Archived answers keep their own evidence copies, so dropping
a document here never orphans them.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from charie.shared.search import embeddings
from charie.shared.tables.knowledge import KbEntry
from charie.shared.tables.sources import Document, DocumentSection

RRF_K = 60
PER_CHANNEL = 20  # Each channel's shortlist; fusion keeps the top few.
RESULT_LIMIT = 8
NAME_FLOOR = 0.05  # Any shared trigram counts; ranking does the rest.


@dataclass(frozen=True)
class SectionHit:
    """One found section with where it came from."""

    section_id: int
    document_id: int
    file_name: str
    heading_path: str | None
    text: str
    page_from: int | None
    page_to: int | None


@dataclass(frozen=True)
class KnowledgeHit:
    """One found knowledge entry."""

    entry_id: int
    key: str
    kind: str
    title: str
    meaning: str
    confidence: str


def _readable():
    """Only readable documents: removed and failed ones stay out of new searches."""
    return Document.status.notin_(["removed", "failed"])


def search_sections(
    session: Session, query: str, *, limit: int = RESULT_LIMIT, app: str = "learner"
) -> list[SectionHit]:
    """The top sections for a question, by meaning, words and names."""
    if not (query or "").strip():
        return []
    vector = _embed_query(query, app)
    ids = _fuse(
        [
            _meaning_section_ids(session, vector),
            _word_section_ids(session, query),
            _name_section_ids(session, query),
        ],
        limit,
    )
    if not ids:
        return []
    rows = session.execute(
        select(DocumentSection, Document.file_name)
        .join(Document, DocumentSection.document_id == Document.id)
        .where(DocumentSection.id.in_(ids))
    ).all()
    by_id = {section.id: (section, file_name) for section, file_name in rows}
    return [
        SectionHit(
            section_id=section.id,
            document_id=section.document_id,
            file_name=file_name,
            heading_path=section.heading_path,
            text=section.text_,
            page_from=section.page_from,
            page_to=section.page_to,
        )
        for section, file_name in (by_id[ident] for ident in ids if ident in by_id)
    ]


def search_knowledge(
    session: Session,
    query: str,
    version_id: int,
    *,
    limit: int = RESULT_LIMIT,
    app: str = "learner",
) -> list[KnowledgeHit]:
    """The top entries of one knowledge version, same three channels."""
    if not (query or "").strip():
        return []
    vector = _embed_query(query, app)
    ids = _fuse(
        [
            _meaning_entry_ids(session, version_id, vector),
            _word_entry_ids(session, version_id, query),
            _name_entry_ids(session, version_id, query),
        ],
        limit,
    )
    if not ids:
        return []
    rows = session.scalars(select(KbEntry).where(KbEntry.id.in_(ids))).all()
    by_id = {entry.id: entry for entry in rows}
    return [
        KnowledgeHit(
            entry_id=entry.id,
            key=entry.key,
            kind=entry.kind,
            title=entry.title,
            meaning=entry.meaning,
            confidence=entry.confidence,
        )
        for entry in (by_id[ident] for ident in ids if ident in by_id)
    ]


def index_entry(
    session: Session,
    entry: KbEntry,
    *,
    app: str = "learner",
    learning_run_id: int | None = None,
) -> None:
    """Fill one entry's meaning vector; its title and meaning stay untouched."""
    result = embeddings.embed_texts(
        [f"{entry.title}\n\n{entry.meaning}"], app=app, learning_run_id=learning_run_id
    )
    entry.embedding = result.vectors[0]
    session.flush()


def _embed_query(query: str, app: str) -> list[float]:
    """One vector for the question; every channel shares it."""
    return embeddings.embed_texts([query], app=app).vectors[0]


def _section_ids(session: Session, where, order) -> list[int]:
    """Section IDs of readable documents in rank order."""
    return list(
        session.scalars(
            select(DocumentSection.id)
            .join(Document, DocumentSection.document_id == Document.id)
            .where(_readable(), where)
            .order_by(order)
            .limit(PER_CHANNEL)
        )
    )


def _meaning_section_ids(session: Session, vector: list[float]) -> list[int]:
    """Closest vectors first; sections without a vector sit this one out."""
    return _section_ids(
        session,
        DocumentSection.embedding.is_not(None),
        DocumentSection.embedding.cosine_distance(vector),
    )


def _word_section_ids(session: Session, query: str) -> list[int]:
    """Full-text matches, best rank first."""
    question = func.plainto_tsquery("english", query)
    return _section_ids(
        session,
        DocumentSection.search_text.op("@@")(question),
        func.ts_rank(DocumentSection.search_text, question).desc(),
    )


def _name_section_ids(session: Session, query: str) -> list[int]:
    """Trigram similarity over headings and notes, closest first."""
    score = func.greatest(
        func.similarity(DocumentSection.heading_path, query),
        func.similarity(DocumentSection.note, query),
    )
    return _section_ids(session, score > NAME_FLOOR, score.desc())


def _entry_ids(session: Session, version_id: int, where, order) -> list[int]:
    """Entry IDs of one version in rank order."""
    return list(
        session.scalars(
            select(KbEntry.id)
            .where(KbEntry.version_id == version_id, where)
            .order_by(order)
            .limit(PER_CHANNEL)
        )
    )


def _meaning_entry_ids(session: Session, version_id: int, vector: list[float]) -> list[int]:
    """Closest entry vectors of one version first."""
    return _entry_ids(
        session,
        version_id,
        KbEntry.embedding.is_not(None),
        KbEntry.embedding.cosine_distance(vector),
    )


def _word_entry_ids(session: Session, version_id: int, query: str) -> list[int]:
    """Full-text matches of one version, best rank first."""
    question = func.plainto_tsquery("english", query)
    return _entry_ids(
        session,
        version_id,
        KbEntry.search_text.op("@@")(question),
        func.ts_rank(KbEntry.search_text, question).desc(),
    )


def _name_entry_ids(session: Session, version_id: int, query: str) -> list[int]:
    """Trigram similarity over entry titles, closest first."""
    score = func.similarity(KbEntry.title, query)
    return _entry_ids(session, version_id, score > NAME_FLOOR, score.desc())


def _fuse(rank_lists: list[list[int]], limit: int) -> list[int]:
    """Reciprocal-rank fusion: shared hits rise, every hit appears once."""
    scores: dict[int, float] = {}
    for ranks in rank_lists:
        for rank, ident in enumerate(ranks, start=1):
            scores[ident] = scores.get(ident, 0.0) + 1.0 / (RRF_K + rank)
    ordered = sorted(scores, key=lambda ident: (-scores[ident], ident))
    return ordered[:limit]
