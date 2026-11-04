"""Shared test fixtures."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import URL, make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

import customer_db
from charie.config import Settings
from charie.datasources import service as datasource_service
from charie.knowledge import embeddings
from charie.llm import registry as llm_registry
from charie.llm.fake import FakeLLM
from charie.main import create_app
from charie.secrets.local import LocalSecretsProvider
from customer_db import CustomerDatabase

API_DIR = Path(__file__).resolve().parents[1]

#: The unprivileged role the API connects as, created by migration 0002.
APP_ROLE = "charie_app"

#: Connecting to a database in order to create another one has to happen through some existing...
MAINTENANCE_DATABASE = "postgres"


# --- No test may call a real model (B-040) ---
# This is not hypothetical. A WP7.2c test called a live provider and billed for two completions.

#: Provider or embedder names a test used that were not stubs. Cleared per test.
_live_provider_uses: list[str] = []

#: Non-empty while the current test carries ``@pytest.mark.live_provider``.
_live_allowed: list[bool] = []

#: How the refusal tells whoever hit it what to do instead.
_ADVICE = (
    "Tests must not reach a real provider: pass `settings=build_settings()` so "
    "configuration comes from the fixture rather than from .env, or mark the "
    "test `@pytest.mark.live_provider` if it genuinely must spend money."
)


@pytest.fixture(scope="session", autouse=True)
def forbid_live_providers() -> Iterator[None]:
    """Wrap both spending doors for the whole session, so no test escapes by ordering."""
    real_provider = llm_registry.get_provider
    real_embedder = embeddings.get_embedder

    def guarded(name: str, settings: Settings | None = None) -> object:
        provider = real_provider(name, settings)
        if provider.capabilities().is_stub or _live_allowed:
            return provider
        _live_provider_uses.append(name)
        raise RuntimeError(f"a test asked for the live provider {name!r}. {_ADVICE}")

    def guarded_embedder(settings: Settings | None = None) -> object:
        embedder = real_embedder(settings)
        # None is the ordinary answer for a deployment with no embedding model.
        if embedder is None or embedder.is_stub or _live_allowed:
            return embedder
        _live_provider_uses.append("embeddings")
        raise RuntimeError(f"a test asked for a live embedder. {_ADVICE}")

    llm_registry.get_provider = guarded  # pyright: ignore[reportAttributeAccessIssue]
    embeddings.get_embedder = guarded_embedder  # pyright: ignore[reportAttributeAccessIssue]
    try:
        yield
    finally:
        llm_registry.get_provider = real_provider  # pyright: ignore[reportAttributeAccessIssue]
        embeddings.get_embedder = real_embedder  # pyright: ignore[reportAttributeAccessIssue]


@pytest.fixture
def expected_live_provider_refusal() -> Iterator[None]:
    """For the guard's own tests: this one meant to trip it."""
    yield
    _live_provider_uses.clear()


@pytest.fixture(autouse=True)
def no_live_provider_used(request: pytest.FixtureRequest) -> Iterator[None]:
    """Fail the test if it reached for a real model, however the error was handled."""
    allowed = request.node.get_closest_marker("live_provider") is not None  # pyright: ignore[reportUnknownMemberType]
    _live_provider_uses.clear()
    _live_allowed.clear()
    if allowed:
        _live_allowed.append(True)

    yield

    used, _live_provider_uses[:] = list(_live_provider_uses), []
    _live_allowed.clear()
    if used and not allowed:
        pytest.fail(
            f"this test reached for {sorted(set(used))}, which would spend real "
            f"money. See B-040. {_ADVICE}"
        )


@pytest.fixture
def settings() -> Settings:
    """Settings for tests, independent of the developer's environment."""
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        env="ci",
        build_env="dev",
        git_sha="testsha",
        log_level="WARNING",
        # A configuration that could actually serve.
        oidc_authority="https://tests.ciamlogin.com/tenant/v2.0",
        local_secrets_key=SecretStr(Fernet.generate_key().decode()),
        # The third thing that fixture was missing, for the same reason (B-126).
        llm_models={"meta": {"small": "test-s", "mid": "test-m", "strong": "test-l"}},
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings=settings)


@pytest.fixture
def secrets_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LocalSecretsProvider:
    """A real local backend, isolated per test, wired into the data-source service."""
    provider = LocalSecretsProvider(
        key=Fernet.generate_key().decode(), path=tmp_path / "secrets" / "secrets.json"
    )
    monkeypatch.setattr(datasource_service, "get_secrets_provider", lambda: provider)
    return provider


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# --- A real PostgreSQL server ---


