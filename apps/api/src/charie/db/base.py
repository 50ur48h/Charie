"""Declarative base and shared column conventions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from sqlalchemy import DateTime, MetaData, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, mapped_column

# Predictable constraint names. Without them Alembic invents names that differ between environments.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

#: The three fixed roles (architecture Part 6.2).
ROLES: tuple[str, ...] = ("admin", "contributor", "reader")

# Server-side defaults, so a row written by a migration or by psql is exactly as valid as one...
UuidPk = Annotated[
    uuid.UUID,
    mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
]
OrgId = Annotated[uuid.UUID, mapped_column(UUID(as_uuid=True), nullable=False)]
UuidRef = Annotated[uuid.UUID, mapped_column(UUID(as_uuid=True))]
CreatedAt = Annotated[
    datetime,
    mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False),
]


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map = {  # noqa: RUF012
        dict[str, object]: JSONB,
        datetime: DateTime(timezone=True),
        uuid.UUID: UUID(as_uuid=True),
    }
