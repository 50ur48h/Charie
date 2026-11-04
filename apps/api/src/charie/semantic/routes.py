"""Semantic layer routes (architecture Part 10.2, plan WP10.2d)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from contextlib import suppress
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from charie.auth.context import RequestContext
from charie.auth.guards import require_admin
from charie.catalog.browse import NoCatalogError
from charie.connectors.base import ConnectorError
from charie.dal.errors import PolicyViolation
from charie.dal.policy import source_policy
from charie.datasources.service import NotFoundError
from charie.semantic import definitions as definitions_service
from charie.semantic import proposals as proposals_service
from charie.semantic import verified as verified_service
from charie.semantic.definitions import (
    FILTER_OPERATORS,
    KEEP,
    Definition,
    DefinitionError,
    Version,
)
from charie.semantic.proposals import ColumnMapping, Proposal
from charie.semantic.verified import VerifiedQuery, VerifiedQueryError

router = APIRouter(prefix="/v1", tags=["semantic"])

DataSourceId = Annotated[uuid.UUID, Path(description="Data source within this organization")]
DefinitionId = Annotated[uuid.UUID, Path(description="Definition within this organization")]
VerifiedQueryId = Annotated[uuid.UUID, Path(description="Verified query in this organization")]


class RequiredFilterModel(BaseModel):
    """One predicate a statement must honour to be computing this metric.

    The half of a definition a check can act on. `op` is a closed set because an
    operator the critic cannot check is one the product would claim to enforce
    and would not.
    """

    table: str = Field(min_length=1, description="Unqualified, as the catalog holds it")
    column: str = Field(min_length=1)
    op: str = Field(description=" | ".join(FILTER_OPERATORS))
    values: list[str] = Field(
        default_factory=list[str],
        description="Compared as text: 40 and '40' are the same thing to a reader of SQL.",
    )


class DefinitionOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    description: str
    expression: str | None = None
    caveat: str | None = Field(
        default=None,
        description=(
            "What an answer resting on this definition must say. Reaches the "
            "reader, not only the model: `description` and `expression` inform "
            "the prompt and bind nothing, so a limit stated only there is one a "
            "model can drop and nothing contradicts (D-053, facing the other way)."
        ),
    )
    required_filters: list[RequiredFilterModel] = Field(default_factory=list[RequiredFilterModel])
    synonyms: list[str] = Field(default_factory=list[str])
    binds: bool = Field(
        description=(
            "Whether this definition constrains generated SQL. False means it is "
            "prose: it informs the model and the critic checks nothing (D-033), "
            "and an answer resting on it says so."
        )
    )
    excluding_nothing: list[str] = Field(
        default_factory=list[str],
        description=(
            "Qualified names of required filters that currently exclude no row "
            "at all, because the column holds a single value the filter accepts "
            "(B-171). `binds` stays true — the critic really does check these — "
            "but a badge reading only *enforced* would overstate the guarantee. "
            "Derived from the live catalog on every read rather than stored, "
            "because a stored answer is what went quietly wrong last time."
        ),
    )
    version: int = Field(
        default=1,
        description=(
            "Which state of this definition is in force. Bumped by every edit, "
            "and the key into its history (B-088)."
        ),
    )

    @classmethod
    def of(cls, definition: Definition, *, excluding_nothing: Sequence[str] = ()) -> DefinitionOut:
        return cls(
            id=definition.id,
            name=definition.name,
            kind=definition.kind,
            description=definition.description,
            expression=definition.expression,
            caveat=definition.caveat,
            required_filters=[
                RequiredFilterModel(
                    table=item.table, column=item.column, op=item.op, values=list(item.values)
                )
                for item in definition.required_filters
            ],
            synonyms=list(definition.synonyms),
            binds=bool(definition.required_filters),
            excluding_nothing=list(excluding_nothing),
            version=definition.version,
        )


class ProposalOut(BaseModel):
    """A definition awaiting an Admin, and where it came from.

    `provenance` is on the wire because the review screen's first question is
    *"where did this sentence come from"* — the source table and the snapshot it
    was read at. A proposal whose origin cannot be shown is one nobody can
    responsibly accept.
    """

    id: uuid.UUID
    name: str
    description: str
    expression: str | None = None
    caveat: str | None = None
    synonyms: list[str] = Field(default_factory=list[str])
    provenance: dict[str, object] = Field(default_factory=dict[str, object])

    @classmethod
    def of(cls, proposal: Proposal) -> ProposalOut:
        return cls(
            id=proposal.id,
            name=proposal.name,
            description=proposal.description,
            expression=proposal.expression,
            caveat=proposal.caveat,
            synonyms=list(proposal.synonyms),
            provenance=dict(proposal.provenance),
        )


class CreateDefinitionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=4000)
    expression: str | None = Field(default=None, max_length=4000)
    caveat: str | None = Field(
        default=None,
        max_length=4000,
        description=(
            "What an answer resting on this definition must say. Reaches the "
            "reader, not only the model: `description` and `expression` inform "
            "the prompt and bind nothing, so a limit stated only there is one a "
            "model can drop and nothing contradicts (D-053, facing the other way)."
        ),
    )
    synonyms: list[str] = Field(
        default_factory=list[str],
        description="What people actually type. `net_revenue` is not one of them.",
    )
    required_filters: list[RequiredFilterModel] = Field(default_factory=list[RequiredFilterModel])
    kind: str = Field(default="metric")


class ImportIn(BaseModel):
    """Which of the customer's tables holds their metrics, and what its columns mean.

    **The mapping is configuration, not a guess.** Nothing divines that a table
    called `meta_metric` is authoritative or that `definition_text` is a
    description. Being wrong here is then a visible mistake in a proposal an
    Admin is about to review, rather than an invisible one in a definition that
    already binds.
    """

    table: str = Field(min_length=1, description="The customer's metric table")
    schema_name: str = Field(default="public", alias="schema")
    name_column: str = Field(min_length=1)
    description_column: str = Field(min_length=1)
    expression_column: str | None = None
    synonyms_column: str | None = Field(
        default=None, description="Comma-separated in the customer's own cell"
    )
    caveat_column: str | None = Field(
        default=None,
        description=(
            "A column saying what an answer using this metric must disclose, "
            "for example: never label this sum as the total cost. Left "
            "unmapped, imported definitions carry no caveat."
        ),
    )

    model_config = {"populate_by_name": True}


class AcceptIn(BaseModel):
    """The filters that turn an imported sentence into a constraint.

    Optional, and an empty list is a real answer rather than a missing one: an
    Admin may bless a definition as prose, which puts it in front of the model
    without binding it. What they cannot do is bless it as binding *by accident*,
    which is why the filters are typed here and not inferred from the sentence.
    """

    required_filters: list[RequiredFilterModel] = Field(default_factory=list[RequiredFilterModel])
    synonyms: list[str] | None = Field(
        default=None,
        description=(
            "What people actually call it. Omit to keep what the import found; send a "
            "list to replace it. An imported metric answers only to its key and to its "
            "own table's label until somebody says otherwise, and a metric nobody can "
            "name is a metric nobody gets (B-085)."
        ),
    )


class UpdateDefinitionIn(BaseModel):
    """A correction to an active definition (**B-088**).

    **Every field is optional and omission means "leave it alone."** A partial
    update is the shape this needs: an Admin fixing a filter should not have to
    resend a description they did not touch, because the resend is where the
    description quietly loses a sentence.

    `name` is absent on purpose. It is what a question is matched against and
    what a run's trace recorded, so renaming would silently change which
    questions the definition answers and orphan every citation of it. What people
    call the metric is `synonyms`, which is what the matcher actually reads.
    """

    description: str | None = Field(default=None, min_length=1, max_length=4000)
    expression: str | None = Field(
        default=None,
        max_length=4000,
        description=(
            "Send null to clear the formula. Omitting the field keeps it — the "
            "one place here where null and absent differ."
        ),
    )
    caveat: str | None = Field(
        default=None,
        max_length=4000,
        description=(
            "Send null to clear it. Omitting the field keeps it — the same "
            "null-versus-absent distinction `expression` makes."
        ),
    )
    synonyms: list[str] | None = Field(
        default=None, description="A list replaces what is there; omit to keep it."
    )
    required_filters: list[RequiredFilterModel] | None = Field(
        default=None,
        description=(
            "A list replaces what is enforced. An empty list is a real request — "
            "stop enforcing this and keep the prose — and an Admin has to be able "
            "to make it, since the alternative way to undo a wrong filter is psql."
        ),
    )


class ReinstateIn(BaseModel):
    """Optional corrections to make as a definition comes back into force.

    Omitted is the ordinary case and means *as it was retired*. Filters are
    accepted here because a retired definition cannot be edited — `PATCH` takes
    only active ones — so one whose catalog has moved on would otherwise be
    permanently unreinstatable, which is a second dead end behind the one B-094
    is about.
    """

    required_filters: list[RequiredFilterModel] | None = Field(
        default=None,
        description="Replaces what it was retired holding. Omit to keep them.",
    )


class VersionOut(BaseModel):
    """One state a definition has been in force in (**B-088**, arch 5.4)."""

    version: int
    change: str = Field(description=" | ".join(("created", "accepted", "updated", "retired")))
    name: str
    description: str
    expression: str | None = None
    caveat: str | None = None
    required_filters: list[RequiredFilterModel] = Field(default_factory=list[RequiredFilterModel])
    synonyms: list[str] = Field(default_factory=list[str])
    status: str
    changed_by: uuid.UUID | None = None
    changed_at: datetime

    @classmethod
    def of(cls, version: Version) -> VersionOut:
        return cls(
            version=version.version,
            change=version.change,
            name=version.name,
            description=version.description,
            expression=version.expression,
            caveat=version.caveat,
            required_filters=[
                RequiredFilterModel(
                    table=item.table, column=item.column, op=item.op, values=list(item.values)
                )
                for item in version.required_filters
            ],
            synonyms=list(version.synonyms),
            status=version.status,
            changed_by=version.changed_by,
            changed_at=version.changed_at,
        )


class VerifiedQueryOut(BaseModel):
    """One approved question and the statement that answers it (arch 5.4)."""

    id: uuid.UUID
    question: str
    sql: str
    notes: str | None = None

    @classmethod
    def of(cls, example: VerifiedQuery) -> VerifiedQueryOut:
        return cls(id=example.id, question=example.question, sql=example.sql, notes=example.notes)


class CreateVerifiedQueryIn(BaseModel):
    """An example an Admin is approving.

    The statement is validated against this data source's catalog by the same
    validator that guards execution, so an approved example naming a table that
    does not exist is refused here rather than sitting in a prompt teaching the
    model to invent one.
    """

    question: str = Field(min_length=1, max_length=2000)
    sql: str = Field(min_length=1, max_length=20000)
    notes: str | None = Field(
        default=None,
        max_length=2000,
        description="Why this shape is right — an example without its reason teaches copying.",
    )


def _filters(models: list[RequiredFilterModel]) -> list[dict[str, object]]:
    return [
        {"table": item.table, "column": item.column, "op": item.op, "values": list(item.values)}
        for item in models
    ]


def _no_such_source(error: Exception) -> HTTPException:
    """A missing data source and an undiscovered one, told apart."""
    if isinstance(error, NoCatalogError):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            f"{error} Refresh this data source's catalog and try again.",
        )
    return HTTPException(status.HTTP_404_NOT_FOUND, "No such data source")


@router.get(
    "/orgs/{org_id}/data-sources/{data_source_id}/verified-queries",
    response_model=list[VerifiedQueryOut],
    summary="Approved question and SQL pairs the planner is shown",
)
async def list_verified_queries(
    context: Annotated[RequestContext, Depends(require_admin)],
    data_source_id: DataSourceId,
) -> list[VerifiedQueryOut]:
    """The active ones, oldest first — the order the matcher breaks ties by."""
    found = await verified_service.verified_for(context.org_id, data_source_id)
    return [VerifiedQueryOut.of(example) for example in found]


@router.post(
    "/orgs/{org_id}/data-sources/{data_source_id}/verified-queries",
    response_model=VerifiedQueryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Approve a question and the SQL that answers it",
)
async def create_verified_query(
    body: CreateVerifiedQueryIn,
    context: Annotated[RequestContext, Depends(require_admin)],
    data_source_id: DataSourceId,
) -> VerifiedQueryOut:
    """Nothing is executed here. The statement is judged against the catalog, not run."""
    try:
        example = await verified_service.create(
            org_id=context.org_id,
            data_source_id=data_source_id,
            question=body.question,
            sql=body.sql,
            notes=body.notes,
            actor_user_id=context.user_id,
        )
    except VerifiedQueryError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    except (NotFoundError, NoCatalogError) as error:
        raise _no_such_source(error) from error
    return VerifiedQueryOut.of(example)


@router.delete(
    "/orgs/{org_id}/data-sources/{data_source_id}/verified-queries/{verified_query_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Stop showing an approved example",
)
async def retire_verified_query(
    context: Annotated[RequestContext, Depends(require_admin)],
    data_source_id: DataSourceId,
    verified_query_id: VerifiedQueryId,
) -> None:
    """Retired rather than deleted, so a run grounded in it last month is still explainable..."""
    try:
        await verified_service.retire(org_id=context.org_id, verified_query_id=verified_query_id)
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such verified query") from error


@router.get(
    "/orgs/{org_id}/data-sources/{data_source_id}/definitions",
    response_model=list[DefinitionOut],
    summary="Every definition binding this data source",
)
async def list_definitions(
    context: Annotated[RequestContext, Depends(require_admin)],
    data_source_id: DataSourceId,
    status: Annotated[
        Literal["active", "retired"],
        Query(description="`active` binds; `retired` is out of force and can be reinstated."),
    ] = "active",
) -> list[DefinitionOut]:
    """The active ones by default, by name."""
    found = await definitions_service.definitions_for(context.org_id, data_source_id, status=status)
    # One catalog load for the whole list (B-171).
    policy = None
    if status == "active" and any(d.required_filters for d in found):
        with suppress(NotFoundError, NoCatalogError):
            policy = await source_policy(context.org_id, data_source_id)
    return [
        DefinitionOut.of(
            definition,
            excluding_nothing=(
                []
                if policy is None
                else [
                    item.qualified
                    for item in definitions_service.non_constraining(definition, policy)
                ]
            ),
        )
        for definition in found
    ]


@router.get(
    "/orgs/{org_id}/data-sources/{data_source_id}/definitions/proposals",
    response_model=list[ProposalOut],
    summary="Imported definitions waiting for an Admin",
)
async def list_proposals(
    context: Annotated[RequestContext, Depends(require_admin)],
    data_source_id: DataSourceId,
) -> list[ProposalOut]:
    """Oldest first, so a review queue reads as a queue."""
    found = await proposals_service.proposals_for(context.org_id, data_source_id)
    return [ProposalOut.of(proposal) for proposal in found]


@router.post(
    "/orgs/{org_id}/data-sources/{data_source_id}/definitions",
    response_model=DefinitionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Write a definition by hand",
)
async def create_definition(
    body: CreateDefinitionIn,
    context: Annotated[RequestContext, Depends(require_admin)],
    data_source_id: DataSourceId,
) -> DefinitionOut:
    """Validated against the catalog before it is written, never after."""
    try:
        definition = await definitions_service.create(
            org_id=context.org_id,
            data_source_id=data_source_id,
            name=body.name,
            description=body.description,
            expression=body.expression,
            caveat=body.caveat,
            synonyms=body.synonyms,
            required_filters=_filters(body.required_filters),
            kind=body.kind,
            actor_user_id=context.user_id,
        )
    except DefinitionError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    except (NotFoundError, NoCatalogError) as error:
        raise _no_such_source(error) from error
    return DefinitionOut.of(definition)


@router.post(
    "/orgs/{org_id}/data-sources/{data_source_id}/definitions/import",
    response_model=list[ProposalOut],
    status_code=status.HTTP_201_CREATED,
    summary="Read a customer's metric table and propose what it says",
)
async def import_definitions(
    body: ImportIn,
    context: Annotated[RequestContext, Depends(require_admin)],
    data_source_id: DataSourceId,
) -> list[ProposalOut]:
    """Nothing imported here binds anything."""
    try:
        created = await proposals_service.propose_from_table(
            org_id=context.org_id,
            data_source_id=data_source_id,
            table=body.table,
            schema=body.schema_name,
            mapping=ColumnMapping(
                name=body.name_column,
                description=body.description_column,
                expression=body.expression_column,
                synonyms=body.synonyms_column,
                caveat=body.caveat_column,
            ),
            actor_user_id=context.user_id,
        )
    except ValueError as error:
        # `_identifier` refusing a name that is not a bare identifier.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    except PolicyViolation as violation:
        # The DAL declined the read — most often a table this catalog does not know.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(violation)) from violation
    except (NotFoundError, NoCatalogError) as error:
        raise _no_such_source(error) from error
    except ConnectorError as error:
        # Already sanitized by the connector: names what failed, never an address or a credential.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
    return [ProposalOut.of(proposal) for proposal in created]


@router.post(
    "/orgs/{org_id}/data-sources/{data_source_id}/definitions/{definition_id}/accept",
    response_model=DefinitionOut,
    summary="Bless a proposal, and say what it requires",
)
async def accept_proposal(
    body: AcceptIn,
    context: Annotated[RequestContext, Depends(require_admin)],
    data_source_id: DataSourceId,
    definition_id: DefinitionId,
) -> DefinitionOut:
    """This is where prose becomes a constraint (D-033)."""
    try:
        definition = await proposals_service.accept(
            org_id=context.org_id,
            definition_id=definition_id,
            required_filters=_filters(body.required_filters),
            synonyms=body.synonyms,
            actor_user_id=context.user_id,
        )
    except DefinitionError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such proposal") from error
    except (NotFoundError, NoCatalogError) as error:
        raise _no_such_source(error) from error
    return DefinitionOut.of(definition)


@router.patch(
    "/orgs/{org_id}/data-sources/{data_source_id}/definitions/{definition_id}",
    response_model=DefinitionOut,
    summary="Correct an active definition",
)
async def update_definition(
    body: UpdateDefinitionIn,
    context: Annotated[RequestContext, Depends(require_admin)],
    data_source_id: DataSourceId,
    definition_id: DefinitionId,
) -> DefinitionOut:
    """B-088. The route that makes an Admin's decision revisable."""
    sent = body.model_fields_set
    try:
        definition = await definitions_service.update(
            org_id=context.org_id,
            definition_id=definition_id,
            description=body.description,
            # The sentinel, so "clear the formula" and "do not touch it" are two requests rather...
            expression=body.expression if "expression" in sent else KEEP,
            caveat=body.caveat if "caveat" in sent else KEEP,
            synonyms=body.synonyms,
            required_filters=(
                None if body.required_filters is None else _filters(body.required_filters)
            ),
            actor_user_id=context.user_id,
        )
    except DefinitionError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such definition") from error
    except (NotFoundError, NoCatalogError) as error:
        raise _no_such_source(error) from error
    return DefinitionOut.of(definition)


