"""Business term discovery from learned evidence (P09.3, fake AI)."""

from charie.learner.steps import business_numbers
from charie.learner.steps.base import StepContext
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge import store, versions
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.sources import DocFact, Document, DocumentSection


def _seed(db_session) -> int:
    version_id = versions.get_or_create_draft(db_session, "first_learning").id
    store.upsert_entry(
        db_session,
        version_id,
        "table.shop.orders",
        "table",
        "orders",
        "One row per order the shop took.",
        {"schema": "shop", "name": "orders", "grain": "one order"},
        "checked",
        [{"type": "structure", "text": "Read from the database structure"}],
        "seed",
    )
    store.upsert_entry(
        db_session,
        version_id,
        "column.shop.orders.total_amount",
        "column",
        "total_amount",
        "What the customer paid, in dollars.",
        {
            "schema": "shop",
            "table": "orders",
            "name": "total_amount",
            "data_type": "numeric",
            "unit": "money",
            "currency": "USD",
        },
        "checked",
        [{"type": "structure", "text": "Read from the database structure"}],
        "seed",
    )
    store.upsert_entry(
        db_session,
        version_id,
        "rule.no_test_restaurants",
        "rule",
        "Test restaurants never count",
        "Test restaurants never count unless asked.",
        {
            "rule_type": "always_filter",
            "table": "shop.restaurants",
            "column": "is_test",
            "values": ["false"],
        },
        "confirmed",
        [{"type": "owner_notes", "quote": "Test restaurants never count"}],
        "seed",
    )
    doc = Document(
        file_name="guide.md", file_type="md", size_bytes=10, sha256="abc", status="learned"
    )
    db_session.add(doc)
    db_session.flush()
    section = DocumentSection(document_id=doc.id, position=0, text_="Net sales defined.")
    db_session.add(section)
    db_session.flush()
    db_session.add(
        DocFact(
            document_id=doc.id,
            section_id=section.id,
            kind="definition",
            topic="Net sales",
            statement="Net sales means completed order totals.",
            quote="Net sales means completed order totals.",
            status="ok",
        )
    )
    db_session.commit()
    return version_id


def _ctx(db_session, version_id: int, source=None, connector=None):
    run = LearningRun(
        kind="first", status="running", step="business_numbers", version_id=version_id
    )
    db_session.add(run)
    db_session.commit()
    said: list = []

    def say(kind: str, message: str, details=None) -> None:
        said.append((kind, message))

    ctx = StepContext(
        session=db_session,
        run_id=run.id,
        version_id=version_id,
        source=source,
        connector=connector,
        strict_mode=False,
        settings={},
        say=say,
    )
    return ctx, said, run


def _run(ctx, monkeypatch, reply: dict, dimensions: dict | None = None) -> FakeAi:
    fake = FakeAi().reply("find_business_terms", reply)
    fake.reply("find_dimensions", dimensions if dimensions is not None else {"dimensions": []})
    client = AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None)
    monkeypatch.setattr(business_numbers, "get_ai", lambda: client)
    business_numbers.run_job(
        JobInfo(
            id=1,
            kind="find_business_terms",
            payload={"step": "business_numbers"},
            run_id=ctx.run_id,
        ),
        ctx,
    )
    return fake


def _term(name: str, **overrides) -> dict:
    term = {
        "name": name,
        "meaning": f"{name} for the period.",
        "unit": "money",
        "evidence": ["column:shop.orders.total_amount"],
        "splits": ["by month"],
    }
    term.update(overrides)
    return term


def test_evidence_required(db_session, monkeypatch) -> None:
    version_id = _seed(db_session)
    ctx, said, _ = _ctx(db_session, version_id)
    _run(
        ctx,
        monkeypatch,
        {
            "terms": [
                _term("Net sales", evidence=["column:shop.orders.total_amount", "doc:Net sales"]),
                _term("Ghost sales", evidence=["table:shop.missing"]),
            ]
        },
    )
    proposals = db_session.get(LearningRun, ctx.run_id).progress["business_numbers"]["proposals"]
    assert [proposal["name"] for proposal in proposals] == ["Net sales"]
    assert any("without real evidence" in message for _, message in said)


def test_duplicate_resume(db_session, monkeypatch) -> None:
    version_id = _seed(db_session)
    ctx, _, _ = _ctx(db_session, version_id)
    _run(
        ctx,
        monkeypatch,
        {
            "terms": [
                _term("Net sales", splits=["by month"]),
                _term(
                    "net sales ",
                    splits=["by restaurant"],
                    evidence=["table:shop.orders", "rule:Test restaurants never count"],
                ),
            ]
        },
    )
    db_session.expire_all()
    proposals = db_session.get(LearningRun, ctx.run_id).progress["business_numbers"]["proposals"]
    assert len(proposals) == 1
    assert sorted(proposals[0]["splits"]) == ["by month", "by restaurant"]
    assert sorted(proposals[0]["evidence"]) == [
        "column:shop.orders.total_amount",
        "rule:Test restaurants never count",
        "table:shop.orders",
    ]
    # Resuming finds the proposals and queues nothing new.
    assert business_numbers.make_jobs(ctx) == []


def test_candidates_not_usable(db_session, monkeypatch) -> None:
    version_id = _seed(db_session)
    ctx, _, _ = _ctx(db_session, version_id)
    _run(ctx, monkeypatch, {"terms": [_term("Net sales")]})
    db_session.expire_all()
    proposals = db_session.get(LearningRun, ctx.run_id).progress["business_numbers"]["proposals"]
    assert proposals and all(proposal["proposed"] for proposal in proposals)
    assert store.list_entries(db_session, version_id, kinds=["metric"]) == []


