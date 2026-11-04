"""Data-source routes (architecture Part 10.2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field, SecretStr

from charie.auth.context import RequestContext
from charie.auth.guards import require_admin, require_member
from charie.config import TlsMode
from charie.connectors.tls import TlsPolicyError
from charie.datasources import service
from charie.datasources.service import DataSourceView, NotFoundError
from charie.orgs.service import ConflictError

router = APIRouter(prefix="/v1", tags=["data sources"])

#: Mirrors ``models.DATA_SOURCE_ENGINES``; a test asserts the two agree.
Engine = Literal["pg", "mssql"]

TLS_MODE_FIELD = Field(
    default=None,
    description=(
        "How much encryption this connection needs. Omit and the deployment's "
        "policy decides: TLS is required for any address that is not on the "
        "server itself. An optional mode ('disable', 'prefer') for a remote "
        "address is refused."
    ),
)

DataSourceId = Annotated[uuid.UUID, Path(description="Data source within this organization")]


class CreateDataSourceIn(BaseModel):
    """Everything needed to register a database.

    ``password`` is a ``SecretStr``: pydantic renders it as ``**********`` in any
    repr, which is what a traceback, a validation error and a debug log all print.
    """

    name: str = Field(min_length=1, max_length=200)
    engine: Engine
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    database: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=128)
    password: SecretStr = Field(min_length=1, max_length=1024)
    tls_mode: TlsMode | None = TLS_MODE_FIELD


class UpdateDataSourceIn(BaseModel):
    """Every field optional: a rename, a re-address, a rotation, or a TLS change."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str | None = Field(default=None, min_length=1, max_length=128)
    username: str | None = Field(default=None, min_length=1, max_length=128)
    password: SecretStr | None = Field(default=None, min_length=1, max_length=1024)
    tls_mode: TlsMode | None = TLS_MODE_FIELD


class DataSourceOut(BaseModel):
    id: uuid.UUID
    name: str
    engine: str
    host: str
    port: int
    database: str
    host_display: str
    status: str
    secret_ref: str = Field(
        description=(
            "Where the credentials are kept, not the credentials. Useless without "
            "the secrets backend it names."
        )
    )
    username_last4: str = Field(
        description="The last four characters of the connecting username, and no more."
    )
    tls_mode: str = Field(
        description=(
            "The encryption this source connects with: disable | prefer | require | "
            "verify-ca | verify-full. 'require' encrypts without checking the "
            "server's certificate; only the verify modes do that."
        )
    )
    readonly_verified: bool = Field(
        description=(
            "True only when this service has proven the credentials cannot write. "
            "Unknown, unchecked and failed all read as false."
        )
    )
    last_verified_at: datetime | None
    created_by: uuid.UUID | None
    created_at: datetime


class TestResultOut(BaseModel):
    reachable: bool
    readonly_verified: bool
    status: str = Field(description="What the data source's row now says: verified | error.")
    detail: str = Field(description="Sanitized: connection strings and addresses are stripped.")
    checked_at: datetime
    server_version: str | None = None
    tls_mode: str | None = Field(
        default=None, description="The encryption this check was made with."
    )
    tls_encrypted: bool | None = Field(
        default=None,
        description=(
            "Whether the server says this connection was actually encrypted. Null "
            "when the check never got far enough to ask."
        ),
    )
    tls_detail: str | None = Field(
        default=None, description="Protocol and cipher, and what was not verified."
    )
    evidence: list[str] = Field(
        default_factory=list,
        description=("What each check found — privileges and role membership, never a credential."),
    )


def _out(view: DataSourceView) -> DataSourceOut:
    return DataSourceOut(
        id=view.id,
        name=view.name,
        engine=view.engine,
        host=view.host,
        port=view.port,
        database=view.database,
        host_display=view.host_display,
        status=view.status,
        secret_ref=view.secret_ref,
        username_last4=view.username_last4,
        tls_mode=view.tls_mode,
        readonly_verified=view.readonly_verified,
        last_verified_at=view.last_verified_at,
        created_by=view.created_by,
        created_at=view.created_at,
    )


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="No such data source in this organization"
    )


