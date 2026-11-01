"""The new-kind questions on the practice database (P10.7 Task 4).

Laptop-only: needs the practice database and the recorded AI replies.
Recording costs about $1: run `AI_REPLAY=record uv run pytest <this file>`
once with the owner's yes, then replay. Without cassettes it fails by
design, like the understand replays.
"""

import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import pytest

from charie.chat.analyst.helpers.new_number import run_new_number_task
from charie.chat.analyst.helpers.tasks import starter_tasks
from charie.chat.analyst.kb_view import KbView
from charie.chat.analyst.understand import understand
from charie.shared.crypto import encrypt_text
from charie.shared.settings import set_setting
from charie.shared.tables.knowledge import KbEntry, KbVersion
from charie.shared.tables.sources import DataSource
from tests.integration.chat import test_data_helper as shop
from tests.questions.format import load_questions

CASES = ["new_kind-001", "new_kind-002"]

PUBLIC = Path(__file__).resolve().parents[2] / "questions" / "public.yaml"


def _seed_tables(db_session) -> int:
    """A published version with the orders and coupons tables, no recipes."""
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

    _entry(
        "public.orders",
        "table",
        {"schema": "public", "name": "orders"},
        title="public.orders",
    )
    for name in ("id", "user_id", "restaurant_id", "created_at"):
        _entry(
            f"public.orders.{name}",
            "column",
            {"schema": "public", "table": "orders", "name": name},
        )
    _entry(
        "public.order_coupons",
        "table",
        {"schema": "public", "name": "order_coupons"},
        title="public.order_coupons",
    )
    for name in ("id", "order_id"):
        _entry(
            f"public.order_coupons.{name}",
            "column",
            {"schema": "public", "table": "order_coupons", "name": name},
        )
    raw = os.environ["PRACTICE_DB_URL"]
    target = urlparse(raw if "://" in raw else f"postgresql://{raw}")
    db_session.add(
        DataSource(
            kind="postgres",
            name="Practice database",
            host=target.hostname or "localhost",
            port=target.port or 5432,
            database=(target.path or "/shop").lstrip("/"),
            username=target.username or "owner",
            password_encrypted=encrypt_text(target.password or ""),
            status="connected",
            data_through=datetime(2025, 12, 31, tzinfo=UTC),
        )
    )
    set_setting(db_session, "time_zone", "America/Chicago")
    db_session.commit()
    return version.id


def _by_id(case_id: str):
    for question in load_questions(str(PUBLIC), "public"):
        if question.id == case_id:
            return question
    raise AssertionError(f"no question {case_id} in public.yaml")


@pytest.mark.practice_db
@pytest.mark.live_ai
@pytest.mark.parametrize("case_id", CASES)
def test_new_kind_question(db_session, case_id) -> None:
    """Each new-kind question gives agreeing numbers matching its answer key."""
    version_id = _seed_tables(db_session)
    question = _by_id(case_id)
    ctx = shop._ctx(db_session, version_id, question=question.question)
    understand(ctx)
    kb = KbView.load(db_session, version_id)
    for task in starter_tasks(ctx.understanding, kb.titles()):
        if task.kind == "new_number":
            run_new_number_task(task, ctx)
    book = shop._notebook(db_session, ctx)
    got = [Decimal(item.value["value"]) for item in book.items() if item.kind == "number"]
    assert got, "the notebook has no numbers"
    for expected in question.expect.numbers:
        want, tolerance = expected.value, expected.tolerance
        assert any(abs(value - want) <= tolerance for value in got), (
            f"{case_id}: no notebook number matches {expected.name}={want}±{tolerance}"
        )