def _configured_url() -> URL | None:
    """Resolve the DSN the way the application does."""
    raw = Settings().database_url
    return make_url(raw) if raw else None


async def _server_is_reachable(url: URL) -> bool:
    engine = create_async_engine(url.set(database=MAINTENANCE_DATABASE))
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        return False
    else:
        return True
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def database_url() -> URL:
    """The configured server, or a skip — unless CI demands otherwise."""
    url = _configured_url()
    required = os.environ.get("REQUIRE_DB") == "1"

    if url is None:
        message = "DATABASE_URL is not set"
        if required:
            pytest.fail(f"REQUIRE_DB=1 but {message}")
        pytest.skip(f"{message} — run `make up`, or set REQUIRE_DB=1 to make this a failure")

    if not asyncio.run(_server_is_reachable(url)):
        message = f"no PostgreSQL server reachable at {url.render_as_string(hide_password=True)}"
        if required:
            pytest.fail(f"REQUIRE_DB=1 but {message}")
        pytest.skip(f"{message} — run `make up`")

    return url


@contextmanager
def _temporary_database(database_url: URL) -> Generator[URL]:
    """An empty database on the configured server, dropped afterwards."""
    name = f"charie_test_{uuid.uuid4().hex[:12]}"
    admin_url = database_url.set(database=MAINTENANCE_DATABASE)

    async def _run(statement: str) -> None:
        engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as connection:
                await connection.execute(text(statement))
        finally:
            await engine.dispose()

    asyncio.run(_run(f'CREATE DATABASE "{name}"'))
    try:
        yield database_url.set(database=name)
    finally:
        # FORCE detaches any connection the test left behind.
        asyncio.run(_run(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture
def temp_database(database_url: URL) -> Iterator[URL]:
    """An empty database, dropped when the test finishes."""
    with _temporary_database(database_url) as url:
        yield url


@pytest.fixture
def alembic_config(temp_database: URL, monkeypatch: pytest.MonkeyPatch) -> Config:
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", temp_database.render_as_string(hide_password=False))
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "src" / "charie" / "db" / "alembic"))
    return config


@pytest.fixture(scope="session")
def app_role_password() -> str:
    """The password the application role should carry, taken from APP_DATABASE_URL."""
    raw = Settings().app_database_url
    if not raw:
        message = "APP_DATABASE_URL is not set"
        if os.environ.get("REQUIRE_DB") == "1":
            pytest.fail(f"REQUIRE_DB=1 but {message}")
        pytest.skip(f"{message} — run `make db.setup`")
    return make_url(raw).password or ""


@pytest.fixture
def customer_database(temp_database: URL) -> CustomerDatabase:
    """An empty database, populated to look like a customer's."""
    return asyncio.run(customer_db.build(temp_database))


@pytest.fixture
def isolated_customer_database(database_url: URL) -> Iterator[CustomerDatabase]:
    """A customer database in a database of its own."""
    with _temporary_database(database_url) as url:
        yield asyncio.run(customer_db.build(url))


@pytest.fixture
def undeclared_customer_database(database_url: URL) -> Iterator[CustomerDatabase]:
    """A customer database with no primary keys and no foreign keys."""
    with _temporary_database(database_url) as url:
        yield asyncio.run(customer_db.build_undeclared(url))


@pytest.fixture
def migrated_database(alembic_config: Config, temp_database: URL) -> URL:
    """A temp database at head: schema, RLS policies and the application role."""
    command.upgrade(alembic_config, "head")
    return temp_database


@pytest.fixture
def app_database(migrated_database: URL, app_role_password: str) -> URL:
    """A DSN for the same database, connecting as ``charie_app``."""

    # ALTER ROLE is DDL and cannot take a bind parameter, so the password has to be a literal.
    literal = "'{}'".format(app_role_password.replace("'", "''"))

    async def _grant_login() -> None:
        engine = create_async_engine(migrated_database, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as connection:
                await connection.execute(
                    text(f"ALTER ROLE {APP_ROLE} WITH LOGIN PASSWORD {literal}")
                )
        finally:
            await engine.dispose()

    asyncio.run(_grant_login())
    return migrated_database.set(username=APP_ROLE, password=app_role_password)


@pytest.fixture
def fake_llm() -> Iterator[FakeLLM]:
    """A FakeLLM registered as the provider named ``fake``, and unregistered after."""
    fake = FakeLLM()
    llm_registry.register_provider("fake", lambda: fake)
    try:
        yield fake
    finally:
        llm_registry.clear_provider_cache()
