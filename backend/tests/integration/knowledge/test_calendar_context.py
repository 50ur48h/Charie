"""Calendar context: Sunday weeks, confirmation, version pinning (P09.4b)."""

import pytest

from charie.shared.knowledge import store, versions
from charie.shared.knowledge.calendar import (
    CALENDAR_KEY,
    KbView,
    calendar_topics,
    confirm_calendar,
    ensure_calendar,
)
from charie.shared.knowledge.query_builder import (
    DateRange,
    QueryRequest,
    build_query,
    load_build_context,
)
from charie.shared.knowledge.recipe import DimensionDetails, Recipe, RecipeDimension
from charie.shared.settings import get_setting, set_setting


@pytest.fixture()
def version_id(db_session):
    return versions.get_or_create_draft(db_session, "first_learning").id


def _seed_calendar(db_session, version_id: int, details: dict) -> None:
    store.upsert_entry(
        db_session,
        version_id,
        CALENDAR_KEY,
        "calendar",
        "Business calendar",
        "The zone, week start and fiscal year the business uses.",
        details,
        "guessed",
        [{"type": "ai", "text": "seed"}],
        "seed",
    )
    db_session.commit()


def test_sunday_week(db_session, version_id) -> None:
    _seed_calendar(
        db_session,
        version_id,
        {"time_zone": "America/Chicago", "week_start": "sunday", "fiscal_year_start": 1},
    )
    context = load_build_context(db_session, version_id, "America/Chicago")
    assert context.week_starts == "sunday"
    assert context.time_zone == "America/Chicago"
    recipe = Recipe(
        kind="simple",
        title="Orders",
        table="shop.orders",
        aggregate="count",
        expression="orders.id",
        time_column="orders.created_at",
        time_column_type="timestamptz",
        unit="count",
        steps_in_words=["Count the rows.", "Keep every row."],
        dimensions=[
            RecipeDimension(
                key="dimension.week",
                kind="time",
                grain="week",
                title="Week",
                table="shop.orders",
                expression="orders.created_at",
            )
        ],
    )
    context.dimension_details["dimension.week"] = DimensionDetails(
        kind="time", table="shop.orders", column="orders.created_at", grain="week"
    )
    built = build_query(
        "orders",
        {"orders": recipe},
        QueryRequest(
            period=DateRange(start="2025-03-09", end="2025-03-15"),
            dimensions=["dimension.week"],
        ),
        context,
    )
    assert "INTERVAL '1 day'" in built.sql
    assert "AT TIME ZONE 'America/Chicago'" in built.sql


def test_confirm_updates(db_session, version_id) -> None:
    _seed_calendar(
        db_session,
        version_id,
        {"time_zone": "UTC", "week_start": "monday", "fiscal_year_start": 1},
    )
    for key, kind, title, details in [
        (
            "table.shop.orders",
            "table",
            "orders",
            {"schema": "shop", "name": "orders", "primary_key": ["id"]},
        ),
        (
            "column.shop.orders.id",
            "column",
            "id",
            {"schema": "shop", "table": "orders", "name": "id", "data_type": "integer"},
        ),
        (
            "column.shop.orders.created_at",
            "column",
            "created_at",
            {
                "schema": "shop",
                "table": "orders",
                "name": "created_at",
                "data_type": "timestamp with time zone",
            },
        ),
    ]:
        store.upsert_entry(
            db_session,
            version_id,
            key,
            kind,
            title,
            title,
            details,
            "checked",
            [{"type": "structure", "text": "seed"}],
            "seed",
        )
    store.upsert_entry(
        db_session,
        version_id,
        "metric.orders",
        "metric",
        "Orders",
        "A count of orders.",
        {
            "kind": "simple",
            "title": "Orders",
            "table": "shop.orders",
            "aggregate": "count",
            "expression": "orders.id",
            "filters": [],
            "time_column": "orders.created_at",
            "time_column_type": "timestamptz",
            "unit": "count",
            "steps_in_words": ["Count the rows.", "Keep every row."],
            "dimensions": [],
            "tests": [
                {"name": "runs", "passed": True, "text": "old"},
                {"name": "believable", "passed": True, "text": "old"},
                {"name": "matches_documents", "passed": None, "text": "old"},
                {"name": "parts_add_up", "passed": True, "text": "old"},
            ],
            "reported_checks": [],
            "sql_preview": "old",
            "tested_at": "2000-01-01T00:00:00+00:00",
        },
        "checked",
        [{"type": "structure", "text": "seed"}],
        "seed",
    )
    store.upsert_entry(
        db_session,
        version_id,
        "data_range.shop.orders",
        "data_range",
        "orders range",
        "The months the shop data covers.",
        {
            "table": "shop.orders",
            "date_column": "created_at",
            "date_from": "2025-03-01",
            "date_to": "2025-03-31",
        },
        "checked",
        [{"type": "structure", "text": "seed"}],
        "seed",
    )
    db_session.commit()
    calls: list[str] = []

    def run(sql: str):
        calls.append(sql)
        return [(5,)]

    set_setting(db_session, "time_zone", "America/Chicago")
    outcome = confirm_calendar(
        db_session,
        version_id,
        {"time_zone": "America/Chicago", "week_start": "sunday", "fiscal_year_start": 1},
        run,
    )
    assert outcome == {"metric.orders": True}
    assert get_setting(db_session, "time_zone") == "America/Chicago"
    entry = store.get_entry(db_session, version_id, CALENDAR_KEY)
    assert entry is not None
    assert entry.confidence == "confirmed"
    assert entry.details["week_start"] == "sunday"
    assert any("COUNT(orders.id)" in sql for sql in calls)
    assert calendar_topics(db_session, version_id) == []
    assert KbView(db_session, version_id).calendar().week_start == "sunday"


def test_version_pinned(db_session, version_id) -> None:
    from charie.shared.tables.knowledge import KbVersion

    _seed_calendar(
        db_session,
        version_id,
        {"time_zone": "UTC", "week_start": "sunday", "fiscal_year_start": 1},
    )
    other = KbVersion(number=99, status="published", made_by="first_learning")
    db_session.add(other)
    db_session.commit()
    other = other.id
    assert load_build_context(db_session, version_id, "UTC").week_starts == "sunday"
    assert load_build_context(db_session, other, "UTC").week_starts == "monday"
    assert KbView(db_session, other).calendar().week_start == "monday"
    assert calendar_topics(db_session, other) == []
    with pytest.raises(ValueError, match="[Dd]raft"):
        ensure_calendar(db_session, other)
