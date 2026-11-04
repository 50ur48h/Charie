"""Admin-approved question→SQL pairs, shown to the planner (arch 5.4)."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select

from charie.db.models import VerifiedQuery as VerifiedQueryRow
from charie.tenancy.session import org_session

__all__ = [
    "MAX_EXAMPLES",
    "VerifiedQuery",
    "create",
    "matching",
    "retire",
    "verified_for",
]

STATUS_ACTIVE = "active"
STATUS_RETIRED = "retired"

#: How many examples one prompt may carry.
MAX_EXAMPLES = 3

#: Words that appear in every question and so distinguish none of them.
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "from",
        "by",
        "with",
        "without",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "do",
        "does",
        "did",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "when",
        "where",
        "why",
        "how",
        "many",
        "much",
        "me",
        "my",
        "our",
        "we",
        "us",
        "you",
        "your",
        "show",
        "tell",
        "give",
        "list",
        "find",
        "get",
        "me",
        "please",
        "about",
        "into",
        "over",
        "under",
        "per",
        "each",
        "all",
        "any",
        "some",
        "no",
        "not",
    ]
)

_WORD = re.compile(r"[a-z0-9_]+")


class VerifiedQueryError(ValueError):
    """An example that could not be accepted, with the reason in its message."""


@dataclass(frozen=True, slots=True)
class VerifiedQuery:
    """One approved question and the statement that answers it."""

    id: uuid.UUID
    question: str
    sql: str
    notes: str | None = None

    def render(self) -> str:
        """How the example reaches the prompt (L3)."""
        lines = [f"Question: {self.question}"]
        if self.notes:
            lines.append(f"Why this shape: {self.notes}")
        lines.append(f"SQL:\n{self.sql.strip()}")
        return "\n".join(lines)


def _terms(text: str) -> frozenset[str]:
    """The content words of a question, lowercased."""
    return frozenset(word for word in _WORD.findall(text.lower()) if word not in _STOPWORDS)


def matching(examples: Sequence[VerifiedQuery], question: str) -> tuple[VerifiedQuery, ...]:
    """The examples worth showing for this question, best first."""
    asked = _terms(question)
    if not asked:
        return ()

    scored: list[tuple[float, int, VerifiedQuery]] = []
    for position, example in enumerate(examples):
        stored = _terms(example.question)
        if not stored:
            continue
        shared = asked & stored
        if len(shared) < 2:
            continue
        scored.append((len(shared) / len(stored), position, example))

    # Descending by score, ascending by original position.
    scored.sort(key=lambda entry: (-entry[0], entry[1]))
    return tuple(example for _, _, example in scored[:MAX_EXAMPLES])


async def create(
    *,
    org_id: uuid.UUID,
    data_source_id: uuid.UUID,
    question: str,
    sql: str,
    notes: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> VerifiedQuery:
    """Approve one example, after checking this platform would run it."""
    from charie.dal.errors import PolicyViolation
    from charie.dal.policy import source_policy
    from charie.dal.validator import validate

    statement = sql.strip()
    asked = question.strip()
    if not statement or not asked:
        raise VerifiedQueryError("A verified query needs both a question and a statement.")

    policy = await source_policy(org_id, data_source_id)
    try:
        validate(statement, source=policy)
    except PolicyViolation as violation:
        raise VerifiedQueryError(
            f"That statement is not one this platform would run, so it cannot be an "
            f"approved example: {violation}"
        ) from violation

    example = VerifiedQuery(id=uuid.uuid4(), question=asked, sql=statement, notes=notes)
    async with org_session(org_id) as session:
        session.add(
            VerifiedQueryRow(
                id=example.id,
                org_id=org_id,
                data_source_id=data_source_id,
                question=example.question,
                sql=example.sql,
                notes=example.notes,
                status=STATUS_ACTIVE,
                created_by=actor_user_id,
            )
        )
        await session.flush()
    return example


async def verified_for(org_id: uuid.UUID, data_source_id: uuid.UUID) -> tuple[VerifiedQuery, ...]:
    """Every active example for one data source, oldest first."""
    async with org_session(org_id) as session:
        rows = (
            (
                await session.execute(
                    select(VerifiedQueryRow)
                    .where(
                        VerifiedQueryRow.data_source_id == data_source_id,
                        VerifiedQueryRow.status == STATUS_ACTIVE,
                    )
                    .order_by(VerifiedQueryRow.created_at)
                )
            )
            .scalars()
            .all()
        )
    return tuple(
        VerifiedQuery(id=row.id, question=row.question, sql=row.sql, notes=row.notes)
        for row in rows
    )


async def retire(*, org_id: uuid.UUID, verified_query_id: uuid.UUID) -> None:
    """Stop showing an example, without forgetting it existed."""
    async with org_session(org_id) as session:
        row = await session.get(VerifiedQueryRow, verified_query_id)
        if row is None or row.status != STATUS_ACTIVE:
            raise LookupError("No such verified query")
        row.status = STATUS_RETIRED
        await session.flush()
