"""The data helper on the shop database (P10.6).

Hand-worked from backend/tests/data/shop_db.sql (America/Chicago):
November completed orders are 40 + 60 + 25 + 10 + 33 = 168 (6 rows
with the cancelled one, 5 completed); December completed orders are
50 + 22 + 35 + 44 + 28 + 12 = 191 (6 rows, all completed).
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from charie.chat.analyst.dates import PeriodExpression, resolve_periods
from charie.chat.analyst.helpers import data as data_module
from charie.chat.analyst.helpers.data import add_period_items, run_recipe_task
from charie.chat.analyst.helpers.tasks import Task
from charie.chat.analyst.kb_view import KbView, load_date_context
from charie.chat.analyst.notebook import Notebook
from charie.chat.analyst.understand import Filter, Understanding
from charie.chat.chat_store import build_context
from charie.shared.connectors.base import ConnectorError
from charie.shared.connectors.postgres import PostgresConnector
from charie.shared.knowledge.recipe import RecipeDimension
from charie.shared.settings import set_setting
from charie.shared.tables.chat import Chat, Message, QueryRun, ThinkingEvent
from charie.shared.tables.knowledge import KbEntry, KbVersion
from charie.shared.tables.sources import DataSource
from tests.shop import COMPLETED_COUNT, NET_SALES_WITH_LABEL, ORDER_COUNT

DASH = "–"


def _seeded_version(db_session) -> int:
    """Shop recipes with passing checks, one excluded metric, names, links."""
    version = KbVersion(number=1, status="published", made_by="first_learning")
    db_session.add(version)
    db_session.flush()

    def _entry(key, kind, details, title=""):
        db_session.add(
            KbEntry(
                version_id=version.id,
                key=key,
                kind=kind,
                title=title or key,
                meaning=f"{key} meaning",
                details=details,
                confidence="checked",
                sources=[],
            )
        )

    passing = [{"name": "runs", "passed": True}]
    _entry(
        "orders",
        "metric",
        {**ORDER_COUNT.model_dump(), "tests": passing},
        title="Orders",
    )
    _entry(
        "completed_orders",
        "metric",
        {
            **COMPLETED_COUNT.model_copy(
                update={
                    "filters": ["orders.status = 'completed'"],
                    "steps_in_words": ["Count completed orders.", "One row counts once."],
                }
            ).model_dump(),
            "tests": passing,
        },
        title="Completed orders",
    )
    _entry(
        "order_value",
        "metric",
        {
            **NET_SALES_WITH_LABEL.model_copy(
                update={
                    "filters": ["orders.status = 'completed'"],
                    "dimensions": [
                        *NET_SALES_WITH_LABEL.dimensions,
                        RecipeDimension(
                            key="dimension.restaurant_id",
                            title="Restaurant",
                            kind="attribute",
                            table="shop.orders",
                            expression="orders.restaurant_id",
                        ),
                    ],
                }
            ).model_dump(),
            "tests": passing,
        },
        title="Order value",
    )
    _entry(
        "excluded_gross",
        "metric",
        {**NET_SALES_WITH_LABEL.model_dump(), "tests": [{"name": "believable", "passed": False}]},
        title="Excluded gross",
    )
    _entry(
        "bad_share",
        "metric",
        {
            "kind": "ratio",
            "title": "Bad share",
            "numerator": "orders",
            "denominator": "excluded_gross",
            "dimensions": [],
            "unit": "percent",
            "steps_in_words": ["Divide by an excluded number.", "Both sides run separately."],
            "tests": passing,
        },
        title="Bad share",
    )
    _entry(
        "completion_share",
        "metric",
        {
            "kind": "ratio",
            "title": "Completion share",
            "numerator": "completed_orders",
            "denominator": "orders",
            "dimensions": [],
            "unit": "percent",
            "steps_in_words": ["Count completed orders.", "Divide by all orders."],
            "tests": passing,
        },
        title="Completion share",
    )
    for key in ("dimension.status", "dimension.month", "dimension.restaurant_name"):
        _entry(key, "dimension", {"kind": "attribute"}, title=key)
    for table in ("shop.orders", "shop.restaurants", "shop.order_items"):
        schema, name = table.split(".")
        _entry(table, "table", {"schema": schema, "name": name}, title=table)
    _entry(
        "restaurant_names",
        "name",
        {
            "table": "shop.restaurants",
            "items": [
                {"id": 1, "name": "Bella Forno"},
                {"id": 2, "name": "Forno North"},
                {"id": 3, "name": "Test Kitchen"},
                {"id": 4, "name": "Lone Star Tacos"},
            ],
        },
        title="Restaurants",
    )
    _entry(
        "orders_restaurants",
        "link",
        {
            "from_table": "shop.orders",
            "to_table": "shop.restaurants",
            "from_columns": ["restaurant_id"],
            "to_columns": ["id"],
            "cardinality": "many_to_one",
            "found_by": "foreign_key",
            "tested_at": "2025-01-01",
        },
        title="Orders restaurants",
    )
    _entry(
        "calendar.business",
        "calendar",
        {"week_start": "monday", "fiscal_year_start": 1, "time_zone": "UTC"},
        title="Calendar",
    )
    db_session.add(
        DataSource(
            kind="postgres",
            name="Shop",
            host="localhost",
            port=5432,
            database="shop",
            username="owner",
            password_encrypted="not-encrypted-in-test",
            status="connected",
            data_through=datetime(2025, 12, 31, tzinfo=UTC),
        )
    )
    db_session.commit()
    return version.id


@pytest.fixture()
def shop_version(db_session, shop_db, test_db_url, monkeypatch):
    """The seeded version, the shop schema, and a test-DB connector."""
    set_setting(db_session, "time_zone", "America/Chicago")
    db_session.commit()
    version_id = _seeded_version(db_session)
    monkeypatch.setattr(
        data_module,
        "customer_connector",
        lambda session: PostgresConnector.from_url(test_db_url),
    )
    return version_id


def _ctx(db_session, version_id, question="How many orders?"):
    chat = Chat(title="New chat")
    db_session.add(chat)
    db_session.flush()
    db_session.add(
        Message(
            chat_id=chat.id,
            role="user",
            text_=question,
            status="done",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
    )
    assistant = Message(
        chat_id=chat.id,
        role="assistant",
        text_="",
        status="thinking",
        mode="thinking",
        kb_version_id=version_id,
        started_at=datetime.now(UTC),
    )
    db_session.add(assistant)
    db_session.commit()
    ctx = build_context(assistant.id)
    ctx.understanding = Understanding(kind="clear", reading="", periods=[])
    kb = KbView.load(db_session, version_id)
    date_ctx = load_date_context(db_session, None, kb)
    ctx.periods = resolve_periods(
        [
            PeriodExpression(kind="month", number=11),
            PeriodExpression(kind="month", number=12),
            PeriodExpression(kind="quarter", number=4),
        ],
        date_ctx,
    )
    return ctx


def _task(metric="orders", periods=("p1",), splits=(), filters=(), top_n=None) -> Task:
    return Task(
        kind="recipe",
        why=f"Get {metric}.",
        metric_key=metric,
        split_by=list(splits),
        filters=list(filters),
        periods=list(periods),
        top_n=top_n,
    )


def _notebook(db_session, ctx) -> Notebook:
    return Notebook.load(db_session, ctx.message_id, ctx.chat_id)


def _lines(db_session, message_id):
    return db_session.scalars(
        select(ThinkingEvent)
        .where(ThinkingEvent.message_id == message_id)
        .order_by(ThinkingEvent.seq)
    ).all()


def _numbers(book: Notebook):
    return [item for item in book.items() if item.kind == "number"]


def test_periods_become_p_items_in_order(db_session, shop_version) -> None:
    """Each resolved period becomes a `p` item, in order."""
    ctx = _ctx(db_session, shop_version)
    add_period_items(ctx)
    book = _notebook(db_session, ctx)
    items = [item for item in book.items() if item.kind == "period"]
    assert [item.label for item in items] == ["p1", "p2", "p3"]
    assert [(item.value["start"], item.value["end"]) for item in items] == [
        ("2025-11-01", "2025-11-30"),
        ("2025-12-01", "2025-12-31"),
        ("2025-10-01", "2025-12-31"),
    ]


def test_total_one_period(db_session, shop_version) -> None:
    """December completed orders are 191, saved with its proof."""
    ctx = _ctx(db_session, shop_version)
    run_recipe_task(_task("order_value", periods=("p2",)), ctx)
    numbers = _numbers(_notebook(db_session, ctx))
    assert len(numbers) == 1
    assert numbers[0].label == "n1"
    assert numbers[0].value["value"] == "191.00"
    assert numbers[0].description == f"Order value, 1{DASH}31 Dec 2025"
    assert numbers[0].proof["fact_key"] == {
        "metric": "order_value",
        "filters": [],
        "split": {},
        "period": "2025-12-01/2025-12-31",
        "compare_period": "",
        "measure": "value",
    }
    assert numbers[0].proof["query_run_ids"] != []


def test_two_periods_add_change_and_percent(db_session, shop_version) -> None:
    """November 168 and December 191, then November's -23 change and its %."""
    ctx = _ctx(db_session, shop_version)
    run_recipe_task(_task("order_value", periods=("p1", "p2")), ctx)
    numbers = _numbers(_notebook(db_session, ctx))
    assert [(item.value["value"], item.proof["fact_key"]["measure"]) for item in numbers[:3]] == [
        ("168.00", "value"),
        ("191.00", "value"),
        ("-23.00", "change"),
    ]
    assert len(numbers) == 4
    assert numbers[2].proof["fact_key"]["compare_period"] == "2025-12-01/2025-12-31"
    percent = next(
        item for item in numbers if item.proof["fact_key"]["measure"] == "percent_change"
    )
    assert percent.value["value"].startswith("-12.04")
    assert percent.value["unit"] == "percent"
    lines = _lines(db_session, ctx.message_id)
    found = [line for line in lines if line.kind == "found"]
    assert len(found) == 1
    assert found[0].title.startswith(
        f"Found: Order value was $168.00, down 12% on 1{DASH}31 Dec 2025."
    )


