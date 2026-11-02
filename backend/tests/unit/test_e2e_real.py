"""The e2e runner guards: the save reads the application database itself.

Covers the PR #52 findings without any database, password, recording or
paid call: the maintenance (/postgres) connection is only for CREATE and
DROP DATABASE, and it keeps the configured SQLAlchemy driver.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import e2e_real


def test_server_url_keeps_the_configured_driver() -> None:
    """The bare server URL keeps +psycopg: plain postgresql wants psycopg2."""
    assert (
        e2e_real.server_url("postgresql+psycopg://charie:pw@localhost:5433/charie")
        == "postgresql+psycopg://charie:pw@localhost:5433/postgres"
    )


def test_server_url_only_ever_points_at_postgres() -> None:
    """Even a custom database name becomes the postgres maintenance one."""
    assert (
        e2e_real.server_url("postgresql+psycopg://u:pw@db:5432/other")
        == "postgresql+psycopg://u:pw@db:5432/postgres"
    )


def test_check_save_ready_accepts_one_published_version() -> None:
    """Exactly one published version and no draft: no refusal."""
    e2e_real.check_save_ready(published=["v7"], drafts=[])


def test_check_save_ready_refuses_anything_else() -> None:
    """Zero or two published versions, or a waiting draft, refuse the save."""
    import pytest

    for published, drafts in [([], []), (["a", "b"], []), (["v7"], ["draft"])]:
        with pytest.raises(SystemExit):
            e2e_real.check_save_ready(published=published, drafts=drafts)


class _Rows:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self) -> list:
        return self._rows


class _Session:
    """A Session stub serving the two readiness queries in order."""

    calls = 0

    def __init__(self, published: list, drafts: list) -> None:
        self._published = published
        self._drafts = drafts

    def __enter__(self) -> "_Session":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def scalars(self, _query: object) -> _Rows:
        _Session.calls += 1
        return _Rows(self._published if _Session.calls == 1 else self._drafts)


def test_save_reads_versions_from_the_application_database(monkeypatch, tmp_path) -> None:
    """cmd_save opens DATABASE_URL itself, never the /postgres connection."""
    from charie.shared.config import get_settings

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:pw@localhost:5433/charie")
    get_settings.cache_clear()
    seen: dict = {}

    def fake_create_engine(url: str, **kwargs: object) -> object:
        seen["url"] = url

        class Engine:
            def dispose(self) -> None:
                return None

        return Engine()

    monkeypatch.setattr("sqlalchemy.create_engine", fake_create_engine)
    monkeypatch.setattr("sqlalchemy.orm.Session", lambda engine: _Session(["v7"], []))

    class Completed:
        returncode = 0
        stdout = b"dump-bytes"
        stderr = b""

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: Completed())
    monkeypatch.setattr(e2e_real, "DUMP_PATH", tmp_path / "e2e-db.dump")
    _Session.calls = 0

    try:
        e2e_real.cmd_save()

        assert seen["url"] == "postgresql+psycopg://u:pw@localhost:5433/charie"
        assert (tmp_path / "e2e-db.dump").read_bytes() == b"dump-bytes"
    finally:
        get_settings.cache_clear()
