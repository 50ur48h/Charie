"""The thinking log and the live message feed (P10.1, P10.2, P10.13)."""

import asyncio
import re
import threading
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from charie.shared.db import session_scope
from charie.shared.tables.chat import ThinkingEvent

_VALID_KINDS = ("step", "found", "query", "document", "decision", "check", "note")
_VALID_STATUSES = ("running", "done", "failed")

# Seconds a finished feed stays before the stream rebuilds from the database.
FEED_KEEP_SECONDS = 60


@dataclass
class StreamEvent:
    """One stream event: a running id, the name, and JSON-ready data."""

    id: int
    event: str
    data: dict


class MessageFeed:
    """Live events for one running answer, then closed (P10.2).

    The producer adds saved events; followers replay what they missed
    and wait for the rest until the feed closes. Finished feeds stay
    for `FEED_KEEP_SECONDS` so a late reconnect still replays. Data
    tasks run in worker threads, so adding and waking is guarded and
    waiters wake on their own loop.
    """

    def __init__(self) -> None:
        self.events: list[StreamEvent] = []
        self._next_id = 1
        self._closed = False
        self._waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Event]] = []
        self._guard = threading.Lock()

    @property
    def closed(self) -> bool:
        """No more events will come."""
        return self._closed

    def has_done(self) -> bool:
        """A terminal event was already sent."""
        return any(item.event == "done" for item in self.events)

    def _wake(self, waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Event]]) -> None:
        """Wake every follower on its own loop."""
        for loop, waiter in waiters:
            try:
                loop.call_soon_threadsafe(waiter.set)
            except RuntimeError:
                waiter.set()

    def add(self, event: str, data: dict) -> StreamEvent:
        """Save one event and wake every follower."""
        with self._guard:
            item = StreamEvent(self._next_id, event, data)
            self._next_id += 1
            self.events.append(item)
            waiters = list(self._waiters)
        self._wake(waiters)
        return item

    def close(self) -> None:
        """End the feed; followers finish what is left and stop."""
        with self._guard:
            self._closed = True
            waiters = list(self._waiters)
        self._wake(waiters)

    def events_after(self, after_id: int) -> list[StreamEvent]:
        """Stored events with an id above `after_id`."""
        with self._guard:
            return [item for item in self.events if item.id > after_id]

    async def follow(self, after_id: int):
        """Replay what was missed, then wait for the rest until closed."""
        last = after_id
        loop = asyncio.get_running_loop()
        while True:
            for item in self.events_after(last):
                last = item.id
                yield item
            if self._closed:
                return
            waiter = asyncio.Event()
            with self._guard:
                self._waiters.append((loop, waiter))
            try:
                await waiter.wait()
            finally:
                with self._guard:
                    if (loop, waiter) in self._waiters:
                        self._waiters.remove((loop, waiter))


# Live feeds by assistant message id. Only one copy of the chat app
# runs, so memory is enough; the database replays everything older.
FEEDS: dict[int, MessageFeed] = {}


def _schedule_removal(message_id: int) -> None:
    """Forget a finished feed a minute later; the database replays after."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        FEEDS.pop(message_id, None)
        return
    loop.call_later(FEED_KEEP_SECONDS, FEEDS.pop, message_id, None)


def finish_feed(message_id: int, status: str | None = None, cost_usd: float = 0) -> None:
    """Send the terminal event if none went out, close, and schedule removal.

    Every producer ends through here, so a stream ends exactly once:
    after the one `done`. A feed with no live stream simply expires.
    """
    feed = FEEDS.get(message_id)
    if feed is None or feed.closed:
        return
    if status is not None and not feed.has_done():
        feed.add("done", {"message_id": message_id, "status": status, "cost_usd": cost_usd})
    feed.close()
    _schedule_removal(message_id)


def _push_thinking(message_id: int, line: dict) -> None:
    """A saved thinking line also goes out live (P10.2)."""
    feed = FEEDS.get(message_id)
    if feed is not None and not feed.closed:
        feed.add("thinking", line)


#: Longest text delta, in characters. Chunks break at word boundaries,
#: so joining them restores the block's text exactly.
TEXT_DELTA_LIMIT = 120


def block_text(block: dict) -> str:
    """One text block as the saved answer shows it.

    Sentences join with a space inside a paragraph; paragraphs join
    with a blank line, the same shape the screen renders.
    """
    return "\n\n".join(
        " ".join(sentence.get("text", "") for sentence in paragraph.get("sentences", []))
        for paragraph in block.get("paragraphs", [])
    )


def text_deltas(text: str, limit: int = TEXT_DELTA_LIMIT) -> list[str]:
    """Split text into bounded word-preserving chunks.

    Breaks fall only on whitespace, so no word is ever cut in half
    (a single longer word travels whole). Joining the chunks restores
    the text exactly, whitespace included.
    """
    if not text:
        return []
    chunks: list[str] = []
    current = ""
    for token in re.findall(r"\S+|\s+", text):
        if current and len(current) + len(token) > limit and token.strip():
            chunks.append(current)
            current = ""
        current += token
    if current:
        chunks.append(current)
    return chunks


def stream_answer(message_id: int, blocks: list[dict], summary: dict) -> None:
    """The final checked answer through the live stream (P10.13).

    Only the saved blocks go out: text blocks arrive empty, then fill
    with bounded word-preserving deltas; every other block arrives
    whole. Emits synchronously, with no timers slowing delivery.
    """
    feed = FEEDS.get(message_id)
    if feed is None or feed.closed:
        return
    feed.add("summary", summary)
    for index, block in enumerate(blocks):
        if block.get("type") == "text":
            feed.add("block", {"index": index, "block": {"type": "text", "paragraphs": []}})
            for delta in text_deltas(block_text(block)):
                feed.add("text", {"index": index, "delta": delta})
        else:
            feed.add("block", {"index": index, "block": block})


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
    ) -> tuple[int, dict]:
        seq = self._next_seq(session)
        row = ThinkingEvent(
            message_id=self.message_id,
            seq=seq,
            kind=kind,
            status=status,
            title=title,
            body=body,
            details=details or {},
        )
        session.add(row)
        session.commit()
        return seq, self._line_shape(row)

    def _run(
        self,
        kind: str,
        title: str,
        body: str = "",
        details: dict | None = None,
        status: str = "done",
    ) -> int:
        with session_scope() as session:
            seq, line = self._save(session, kind, title, body, details, status)
        _push_thinking(self.message_id, line)
        return seq

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
            shape = self._line_shape(line)
        _push_thinking(self.message_id, shape)

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

    @staticmethod
    def _line_shape(row: ThinkingEvent) -> dict:
        """One saved line as the screen and the stream read it."""
        return {
            "seq": row.seq,
            "kind": row.kind,
            "status": row.status,
            "title": row.title,
            "body": row.body,
            "details": row.details,
            "at": row.at.isoformat() if row.at is not None else None,
        }

    def lines(self) -> list[dict]:
        """Every saved line, in `seq` order (for the screen and the stream)."""
        with session_scope() as session:
            rows = session.scalars(
                select(ThinkingEvent)
                .where(ThinkingEvent.message_id == self.message_id)
                .order_by(ThinkingEvent.seq)
            ).all()
            return [self._line_shape(row) for row in rows]
