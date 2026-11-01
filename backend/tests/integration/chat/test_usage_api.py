"""GET /api/usage on the real database (chat app only)."""

from datetime import UTC, datetime
from decimal import Decimal

from charie.shared.tables.chat import Chat, Message
from charie.shared.tables.usage import AiCall
from tests.conftest import log_in

NOV = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
NOV_10 = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def _call(db_session, job, app, cost, at=NOV, message_id=None, run_id=None) -> None:
    db_session.add(
        AiCall(
            app=app,
            job=job,
            provider="meta",
            model="muse-wonder-1.0",
            cost_usd=Decimal(cost),
            at=at,
            message_id=message_id,
            learning_run_id=run_id,
        )
    )
    db_session.commit()


def _messages(db_session, count: int) -> list[int]:
    db_session.add(Chat(title="Usage"))
    db_session.flush()
    chat_id = db_session.query(Chat).one().id
    ids = []
    for _ in range(count):
        message = Message(chat_id=chat_id, role="user", text_="Q")
        db_session.add(message)
        db_session.flush()
        ids.append(message.id)
    db_session.commit()
    return ids


def _november(db_session) -> None:
    first, second = _messages(db_session, 2)
    _call(db_session, "write_answer", "chat", "0.0042", message_id=first)
    _call(db_session, "review_answer", "chat", "0.0025", NOV_10, message_id=second)
    _call(db_session, "name_chat", "tests", "0.0042", NOV_10)


def _get(client, month=None):
    url = "/api/usage" + (f"?month={month}" if month else "")
    response = client.get(url)
    assert response.status_code == 200, response.text
    return response.json()


def test_totals_and_percent(chat_client, db_session) -> None:
    log_in(chat_client)
    _november(db_session)
    usage = _get(chat_client, "2026-11")
    assert usage["month"] == "2026-11" and usage["days_in_month"] == 30
    assert usage["resets_on"] == "2026-12-01"
    assert usage["spent_usd"] == 0.0109
    assert usage["questions"] == {"count": 2, "cost_usd": 0.0067}
    assert usage["learning_runs"] == {"count": 0, "cost_usd": 0.0}
    assert usage["state"] == "ok" and usage["limit_usd"] == 150.0


def test_expected_month_end(chat_client, db_session, monkeypatch) -> None:
    from datetime import datetime as real_datetime

    class _Frozen(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 11, 15, 12, 0, tzinfo=UTC)

    monkeypatch.setattr("charie.chat.api.usage.datetime", _Frozen)
    log_in(chat_client)
    _november(db_session)
    assert _get(chat_client, "2026-11")["expected_usd"] == 0.0218


def test_per_day_split_by_app(chat_client, db_session) -> None:
    log_in(chat_client)
    _november(db_session)
    per_day = {day["date"]: day for day in _get(chat_client, "2026-11")["per_day"]}
    assert len(per_day) == 30
    assert per_day["2026-11-03"]["questions_usd"] == 0.0042
    assert per_day["2026-11-10"]["questions_usd"] == 0.0025
    assert per_day["2026-11-10"]["tests_usd"] == 0.0042
    assert per_day["2026-11-04"]["questions_usd"] == 0.0


def test_groups_follow_job_groups(chat_client, db_session) -> None:
    log_in(chat_client)
    _call(db_session, "understand_question", "chat", "0.0010")
    _call(db_session, "write_sql", "chat", "0.0010", NOV_10)
    _call(db_session, "find_quotes", "chat", "0.0010", NOV_10)
    _call(db_session, "write_answer", "chat", "0.0010", NOV_10)
    _call(db_session, "review_answer", "chat", "0.0010", NOV_10)
    _call(db_session, "sort_owner_notes", "learner", "0.0010", NOV_10)
    _call(db_session, "judge_test_answer", "tests", "0.0010", NOV_10)
    groups = [group["group"] for group in _get(chat_client, "2026-11")["per_group"]]
    assert groups == [
        "Planning and judging",
        "Data helpers",
        "Document search",
        "Writing answers",
        "Reviewing answers",
        "Learning",
        "Tests",
    ]


