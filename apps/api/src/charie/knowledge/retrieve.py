"""Finding the passage that answers "what does this mean here" (arch 5.5)."""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import Float, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from charie.config import Settings
from charie.db.models import KnowledgeChunk, KnowledgeDocument
from charie.knowledge.embeddings import Embedder, embed_texts
from charie.llm.base import LLMError
from charie.llm.budget import RunCostExceededError
from charie.tenancy.session import org_session

__all__ = ["Passage", "Retrieval", "search_knowledge"]

logger = logging.getLogger(__name__)

#: How many results a caller gets by default.
DEFAULT_LIMIT = 5

#: How deep each arm looks before the merge.
CANDIDATE_DEPTH = 25

#: At most this many chunks from any one document.
PER_DOCUMENT_CAP = 2

#: RRF's smoothing constant. 60 is the value the original paper used and the one every...
RRF_K = 60


@dataclass(frozen=True, slots=True)
class Passage:
    """One retrieved chunk, with everything needed to attribute it."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    seq: int
    text: str
    headings: tuple[str, ...]
    #: Which arm found it, for the trace: `vector`, `lexical`, or `both`.
    found_by: str = "both"
    score: float = 0.0

    @property
    def citation(self) -> str:
        """How the passage names itself in a prompt and in an answer."""
        trail = " > ".join(self.headings)
        return f"{self.document_title}{f' — {trail}' if trail else ''} (chunk {self.seq})"


#: Why the vector arm did not run, in words a person and a model can both read.
NO_EMBEDDER = (
    "Only the wording of the documents was searched: this deployment has no "
    "embedding model configured, so a passage that means the same thing in "
    "different words was not found."
)
EMBEDDING_REFUSED = (
    "Only the wording of the documents was searched: the search by meaning was "
    "not run because this run has reached its spending ceiling."
)
EMBEDDING_FAILED = (
    "Only the wording of the documents was searched: the search by meaning "
    "could not be run just now."
)


@dataclass(frozen=True, slots=True)
class Retrieval:
    """What one search found, and how much of the search actually happened."""

    passages: tuple[Passage, ...] = ()
    arms: tuple[str, ...] = ()
    #: Set when the vector arm was skipped, naming which of the ordinary reasons it was.
    degraded: str | None = None


@dataclass
class _Hit:
    """One chunk's standing across both arms, before the merge."""

    row: KnowledgeChunk
    title: str
    ranks: dict[str, int] = field(default_factory=dict[str, int])

    @property
    def found_by(self) -> str:
        return "both" if len(self.ranks) > 1 else next(iter(self.ranks))

    @property
    def score(self) -> float:
        # Reciprocal Rank Fusion: each arm contributes 1/(k + rank).
        return sum(1.0 / (RRF_K + rank) for rank in self.ranks.values())


async def search_knowledge(
    *,
    org_id: uuid.UUID,
    query: str,
    embedder: Embedder | None = None,
    limit: int = DEFAULT_LIMIT,
    document_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    settings: Settings | None = None,
) -> Retrieval:
    """The passages most likely to explain a term, best first."""
    if not query.strip():
        return Retrieval()

    vector, degraded = await _query_vector(
        org_id=org_id,
        query=query,
        embedder=embedder,
        run_id=run_id,
        actor_user_id=actor_user_id,
        settings=settings,
    )

    async with org_session(org_id) as session:
        hits: dict[uuid.UUID, _Hit] = {}
        if vector is not None:
            _absorb(hits, await _by_vector(session, org_id, vector, document_id), "vector")
        _absorb(hits, await _by_text(session, org_id, query, document_id), "lexical")

    # Merged and shaped outside the session.
    ordered = sorted(hits.values(), key=lambda hit: hit.score, reverse=True)
    arms = ("vector", "lexical") if vector is not None else ("lexical",)
    return Retrieval(passages=tuple(_capped(ordered, limit)), arms=arms, degraded=degraded)


