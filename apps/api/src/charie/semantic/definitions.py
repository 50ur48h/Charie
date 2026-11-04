"""What a metric means here, and the half of it a check can act on (arch 5.4)."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Final, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from charie.dal.policy import SourcePolicy
from charie.db.models import SemanticDefinition, SemanticDefinitionVersion
from charie.orgs.service import audit
from charie.tenancy.session import org_session

__all__ = [
    "FILTER_OPERATORS",
    "KEEP",
    "Definition",
    "Keep",
    "RequiredFilter",
    "Version",
    "create",
    "definitions_for",
    "matching",
    "record_version",
    "reinstate",
    "retire",
    "update",
    "validate",
    "versions_for",
]

STATUS_ACTIVE = "active"
STATUS_RETIRED = "retired"

#: The operators a filter may use.
FILTER_OPERATORS: tuple[str, ...] = ("in", "not_in", "eq", "ne", "gt", "gte", "lt", "lte")

#: Operators whose meaning is carried by their values.
_NEEDS_VALUES = frozenset(FILTER_OPERATORS)


class DefinitionError(ValueError):
    """A definition that could not be accepted, with the reason in its message."""


@dataclass(frozen=True, slots=True)
class RequiredFilter:
    """One predicate a statement must honour to be computing this metric."""

    table: str
    column: str
    op: str
    values: tuple[str, ...] = ()

    @property
    def qualified(self) -> str:
        return f"{self.table}.{self.column}"

    def describe(self) -> str:
        """The filter as a person would read it, for a prompt and for a finding."""
        readable = {
            "in": "one of",
            "not_in": "none of",
            "eq": "equal to",
            "ne": "not equal to",
            "gt": "greater than",
            "gte": "at least",
            "lt": "less than",
            "lte": "at most",
        }[self.op]
        return f"{self.qualified} {readable} {', '.join(self.values)}"

    @classmethod
    def of(cls, raw: dict[str, object]) -> RequiredFilter:
        table = str(raw.get("table", "")).strip()
        column = str(raw.get("column", "")).strip()
        op = str(raw.get("op", "")).strip().lower()
        values = raw.get("values", [])
        if not table or not column:
            raise DefinitionError("a required filter must name a table and a column")
        if op not in FILTER_OPERATORS:
            raise DefinitionError(
                f"{op!r} is not a filter operator this layer can check. "
                f"Use one of: {', '.join(FILTER_OPERATORS)}."
            )
        listed: tuple[str, ...] = ()
        if isinstance(values, list):
            listed = tuple(str(value) for value in cast("list[object]", values))
        if op in _NEEDS_VALUES and not listed:
            raise DefinitionError(f"the {op!r} filter on {table}.{column} names no values")
        return cls(table=table, column=column, op=op, values=listed)


@dataclass(frozen=True, slots=True)
class Definition:
    """One metric or dimension, as the prompt and the critic each need it."""

    id: uuid.UUID
    name: str
    kind: str
    description: str
    expression: str | None = None
    required_filters: tuple[RequiredFilter, ...] = ()
    synonyms: tuple[str, ...] = ()
    #: What this definition makes the answer say (revision 0033).
    caveat: str | None = None
    #: Which state of this definition the caller is holding (B-088).
    version: int = 1

    @property
    def names(self) -> tuple[str, ...]:
        """Everything this definition answers to, lowercased."""
        spoken = {self.name.lower(), self.name.lower().replace("_", " ")}
        return tuple(sorted(spoken | {synonym.lower() for synonym in self.synonyms}))

    def render(self) -> str:
        """How the definition reaches the prompt (L3)."""
        lines = [f"### {self.name}", self.description.strip()]
        if self.expression:
            lines.append(f"Computed as: {self.expression}")
        if self.required_filters:
            lines.append(
                "This metric is only correct with these filters, and the query you "
                "write is checked against them: "
                + "; ".join(item.describe() for item in self.required_filters)
                + "."
            )
        return "\n".join(lines)


def _word(term: str) -> re.Pattern[str]:
    """A whole-word matcher for a term that may contain spaces."""
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)


def matching(definitions: Sequence[Definition], question: str) -> tuple[Definition, ...]:
    """The definitions this question is about, in the order they were given."""
    if not question.strip():
        return ()
    found: list[Definition] = []
    for definition in definitions:
        if any(_word(term).search(question) for term in definition.names):
            found.append(definition)
    return tuple(found)


def validate(definition: Definition, policy: SourcePolicy) -> None:
    """Refuse a definition this database cannot support, naming what is wrong."""
    known = {
        (table.table_name.lower(), column.name.lower())
        for table in policy.catalog.tables
        for column in table.columns
    }
    tables = {table.table_name.lower() for table in policy.catalog.tables}
    for item in definition.required_filters:
        if item.table.lower() not in tables:
            raise DefinitionError(
                f"{definition.name!r} requires a filter on {item.qualified}, and this "
                f"data source has no table called {item.table!r}."
            )
        if (item.table.lower(), item.column.lower()) not in known:
            raise DefinitionError(
                f"{definition.name!r} requires a filter on {item.qualified}, and "
                f"{item.table!r} has no column called {item.column!r}."
            )


def _satisfies(value: str, item: RequiredFilter) -> bool | None:
    """Whether a single known value passes this filter."""
    if item.op in ("in", "eq"):
        return value in item.values
    if item.op in ("not_in", "ne"):
        return value not in item.values
    if not item.values:
        return None
    try:
        left = float(value)
        right = float(item.values[0])
    except (TypeError, ValueError):
        return None
    return {
        "gt": left > right,
        "gte": left >= right,
        "lt": left < right,
        "lte": left <= right,
    }.get(item.op)


def non_constraining(definition: Definition, policy: SourcePolicy) -> tuple[RequiredFilter, ...]:
    """The required filters that currently exclude no row at all (B-171)."""
    columns = {
        (table.table_name.lower(), column.name.lower()): column
        for table in policy.catalog.tables
        for column in table.columns
    }
    found: list[RequiredFilter] = []
    for item in definition.required_filters:
        column = columns.get((item.table.lower(), item.column.lower()))
        if column is None or column.distinct_est != 1 or not column.top_values:
            continue
        only = column.top_values[0].get("value")
        if only is None or _satisfies(str(only), item) is not True:
            continue
        found.append(item)
    return tuple(found)


async def create(
    *,
    org_id: uuid.UUID,
    data_source_id: uuid.UUID,
    name: str,
    description: str,
    required_filters: Sequence[dict[str, object]] = (),
    expression: str | None = None,
    caveat: str | None = None,
    synonyms: Sequence[str] = (),
    kind: str = "metric",
    status: str = STATUS_ACTIVE,
    actor_user_id: uuid.UUID | None = None,
    policy: SourcePolicy | None = None,
) -> Definition:
    """Write a definition, after checking this database can support it."""
    from charie.dal.policy import source_policy

    resolved = policy if policy is not None else await source_policy(org_id, data_source_id)
    definition = Definition(
        id=uuid.uuid4(),
        name=name.strip().lower(),
        kind=kind,
        description=description.strip(),
        expression=expression,
        caveat=(caveat.strip() or None) if caveat else None,
        required_filters=tuple(RequiredFilter.of(dict(item)) for item in required_filters),
        synonyms=tuple(word.strip() for word in synonyms if word.strip()),
    )
    validate(definition, resolved)

    async with org_session(org_id) as session:
        row = SemanticDefinition(
            id=definition.id,
            org_id=org_id,
            data_source_id=data_source_id,
            name=definition.name,
            kind=definition.kind,
            description=definition.description,
            expression=definition.expression,
            caveat=definition.caveat,
            required_filters=_filters_json(definition.required_filters),
            synonyms=list(definition.synonyms),
            status=status,
            version=1,
            created_by=actor_user_id,
        )
        session.add(row)
        if status == STATUS_ACTIVE:
            # A proposal is not a version: it binds nothing while it waits.
            record_version(session, row, change="created", actor_user_id=actor_user_id)
            audit(
                session,
                org_id=org_id,
                actor_user_id=actor_user_id,
                action="semantic.definition_created",
                object_type="semantic_definition",
                object_id=str(row.id),
                details={
                    "name": row.name,
                    "version": row.version,
                    "binds": bool(definition.required_filters),
                },
            )
        await session.flush()
    return definition


async def definitions_for(
    org_id: uuid.UUID, data_source_id: uuid.UUID, *, status: str = STATUS_ACTIVE
) -> tuple[Definition, ...]:
    """Every definition for one data source in one state, by name."""
    async with org_session(org_id) as session:
        rows = (
            (
                await session.execute(
                    select(SemanticDefinition)
                    .where(
                        SemanticDefinition.data_source_id == data_source_id,
                        SemanticDefinition.status == status,
                    )
                    .order_by(SemanticDefinition.name)
                )
            )
            .scalars()
            .all()
        )
    return tuple(_definition_of(row) for row in rows)


@dataclass(frozen=True, slots=True)
class Version:
    """One state a definition has been in force in (B-088, revision 0022)."""

    version: int
    change: str
    name: str
    description: str
    expression: str | None
    caveat: str | None
    required_filters: tuple[RequiredFilter, ...]
    synonyms: tuple[str, ...]
    status: str
    changed_by: uuid.UUID | None
    changed_at: datetime


class Keep:
    """The sentinel meaning "this field was not sent"."""

    __slots__ = ()


KEEP: Final = Keep()


def _filters_json(filters: Sequence[RequiredFilter]) -> list[dict[str, object]]:
    return [
        {"table": item.table, "column": item.column, "op": item.op, "values": list(item.values)}
        for item in filters
    ]


def record_version(
    session: AsyncSession,
    row: SemanticDefinition,
    *,
    change: str,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Append the state ``row`` is now in to its history."""
    session.add(
        SemanticDefinitionVersion(
            org_id=row.org_id,
            definition_id=row.id,
            version=row.version,
            name=row.name,
            kind=row.kind,
            description=row.description,
            expression=row.expression,
            caveat=row.caveat,
            required_filters=list(row.required_filters),
            synonyms=list(row.synonyms),
            status=row.status,
            change=change,
            changed_by=actor_user_id,
        )
    )


