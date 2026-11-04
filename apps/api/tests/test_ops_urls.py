"""The URLs start.sh derives from a hosting provider's DATABASE_URL."""

from __future__ import annotations

from charie.ops.urls import app_url, exports, with_driver


def test_a_providers_url_gets_the_driver_and_asyncpgs_ssl_spelling() -> None:
    assert (
        with_driver("postgresql://u:p@db.example:5432/app?sslmode=require")
        == "postgresql+asyncpg://u:p@db.example:5432/app?ssl=require"
    )
    assert with_driver("postgres://u:p@h/d") == "postgresql+asyncpg://u:p@h/d"


def test_the_app_url_is_the_owner_url_as_charie_app() -> None:
    url = app_url("postgresql://owner:secret@db.internal:6543/app?sslmode=require", "p@ss/word")

    assert url == "postgresql+asyncpg://charie_app:p%40ss%2Fword@db.internal:6543/app?ssl=require"


def test_an_explicit_app_url_wins_and_no_database_means_no_exports() -> None:
    lines = exports(
        {
            "DATABASE_URL": "postgresql://o:p@h/d",
            "APP_DATABASE_URL": "postgresql://charie_app:x@h/d",
            "APP_DB_PASSWORD": "ignored",
        }
    )

    assert lines == [
        "export DATABASE_URL=postgresql+asyncpg://o:p@h/d",
        "export APP_DATABASE_URL=postgresql+asyncpg://charie_app:x@h/d",
    ]
    assert exports({}) == []