def _refused(error: TlsPolicyError) -> HTTPException:
    """A TLS mode this address may not use is the caller's mistake to fix."""
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.get(
    "/orgs/{org_id}/data-sources",
    response_model=list[DataSourceOut],
    summary="List this organization's data sources",
)
async def list_data_sources(
    context: Annotated[RequestContext, Depends(require_member)],
) -> list[DataSourceOut]:
    return [_out(view) for view in await service.list_data_sources(context.org_id)]


@router.post(
    "/orgs/{org_id}/data-sources",
    response_model=DataSourceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a database; credentials go to the secrets store",
)
async def create_data_source(
    body: CreateDataSourceIn, context: Annotated[RequestContext, Depends(require_admin)]
) -> DataSourceOut:
    try:
        view = await service.create_data_source(
            org_id=context.org_id,
            actor_user_id=context.user_id,
            name=body.name,
            engine=body.engine,
            host=body.host,
            port=body.port,
            database=body.database,
            username=body.username,
            password=body.password.get_secret_value(),
            tls_mode=body.tls_mode,
        )
    except ConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except TlsPolicyError as error:
        raise _refused(error) from error
    return _out(view)


@router.get(
    "/orgs/{org_id}/data-sources/{data_source_id}",
    response_model=DataSourceOut,
    summary="One data source",
)
async def get_data_source(
    context: Annotated[RequestContext, Depends(require_member)], data_source_id: DataSourceId
) -> DataSourceOut:
    try:
        return _out(await service.get_data_source(context.org_id, data_source_id))
    except NotFoundError as error:
        raise _not_found() from error


@router.patch(
    "/orgs/{org_id}/data-sources/{data_source_id}",
    response_model=DataSourceOut,
    summary="Rename, re-address, or rotate credentials",
)
async def update_data_source(
    body: UpdateDataSourceIn,
    context: Annotated[RequestContext, Depends(require_admin)],
    data_source_id: DataSourceId,
) -> DataSourceOut:
    try:
        view = await service.update_data_source(
            org_id=context.org_id,
            actor_user_id=context.user_id,
            data_source_id=data_source_id,
            name=body.name,
            host=body.host,
            port=body.port,
            database=body.database,
            username=body.username,
            password=body.password.get_secret_value() if body.password is not None else None,
            tls_mode=body.tls_mode,
        )
    except NotFoundError as error:
        raise _not_found() from error
    except TlsPolicyError as error:
        raise _refused(error) from error
    return _out(view)


@router.delete(
    "/orgs/{org_id}/data-sources/{data_source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a data source and its stored credentials",
)
async def delete_data_source(
    context: Annotated[RequestContext, Depends(require_admin)], data_source_id: DataSourceId
) -> None:
    try:
        await service.delete_data_source(
            org_id=context.org_id,
            actor_user_id=context.user_id,
            data_source_id=data_source_id,
        )
    except NotFoundError as error:
        raise _not_found() from error


@router.post(
    "/orgs/{org_id}/data-sources/{data_source_id}/test",
    response_model=TestResultOut,
    summary="Verify the address, the credentials, and that they cannot write",
)
async def test_data_source(
    context: Annotated[RequestContext, Depends(require_admin)], data_source_id: DataSourceId
) -> TestResultOut:
    """Answers 200 for an unusable data source too."""
    try:
        health = await service.test_data_source(
            org_id=context.org_id,
            actor_user_id=context.user_id,
            data_source_id=data_source_id,
        )
    except NotFoundError as error:
        raise _not_found() from error
    return TestResultOut(
        reachable=health.reachable,
        readonly_verified=health.readonly_verified,
        status=service.STATUS_VERIFIED if health.readonly_verified else service.STATUS_ERROR,
        detail=health.detail,
        checked_at=health.checked_at,
        server_version=health.server_version,
        tls_mode=health.tls.mode if health.tls is not None else None,
        tls_encrypted=health.tls.encrypted if health.tls is not None else None,
        tls_detail=health.tls.detail if health.tls is not None else None,
        evidence=list(health.evidence),
    )
