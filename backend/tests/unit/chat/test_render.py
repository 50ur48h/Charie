"""The answer builders on in-memory notebook items (P10.10)."""

from charie.chat.analyst.labels import fill_labels
from charie.chat.analyst.notebook import (
    NotebookItem,
    NumberValue,
    PeriodValue,
    QuoteValue,
    TableColumn,
    TableValue,
)
from charie.chat.analyst.render import (
    VAGUE_KINDS,
    chart_block,
    code_notes,
    follow_ups_block,
    kpi_block,
    method_block,
    reading_block,
    table_block,
    text_block,
    values_for,
)
from charie.chat.analyst.write import DraftChart, DraftKpi, DraftSentence, DraftTable


def _number(label, value, unit="money", description="Net sales", proof=None, **over):
    return NotebookItem(
        label=label,
        kind="number",
        description=description,
        value=NumberValue(value=value, unit=unit).model_dump(),
        proof=proof or {},
        **over,
    )


def _period(label, start, end, text):
    return NotebookItem(
        label=label,
        kind="period",
        description=text,
        value=PeriodValue(
            start=start, end=end, text=text, partial=False, expression="month 2025-12"
        ).model_dump(),
    )


def _table(label, rows, total, columns=None, description="Sales by restaurant"):
    columns = columns or [
        TableColumn(key="restaurant", label="Restaurant"),
        TableColumn(key="change", label="Change", unit="percent"),
    ]
    return NotebookItem(
        label=label,
        kind="table",
        description=description,
        value=TableValue(columns=columns, rows=rows, rows_total=total, sql="SELECT 1").model_dump(),
    )


def test_fill_number_short_and_full() -> None:
    """Money fills short ($1.35M) or full ($1,354,004.63) by the setting."""
    item = _number("n1", "1354004.63")
    assert values_for([item], "short")["n1"] == "$1.35M"
    assert values_for([item], "full")["n1"] == "$1,354,005"
    assert values_for([_number("n2", "5", unit="count")], "short")["n2"] == "5"


def test_fill_period_and_quote() -> None:
    """Periods fill with their text; quotes come with document and place."""
    items = [
        _period("p1", "2025-12-01", "2025-12-31", "1–31 Dec 2025"),
        NotebookItem(
            label="q1",
            kind="quote",
            description="Freshness note",
            value=QuoteValue(
                text="fresh daily",
                document_id=1,
                document="notes/inbox",
                section_id=2,
                heading_path="",
                location="page 2",
            ).model_dump(),
        ),
    ]
    values = values_for(items, "short")
    assert fill_labels("In [p1] she said [q1].", values) == (
        "In 1–31 Dec 2025 she said \u201cfresh daily\u201d (notes/inbox, page 2)."
    )


def test_text_paragraphs() -> None:
    """Sentences group into paragraphs at starts_paragraph."""
    sentences = [
        DraftSentence(kind="fact", text="Sales were [n1].", proof=["n1"], starts_paragraph=True),
        DraftSentence(kind="fact", text="Orders held.", proof=[], starts_paragraph=False),
        DraftSentence(kind="conclusion", text="A good month.", proof=[], starts_paragraph=True),
    ]
    block = text_block(sentences, {"n1": "$359.00"})
    assert block == {
        "type": "text",
        "paragraphs": [
            {
                "sentences": [
                    {"kind": "fact", "text": "Sales were $359.00."},
                    {"kind": "fact", "text": "Orders held."},
                ]
            },
            {"sentences": [{"kind": "conclusion", "text": "A good month."}]},
        ],
    }


def test_kpi_direction_and_compare() -> None:
    """A falling change points down and names the comparison period."""
    change = NotebookItem(
        label="n2",
        kind="number",
        description="Change in net sales",
        value=NumberValue(value="-18.20", unit="percent", style="change").model_dump(),
        proof={"fact_key": {"compare_period": "2025-11-01/2025-11-30"}},
    )
    cards = {
        "n1": _number("n1", "359.00"),
        "n2": change,
        "p1": _period("p1", "2025-12-01", "2025-12-31", "1–31 Dec 2025"),
        "p2": _period("p2", "2025-11-01", "2025-11-30", "1–30 Nov 2025"),
    }
    values = values_for(list(cards.values()), "short")
    block = kpi_block([DraftKpi(title="Net sales", value="n1", change="n2")], cards, values)
    assert block["items"] == [
        {
            "label": "Net sales",
            "value": "$359.00",
            "change": values["n2"],
            "direction": "down",
            "compare": "vs 1–30 Nov 2025",
        }
    ]


def test_chart_sorted_by_value() -> None:
    """Bars run largest first, with the unit and the highlight kept."""
    card = _table("t1", [["Uptown", "6.2"], ["Downtown", "-18.2"]], 2)
    draft = DraftChart(
        kind="bar",
        title="Sales [p1]",
        table="t1",
        x="restaurant",
        y="change",
        highlight=["Downtown", "Nowhere"],
    )
    block = chart_block(draft, {"t1": card}, {"p1": "1–31 Dec 2025"}, "short")
    assert block["title"] == "Sales 1–31 Dec 2025"
    assert [row[0] for row in block["data"]["rows"]] == ["Uptown", "Downtown"]
    assert block["data"]["rows"][0][1]["v"] == 6.2
    assert block["highlight"] == ["Downtown"]
    assert block["unit"] == "percent"


