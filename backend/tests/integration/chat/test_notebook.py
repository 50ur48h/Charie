"""The notebook: labels, saving, replacing, loading, short view (P10.5)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from charie.chat.analyst.notebook import (
    FindingValue,
    Notebook,
    NotebookError,
    NotebookItem,
    NumberValue,
    PeriodValue,
    QuoteValue,
    TableColumn,
    TableValue,
)
from charie.shared.tables.chat import Chat, Message

DASH = "–"


def _message(db_session) -> Message:
    chat = Chat(title="New chat")
    db_session.add(chat)
    db_session.flush()
    message = Message(
        chat_id=chat.id,
        role="assistant",
        text_="",
        status="thinking",
        started_at=datetime.now(UTC),
    )
    db_session.add(message)
    db_session.commit()
    return message


def _number(value="1420000.00", unit="money", currency="USD", style="value") -> NumberValue:
    return NumberValue(value=value, unit=unit, currency=currency, style=style)


def _table(rows_total=60, rows=None) -> TableValue:
    columns = [
        TableColumn(key="restaurant", label="Restaurant"),
        TableColumn(key="net_sales", label="Net sales", unit="money", currency="USD"),
    ]
    if rows is None:
        rows = [[f"Place {n}", str(n * 1000)] for n in range(1, rows_total + 1)]
    return TableValue(columns=columns, rows=rows, rows_total=rows_total, sql="SELECT 1")


def _period() -> PeriodValue:
    return PeriodValue(
        start="2025-12-01",
        end="2025-12-31",
        text=f"1{DASH}31 Dec 2025",
        partial=False,
        expression="month 2025-12",
    )


def _quote() -> QuoteValue:
    return QuoteValue(
        text="Net sales are order totals minus discounts.",
        document_id=1,
        document="Finance definitions 2025.docx",
        section_id=2,
        heading_path="Net sales",
        location="page 1",
    )


def _finding() -> FindingValue:
    return FindingValue(type="failed", text="Couldn't get orders by hour: the query took too long.")


def test_value_shapes() -> None:
    """Each value model takes the 05 shape and refuses a missing field."""
    _number()
    _table()
    _period()
    _quote()
    _finding()
    with pytest.raises(ValidationError):
        NumberValue(unit="money")
    with pytest.raises(ValidationError):
        TableValue(columns=[], rows=[], rows_total=0)
    with pytest.raises(ValidationError):
        PeriodValue(start="2025-12-01", end="2025-12-31", text="December", partial=False)
    with pytest.raises(ValidationError):
        QuoteValue(document_id=1)
    with pytest.raises(ValidationError):
        FindingValue(text="no type")


def test_labels_count_up_per_kind(db_session) -> None:
    """n1, n2, t1, p1, q1, n3 in the order added."""
    message = _message(db_session)
    book = Notebook(db_session, message.id, message.chat_id)
    first = book.add_number("First", _number())
    second = book.add_number("Second", _number())
    table = book.add_table("Table", _table())
    period = book.add_period("December 2025", _period())
    quote = book.add_quote("Definition", _quote())
    third = book.add_number("Third", _number())
    assert [item.label for item in (first, second, table, period, quote, third)] == [
        "n1",
        "n2",
        "t1",
        "p1",
        "q1",
        "n3",
    ]


def test_items_saved_with_round_and_seq(db_session) -> None:
    """Round and order are stored on every card."""
    message = _message(db_session)
    book = Notebook(db_session, message.id, message.chat_id, round=2)
    first = book.add_number("First", _number())
    second = book.add_number("Second", _number())
    assert (first.round, first.seq) == (2, 1)
    assert (second.round, second.seq) == (2, 2)
    assert [item.seq for item in book.items()] == [1, 2]


def test_findings_have_no_label(db_session) -> None:
    """Findings share the empty label, even two of them."""
    message = _message(db_session)
    book = Notebook(db_session, message.id, message.chat_id)
    first = book.add_finding("First failure", _finding())
    second = book.add_finding("Second failure", _finding())
    assert first.label == "" and second.label == ""
    assert len(book.items()) == 2


def test_replace_marks_old_item(db_session) -> None:
    """Replacing keeps the old card, marked, and hides it by default."""
    message = _message(db_session)
    book = Notebook(db_session, message.id, message.chat_id)
    book.add_number("First", _number())
    book.add_number("Second", _number())
    book.replace("n1", "n2", "the first query left out refunds")
    old = book.get("n1")
    assert old.status == "replaced"
    assert old.replaced_by == "n2"
    assert old.replace_reason == "the first query left out refunds"
    assert [item.label for item in book.items()] == ["n2"]
    assert [item.label for item in book.items(status="replaced")] == ["n1"]


def test_replace_unknown_label_fails(db_session) -> None:
    """Replacing a missing label names it exactly."""
    message = _message(db_session)
    book = Notebook(db_session, message.id, message.chat_id)
    with pytest.raises(NotebookError, match="There's no item n9 in this notebook."):
        book.replace("n9", "n1", "reason")


def test_replace_twice_fails(db_session) -> None:
    """Replacing twice names the label exactly."""
    message = _message(db_session)
    book = Notebook(db_session, message.id, message.chat_id)
    book.add_number("First", _number())
    book.add_number("Second", _number())
    book.replace("n1", "n2", "reason")
    with pytest.raises(NotebookError, match="n1 was already replaced."):
        book.replace("n1", "n2", "reason")


def test_table_keeps_500_rows(db_session) -> None:
    """700 rows in, 500 kept, rows_total stays 700."""
    message = _message(db_session)
    book = Notebook(db_session, message.id, message.chat_id)
    item = book.add_table("Big", _table(rows_total=700))
    assert len(item.value["rows"]) == 500
    assert item.value["rows_total"] == 700


def test_load_continues_labels(db_session) -> None:
    """After load, the next number is the next label and order continues."""
    message = _message(db_session)
    book = Notebook(db_session, message.id, message.chat_id)
    book.add_number("First", _number())
    book.add_table("Table", _table(rows_total=2))
    loaded = Notebook.load(db_session, message.id, message.chat_id)
    third = loaded.add_number("Third", _number())
    assert third.label == "n2"
    assert third.seq == 3
    assert [item.label for item in loaded.items()] == ["n1", "t1", "n2"]


def test_mark_shown_sets_proof_flag(db_session) -> None:
    """Shown labels carry proof.shown; the rest don't."""
    message = _message(db_session)
    book = Notebook(db_session, message.id, message.chat_id)
    book.add_number("First", _number())
    book.add_number("Second", _number(), proof={"fact_key": {"metric": "x"}})
    book.mark_shown(["n2"])
    assert book.get("n2").proof["shown"] is True
    assert book.get("n2").proof["fact_key"] == {"metric": "x"}
    assert "shown" not in book.get("n1").proof