def test_split_with_comparison_labels_biggest_moves(db_session, shop_version) -> None:
    """December by restaurant with November: the table, movers and counts."""

    ctx = _ctx(db_session, shop_version)
    task = _task("order_value", periods=("p1", "p2"), splits=["dimension.restaurant_name"])
    run_recipe_task(task, ctx)
    book = _notebook(db_session, ctx)
    tables = [item for item in book.items() if item.kind == "table"]
    assert len(tables) == 1
    table = tables[0]
    assert [column["label"] for column in table.value["columns"]] == [
        "Restaurant",
        "Order value",
        "Change",
        "Change %",
    ]
    assert [row[0] for row in table.value["rows"]] == [
        "Bella Forno",
        "Lone Star Tacos",
        "Forno North",
        "Test Kitchen",
    ]
    assert [row[1] for row in table.value["rows"]] == ["100.00", "33.00", "25.00", "10.00"]
    movers = [
        item
        for item in book.items()
        if item.kind == "number" and item.proof["fact_key"]["measure"] == "change"
    ]
    assert [
        (item.value["value"], item.description.split(" at ")[1].split(",")[0]) for item in movers
    ] == [
        ("6.00", "Bella Forno"),
        ("-2.00", "Test Kitchen"),
        ("-10.00", "Forno North"),
        ("-17.00", "Lone Star Tacos"),
    ]
    counts = {
        item.proof["fact_key"]["measure"]: item.value["value"]
        for item in book.items()
        if item.kind == "number" and item.proof["fact_key"]["measure"].startswith("count_")
    }
    assert counts == {"count_grew": "1", "count_total": "4"}
    lines = _lines(db_session, ctx.message_id)
    found = [line for line in lines if line.kind == "found"]
    assert len(found) == 1
    assert found[0].title == "Found: 1 of 4 grew. The biggest drop is Lone Star Tacos."


