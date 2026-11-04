"""The per-org context loader and its cache (``dal/policy.py``)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from catalog_fixture import build_catalog

from charie.catalog.browse import Catalog
from charie.dal import policy as policy_module
from charie.dal.policy import (
    POLICY_TTL_SECONDS,
    invalidate_all,
    invalidate_source,
    source_policy,
)


class _Source:
    """Just enough of a DataSourceView for the loader."""

    def __init__(self, engine: str = "pg") -> None:
        self.engine = engine


@pytest.fixture(autouse=True)
def reset_cache() -> None:
    invalidate_all()


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Count the reads the loader makes, so "cached" means "did not go back"."""
    calls = {"source": 0, "catalog": 0}

    async def fake_source(org_id: uuid.UUID, data_source_id: uuid.UUID) -> Any:
        calls["source"] += 1
        return _Source()

    async def fake_catalog(org_id: uuid.UUID, data_source_id: uuid.UUID) -> Catalog:
        calls["catalog"] += 1
        return build_catalog()

    monkeypatch.setattr(policy_module, "get_data_source", fake_source)
    monkeypatch.setattr(policy_module, "active_catalog", fake_catalog)
    return calls


async def test_it_loads_the_catalog_and_the_engines_capabilities(counted: dict[str, int]) -> None:
    loaded = await source_policy(uuid.uuid4(), uuid.uuid4())

    assert loaded.dialect == "postgres"
    assert loaded.caps.limit_syntax == "limit"
    assert {table.table_name for table in loaded.catalog.tables} >= {"orders", "customers"}


async def test_a_second_query_reuses_the_context(counted: dict[str, int]) -> None:
    org, source = uuid.uuid4(), uuid.uuid4()

    await source_policy(org, source)
    await source_policy(org, source)

    assert counted == {"source": 1, "catalog": 1}


async def test_two_organizations_never_share_an_entry(counted: dict[str, int]) -> None:
    """The cache key carries the org (arch Part 6.4)."""
    source = uuid.uuid4()

    await source_policy(uuid.uuid4(), source)
    await source_policy(uuid.uuid4(), source)

    assert counted["catalog"] == 2


async def test_the_entry_expires(counted: dict[str, int], monkeypatch: pytest.MonkeyPatch) -> None:
    """The TTL is the backstop for anything that changes without telling us."""
    org, source = uuid.uuid4(), uuid.uuid4()
    clock = [1000.0]
    monkeypatch.setattr(policy_module.time, "monotonic", lambda: clock[0])

    await source_policy(org, source)
    clock[0] += POLICY_TTL_SECONDS - 1.0
    await source_policy(org, source)
    assert counted["catalog"] == 1, "still inside the window"

    clock[0] += 2.0
    await source_policy(org, source)

    assert counted["catalog"] == 2


async def test_invalidating_one_source_leaves_the_others(counted: dict[str, int]) -> None:
    """What an Admin has just decided must apply to the next query, not to the one after the TTL."""
    org, first, second = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await source_policy(org, first)
    await source_policy(org, second)

    invalidate_source(org, first)
    await source_policy(org, first)
    await source_policy(org, second)

    assert counted["catalog"] == 3


async def test_nothing_cached_holds_a_credential(counted: dict[str, int]) -> None:
    """A dataclass in memory is a thing that ends up in a heap dump or a repr."""
    loaded = await source_policy(uuid.uuid4(), uuid.uuid4())

    rendered = repr(loaded)
    assert "password" not in rendered.lower()
    assert not hasattr(loaded, "secret_ref")


async def test_the_context_is_frozen(counted: dict[str, int]) -> None:
    """Callers share one cached object."""
    loaded = await source_policy(uuid.uuid4(), uuid.uuid4())

    with pytest.raises((AttributeError, TypeError)):
        loaded.engine = "mssql"  # pyright: ignore[reportAttributeAccessIssue]


def test_the_snapshot_is_the_one_the_catalog_module_returned() -> None:
    """The DAL does not build a catalog, it reads one."""
    built = build_catalog()

    assert built.snapshot.status == "active"
    assert built.snapshot.captured_at <= datetime.now(UTC)