def test_chart_time_kept_in_order() -> None:
    """A time x keeps the table's order, even when values fall."""
    columns = [
        TableColumn(key="month", label="Month", is_time=True),
        TableColumn(key="sales", label="Sales", unit="money", currency="USD"),
    ]
    card = _table(
        "t1",
        [["2025-11-01", "100"], ["2025-12-01", "50"]],
        2,
        columns=columns,
        description="Sales by month",
    )
    draft = DraftChart(kind="line", title="Sales", table="t1", x="month", y="sales")
    block = chart_block(draft, {"t1": card}, {}, "short")
    assert [row[0] for row in block["data"]["rows"]] == ["2025-11-01", "2025-12-01"]
    assert block["data"]["rows"][0][1] == {"v": 100.0, "f": "$100.00"}


def test_31_bars_become_29_plus_others() -> None:
    """Over 30 bars the top 29 stay and the rest sum into Others."""
    rows = [[f"r{number}", str(number)] for number in range(1, 32)]
    card = _table("t1", rows, 31)
    draft = DraftChart(kind="bar", title="Sales", table="t1", x="restaurant", y="change")
    block = chart_block(draft, {"t1": card}, {}, "short")
    data = block["data"]["rows"]
    assert len(data) == 30
    assert [row[0] for row in data[:3]] == ["r31", "r30", "r29"]
    assert data[-1][0] == "Others"
    assert data[-1][1]["v"] == 3.0


def test_table_first_100_rows() -> None:
    """Past 100 rows the table stops and the title says how many."""
    columns = [
        TableColumn(key="name", label="Restaurant"),
        TableColumn(key="sales", label="Sales", unit="money", currency="USD"),
    ]
    rows = [[f"r{number}", str(number)] for number in range(1, 106)]
    card = _table("t1", rows, 105, columns=columns)
    draft = DraftTable(title="Top restaurants", table="t1", columns=["name", "sales"])
    block = table_block(draft, {"t1": card}, {}, "short")
    assert len(block["rows"]) == 100
    assert block["title"] == "Top restaurants (first 100 of 105 rows)"
    assert block["columns"] == [
        {"key": "name", "label": "Restaurant"},
        {"key": "sales", "label": "Sales", "unit": "money"},
    ]
    assert block["rows"][0] == {"name": "r1", "sales": {"v": 1.0, "f": "$1.00"}}


def test_reading_always_shown_for_vague() -> None:
    """The reading shows on request; vague questions always request it."""
    assert reading_block("I read this as sales.", True) == {
        "type": "reading",
        "text": "I read this as sales.",
    }
    assert reading_block("I read this as sales.", False) is None
    assert reading_block("", True) is None
    assert VAGUE_KINDS == ("vague_with_default", "vague_no_default", "two_meanings")


def test_note_words() -> None:
    """Anchor, periods, defaults, corrections, new measures and unknowns."""
    old = _number("n1", "18.00", status="replaced")
    old.replaced_by = "n2"
    old.replace_reason = "a better query"
    new = _number("n2", "19.00", description="Net sales")
    values = {"n1": "$18.00", "n2": "$19.00"}
    notes = code_notes(
        anchor="The data only goes up to 31 Dec 2025.",
        period_notes=["December has data up to the 18th only."],
        default_titles=["Net sales"],
        corrections=[(old, new)],
        new_measures=[_number("n3", "7.00", description="Order tips")],
        stop_reason="rounds_done",
        still_open=["Why Downtown fell"],
        values=values,
    )
    assert [note["text"] for note in notes] == [
        "The data only goes up to 31 Dec 2025.",
        "December has data up to the 18th only.",
        'I used the default meaning of "Net sales". You can change it in Questions for you.',
        "Correction: I first found $18.00 for Net sales, but a better query. "
        "This answer uses $19.00.",
        '"Order tips" isn\'t a standard measure yet. I worked it out two ways and both agree. '
        "I've asked the Learner to add it to the knowledge base.",
        "Still unknown: Why Downtown fell.",
    ]
    assert all(note["tone"] == "note" for note in notes)


def test_method_lists_queries_and_sources() -> None:
    """Definitions, steps, queries and sources pass through exactly."""
    block = method_block(
        definitions=["Net sales: what the shop kept."],
        steps=["Round 1 done: the question is answered.", "The rounds answered the question."],
        queries=[{"purpose": "Get net sales.", "sql": "SELECT 1"}],
        sources=[{"document": "notes", "quote": "fresh daily", "location": "page 1"}],
    )
    assert block == {
        "type": "method",
        "definitions": ["Net sales: what the shop kept."],
        "steps": ["Round 1 done: the question is answered.", "The rounds answered the question."],
        "queries": [{"purpose": "Get net sales.", "sql": "SELECT 1"}],
        "sources": [{"document": "notes", "quote": "fresh daily", "location": "page 1"}],
    }


def test_follow_up_rules() -> None:
    """The first 3 applying questions stay, in order; one is no block."""
    block = follow_ups_block(
        drop="Downtown",
        rise=None,
        last_year_used=False,
        first_period="1–31 Dec 2025",
        unsplit=("Net sales", "Restaurant"),
    )
    assert block == {
        "type": "follow_ups",
        "items": [
            "Why did Downtown drop?",
            "How does 1–31 Dec 2025 compare with the same time last year?",
            "Show Net sales by Restaurant for 1–31 Dec 2025.",
        ],
    }
    assert (
        follow_ups_block(
            drop="Downtown",
            rise=None,
            last_year_used=True,
            first_period="1–31 Dec 2025",
            unsplit=None,
        )
        is None
    )
