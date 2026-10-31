"""Owner questions API for both apps: list, answer, skip (P09.6).

The same router serves the chat and learner apps; login is enforced by
the apps. Evidence is serialized safe: plain summaries and quotes only,
never credentials. Exactly one of option_id or text answers a question;
a different answer conflicts unless it sends the saved answer back as
previous, which proves the change is deliberate and not stale.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from charie.shared.db import get_session
from charie.shared.errors import ApiError
from charie.shared.knowledge.answers import (
    AnswerConflict,
    AnswerNotFound,
    BadAnswer,
    apply_answer,
)
from charie.shared.tables.questions import OwnerQuestion

questions_router = APIRouter()

STATUSES = ("waiting", "answered", "skipped")


class AnswerBody(BaseModel):
    option_id: str | None = None
    text: str | None = None
    previous_option_id: str | None = None
    previous_text: str | None = None


def _source_name(source: dict) -> str:
    if source.get("type") == "owner_notes":
        return "Your notes"
    if source.get("type") == "owner_answer":
        return "Your answer"
    if source.get("document"):
        return str(source["document"])
    return "A document"


def _summary(origin: str, row: OwnerQuestion, context: dict) -> str:
    word = context.get("word") or ""
    title = context.get("title") or row.title
    if origin == "default":
        return f"Charie guessed what “{word}” means. Your answer confirms it."
    if origin == "calendar":
        return "Charie guessed the business calendar. Your answer confirms it."
    if origin == "recipe":
        return f"A business number failed its checks. Your answer unblocks “{title}”."
    if origin == "conflict":
        return f"Two pieces of evidence disagree about “{title}”. Your answer picks it."
    if origin == "business":
        name = context.get("name") or title
        return f"“{name}” has no checked recipe yet. Your answer defines it."
    return "Charie needs your answer to keep learning."


def _public_question(row: OwnerQuestion) -> dict:
    """The safe public shape: summary, quotes and code numbers only."""
    evidence = row.evidence if isinstance(row.evidence, dict) else {}
    context = evidence.get("context") if isinstance(evidence.get("context"), dict) else {}
    docs = []
    for source in evidence.get("sources") or []:
        if not isinstance(source, dict) or not source.get("quote"):
            continue
        if source.get("type") not in ("owner_notes", "document", "owner_answer"):
            continue
        docs.append({"name": _source_name(source), "quote": source["quote"]})
    public_evidence: dict = {"summary": _summary(evidence.get("origin") or "", row, context)}
    if docs:
        public_evidence["docs"] = docs
    options = []
    for option in row.options or []:
        if not isinstance(option, dict):
            continue
        options.append(
            {
                "id": option.get("id"),
                "label": option.get("label"),
                "number": option.get("number"),
                "explanation": option.get("explanation") or "",
            }
        )
    answer = row.answer if isinstance(row.answer, dict) else {}
    public_answer = {}
    if isinstance(answer.get("optionId"), str) or isinstance(answer.get("option_id"), str):
        public_answer["optionId"] = answer.get("optionId") or answer.get("option_id")
    if isinstance(answer.get("text"), str):
        public_answer["text"] = answer["text"]
    default_label = next(
        (option["label"] for option in options if option["id"] == row.default_option),
        "",
    )
    return {
        "id": row.id,
        "status": row.status,
        "rank": row.rank,
        "importance": str(row.importance),
        "topic": row.topic,
        "title": row.title,
        "body": row.body,
        "evidence": public_evidence,
        "options": options,
        "allowText": "Something else",
        "defaultOption": row.default_option,
        "defaultReason": (
            f"If you skip, Charie uses “{default_label}” without marking it confirmed."
            if default_label
            else ""
        ),
        "answer": public_answer,
        "answeredAt": row.answered_at.isoformat() if row.answered_at else None,
        "affects": row.affects or [],
        "source": row.source,
    }


def _run_for(session: Session):
    """Read-only customer queries for retests, or None without a source."""
    from charie.learner.api.sources import saved_password, saved_source
    from charie.shared.connectors.postgres import PostgresConnector

    source = saved_source(session)
    if source is None:
        return None
    connector = PostgresConnector(
        source.host, source.port, source.database, source.username, saved_password(session)
    )

    def run(sql: str):
        return connector.run_query(sql).rows

    return run


@questions_router.get("/api/questions")
def list_questions(status: str | None = None, session: Session = Depends(get_session)) -> dict:
    """Waiting, answered or skipped questions; every question without a status."""
    if status is not None and status not in STATUSES:
        raise ApiError(400, "bad_status", "Status must be waiting, answered or skipped.")
    query = select(OwnerQuestion).order_by(OwnerQuestion.rank, OwnerQuestion.id)
    if status is not None:
        query = query.where(OwnerQuestion.status == status)
    rows = session.scalars(query).all()
    return {"questions": [_public_question(row) for row in rows]}


@questions_router.post("/api/questions/{question_id}/answer")
def answer_question(
    question_id: int, body: AnswerBody, session: Session = Depends(get_session)
) -> dict:
    """Apply one answer to the draft and retest what it affects."""
    from charie.shared.settings import get_setting

    try:
        summary = apply_answer(
            session,
            question_id,
            {
                "option_id": body.option_id,
                "text": body.text,
                "previous_option_id": body.previous_option_id,
                "previous_text": body.previous_text,
            },
            _run_for(session),
            get_setting(session, "time_zone") or "UTC",
        )
    except AnswerNotFound as err:
        raise ApiError(404, "not_found", str(err)) from err
    except BadAnswer as err:
        raise ApiError(400, "bad_answer", str(err)) from err
    except AnswerConflict as err:
        raise ApiError(409, "already_answered", str(err)) from err
    session.commit()
    return {"ok": True, "question": {"id": summary["id"], "status": summary["status"]}}


@questions_router.post("/api/questions/{question_id}/skip")
def skip_question(question_id: int, session: Session = Depends(get_session)) -> dict:
    """Skip a waiting question; its default stays unconfirmed."""
    row = session.scalar(
        select(OwnerQuestion).where(OwnerQuestion.id == question_id).with_for_update()
    )
    if row is None:
        raise ApiError(404, "not_found", "That question is gone.")
    if row.status == "answered":
        raise ApiError(409, "already_answered", "This question already has an answer.")
    row.status = "skipped"
    session.commit()
    return {"ok": True}