def test_time_split_sorted_by_time(db_session, shop_version) -> None:
    """A month split reads oldest first."""
    ctx = _ctx(db_session, shop_version)
    run_recipe_task(_task("orders", periods=("p3",), splits=["dimension.month"]), ctx)
    tables = [item for item in _notebook(db_session, ctx).items() if item.kind == "table"]
    assert len(tables) == 1
    assert [row[0] for row in tables[0].value["rows"]] == ["2025-11-01", "2025-12-01"]
    assert [row[1] for row in tables[0].value["rows"]] == [6, 6]


def test_percent_fraction_stored_as_points(db_session, shop_version) -> None:
    """A ratio fraction is stored as points, not as a fraction."""
    ctx = _ctx(db_session, shop_version)
    run_recipe_task(_task("completion_share", periods=("p1",)), ctx)
    numbers = _numbers(_notebook(db_session, ctx))
    assert len(numbers) == 1
    assert numbers[0].value["unit"] == "percent"
    assert abs(Decimal(numbers[0].value["value"]) - Decimal(250) / Decimal(3)) < Decimal("0.01")


def test_blocked_recipe_query_is_a_bug(db_session, shop_version, monkeypatch) -> None:
    """A checker block fails the task, logs, and saves the blocked row."""
    from charie.shared.connectors.base import QueryBlocked

    class _Blocked:
        def run_checked(self, sql, catalog, max_rows=50000, explain=None):
            raise QueryBlocked(["nope"])

    monkeypatch.setattr(data_module, "customer_connector", lambda session: _Blocked())
    ctx = _ctx(db_session, shop_version)
    run_recipe_task(_task("orders", periods=("p2",)), ctx)
    book = _notebook(db_session, ctx)
    assert _numbers(book) == []
    findings = [item for item in book.items() if item.kind == "finding"]
    assert len(findings) == 1
    assert findings[0].value["text"] == (
        "The safety check blocked the recipe's query. This is a bug in Charie."
    )
    lines = _lines(db_session, ctx.message_id)
    failed = [line for line in lines if line.kind == "query" and line.status == "failed"]
    assert len(failed) == 1
    assert failed[0].body == findings[0].value["text"]
    runs = db_session.scalars(select(QueryRun)).all()
    assert len(runs) == 1
    assert (runs[0].status, runs[0].way, runs[0].recipe_key) == ("blocked", "recipe", "orders")
    assert runs[0].check_report == {"ok": False, "reasons": ["nope"]}


