"""The thinking log: one saved line per thinking-panel row (P10.1)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from charie.shared.db import session_scope
from charie.shared.tables.chat import ThinkingEvent

_VALID_KINDS = ("step", "found", "query", "document", "decision", "check", "note")
_VALID_STATUSES = ("running", "done", "failed")


class ThinkingLog:
    """Append-only thinking lines for one assistant message.

    Every save is its own short transaction, so a reopened chat shows
    each line at once. `seq` counts up from 1 per message.
    """

    def __init__(self, message_id: int) -> None:
        self.message_id = message_id

    def _next_seq(self, session: Session) -> int:
        top = session.scalar(
            select(func.max(ThinkingEvent.seq)).where(ThinkingEvent.message_id == self.message_id)
        )
        return (top or 0) + 1

    def _save(
        self,
        session: Session,
        kind: str,
        title: str,
        body: str = "",
        details: dict | None = None,
        status: str = "done",
    ) -> int:
        seq = self._next_seq(session)
        session.add(
            ThinkingEvent(
                message_id=self.message_id,
                seq=seq,
                kind=kind,
                status=status,
                title=title,
                body=body,
                details=details or {},
            )
        )
        session.commit()
        return seq

    def _run(
        self,
        kind: str,
        title: str,
        body: str = "",
        details: dict | None = None,
        status: str = "done",
    ) -> int:
        with session_scope() as session:
            return self._save(session, kind, title, body, details, status)

    def start(self, kind: str, title: str, body: str = "", details: dict | None = None) -> int:
        """Open a running line; the caller finishes it later."""
        assert kind in _VALID_KINDS, f"unknown thinking kind: {kind}"
        return self._run(kind, title, body, details, "running")

    def finish(
        self,
        seq: int,
        status: str = "done",
        title: str | None = None,
        body: str | None = None,
        details: dict | None = None,
    ) -> None:
        """Close a running line. Only its status, words and details change."""
        assert status in _VALID_STATUSES, f"unknown thinking status: {status}"
        with session_scope() as session:
            line = session.scalar(
                select(ThinkingEvent).where(
                    ThinkingEvent.message_id == self.message_id,
                    ThinkingEvent.seq == seq,
                )
            )
            assert line is not None, f"no thinking line {seq}"
            line.status = status
            if title is not None:
                line.title = title
            if body is not None:
                line.body = body
            if details is not None:
                line.details = details
            session.commit()

    def add(
        self,
        kind: str,
        title: str,
        body: str = "",
        details: dict | None = None,
        status: str = "done",
    ) -> int:
        """Save one finished line."""
        assert kind in _VALID_KINDS, f"unknown thinking kind: {kind}"
        assert status in _VALID_STATUSES, f"unknown thinking status: {status}"
        return self._run(kind, title, body, details, status)

    def lines(self) -> list[dict]:
        """Every saved line, in `seq` order (for the screen and the stream)."""
        with session_scope() as session:
            rows = session.scalars(
                select(ThinkingEvent)
                .where(ThinkingEvent.message_id == self.message_id)
                .order_by(ThinkingEvent.seq)
            ).all()
            return [
                {
                    "seq": row.seq,
                    "kind": row.kind,
                    "status": row.status,
                    "title": row.title,
                    "body": row.body,
                    "details": row.details,
                    "at": row.at.isoformat() if row.at is not None else None,
                }
                for row in rows
            ]
