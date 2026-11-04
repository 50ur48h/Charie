"""Importing the definitions a database already carries (B-059, WP10.2d)."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from sqlalchemy import select

from charie.db.models import SemanticDefinition
from charie.orgs.service import audit
from charie.semantic.definitions import Definition, RequiredFilter, record_version, validate
from charie.tenancy.session import org_session

__all__ = [
    "ColumnMapping",
    "Proposal",
    "accept",
    "proposals_for",
    "propose_from_table",
    "reject",
]

STATUS_PROPOSED = "proposed"
STATUS_ACTIVE = "active"
STATUS_RETIRED = "retired"

#: How many rows one import may read.
MAX_ROWS = 200

#: A bare SQL identifier. Everything this module interpolates into a statement — schema, table.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class ColumnMapping:
    """Which of the customer's columns mean what."""

    name: str
    description: str
    expression: str | None = None
    synonyms: str | None = None
    caveat: str | None = None

    def columns(self) -> tuple[str, ...]:
        """The columns to select, deduplicated and in order."""
        seen: dict[str, None] = {}
        for column in (self.name, self.description, self.expression, self.synonyms, self.caveat):
            if column:
                seen.setdefault(column, None)
        return tuple(seen)


@dataclass(frozen=True, slots=True)
class Proposal:
    """A definition awaiting an Admin, and where it came from."""

    id: uuid.UUID
    name: str
    description: str
    expression: str | None
    synonyms: tuple[str, ...]
    caveat: str | None
    provenance: dict[str, object]


async def propose_from_table(
    *,
    org_id: uuid.UUID,
    data_source_id: uuid.UUID,
    table: str,
    mapping: ColumnMapping,
    actor_user_id: uuid.UUID | None = None,
    schema: str = "public",
) -> tuple[Proposal, ...]:
    """Read a customer's metric table and write what it says as proposals."""
    from charie.dal import service as dal

    qualified = f"{_identifier(schema, 'schema')}.{_identifier(table, 'table')}"
    columns = ", ".join(_identifier(name, "column") for name in mapping.columns())
    # Through the DAL, so the catalog grounds it, the cap applies and the read is recorded.
    execution = await dal.run(
        org_id=org_id,
        data_source_id=data_source_id,
        # Every fragment here has been through `_IDENTIFIER`.
        sql=f"SELECT {columns} FROM {qualified}",  # noqa: S608
        actor_user_id=actor_user_id,
        max_rows=MAX_ROWS,
    )

    position = {name.lower(): index for index, name in enumerate(execution.frame.columns)}
    snapshot_id = _snapshot_of(execution)

    async with org_session(org_id) as session:
        taken = {
            name.lower()
            for name in (
                await session.execute(
                    select(SemanticDefinition.name).where(
                        SemanticDefinition.data_source_id == data_source_id
                    )
                )
            ).scalars()
        }

        created: list[Proposal] = []
        for row in execution.frame.rows:
            name = _cell(row, position, mapping.name)
            description = _cell(row, position, mapping.description)
            if not name.strip() or not description.strip():
                # A row missing either is not a definition.
                continue
            key = name.strip().lower()
            if key in taken:
                continue
            taken.add(key)

            provenance: dict[str, object] = {
                "kind": "import",
                "table": qualified,
                "snapshot_id": str(snapshot_id) if snapshot_id else None,
                "columns": {
                    "name": mapping.name,
                    "description": mapping.description,
                    "expression": mapping.expression,
                    "caveat": mapping.caveat,
                },
            }
            proposal = Proposal(
                id=uuid.uuid4(),
                name=key,
                description=description.strip(),
                expression=_cell(row, position, mapping.expression).strip() or None,
                synonyms=_synonyms(_cell(row, position, mapping.synonyms)),
                caveat=_cell(row, position, mapping.caveat).strip() or None,
                provenance=provenance,
            )
            session.add(
                SemanticDefinition(
                    id=proposal.id,
                    org_id=org_id,
                    data_source_id=data_source_id,
                    name=proposal.name,
                    kind="metric",
                    description=proposal.description,
                    expression=proposal.expression,
                    required_filters=[],
                    synonyms=list(proposal.synonyms),
                    caveat=proposal.caveat,
                    provenance=provenance,
                    status=STATUS_PROPOSED,
                    created_by=actor_user_id,
                )
            )
            created.append(proposal)
        await session.flush()
    return tuple(created)