def test_timeout_adds_finding(db_session, shop_version, monkeypatch) -> None:
    """A timed-out query fails with its own message and a timeout row."""
    message = "The query took longer than 60 seconds, so it was stopped."

    class _Slow:
        def run_checked(self, sql, catalog, max_rows=50000, explain=None):
            raise ConnectorError("query_timeout", message)

    monkeypatch.setattr(data_module, "customer_connector", lambda session: _Slow())
    ctx = _ctx(db_session, shop_version)
    run_recipe_task(_task("orders", periods=("p2",)), ctx)
    book = _notebook(db_session, ctx)
    assert _numbers(book) == []
    findings = [item for item in book.items() if item.kind == "finding"]
    assert len(findings) == 1
    assert findings[0].value["text"] == message
    runs = db_session.scalars(select(QueryRun)).all()
    assert len(runs) == 1
    assert (runs[0].status, runs[0].error) == ("timeout", message)


def test_query_runs_saved_with_details(db_session, shop_version) -> None:
    """One ok row per query: purpose, recipe, sql, check, rows, seconds."""
    ctx = _ctx(db_session, shop_version)
    run_recipe_task(_task("order_value", periods=("p2",)), ctx)
    runs = db_session.scalars(select(QueryRun)).all()
    assert len(runs) == 1
    run = runs[0]
    assert run.purpose == "Get order_value."
    assert run.recipe_key == "order_value"
    assert run.way == "recipe"
    assert "shop.orders" in run.sql_text
    assert run.check_report == {"ok": True, "reasons": []}
    assert run.status == "ok"
    assert run.row_count == 1
    assert run.duration_ms >= 0
    assert run.error is None


def test_thinking_line_words(db_session, shop_version) -> None:
    """Getting ..., then Got ... with the query when expanded."""
    ctx = _ctx(db_session, shop_version)
    run_recipe_task(_task("order_value", periods=("p1", "p2")), ctx)
    lines = _lines(db_session, ctx.message_id)
    query = [line for line in lines if line.kind == "query"]
    assert len(lines) == 2
    assert (query[0].title, query[0].status) == (
        f"Getting order value for 1{DASH}30 Nov 2025 and 1{DASH}31 Dec 2025",
        "done",
    )
    assert query[0].body == 'Used the tested "Order value" recipe.'
    assert query[0].details["recipe"] == "order_value"
    assert "shop.orders" in query[0].details["sql"]
    assert query[0].details["rows"] == 1


