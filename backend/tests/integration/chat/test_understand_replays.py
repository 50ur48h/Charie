"""The 15 understand cases against recorded AI replies (P10.4).

Recording costs about $1-2: `AI_REPLAY=record uv run pytest <file>
-m "practice_db and live_ai"`. Replaying is free and runs with
`AI_REPLAY=replay`. The replays stay out of git with the snapshot.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from charie.chat.analyst.understand import understand
from charie.shared.tables.chat import Chat, Message

CASES = yaml.safe_load((Path(__file__).parent / "data" / "understand_cases.yaml").read_text())


def _ctx_for(db_session, kb_version, question):
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
        kb_version_id=kb_version,
        started_at=datetime.now(UTC),
    )
    db_session.add(assistant)
    db_session.commit()
    from charie.chat.chat_store import build_context

    return build_context(assistant.id)


@pytest.mark.practice_db
@pytest.mark.live_ai
def test_snapshot_loads(db_session, kb_version) -> None:
    """The frozen knowledge loads in the test database."""
    from charie.chat.analyst.kb_view import KbView

    kb = KbView.load(db_session, kb_version)
    assert len(kb.metrics()) == 21
    assert kb.calendar().week_start == "monday"


@pytest.mark.practice_db
@pytest.mark.live_ai
@pytest.mark.parametrize("case", CASES, ids=[item["id"] for item in CASES])
def test_understanding_case(db_session, kb_version, practice_source, case) -> None:
    """The recorded reading matches the agreed kinds, keys and dates."""
    _ = practice_source
    ctx = _ctx_for(db_session, kb_version, case["question"])
    understand(ctx)
    reading = ctx.understanding
    assert reading.kind in case["allowed_kinds"], reading.kind
    assert {ask.metric_key for ask in reading.asks if ask.metric_key} == set(
        case.get("metrics", [])
    )
    if case.get("new_metric"):
        assert any(ask.new_metric for ask in reading.asks)
    if case.get("document_topics"):
        assert reading.document_topics != []
    shorts = [period.short_text() for period in reading.periods]
    assert shorts in case["period_options"], shorts
    if case.get("splits"):
        assert [split for ask in reading.asks for split in ask.split_by] == case["splits"]
    if case.get("top_n"):
        assert [ask.top_n for ask in reading.asks if ask.metric_key] == [case["top_n"]] * len(
            case.get("metrics", [])
        )
    assert [
        {"dimension": filt.dimension_key, "values": filt.values} for filt in reading.filters
    ] == case.get("filters", [])
    assert [
        (period.start.isoformat(), period.end.isoformat()) for period in ctx.periods.periods
    ] == [tuple(pair) for pair in case.get("dates", [])]
    if case.get("no_data"):
        assert all(period.no_data for period in ctx.periods.periods)