@router.delete(
    "/orgs/{org_id}/data-sources/{data_source_id}/definitions/{definition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Take a definition out of force",
)
async def retire_definition(
    context: Annotated[RequestContext, Depends(require_admin)],
    data_source_id: DataSourceId,
    definition_id: DefinitionId,
) -> None:
    """Retired rather than deleted, like everything else in this layer."""
    try:
        await definitions_service.retire(
            org_id=context.org_id, definition_id=definition_id, actor_user_id=context.user_id
        )
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such definition") from error


@router.post(
    "/orgs/{org_id}/data-sources/{data_source_id}/definitions/{definition_id}/reinstate",
    response_model=DefinitionOut,
    summary="Bring a retired definition back into force",
)
async def reinstate_definition(
    context: Annotated[RequestContext, Depends(require_admin)],
    data_source_id: DataSourceId,
    definition_id: DefinitionId,
    body: ReinstateIn | None = None,
) -> DefinitionOut:
    """B-094."""
    try:
        definition = await definitions_service.reinstate(
            org_id=context.org_id,
            definition_id=definition_id,
            required_filters=(
                None
                if body is None or body.required_filters is None
                else _filters(body.required_filters)
            ),
            actor_user_id=context.user_id,
        )
    except DefinitionError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such retired definition") from error
    except (NotFoundError, NoCatalogError) as error:
        raise _no_such_source(error) from error
    return DefinitionOut.of(definition)


@router.get(
    "/orgs/{org_id}/data-sources/{data_source_id}/definitions/{definition_id}/versions",
    response_model=list[VersionOut],
    summary="Everything this definition has said",
)
async def list_definition_versions(
    context: Annotated[RequestContext, Depends(require_admin)],
    data_source_id: DataSourceId,
    definition_id: DefinitionId,
) -> list[VersionOut]:
    """Oldest first, because it reads as a life rather than as a feed."""
    found = await definitions_service.versions_for(context.org_id, definition_id)
    return [VersionOut.of(version) for version in found]


@router.post(
    "/orgs/{org_id}/data-sources/{data_source_id}/definitions/{definition_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Turn a proposal down",
)
async def reject_proposal(
    context: Annotated[RequestContext, Depends(require_admin)],
    data_source_id: DataSourceId,
    definition_id: DefinitionId,
) -> None:
    """Retired rather than deleted, so "we looked at this and said no" is answerable."""
    try:
        await proposals_service.reject(
            org_id=context.org_id, definition_id=definition_id, actor_user_id=context.user_id
        )
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such proposal") from error
