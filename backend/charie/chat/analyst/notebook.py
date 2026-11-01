"""The notebook: every finding for one question, each with a label (P10.5).

Code writes every item; the AI never types numbers. Nothing is thrown
away: a wrong item is marked replaced, with the reason. Prompts get the
short view.
"""

import contextlib
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from charie.shared.tables.chat import NotebookItem as NotebookRow
from charie.shared.text.numbers import (
    format_change,
    format_count,
    format_money,
    format_percent,
    format_ratio,
)

#: At most this many table rows are kept; `rows_total` keeps the real count.
MAX_TABLE_ROWS = 500

#: One line per kind, in the order items are added.
KIND_LETTERS = {"number": "n", "table": "t", "period": "p", "quote": "q"}

FindingType = Literal[
    "failed", "disagreement", "couldnt_check", "nothing_found", "dropped_quote", "stopped", "note"
]


class NotebookError(Exception):
    """A notebook mistake, in the owner's words."""


class NumberValue(BaseModel):
    """One number: an exact decimal as text, never a float."""

    value: str = Field(description="The exact decimal value, as text.")
    unit: Literal["money", "count", "percent", "ratio"] = Field(description="What kind of number.")
    currency: str = Field(default="", description="The ISO currency, or empty.")
    style: Literal["value", "change"] = Field(
        default="value", description="A plain value or a change."
    )


class TableColumn(BaseModel):
    """One table column: how to read and format it."""

    key: str = Field(description="The column key in each row.")
    label: str = Field(description="The column name the owner sees.")
    unit: str = Field(default="", description="money, count, percent, ratio, or empty.")
    currency: str = Field(default="", description="The ISO currency, or empty.")
    is_time: bool = Field(default=False, description="True for a time column.")


class TableValue(BaseModel):
    """One table: columns, up to 500 rows, and the real row count."""

    columns: list[TableColumn] = Field(description="The columns, in order.")
    rows: list[list] = Field(description="One value list per row, in column order.")
    rows_total: int = Field(description="The real row count, before trimming.")
    sql: str = Field(description="The query that produced the rows.")


class PeriodValue(BaseModel):
    """One resolved period, as the notebook remembers it."""

    start: str = Field(description="The first day, YYYY-MM-DD.")
    end: str = Field(description="The last day, YYYY-MM-DD.")
    text: str = Field(description="The period in the owner's words.")
    partial: bool = Field(description="True when the data ends mid-period.")
    expression: str = Field(description="The period expression, like month 2025-12.")


class QuoteValue(BaseModel):
    """One exact quote from a document."""

    text: str = Field(description="The exact quoted words.")
    document_id: int = Field(description="The document row id.")
    document: str = Field(default="", description="The file name.")
    section_id: int = Field(default=0, description="The section row id.")
    heading_path: str = Field(default="", description="Where in the document.")
    location: str = Field(default="", description="The page or position.")


class FindingValue(BaseModel):
    """A failure, disagreement or note for the next round: no label."""

    type: FindingType = Field(description="What kind of finding this is.")
    text: str = Field(description="The finding in plain words.")
    task: str = Field(default="", description="The task it came from, or empty.")


class NotebookItem(BaseModel):
    """One notebook card, as the analyst passes it around."""

    label: str = Field(description="n1, t1, p1, q1, or empty for findings.")
    kind: Literal["number", "table", "period", "quote", "finding"] = Field(
        description="What kind of card."
    )
    description: str = Field(description="What the card is, in the owner's words.")
    value: dict = Field(description="One of the value shapes above.")
    status: Literal["ok", "replaced"] = Field(default="ok", description="ok or replaced.")
    replaced_by: str = Field(default="", description="The new label, or empty.")
    replace_reason: str = Field(default="", description="Why it was replaced, or empty.")
    round: int = Field(default=0, description="The round that added it.")
    seq: int = Field(default=0, description="The order it was added in.")
    proof: dict = Field(default={}, description="Where the value came from.")