def test_excluded_metric_builds_nothing(db_session, shop_version) -> None:
    """An excluded metric refuses: no numbers, one failed finding (B018)."""
    ctx = _ctx(db_session, shop_version)
    run_recipe_task(_task("excluded_gross", periods=("p2",)), ctx)
    book = _notebook(db_session, ctx)
    assert _numbers(book) == []
    assert [item for item in book.items() if item.kind == "table"] == []
    findings = [item for item in book.items() if item.kind == "finding"]
    assert len(findings) == 1
    assert findings[0].value["text"].startswith('We can\'t use "Excluded gross": ')
    lines = _lines(db_session, ctx.message_id)
    failed = [line for line in lines if line.status == "failed"]
    assert len(failed) == 1
    assert db_session.scalars(select(QueryRun)).all() == []


@pytest.mark.asyncio
async def test_temp_answer_runs_tasks(db_session, shop_version, monkeypatch) -> None:
    """The temporary flow: understand, tasks together, note plus short view."""
    from charie.chat.analyst import understand as understand_module
    from charie.chat.analyst.answer import TEMP_NOTE, answer_question
    from charie.shared.ai.client import AiClient
    from charie.shared.ai.cost_log import MemoryCostLog
    from charie.shared.ai.fake import FakeAi

    ctx = _ctx(db_session, shop_version, question="Completed orders in December 2025?")
    fake = FakeAi()
    fake.reply(
        "understand_question",
        {
            "kind": "clear",
            "reading": "I read this as **completed orders** for [p1], compared with [p2].",
            "periods": [{"kind": "month", "number": 11}, {"kind": "month", "number": 12}],
            "asks": [{"metric_key": "completed_orders"}],
            "filters": [],
            "defaults_used": [],
            "document_topics": [],
        },
    )
    monkeypatch.setattr(
        understand_module,
        "get_ai",
        lambda: AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None),
    )
    await answer_question(ctx)
    book = _notebook(db_session, ctx)
    assert [item.label for item in book.items()][:5] == ["p1", "p2", "n1", "n2", "n3"]
    assert book.items()[2].value["value"] == "5"
    saved = db_session.get(Message, ctx.message_id)
    assert saved.status == "done"
    assert saved.answer["blocks"][0]["sentences"][0]["text"] == TEMP_NOTE
    assert "n1 = 5" in saved.answer["blocks"][0]["sentences"][1]["text"]
    titles = [line.title for line in _lines(db_session, ctx.message_id)]
    assert titles[0] == "Understood the question"
    assert any(title.startswith("Getting completed orders for ") for title in titles)


def test_excluded_ratio_side_builds_nothing(db_session, shop_version) -> None:
    """A ratio over an excluded side refuses too (B018)."""
    ctx = _ctx(db_session, shop_version)
    run_recipe_task(_task("bad_share", periods=("p2",)), ctx)
    book = _notebook(db_session, ctx)
    assert _numbers(book) == [] and [item for item in book.items() if item.kind == "table"] == []
    findings = [item for item in book.items() if item.kind == "finding"]
    assert len(findings) == 1
    assert findings[0].value["text"] == (
        'We can\'t use "Bad share": It divides excluded_gross, which is excluded.'
    )


def test_names_become_ids(db_session, shop_version) -> None:
    """Bella Forno filters by name or by id: December is 94 either way."""

    ctx = _ctx(db_session, shop_version)
    run_recipe_task(
        _task(
            "order_value",
            periods=("p2",),
            filters=[Filter(dimension_key="dimension.restaurant_name", values=["Bella Forno"])],
        ),
        ctx,
    )
    run_recipe_task(
        _task(
            "order_value",
            periods=("p2",),
            filters=[Filter(dimension_key="dimension.restaurant_id", values=["Bella Forno"])],
        ),
        ctx,
    )
    numbers = _numbers(_notebook(db_session, ctx))
    assert len(numbers) == 2
    assert [number.value["value"] for number in numbers] == ["94.00", "94.00"]
    assert numbers[0].proof["fact_key"]["filters"] == ["Bella Forno"]
    assert numbers[1].proof["fact_key"]["filters"] == [1]
