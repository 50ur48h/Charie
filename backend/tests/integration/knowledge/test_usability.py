"""Usable knowledge: failed/untested stay out, even through ratios and defaults (P09.10)."""

from charie.shared.knowledge import store, versions
from charie.shared.knowledge.query_builder import (
    BuildContext,
    DateRange,
    QueryRequest,
    build_query,
)
from charie.shared.knowledge.recipe import Recipe
from charie.shared.tables.knowledge import KbVersion
from tests.conftest import log_in


def _version_id(db_session):
    return versions.get_or_create_draft(db_session, "first_learning").id


def _passing_tests():
    return [
        {"name": "runs", "passed": True, "text": "seed"},
        {"name": "believable", "passed": True, "text": "seed"},
        {"name": "matches_documents", "passed": None, "text": "seed"},
        {"name": "parts_add_up", "passed": True, "text": "seed"},
    ]


def _seed_simple(db_session, version_id, key, expression="orders.total_amount", tests=None):
    store.upsert_entry(
        db_session,
        version_id,
        key,
        "metric",
        "Seed",
        "Seed",
        {
            "kind": "simple",
            "title": "Seed",
            "table": "shop.orders",
            "aggregate": "sum",
            "expression": expression,
            "filters": ["orders.status = 'completed'"],
            "time_column": "orders.created_at",
            "time_column_type": "timestamptz",
            "unit": "money",
            "currency": "USD",
            "steps_in_words": ["Add them up.", "Keep completed ones."],
            "dimensions": [],
            "tests": _passing_tests() if tests is None else tests,
            "reported_checks": [],
            "sql_preview": "seed",
            "tested_at": "2000-01-01T00:00:00+00:00",
        },
        "checked",
        [{"type": "structure", "text": "seed"}],
        "seed",
    )


def _seed_ratio(db_session, version_id, key, numerator, denominator):
    store.upsert_entry(
        db_session,
        version_id,
        key,
        "metric",
        "Seed ratio",
        "Seed ratio",
        {
            "kind": "ratio",
            "title": "Seed ratio",
            "numerator": numerator,
            "denominator": denominator,
            "unit": "ratio",
            "currency": "",
            "steps_in_words": ["Add up both sides.", "Divide."],
            "dimensions": [],
            "tests": _passing_tests(),
            "reported_checks": [],
            "sql_preview": "seed",
            "tested_at": "2000-01-01T00:00:00+00:00",
        },
        "checked",
        [{"type": "structure", "text": "seed"}],
        "seed",
    )


def _seed_default(db_session, version_id, key, metrics):
    store.upsert_entry(
        db_session,
        version_id,
        key,
        "default",
        "Seed default",
        "Seed default",
        {"word": "sales", "value": "metric.a_one", "metrics": metrics},
        "checked",
        [{"type": "structure", "text": "seed"}],
        "seed",
    )


def _seed_mixed(db_session, version_id):
    _seed_simple(db_session, version_id, "metric.a_one", "orders.total_amount")
    _seed_simple(db_session, version_id, "metric.a_two", "orders.delivery_fee")
    _seed_simple(
        db_session,
        version_id,
        "metric.bad_one",
        tests=[
            {"name": "runs", "passed": True, "text": "seed"},
            {"name": "believable", "passed": False, "text": "seed"},
        ],
    )
    _seed_simple(db_session, version_id, "metric.new_one", tests=[])
    _seed_ratio(db_session, version_id, "metric.ratio_ok", "metric.a_one", "metric.a_two")
    _seed_ratio(db_session, version_id, "metric.ratio_bad", "metric.a_one", "metric.bad_one")
    _seed_default(db_session, version_id, "default.d_ok", ["metric.a_one"])
    _seed_default(db_session, version_id, "default.d_bad", ["metric.bad_one"])
    db_session.commit()


def test_excluded_metrics_cannot_be_used(db_session):
    """Failed, untested and their dependents stay out of usable knowledge."""
    version_id = _version_id(db_session)
    _seed_mixed(db_session, version_id)
    scope = versions.usability(db_session, version_id)
    assert scope["usable"] == ["metric.a_one", "metric.a_two", "metric.ratio_ok"]
    excluded = {item["key"]: item["reason"] for item in scope["excluded"]}
    assert set(excluded) == {"metric.bad_one", "metric.new_one", "metric.ratio_bad"}
    assert "believable" in excluded["metric.bad_one"]
    assert "never checked" in excluded["metric.new_one"]
    assert "metric.bad_one" in excluded["metric.ratio_bad"]
    assert scope["usable_defaults"] == ["default.d_ok"]
    bad_defaults = {item["key"]: item["reason"] for item in scope["excluded_defaults"]}
    assert set(bad_defaults) == {"default.d_bad"}
    assert "metric.bad_one" in bad_defaults["default.d_bad"]


def test_usable_metrics_build(db_session):
    """Every usable metric builds through the real query-builder path."""
    version_id = _version_id(db_session)
    _seed_mixed(db_session, version_id)
    scope = versions.usability(db_session, version_id)
    recipes = {}
    for key in scope["usable"]:
        recipes[key] = Recipe.model_validate(store.get_entry(db_session, version_id, key).details)
    context = BuildContext(time_zone="America/Chicago")
    request = QueryRequest(period=DateRange(start="2025-11-01", end="2025-11-30"), dimensions=[])
    for key in scope["usable"]:
        built = build_query(key, recipes, request, context)
        assert built.sql.startswith("SELECT ")
        assert built.recipe_key == key


def test_partial_publish_scope(db_session, learner_client):
    """Manual publish succeeds with failures present; the scope names them."""
    log_in(learner_client)
    version_id = _version_id(db_session)
    _seed_mixed(db_session, version_id)
    response = learner_client.post("/api/versions/1/publish")
    assert response.status_code == 200
    scope = response.json()["scope"]
    assert scope["usable"] == ["metric.a_one", "metric.a_two", "metric.ratio_ok"]
    assert {item["key"] for item in scope["excluded"]} == {
        "metric.bad_one",
        "metric.new_one",
        "metric.ratio_bad",
    }
    assert db_session.get(KbVersion, version_id).status == "published"


def test_nothing_usable_still_refused(db_session, learner_client):
    """A draft with no passing number cannot publish, even by hand."""
    log_in(learner_client)
    version_id = _version_id(db_session)
    _seed_simple(
        db_session,
        version_id,
        "metric.bad_one",
        tests=[{"name": "runs", "passed": False, "text": "seed"}],
    )
    db_session.commit()
    refused = learner_client.post("/api/versions/1/publish")
    assert refused.status_code == 409
    assert refused.json()["error"] == "failed_checks"
    assert db_session.get(KbVersion, version_id).status == "draft"


def test_auto_publish_still_strict(db_session):
    """Automatic publication keeps every restriction."""
    from charie.shared.settings import set_setting

    version_id = _version_id(db_session)
    _seed_mixed(db_session, version_id)
    set_setting(db_session, "setup_done", True)
    db_session.commit()
    decision = versions.finalize_run(db_session, version_id)
    assert decision["published"] is False
    assert "stay for review" in decision["reason"]
    assert db_session.get(KbVersion, version_id).status == "draft"
