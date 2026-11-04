"""Finding the right table by asking for it in words (architecture Part 5.2)."""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Float, Select, func, select
from sqlalchemy.sql.elements import ColumnElement

from charie.config import Settings
from charie.db.models import CARD_TEXT_CONFIGURATION, CatalogSnapshot, CatalogTable
from charie.knowledge.embeddings import Embedder, embed_texts
from charie.llm.base import LLMError
from charie.tenancy.session import org_session

__all__ = ["CardHit", "search_cards"]

logger = logging.getLogger(__name__)

#: Enough to choose from, few enough to put in a prompt.
DEFAULT_LIMIT = 10
MAX_LIMIT = 50

#: How deep each arm looks before the merge.
CANDIDATE_DEPTH = 25

#: RRF's smoothing constant, the value the original paper used.
RRF_K = 60

#: Word characters only. Everything else — quotes, operators, punctuation — is a separator.
_WORD = re.compile(r"[^0-9A-Za-z_]+")

#: A single letter carries no meaning and matches half the catalog.
_MIN_TERM = 2


def _or_terms(text: str) -> str:
    """The caller's words, joined by OR, as ``to_tsquery`` syntax."""
    terms = [term for term in _WORD.split(text) if len(term) >= _MIN_TERM]
    return " | ".join(terms)


@dataclass(frozen=True, slots=True)
class CardHit:
    data_source_id: uuid.UUID
    schema_name: str
    table_name: str
    card_text: str
    #: The merged score: with one arm it is `ts_rank_cd`, with two it is the RRF sum.
    rank: float
    #: Which arm found it: `vector`, `lexical`, or `both`.
    found_by: str = "lexical"


#: One row as either arm returns it, before the merge.
_Row = tuple[uuid.UUID, str, str, str | None]

#: What identifies a card across the two arms: its source and its qualified name.
_Key = tuple[uuid.UUID, str, str]


async def search_cards(
    org_id: uuid.UUID,
    query: str,
    *,
    data_source_id: uuid.UUID | None = None,
    limit: int = DEFAULT_LIMIT,
    embedder: Embedder | None = None,
    run_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    settings: Settings | None = None,
) -> list[CardHit]:
    """Table cards matching ``query``, best first."""
    text = query.strip()
    if not text:
        return []

    capped = max(1, min(limit, MAX_LIMIT))
    vector = await _query_vector(
        org_id=org_id,
        query=text,
        embedder=embedder,
        run_id=run_id,
        actor_user_id=actor_user_id,
        settings=settings,
    )

    def scoped(
        statement: Select[tuple[uuid.UUID, str, str, str | None]],
    ) -> Select[tuple[uuid.UUID, str, str, str | None]]:
        statement = statement.join(
            CatalogSnapshot, CatalogSnapshot.id == CatalogTable.snapshot_id
        ).where(CatalogSnapshot.status == "active")
        if data_source_id is not None:
            statement = statement.where(CatalogSnapshot.data_source_id == data_source_id)
        return statement

    def selected() -> Select[tuple[uuid.UUID, str, str, str | None]]:
        return select(
            CatalogSnapshot.data_source_id,
            CatalogTable.schema_name,
            CatalogTable.table_name,
            CatalogTable.card_text,
        )

    def matching(tsquery: ColumnElement[str]) -> Select[tuple[uuid.UUID, str, str, str | None]]:
        rank: ColumnElement[float] = func.ts_rank_cd(CatalogTable.card_tsv, tsquery).cast(Float)
        return (
            scoped(selected())
            .where(CatalogTable.card_tsv.op("@@")(tsquery))
            # Ties broken by name so the same query twice gives the same answer.
            .order_by(rank.desc(), CatalogTable.schema_name, CatalogTable.table_name)
            .limit(CANDIDATE_DEPTH)
        )

    def nearest(embedded: list[float]) -> Select[tuple[uuid.UUID, str, str, str | None]]:
        # `is_not(None)` is stated rather than left to the operator.
        return (
            scoped(selected())
            .where(CatalogTable.embedding.is_not(None))
            .order_by(
                CatalogTable.embedding.cosine_distance(embedded),
                CatalogTable.schema_name,
                CatalogTable.table_name,
            )
            .limit(CANDIDATE_DEPTH)
        )

    terms = _or_terms(text)
    async with org_session(org_id) as session:

        async def rows(statement: Select[tuple[uuid.UUID, str, str, str | None]]) -> list[_Row]:
            # Destructured into plain tuples rather than passed on as SQLAlchemy `Row`s.
            return [
                (source_id, schema_name, table_name, card_text)
                for source_id, schema_name, table_name, card_text in (
                    await session.execute(statement)
                ).all()
            ]

        lexical = await rows(matching(_strict(text)))
        semantic = await rows(nearest(vector)) if vector else []
        if not lexical and terms and not semantic:
            # Nothing matched with every word required.
            lexical = await rows(matching(func.to_tsquery(CARD_TEXT_CONFIGURATION, terms)))

    return _merge(lexical, semantic)[:capped]


def _strict(text: str) -> ColumnElement[str]:
    return func.websearch_to_tsquery(CARD_TEXT_CONFIGURATION, text)


async def _query_vector(
    *,
    org_id: uuid.UUID,
    query: str,
    embedder: Embedder | None,
    run_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    settings: Settings | None,
) -> list[float] | None:
    """The question as a vector, or None and a line in the log."""
    if embedder is None:
        return None
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
        logger.warning("card search fell back to wording alone: %s", error)
        return None
    return list(vectors[0]) if vectors else None


def _merge(lexical: Sequence[_Row], semantic: Sequence[_Row]) -> list[CardHit]:
    """Reciprocal Rank Fusion over the two arms, best first."""
    # Keyed by source as well as name.
    scores: dict[_Key, float] = {}
    arms: dict[_Key, set[str]] = {}
    rows: dict[_Key, _Row] = {}

    for arm, found in (("lexical", lexical), ("vector", semantic)):
        for position, row in enumerate(found, start=1):
            key = (row[0], row[1], row[2])
            rows.setdefault(key, row)
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + position)
            arms.setdefault(key, set()).add(arm)

    # Ties broken by name, for the reason the lexical order already was.
    ordered = sorted(scores, key=lambda key: (-scores[key], key[1], key[2], str(key[0])))
    return [
        CardHit(
            data_source_id=rows[key][0],
            schema_name=rows[key][1],
            table_name=rows[key][2],
            card_text=rows[key][3] or "",
            rank=scores[key],
            found_by="both" if len(arms[key]) > 1 else next(iter(arms[key])),
        )
        for key in ordered
    ]