def test_top_questions_with_question_text(chat_client, db_session) -> None:
    log_in(chat_client)
    db_session.add(Chat(title="Q"))
    db_session.flush()
    chat_id = db_session.query(Chat).one().id
    db_session.add(
        Message(
            chat_id=chat_id,
            role="user",
            text_="What is revenue?",
            started_at=datetime(2026, 11, 5, 12, 0, tzinfo=UTC),
        )
    )
    db_session.add(
        Message(
            chat_id=chat_id,
            role="assistant",
            text_="Lots.",
            seconds=12,
            steps=3,
            cost_usd=Decimal("0.005"),
            started_at=datetime(2026, 11, 5, 12, 1, tzinfo=UTC),
        )
    )
    db_session.add(
        Message(
            chat_id=chat_id,
            role="assistant",
            text_="More.",
            seconds=2,
            steps=1,
            cost_usd=Decimal("0.001"),
            started_at=datetime(2026, 11, 6, 12, 0, tzinfo=UTC),
        )
    )
    db_session.commit()
    top = _get(chat_client, "2026-11")["top_questions"]
    assert len(top) == 2
    assert top[0]["question"] == "What is revenue?"
    assert top[0]["seconds"] == 12 and top[0]["steps"] == 3
    assert top[0]["cost_usd"] == 0.005 and top[0]["chat_id"] == chat_id


def test_bad_month(chat_client, db_session) -> None:
    log_in(chat_client)
    for bad in ("2026-13", "november", "2026-1"):
        response = chat_client.get(f"/api/usage?month={bad}")
        assert response.status_code == 400
        assert response.json() == {
            "error": "bad_month",
            "message": "Month must look like 2026-10.",
        }


def test_other_month(chat_client, db_session) -> None:
    log_in(chat_client)
    _november(db_session)
    usage = _get(chat_client, "2026-08")
    assert usage["days_in_month"] == 31 and usage["spent_usd"] == 0.0
    assert usage["expected_usd"] == 0.0 and len(usage["per_day"]) == 31


def test_learner_app_has_no_usage_address(learner_client) -> None:
    log_in(learner_client)
    assert learner_client.get("/api/usage").status_code == 404


OCTOBER_LAST = datetime(2026, 10, 31, 19, 0, tzinfo=UTC)  # Nov 1, 00:30 in Kolkata.
IST = "Asia/Kolkata"


def test_calls_grouped_by_owner_month(chat_client, db_session) -> None:
    from charie.shared.settings import set_setting

    log_in(chat_client)
    set_setting(db_session, "time_zone", IST)
    _call(db_session, "write_answer", "chat", "0.0042", at=OCTOBER_LAST)
    _call(db_session, "write_answer", "chat", "0.0010", at=NOV)
    november = _get(chat_client, "2026-11")
    assert november["spent_usd"] == 0.0052
    first = next(day for day in november["per_day"] if day["date"] == "2026-11-01")
    assert first["questions_usd"] == 0.0042
    assert _get(chat_client, "2026-10")["spent_usd"] == 0.0


def test_top_questions_follow_owner_month(chat_client, db_session) -> None:
    from charie.shared.settings import set_setting

    log_in(chat_client)
    set_setting(db_session, "time_zone", IST)
    db_session.add(Chat(title="Boundary"))
    db_session.flush()
    chat_id = db_session.query(Chat).one().id
    db_session.add(Message(chat_id=chat_id, role="user", text_="Late question?"))
    db_session.flush()
    db_session.add(
        Message(
            chat_id=chat_id,
            role="assistant",
            text_="",
            started_at=OCTOBER_LAST,
            cost_usd=0.01,
            seconds=3,
            steps=1,
        )
    )
    db_session.commit()
    november = _get(chat_client, "2026-11")["top_questions"]
    assert [row["message_id"] for row in november] != []
    assert november[0]["question"] == "Late question?"
    assert _get(chat_client, "2026-10")["top_questions"] == []


def test_top_questions_skip_private_chats(chat_client, db_session, monkeypatch) -> None:
    """Hidden test runs never surface on Usage; their spend still counts."""
    monkeypatch.setenv("AI_REPLAY", "replay")
    log_in(chat_client)
    shown = Chat(title="Shown", private=False)
    hidden = Chat(title="Hidden", private=True)
    db_session.add_all([shown, hidden])
    db_session.flush()
    for chat, text, cost in (
        (shown, "What is revenue?", "0.0040"),
        (hidden, "Hidden question?", "0.0090"),
    ):
        db_session.add(Message(chat_id=chat.id, role="user", text_=text, started_at=NOV))
        db_session.add(
            Message(
                chat_id=chat.id,
                role="assistant",
                text_="A.",
                seconds=5,
                steps=2,
                cost_usd=Decimal(cost),
                started_at=NOV,
            )
        )
    _call(db_session, "write_answer", "chat", "0.0040", NOV)
    _call(db_session, "write_answer", "chat", "0.0090", NOV)
    summary = _get(chat_client, "2026-11")
    # The hidden chat outspends the shown one and still stays out.
    assert [row["chat_id"] for row in summary["top_questions"]] == [shown.id]
    assert summary["top_questions"][0]["question"] == "What is revenue?"
    assert summary["spent_usd"] == 0.013