def test_short_view_format(db_session) -> None:
    """Exactly the plan's lines for a sample notebook."""
    message = _message(db_session)
    book = Notebook(db_session, message.id, message.chat_id)
    rows = [[f"Place {n}", str(n * 1000)] for n in range(1, 61)]
    book.add_period("December 2025", _period())
    book.add_number(f"Net sales, 1{DASH}31 Dec 2025", _number())
    book.add_table(f"Net sales by restaurant, 1{DASH}31 Dec 2025", _table(rows_total=60, rows=rows))
    book.add_quote("Definition", _quote())
    book.add_finding("Hourly orders", _finding())
    book.add_number("Second number", _number())
    book.add_number("Third number", _number())
    book.add_number("Net sales fixed", _number())
    book.replace("n1", "n4", "the first query left out refunds")
    view = Notebook.load(db_session, message.id, message.chat_id).short_view()
    first_rows = "\n".join(f"Place {n}, ${n}K" for n in range(1, 21))
    assert view == (
        f"p1 = 1{DASH}31 Dec 2025 (December 2025)\n"
        f"n1 = replaced by n4: the first query left out refunds\n"
        f"t1 = table, 60 rows: Net sales by restaurant, 1{DASH}31 Dec 2025 "
        f"(columns: Restaurant, Net sales)\n"
        f"{first_rows}\n"
        f"… and 40 more rows\n"
        f'q1 = "Net sales are order totals minus discounts." '
        f"(Finance definitions 2025.docx, page 1)\n"
        f"finding (failed): Couldn't get orders by hour: the query took too long.\n"
        f"n2 = $1.42M: Second number\n"
        f"n3 = $1.42M: Third number\n"
        f"n4 = $1.42M: Net sales fixed"
    )


def test_cards_read_back(db_session) -> None:
    """Saved cards read back with every field."""
    message = _message(db_session)
    book = Notebook(db_session, message.id, message.chat_id)
    book.add_number("First", _number(), proof={"fact_key": {"metric": "x"}})
    card = book.get("n1")
    assert isinstance(card, NotebookItem)
    assert (card.kind, card.status, card.round, card.seq) == ("number", "ok", 0, 1)
    assert card.proof == {"fact_key": {"metric": "x"}}
    with pytest.raises(NotebookError, match="There's no item n9 in this notebook."):
        book.get("n9")