def _format_number(value: NumberValue) -> str:
    """The short prompt format for one number value."""
    if value.style == "change":
        return format_change(value.value, value.unit, value.currency or "USD")
    if value.unit == "money":
        return format_money(value.value, value.currency or "USD")
    if value.unit == "count":
        return format_count(value.value)
    if value.unit == "percent":
        return format_percent(value.value)
    return format_ratio(value.value)


def _format_cell(column: TableColumn, raw) -> str:
    """One table cell in the owner's format."""
    if raw is None:
        return ""
    if column.unit == "money":
        return format_money(str(raw), column.currency or "USD")
    if column.unit == "count":
        return format_count(str(raw))
    if column.unit == "percent":
        return format_percent(str(raw))
    if column.unit == "ratio":
        return format_ratio(str(raw))
    return str(raw)


class Notebook:
    """One question's notebook, saved as it grows."""

    def __init__(self, session: Session, message_id: int, chat_id: int, round: int = 0) -> None:
        self._session = session
        self.message_id = message_id
        self.chat_id = chat_id
        self.round = round
        self._counters = {letter: 0 for letter in "ntpq"}
        self._seq = 0
        self._init_counters()

    def _init_counters(self) -> None:
        """Continue labels and order from the saved rows, if any."""
        rows = self._session.scalars(
            select(NotebookRow)
            .where(NotebookRow.message_id == self.message_id)
            .order_by(NotebookRow.seq)
        ).all()
        for row in rows:
            if len(row.label) == 2 and row.label[0] in self._counters:
                with contextlib.suppress(ValueError):
                    self._counters[row.label[0]] = max(
                        self._counters[row.label[0]], int(row.label[1:])
                    )
            self._seq = max(self._seq, row.seq)
            self.round = max(self.round, row.round)

    @classmethod
    def load(cls, session: Session, message_id: int, chat_id: int) -> "Notebook":
        """Read a saved notebook back; labels and order continue."""
        return cls(session, message_id, chat_id)

    def _next_label(self, kind: str) -> str:
        """The next label for a kind; findings get none."""
        if kind == "finding":
            return ""
        letter = KIND_LETTERS[kind]
        self._counters[letter] += 1
        return f"{letter}{self._counters[letter]}"

    def _save(
        self, kind: str, description: str, value: BaseModel, proof: dict | None
    ) -> NotebookItem:
        """Save one card now and return it."""
        self._seq += 1
        label = self._next_label(kind)
        row = NotebookRow(
            message_id=self.message_id,
            chat_id=self.chat_id,
            seq=self._seq,
            round=self.round,
            label=label,
            kind=kind,
            description=description,
            value=value.model_dump(),
            status="ok",
            proof=proof or {},
        )
        self._session.add(row)
        self._session.commit()
        return self._read(row)

    @staticmethod
    def _read(row: NotebookRow) -> NotebookItem:
        """One saved row as a card."""
        return NotebookItem(
            label=row.label,
            kind=row.kind,
            description=row.description,
            value=row.value,
            status=row.status,
            replaced_by=row.replaced_by or "",
            replace_reason=row.replace_reason or "",
            round=row.round,
            seq=row.seq,
            proof=row.proof,
        )

    def add_number(
        self, description: str, value: NumberValue, proof: dict | None = None
    ) -> NotebookItem:
        """Save one labelled number."""
        return self._save("number", description, value, proof)

    def add_table(
        self, description: str, value: TableValue, proof: dict | None = None
    ) -> NotebookItem:
        """Save one labelled table, keeping at most 500 rows."""
        trimmed = TableValue(
            columns=value.columns,
            rows=value.rows[:MAX_TABLE_ROWS],
            rows_total=value.rows_total,
            sql=value.sql,
        )
        return self._save("table", description, trimmed, proof)

    def add_period(
        self, description: str, value: PeriodValue, proof: dict | None = None
    ) -> NotebookItem:
        """Save one labelled period."""
        return self._save("period", description, value, proof)

    def add_quote(
        self, description: str, value: QuoteValue, proof: dict | None = None
    ) -> NotebookItem:
        """Save one labelled quote."""
        return self._save("quote", description, value, proof)

    def add_finding(
        self, description: str, value: FindingValue, proof: dict | None = None
    ) -> NotebookItem:
        """Save one finding; it gets no label."""
        return self._save("finding", description, value, proof)

    def get(self, label: str) -> NotebookItem:
        """One card by label, or an error that names it."""
        row = self._session.scalar(
            select(NotebookRow).where(
                NotebookRow.message_id == self.message_id, NotebookRow.label == label
            )
        )
        if row is None:
            raise NotebookError(f"There's no item {label} in this notebook.")
        return self._read(row)

    def items(self, status: str = "ok") -> list[NotebookItem]:
        """The cards in the order added, leaving replaced ones out by default."""
        rows = self._session.scalars(
            select(NotebookRow)
            .where(NotebookRow.message_id == self.message_id, NotebookRow.status == status)
            .order_by(NotebookRow.seq)
        ).all()
        return [self._read(row) for row in rows]

    def replace(self, old_label: str, new_label: str, reason: str) -> None:
        """Mark one card replaced by another; nothing is ever deleted."""
        row = self._session.scalar(
            select(NotebookRow).where(
                NotebookRow.message_id == self.message_id, NotebookRow.label == old_label
            )
        )
        if row is None:
            raise NotebookError(f"There's no item {old_label} in this notebook.")
        if row.status == "replaced":
            raise NotebookError(f"{old_label} was already replaced.")
        row.status = "replaced"
        row.replaced_by = new_label
        row.replace_reason = reason
        self._session.commit()

    def mark_shown(self, labels: list[str]) -> None:
        """Remember that the final answer showed these labels."""
        for label in labels:
            row = self._session.scalar(
                select(NotebookRow).where(
                    NotebookRow.message_id == self.message_id, NotebookRow.label == label
                )
            )
            if row is not None:
                row.proof = {**(row.proof or {}), "shown": True}
        self._session.commit()

    def _short_number(self, item: NotebookItem) -> str:
        """`n1 = $1.42M: Net sales, 1–31 Dec 2025`."""
        value = NumberValue.model_validate(item.value)
        return f"{item.label} = {_format_number(value)}: {item.description}"

    def _short_table(self, item: NotebookItem) -> list[str]:
        """The table line, then up to 20 rows, then the overflow line."""
        value = TableValue.model_validate(item.value)
        names = ", ".join(column.label for column in value.columns)
        lines = [
            f"{item.label} = table, {value.rows_total} rows: {item.description} (columns: {names})"
        ]
        for row in value.rows[:20]:
            cells = [
                _format_cell(column, raw) for column, raw in zip(value.columns, row, strict=False)
            ]
            lines.append(", ".join(cells))
        if value.rows_total > len(value.rows[:20]):
            lines.append(f"\u2026 and {value.rows_total - 20} more rows")
        return lines

    def _short_period(self, item: NotebookItem) -> str:
        """`p1 = 1–31 Dec 2025 (December 2025)`."""
        value = PeriodValue.model_validate(item.value)
        return f"{item.label} = {value.text} ({item.description})"

    def _short_quote(self, item: NotebookItem) -> str:
        """`q1 = "..." (file, page 1)`."""
        value = QuoteValue.model_validate(item.value)
        where = value.document
        if value.location:
            where += f", {value.location}"
        return f'{item.label} = "{value.text}" ({where})'

    def _short_finding(self, item: NotebookItem) -> str:
        """`finding (failed): ...`."""
        value = FindingValue.model_validate(item.value)
        return f"finding ({value.type}): {value.text}"

    def short_view(self) -> str:
        """The prompt's view: one line per card, in the order added."""
        lines: list[str] = []
        cards = sorted(
            self.items(status="ok") + self.items(status="replaced"), key=lambda card: card.seq
        )
        for item in cards:
            if item.status == "replaced":
                lines.append(
                    f"{item.label} = replaced by {item.replaced_by}: {item.replace_reason}"
                )
            elif item.kind == "number":
                lines.append(self._short_number(item))
            elif item.kind == "table":
                lines.extend(self._short_table(item))
            elif item.kind == "period":
                lines.append(self._short_period(item))
            elif item.kind == "quote":
                lines.append(self._short_quote(item))
            else:
                lines.append(self._short_finding(item))
        return "\n".join(lines)
