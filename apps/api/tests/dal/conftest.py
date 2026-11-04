"""Fixtures for the DAL suite. The catalog they are built from is in ``catalog_fixture``."""

from __future__ import annotations

import pytest
from catalog_fixture import build_source

from charie.dal.policy import SourcePolicy


@pytest.fixture
def pg() -> SourcePolicy:
    return build_source("pg")


@pytest.fixture
def mssql() -> SourcePolicy:
    return build_source("mssql")


@pytest.fixture(params=["pg", "mssql"], ids=["postgres", "sqlserver"])
def either(request: pytest.FixtureRequest) -> SourcePolicy:
    """Both dialects, for every rule that is not about one of them."""
    engine: str = request.param
    return build_source(engine)