async def update(
    *,
    org_id: uuid.UUID,
    definition_id: uuid.UUID,
    description: str | None = None,
    expression: str | Keep | None = KEEP,
    caveat: str | Keep | None = KEEP,
    synonyms: Sequence[str] | None = None,
    required_filters: Sequence[Mapping[str, object]] | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> Definition:
    """Correct an active definition, validating it exactly as ``accept`` does."""
    from charie.dal.policy import source_policy

    async with org_session(org_id) as session:
        row = await session.get(SemanticDefinition, definition_id)
        if row is None or row.status != STATUS_ACTIVE:
            # Proposals are not edited, they are accepted.
            raise LookupError("No such definition")

        current = _definition_of(row)
        edited = current
        if description is not None:
            edited = replace(edited, description=description.strip())
        if not isinstance(expression, Keep):
            edited = replace(edited, expression=expression)
        if not isinstance(caveat, Keep):
            edited = replace(edited, caveat=caveat)
        if synonyms is not None:
            edited = replace(
                edited, synonyms=tuple(word.strip() for word in synonyms if word.strip())
            )
        if required_filters is not None:
            edited = replace(
                edited,
                required_filters=tuple(RequiredFilter.of(dict(item)) for item in required_filters),
            )

        if edited.required_filters:
            validate(edited, await source_policy(org_id, row.data_source_id))

        changed = tuple(
            field
            for field, before, after in (
                ("description", current.description, edited.description),
                ("expression", current.expression, edited.expression),
                ("caveat", current.caveat, edited.caveat),
                ("synonyms", current.synonyms, edited.synonyms),
                ("required_filters", current.required_filters, edited.required_filters),
            )
            if before != after
        )
        if not changed:
            # Nothing to record.
            return current

        row.description = edited.description
        row.expression = edited.expression
        row.caveat = edited.caveat
        row.synonyms = list(edited.synonyms)
        row.required_filters = _filters_json(edited.required_filters)
        row.updated_at = datetime.now(UTC)
        row.version += 1
        record_version(session, row, change="updated", actor_user_id=actor_user_id)
        audit(
            session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="semantic.definition_updated",
            object_type="semantic_definition",
            object_id=str(row.id),
            # Which fields moved and which version to read, not the values.
            details={
                "name": row.name,
                "changed": list(changed),
                "version": row.version,
                "binds": bool(edited.required_filters),
            },
        )
        await session.flush()
        return replace(edited, version=row.version)


async def retire(
    *, org_id: uuid.UUID, definition_id: uuid.UUID, actor_user_id: uuid.UUID | None = None
) -> None:
    """Take an active definition out of force, keeping what it said."""
    async with org_session(org_id) as session:
        row = await session.get(SemanticDefinition, definition_id)
        if row is None or row.status != STATUS_ACTIVE:
            raise LookupError("No such definition")
        row.status = STATUS_RETIRED
        row.updated_at = datetime.now(UTC)
        row.version += 1
        record_version(session, row, change="retired", actor_user_id=actor_user_id)
        audit(
            session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="semantic.definition_retired",
            object_type="semantic_definition",
            object_id=str(row.id),
            details={"name": row.name, "version": row.version},
        )
        await session.flush()


async def reinstate(
    *,
    org_id: uuid.UUID,
    definition_id: uuid.UUID,
    required_filters: Sequence[Mapping[str, object]] | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> Definition:
    """Bring a retired definition back into force (B-094)."""
    from charie.dal.policy import source_policy

    async with org_session(org_id) as session:
        row = await session.get(SemanticDefinition, definition_id)
        if row is None or row.status != STATUS_RETIRED:
            # A proposal that was rejected is `retired` too.
            raise LookupError("No such retired definition")

        definition = _definition_of(row)
        if required_filters is not None:
            definition = replace(
                definition,
                required_filters=tuple(RequiredFilter.of(dict(item)) for item in required_filters),
            )
        if definition.required_filters:
            validate(definition, await source_policy(org_id, row.data_source_id))

        row.required_filters = _filters_json(definition.required_filters)
        row.status = STATUS_ACTIVE
        row.updated_at = datetime.now(UTC)
        row.version += 1
        record_version(session, row, change="reinstated", actor_user_id=actor_user_id)
        audit(
            session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="semantic.definition_reinstated",
            object_type="semantic_definition",
            object_id=str(row.id),
            details={
                "name": row.name,
                "version": row.version,
                "binds": bool(definition.required_filters),
                "filters_corrected": required_filters is not None,
            },
        )
        await session.flush()
        return replace(definition, version=row.version)


async def versions_for(org_id: uuid.UUID, definition_id: uuid.UUID) -> tuple[Version, ...]:
    """Everything this definition has said, oldest first."""
    async with org_session(org_id) as session:
        rows = (
            (
                await session.execute(
                    select(SemanticDefinitionVersion)
                    .where(SemanticDefinitionVersion.definition_id == definition_id)
                    .order_by(SemanticDefinitionVersion.version)
                )
            )
            .scalars()
            .all()
        )
    return tuple(
        Version(
            version=row.version,
            change=row.change,
            name=row.name,
            description=row.description,
            expression=row.expression,
            caveat=row.caveat,
            required_filters=tuple(_readable_filters(row.required_filters)),
            synonyms=tuple(str(word) for word in row.synonyms),
            status=row.status,
            changed_by=row.changed_by,
            changed_at=row.created_at,
        )
        for row in rows
    )


def _readable_filters(raw: Sequence[dict[str, object]]) -> list[RequiredFilter]:
    """The filters a stored row carries, skipping any that cannot be read."""
    filters: list[RequiredFilter] = []
    for item in raw:
        with suppress(DefinitionError):
            filters.append(RequiredFilter.of(item))
    return filters


def _definition_of(row: SemanticDefinition) -> Definition:
    filters: list[RequiredFilter] = []
    for raw in row.required_filters:
        # A row that cannot be read is skipped rather than fatal.
        with suppress(DefinitionError):
            filters.append(RequiredFilter.of(raw))
    return Definition(
        id=row.id,
        name=row.name,
        kind=row.kind,
        description=row.description,
        expression=row.expression,
        caveat=row.caveat,
        required_filters=tuple(filters),
        synonyms=tuple(str(word) for word in row.synonyms),
        version=row.version,
    )