async def proposals_for(org_id: uuid.UUID, data_source_id: uuid.UUID) -> tuple[Proposal, ...]:
    """Everything waiting for an Admin, oldest first."""
    async with org_session(org_id) as session:
        rows = (
            (
                await session.execute(
                    select(SemanticDefinition)
                    .where(
                        SemanticDefinition.data_source_id == data_source_id,
                        SemanticDefinition.status == STATUS_PROPOSED,
                    )
                    .order_by(SemanticDefinition.created_at)
                )
            )
            .scalars()
            .all()
        )
    return tuple(
        Proposal(
            id=row.id,
            name=row.name,
            description=row.description,
            expression=row.expression,
            synonyms=tuple(str(word) for word in row.synonyms),
            caveat=row.caveat,
            provenance=dict(row.provenance or {}),
        )
        for row in rows
    )


async def accept(
    *,
    org_id: uuid.UUID,
    definition_id: uuid.UUID,
    required_filters: Sequence[Mapping[str, object]] = (),
    synonyms: Sequence[str] | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> Definition:
    """Bless a proposal into a definition, optionally giving it filters."""
    from charie.dal.policy import source_policy

    async with org_session(org_id) as session:
        row = await session.get(SemanticDefinition, definition_id)
        if row is None or row.status != STATUS_PROPOSED:
            raise LookupError("No such proposal")
        parsed = tuple(RequiredFilter.of(dict(item)) for item in required_filters)
        definition = Definition(
            id=row.id,
            name=row.name,
            kind=row.kind,
            description=row.description,
            expression=row.expression,
            required_filters=parsed,
            synonyms=tuple(str(word) for word in row.synonyms),
            caveat=row.caveat,
        )
        if synonyms is not None:
            words = tuple(word.strip() for word in synonyms if word.strip())
            definition = replace(definition, synonyms=words)
        if parsed:
            validate(definition, await source_policy(org_id, row.data_source_id))
        row.required_filters = [
            {
                "table": item.table,
                "column": item.column,
                "op": item.op,
                "values": list(item.values),
            }
            for item in parsed
        ]
        row.synonyms = list(definition.synonyms)
        row.status = STATUS_ACTIVE
        # Who blessed it, over who imported it: acceptance is the act that made this bind anything.
        row.created_by = actor_user_id or row.created_by
        # Version 1 is the first state it was ever in force in, which is this one.
        record_version(session, row, change="accepted", actor_user_id=actor_user_id)
        audit(
            session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="semantic.definition_accepted",
            object_type="semantic_definition",
            object_id=str(row.id),
            details={"name": row.name, "version": row.version, "binds": bool(parsed)},
        )
        await session.flush()
    return replace(definition, version=row.version)


async def reject(
    *, org_id: uuid.UUID, definition_id: uuid.UUID, actor_user_id: uuid.UUID | None = None
) -> None:
    """Retire a proposal rather than deleting it."""
    async with org_session(org_id) as session:
        row = await session.get(SemanticDefinition, definition_id)
        if row is None or row.status != STATUS_PROPOSED:
            raise LookupError("No such proposal")
        row.status = STATUS_RETIRED
        audit(
            session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="semantic.definition_rejected",
            object_type="semantic_definition",
            object_id=str(row.id),
            details={"name": row.name},
        )
        await session.flush()


def _identifier(name: str, kind: str) -> str:
    """A bare SQL identifier, or a refusal naming what was wrong with it."""
    if not _IDENTIFIER.match(name or ""):
        raise ValueError(
            f"{name!r} is not a valid {kind} name. An import names plain tables and "
            "columns; quoting, dots and expressions are not accepted here."
        )
    return name


def _cell(row: Sequence[object], position: Mapping[str, int], column: str | None) -> str:
    if not column:
        return ""
    index = position.get(column.lower())
    if index is None or index >= len(row):
        return ""
    value = row[index]
    return "" if value is None else str(value)


def _synonyms(raw: str) -> tuple[str, ...]:
    """A comma-separated cell, as a tuple. Empty when the column was not mapped."""
    return tuple(word.strip() for word in raw.split(",") if word.strip())


def _snapshot_of(execution: object) -> uuid.UUID | None:
    """The catalog snapshot the read was grounded against, when it is knowable."""
    validated = getattr(execution, "validated", None)
    found = getattr(validated, "snapshot_id", None)
    return found if isinstance(found, uuid.UUID) else None