async def _query_vector(
    *,
    org_id: uuid.UUID,
    query: str,
    embedder: Embedder | None,
    run_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    settings: Settings | None,
) -> tuple[list[float] | None, str | None]:
    """The query as a vector, or the reason there is not one."""
    if embedder is None:
        return None, NO_EMBEDDER

    try:
        vectors = await embed_texts(
            org_id=org_id,
            texts=[query],
            embedder=embedder,
            run_id=run_id,
            actor_user_id=actor_user_id,
            settings=settings,
        )
    except LLMError as error:
        # Logged, because a deployment whose vector arm has quietly stopped working should be...
        logger.warning("the query could not be embedded, searching lexically only: %s", error)
        if isinstance(error, RunCostExceededError):
            return None, EMBEDDING_REFUSED
        return None, EMBEDDING_FAILED

    return (list(vectors[0]), None) if vectors else (None, EMBEDDING_FAILED)


async def _by_vector(
    session: AsyncSession,
    org_id: uuid.UUID,
    vector: list[float],
    document_id: uuid.UUID | None,
) -> list[tuple[KnowledgeChunk, str]]:
    """Nearest by cosine distance, among chunks that have a vector at all."""
    statement = (
        select(KnowledgeChunk, KnowledgeDocument.title)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(
            # Redundant with row-level security, and deliberately so: two independent layers.
            KnowledgeChunk.org_id == org_id,
            KnowledgeChunk.embedding.is_not(None),
        )
        .order_by(KnowledgeChunk.embedding.cosine_distance(vector))
        .limit(CANDIDATE_DEPTH)
    )
    if document_id is not None:
        statement = statement.where(KnowledgeChunk.document_id == document_id)
    return list((await session.execute(statement)).all())  # type: ignore[arg-type]


async def _by_text(
    session: AsyncSession,
    org_id: uuid.UUID,
    query: str,
    document_id: uuid.UUID | None,
) -> list[tuple[KnowledgeChunk, str]]:
    """Postgres full-text, with B-041's lesson applied."""
    strict = func.websearch_to_tsquery("english", query)
    rows = await _ranked(session, org_id, strict, document_id)
    if rows:
        return rows

    words = [word for word in _words(query) if word]
    if not words:
        return []
    loose = func.to_tsquery("english", " | ".join(words))
    return await _ranked(session, org_id, loose, document_id)


async def _ranked(
    session: AsyncSession,
    org_id: uuid.UUID,
    tsquery: object,
    document_id: uuid.UUID | None,
) -> list[tuple[KnowledgeChunk, str]]:
    rank: ColumnElement[float] = func.ts_rank_cd(KnowledgeChunk.tsv, tsquery).cast(Float)
    statement = (
        select(KnowledgeChunk, KnowledgeDocument.title)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(KnowledgeChunk.org_id == org_id, KnowledgeChunk.tsv.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(CANDIDATE_DEPTH)
    )
    if document_id is not None:
        statement = statement.where(KnowledgeChunk.document_id == document_id)
    return list((await session.execute(statement)).all())  # type: ignore[arg-type]


def _words(query: str) -> list[str]:
    """The query's words, safe to put inside a `to_tsquery` string."""
    cleaned = "".join(character if character.isalnum() else " " for character in query.lower())
    return [word for word in cleaned.split() if len(word) > 1]


def _absorb(
    hits: dict[uuid.UUID, _Hit],
    rows: list[tuple[KnowledgeChunk, str]],
    arm: str,
) -> None:
    """Record each row's 1-based rank within one arm's result list."""
    for position, (row, title) in enumerate(rows, start=1):
        hit = hits.get(row.id)
        if hit is None:
            hit = _Hit(row=row, title=title)
            hits[row.id] = hit
        hit.ranks[arm] = position


def _capped(ordered: list[_Hit], limit: int) -> list[Passage]:
    """Best first, with no document allowed to fill the result on its own."""
    seen: defaultdict[uuid.UUID, int] = defaultdict(int)
    out: list[Passage] = []
    for hit in ordered:
        if len(out) >= limit:
            break
        if seen[hit.row.document_id] >= PER_DOCUMENT_CAP:
            continue
        seen[hit.row.document_id] += 1
        out.append(
            Passage(
                chunk_id=hit.row.id,
                document_id=hit.row.document_id,
                document_title=hit.title,
                seq=hit.row.seq,
                text=hit.row.text_,
                headings=tuple(str(heading) for heading in hit.row.headings),
                found_by=hit.found_by,
                score=hit.score,
            )
        )
    return out