def _seed_dimension_tables(db_session, version_id: int) -> None:
    store.upsert_entry(
        db_session,
        version_id,
        "table.shop.orders",
        "table",
        "orders",
        "One row per order.",
        {"schema": "shop", "name": "orders", "primary_key": ["id"]},
        "checked",
        [{"type": "structure", "text": "Read from the database structure"}],
        "seed",
    )
    store.upsert_entry(
        db_session,
        version_id,
        "column.shop.orders.status",
        "column",
        "status",
        "How the order ended.",
        {"schema": "shop", "table": "orders", "name": "status", "data_type": "text"},
        "checked",
        [{"type": "structure", "text": "Read from the database structure"}],
        "seed",
    )
    store.upsert_entry(
        db_session,
        version_id,
        "table.shop.restaurants",
        "table",
        "restaurants",
        "One row per restaurant.",
        {"schema": "shop", "name": "restaurants", "primary_key": ["id"]},
        "checked",
        [{"type": "structure", "text": "Read from the database structure"}],
        "seed",
    )
    store.upsert_entry(
        db_session,
        version_id,
        "column.shop.restaurants.name",
        "column",
        "name",
        "What the restaurant is called.",
        {"schema": "shop", "table": "restaurants", "name": "name", "data_type": "text"},
        "checked",
        [{"type": "structure", "text": "Read from the database structure"}],
        "seed",
    )
    db_session.commit()


def test_dimensions_prove_overlap_on_real_data(db_session, shop_db, monkeypatch) -> None:
    from sqlalchemy import text

    version_id = versions.get_or_create_draft(db_session, "first_learning").id
    for key, kind, title, meaning, details in [
        (
            "table.shop.ev",
            "table",
            "events",
            "One row per event.",
            {"schema": "shop", "name": "ev", "primary_key": ["id"]},
        ),
        (
            "table.shop.ev_tag",
            "table",
            "event tags",
            "One tag per event row.",
            {"schema": "shop", "name": "ev_tag"},
        ),
        (
            "column.shop.ev.amount",
            "column",
            "amount",
            "What the event brought in.",
            {"schema": "shop", "table": "ev", "name": "amount", "data_type": "numeric"},
        ),
        (
            "column.shop.ev_tag.tag",
            "column",
            "tag",
            "How the event is tagged.",
            {"schema": "shop", "table": "ev_tag", "name": "tag", "data_type": "text"},
        ),
        (
            "link.shop.ev_tag.ev_id~shop.ev.id",
            "link",
            "ev_tag.ev_id → ev.id",
            "Each tag names its event.",
            {
                "from_table": "shop.ev_tag",
                "to_table": "shop.ev",
                "from_columns": ["ev_id"],
                "to_columns": ["id"],
                "found_by": "foreign_key",
                "cardinality": "many_to_one",
                "match_share": 1.0,
                "tested_at": "2025-11-07T12:00:00+00:00",
            },
        ),
    ]:
        store.upsert_entry(
            db_session,
            version_id,
            key,
            kind,
            title,
            meaning,
            details,
            "checked",
            [{"type": "structure", "text": "Read from the database structure"}],
            "seed",
        )
    db_session.commit()
    with shop_db["owner"].begin() as conn:
        conn.execute(text("CREATE TABLE shop.ev (id integer PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE shop.ev_tag ("
                "ev_id integer NOT NULL REFERENCES shop.ev (id), tag text NOT NULL)"
            )
        )
        conn.execute(text("INSERT INTO shop.ev (id) VALUES (1), (2)"))
        conn.execute(
            text(
                "INSERT INTO shop.ev_tag (ev_id, tag) VALUES (1, 'a'), (1, 'a'), (1, 'b'), (2, 'b')"
            )
        )
        conn.execute(text("GRANT SELECT ON shop.ev, shop.ev_tag TO PUBLIC"))
    ctx, _, _ = _ctx(
        db_session, version_id, source=shop_db["source"], connector=shop_db["connector"]
    )
    _run(
        ctx,
        monkeypatch,
        {
            "terms": [
                {
                    "name": "Event spend",
                    "meaning": "Tagged event counts.",
                    "unit": "count",
                    "evidence": ["column:shop.ev.amount"],
                    "splits": ["by tag"],
                }
            ]
        },
        {
            "dimensions": [
                {"term": "term.event_spend", "table": "shop.ev_tag", "column": "tag"},
            ]
        },
    )
    db_session.expire_all()
    ours = db_session.get(LearningRun, ctx.run_id).progress["business_numbers"]
    assert ours["proposals"][0]["dimensions"] == ["dimension.tag"]
    entry = store.get_entry(db_session, version_id, "dimension.tag")
    assert entry is not None
    (proof,) = entry.details["unique_with"]
    assert proof["exact"] is True
    assert proof["base_table"] == "shop.ev"
    assert proof["link_keys"] == ["shop.ev_tag"]


def test_dimensions_attach_to_terms(db_session, monkeypatch) -> None:
    version_id = _seed(db_session)
    _seed_dimension_tables(db_session, version_id)
    ctx, _, _ = _ctx(db_session, version_id)
    _run(
        ctx,
        monkeypatch,
        {"terms": [_term("Net sales", evidence=["table:shop.orders"])]},
        {
            "dimensions": [
                {"term": "term.net_sales", "table": "shop.orders", "column": "status"},
            ]
        },
    )
    db_session.expire_all()
    ours = db_session.get(LearningRun, ctx.run_id).progress["business_numbers"]
    assert ours["proposals"][0]["dimensions"] == ["dimension.status"]
    assert ours["dimensions_done"] is True
    entry = store.get_entry(db_session, version_id, "dimension.status")
    assert entry is not None
    assert entry.details["unique_with"] == []
    assert entry.details["kind"] == "attribute"
