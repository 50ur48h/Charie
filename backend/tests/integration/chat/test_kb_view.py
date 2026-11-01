"""The per-question knowledge view: grouping, dates, calendar (P10.3)."""

from datetime import UTC, date, datetime

from charie.chat.analyst.dates import DateContext
from charie.chat.analyst.kb_view import KbView, load_date_context
from charie.shared.settings import set_setting
from charie.shared.tables.knowledge import KbEntry, KbVersion
from charie.shared.tables.sources import DataSource


def _version(db_session) -> KbVersion:
    version = KbVersion(number=1, status="published", made_by="first_learning")
    db_session.add(version)
    db_session.commit()
    return version


def _entry(db_session, version_id, key, kind, details, confidence="checked") -> None:
    db_session.add(
        KbEntry(
            version_id=version_id,
            key=key,
            kind=kind,
            title=key,
            meaning=f"{key} meaning",
            details=details,
            confidence=confidence,
            sources=[],
        )
    )
    db_session.commit()


def _source(db_session, through) -> None:
    db_session.add(
        DataSource(
            kind="postgres",
            name="shop",
            host="localhost",
            port=5432,
            database="shop",
            username="owner",
            password_encrypted="x",
            status="connected",
            data_through=through,
        )
    )
    db_session.commit()


def _recipe(details=None) -> dict:
    return {
        "kind": "sum",
        "table": "shop.orders",
        "column": "total",
        "filters": [],
        "checks": [],
        **(details or {}),
    }


def test_kb_view_groups_entries_by_kind(db_session) -> None:
    """Metrics, dimensions, defaults, rules, names and styles group by kind."""
    version = _version(db_session)
    _entry(db_session, version.id, "net_sales", "metric", _recipe())
    _entry(db_session, version.id, "week", "dimension", {"column": "placed_at"})
    _entry(db_session, version.id, "sales", "default", {"word": "sales", "value": "net_sales"})
    _entry(db_session, version.id, "no_test", "rule", {"rule_type": "exclude_values"})
    _entry(db_session, version.id, "shop_name", "name", {"table": "shops"})
    _entry(db_session, version.id, "tone", "style", {"topics": ["totals"]})
    kb = KbView.load(db_session, version.id)
    assert set(kb.metrics()) == {"net_sales"}
    assert set(kb.dimensions()) == {"week"}
    assert set(kb.rules()) == {"no_test"}
    assert set(kb.names()) == {"shop_name"}
    assert set(kb.styles()) == {"tone"}
    assert kb.defaults()["sales"].value == "net_sales"


def test_default_last_week_reads_back_as_expression(db_session) -> None:
    """`default.last_week` values parse as period expressions."""
    from charie.chat.analyst.dates import PeriodExpression

    version = _version(db_session)
    _entry(
        db_session,
        version.id,
        "last_week",
        "default",
        {"word": "last week", "value": "last_7_days"},
    )
    kb = KbView.load(db_session, version.id)
    parsed = PeriodExpression.from_short_text(kb.defaults()["last week"].value)
    assert parsed.short_text() == "last_7_days"
    assert PeriodExpression.from_short_text("last_full_week").short_text() == "last_full_week"


def test_keeps_every_metric_entry_for_later_enforcement(db_session) -> None:
    """KbView exposes all metric recipes; usable-set filtering happens later."""
    version = _version(db_session)
    _entry(db_session, version.id, "good_metric", "metric", _recipe(), confidence="checked")
    _entry(db_session, version.id, "weak_metric", "metric", _recipe(), confidence="guessed")
    kb = KbView.load(db_session, version.id)
    assert set(kb.metrics()) == {"good_metric", "weak_metric"}


def test_data_through_from_latest_source(db_session) -> None:
    """The newest source's data end is the data end, as a date."""
    version = _version(db_session)
    _source(db_session, datetime(2025, 11, 30, tzinfo=UTC))
    _source(db_session, datetime(2025, 12, 31, tzinfo=UTC))
    kb = KbView.load(db_session, version.id)
    assert kb.data_through == date(2025, 12, 31)


def test_data_through_none_without_source(db_session) -> None:
    """No connected source means no data end."""
    version = _version(db_session)
    kb = KbView.load(db_session, version.id)
    assert kb.data_through is None
    assert kb.data_from() is None


def test_data_from_uses_activity_tables(db_session) -> None:
    """The earliest start among ranges ending at the data end wins."""
    version = _version(db_session)
    _source(db_session, datetime(2025, 12, 31, tzinfo=UTC))
    _entry(
        db_session,
        version.id,
        "orders_range",
        "data_range",
        {"table": "orders", "date_from": "2024-01-01", "date_to": "2025-12-31"},
    )
    _entry(
        db_session,
        version.id,
        "items_range",
        "data_range",
        {"table": "items", "date_from": "2023-06-01", "date_to": "2025-12-31"},
    )
    _entry(
        db_session,
        version.id,
        "snapshot_range",
        "data_range",
        {"table": "stock", "date_from": "2020-01-01", "date_to": "2025-06-30"},
    )
    kb = KbView.load(db_session, version.id)
    assert kb.data_from() == date(2023, 6, 1)


def test_calendar_defaults_when_missing(db_session) -> None:
    """No calendar entry means Monday weeks and a January fiscal start."""
    version = _version(db_session)
    kb = KbView.load(db_session, version.id)
    assert kb.calendar().week_start == "monday"
    assert kb.calendar().fiscal_year_start == 1


def test_load_date_context_uses_time_zone_and_data_through(db_session) -> None:
    """The resolver inputs follow the calendar entry and time zone setting."""
    version = _version(db_session)
    _source(db_session, datetime(2025, 12, 31, tzinfo=UTC))
    _entry(
        db_session,
        version.id,
        "calendar",
        "calendar",
        {"week_start": "sunday", "fiscal_year_start": 4, "time_zone": "UTC"},
    )
    set_setting(db_session, "time_zone", "America/Chicago")
    kb = KbView.load(db_session, version.id)
    ctx = load_date_context(db_session, None, kb)
    assert isinstance(ctx, DateContext)
    assert ctx.week_start == "sunday"
    assert ctx.fiscal_start_month == 4
    assert ctx.time_zone == "America/Chicago"
    assert ctx.data_through == date(2025, 12, 31)
    assert ctx.data_from is None
