"""Answer blocks: the draft filled and rendered, plus the code-built blocks (P10.10).

The AI writes labels only; code fills every label, renders the 09 blocks
in order (reading, warns, the AI's blocks, notes, method, follow-ups),
and reports which labels the answer showed.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from sqlalchemy import select

from charie.chat.analyst.kb_view import KbView
from charie.chat.analyst.labels import fill_labels, labels_in, mixed_tokens, stray_digits
from charie.chat.analyst.loop import MAX_ROUNDS
from charie.chat.analyst.notebook import (
    Notebook,
    NotebookError,
    NotebookItem,
    NumberValue,
    PeriodValue,
    QuoteValue,
    TableValue,
    _format_number,
)
from charie.shared.calc.core import ResultTable
from charie.shared.db import session_scope
from charie.shared.settings import get_setting
from charie.shared.tables.chat import QueryRun, ThinkingEvent
from charie.shared.tables.knowledge import KbVersion

#: Columns that carry numbers a chart or spark line can draw.
NUMBER_UNITS = ("money", "count", "percent", "ratio")

#: At most this many bars; the rest become one "Others" bar.
MAX_BARS = 30

#: At most this many table rows; the title names the real count.
MAX_TABLE_ROWS = 100


def ai_texts(draft) -> list[str]:
    """Every AI-written text field the checks and the fill must cover."""
    texts = []
    for block in draft.blocks:
        texts.extend(sentence.text for sentence in block.sentences)
        texts.extend(kpi.title for kpi in block.kpis)
        if block.chart is not None:
            texts.extend([block.chart.title, block.chart.subtitle])
        if block.table is not None:
            texts.append(block.table.title)
        texts.append(block.tree_title)
        texts.extend(node.label for node in block.tree_nodes)
        texts.append(block.callout_text)
        texts.append(block.suggestions_title)
        texts.extend(suggestion.text for suggestion in block.suggestions)
    return texts


def block_refs(draft) -> list[str]:
    """Labels the blocks use without writing them: kpis, charts, tables."""
    refs = []
    for block in draft.blocks:
        refs.extend(kpi.value for kpi in block.kpis)
        refs.extend(kpi.change for kpi in block.kpis)
        refs.extend(kpi.spark for kpi in block.kpis)
        if block.chart is not None and block.chart.table:
            refs.append(block.chart.table)
        if block.table is not None and block.table.table:
            refs.append(block.table.table)
    return [ref for ref in refs if ref]


def used_labels(draft) -> list[str]:
    """Every label the draft writes or uses, in order."""
    seen: list[str] = []
    for text in ai_texts(draft):
        for label in labels_in(text):
            if label not in seen:
                seen.append(label)
    for ref in block_refs(draft):
        if ref not in seen:
            seen.append(ref)
    for block in draft.blocks:
        for sentence in block.sentences:
            for label in sentence.proof:
                if label not in seen:
                    seen.append(label)
    return seen


def values_for(items: list[NotebookItem], style: str) -> dict[str, str]:
    """Every card's fill text; tables fill with their description."""

    values: dict[str, str] = {}
    for item in items:
        if item.kind == "table":
            values[item.label] = item.description
        else:
            filled = Notebook.fill_value(item, style)
            if filled is not None:
                values[item.label] = filled
    return values


def fill_text(text: str, ctx) -> str:
    """Fill one AI text with this question's checked values."""

    with session_scope() as session:
        book = Notebook.load(session, ctx.message_id, ctx.chat_id)
        style = (ctx.settings or {}).get("number_format", "short")
        return fill_labels(text, values_for(book.items(), style))


def check_matches(text: str, view: str) -> bool:
    """A sentence uses only notebook labels and exact-copied numbers.

    Every label must appear in the labelled notebook view. Every other
    digit word must also appear there exactly (so `2025` may repeat a
    period line, but `1.4M` never passes); known mixed words like codes
    are allowed. Whether each card is current is checked separately.
    """

    if any(f"[{label}]" not in view for label in labels_in(text)):
        return False
    return all(token in view for token in stray_digits(text, mixed_tokens(view.splitlines())))


def text_block(sentences: list, values: dict[str, str]) -> dict | None:
    """Sentences grouped into paragraphs at `starts_paragraph`."""
    paragraphs: list[dict] = []
    for sentence in sentences:
        if sentence.starts_paragraph or not paragraphs:
            paragraphs.append({"sentences": []})
        paragraphs[-1]["sentences"].append(
            {"kind": sentence.kind, "text": fill_labels(sentence.text, values)}
        )
    if not paragraphs:
        return None
    return {"type": "text", "paragraphs": paragraphs}


def _dec(raw) -> Decimal | None:
    """One cell as an exact decimal; empty or text stays empty."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, int):
        return Decimal(raw)
    if isinstance(raw, str):
        try:
            return Decimal(raw)
        except InvalidOperation:
            return None
    return None


def _float(raw) -> float | None:
    """One cell as a plain number for the screen, or empty."""
    found = _dec(raw)
    return float(found) if found is not None else None


def kpi_block(kpis: list, cards: dict[str, NotebookItem], values: dict[str, str]) -> dict | None:
    """Number cards with direction and comparison, from the change cards."""
    items = []
    for kpi in kpis:
        if not kpi.value or kpi.value not in values:
            continue
        item: dict = {"label": fill_labels(kpi.title, values), "value": values[kpi.value]}
        change = cards.get(kpi.change) if kpi.change else None
        if change is not None and kpi.change in values:
            item["change"] = values[kpi.change]
            amount = _dec(NumberValue.model_validate(change.value).value)
            if amount is not None:
                item["direction"] = "up" if amount > 0 else "down" if amount < 0 else "flat"
                period = (change.proof or {}).get("fact_key", {}).get("compare_period")
                text = _period_text(cards, period)
                if text:
                    item["compare"] = f"vs {text}"
        spark = cards.get(kpi.spark) if kpi.spark else None
        if spark is not None and spark.kind == "table":
            drawn = spark_block(TableValue.model_validate(spark.value))
            if drawn is not None:
                item["spark"] = drawn
        items.append(item)
    if not items:
        return None
    return {"type": "kpis", "items": items}


def spark_block(table: TableValue) -> dict | None:
    """The first number column as plain values, for a KPI spark line."""
    for column in table.columns:
        if column.unit in NUMBER_UNITS:
            found = [_float(row[table.columns.index(column)]) for row in table.rows]
            return {
                "values": [value for value in found if value is not None],
                "unit": column.unit,
                **({"currency": column.currency} if column.currency else {}),
            }
    return None


def _period_text(cards: dict[str, NotebookItem], period: str | None) -> str:
    """The period card matching one `start/end` range, or empty."""
    if not period or "/" not in period:
        return ""
    start, _, end = period.partition("/")
    for card in cards.values():
        if card.kind != "period":
            continue

        value = PeriodValue.model_validate(card.value)
        if value.start == start and value.end == end:
            return value.text
    return ""


def chart_block(
    chart, cards: dict[str, NotebookItem], values: dict[str, str], style: str
) -> dict | None:
    """One chart of a table: sorted bars, time kept in order, Others past 30."""

    table = cards.get(chart.table)
    if table is None or table.kind != "table":
        return None
    value = TableValue.model_validate(table.value)
    keys = [column.key for column in value.columns]
    if chart.x not in keys or chart.y not in keys:
        return None
    pos_x, pos_y = keys.index(chart.x), keys.index(chart.y)
    column_y = value.columns[pos_y]
    rows = [[row[pos_x], row[pos_y]] for row in value.rows if row[pos_y] is not None]
    if not rows:
        return None
    if value.columns[pos_x].is_time:
        ordered = rows
    else:
        with ResultTable(["x", "v"], rows) as drawn:
            ordered = drawn.rows_sorted("v", descending=True)
    if len(ordered) > MAX_BARS and not value.columns[pos_x].is_time:
        top = ordered[: MAX_BARS - 1]
        with ResultTable(["x", "v"], ordered[MAX_BARS - 1 :]) as rest:
            total = rest.total("v")
        if total is None:
            return None
        top.append(["Others", str(total)])
        ordered = top
    data = []
    for raw_x, raw_y in ordered:
        amount = _dec(raw_y)
        if amount is None:
            continue
        number = NumberValue(
            value=str(amount), unit=column_y.unit or "count", currency=column_y.currency or ""
        )
        data.append(
            [
                raw_x if raw_x is not None else "",
                {"v": float(amount), "f": _format_number(number, style)},
            ]
        )
    if not data:
        return None
    names = [row[0] for row in data]
    return {
        "type": "chart",
        "kind": chart.kind,
        "title": fill_labels(chart.title, values),
        "subtitle": fill_labels(chart.subtitle, values),
        "x": chart.x,
        "y": chart.y,
        "unit": column_y.unit,
        **({"currency": column_y.currency} if column_y.currency else {}),
        "highlight": [name for name in chart.highlight if name in names],
        "data": {"columns": [chart.x, chart.y], "rows": data},
    }


def table_block(
    table, cards: dict[str, NotebookItem], values: dict[str, str], style: str
) -> dict | None:
    """One table block: the chosen columns, numbers as `{ v, f }`."""

    card = cards.get(table.table)
    if card is None or card.kind != "table":
        return None
    value = TableValue.model_validate(card.value)
    by_key = {column.key: (position, column) for position, column in enumerate(value.columns)}
    picked = [(key, by_key[key]) for key in table.columns if key in by_key]
    if not picked:
        return None

    rows = []
    for row in value.rows[:MAX_TABLE_ROWS]:
        cells: dict = {}
        for key, (position, column) in picked:
            raw = row[position] if position < len(row) else None
            if column.unit in NUMBER_UNITS and _dec(raw) is not None:
                amount = _dec(raw)
                number = NumberValue(value=str(amount), unit=column.unit)
                if column.currency:
                    number = NumberValue(
                        value=str(amount), unit=column.unit, currency=column.currency
                    )
                cells[key] = {"v": float(amount), "f": _format_number(number, style)}
            else:
                cells[key] = raw
        rows.append(cells)
    title = fill_labels(table.title, values)
    if value.rows_total > MAX_TABLE_ROWS:
        title += f" (first {MAX_TABLE_ROWS} of {value.rows_total} rows)"
    return {
        "type": "table",
        "title": title,
        "columns": [
            {"key": key, "label": column.label, **({"unit": column.unit} if column.unit else {})}
            for key, (_, column) in picked
        ],
        "rows": rows,
    }


def tree_block(title: str, nodes: list, values: dict[str, str]) -> dict | None:
    """A flat tree with filled labels."""
    if not nodes:
        return None
    return {
        "type": "tree",
        "title": fill_labels(title, values),
        "nodes": [
            {
                "id": node.id,
                "parent": node.parent or None,
                "label": fill_labels(node.label, values),
                "tone": node.tone,
            }
            for node in nodes
        ],
    }


def ai_filled_texts(blocks: list[dict]) -> list[str]:
    """Every filled word of the rendered answer, except query SQL."""
    texts = []
    for block in blocks if isinstance(blocks, list) else []:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "reading":
            texts.append(block.get("text") or "")
        elif kind == "text":
            for paragraph in block.get("paragraphs", []):
                for sentence in paragraph.get("sentences", []):
                    texts.append(sentence.get("text") or "")
        elif kind == "kpis":
            for item in block.get("items", []):
                texts.extend(
                    str(item.get(key) or "") for key in ("label", "value", "change", "compare")
                )
        elif kind == "chart":
            texts.extend([block.get("title") or "", block.get("subtitle") or ""])
        elif kind == "table":
            texts.append(block.get("title") or "")
        elif kind == "tree":
            texts.append(block.get("title") or "")
            for node in block.get("nodes", []):
                texts.append(node.get("label") or "")
        elif kind == "callout":
            texts.append(block.get("text") or "")
        elif kind == "suggestions":
            texts.append(block.get("title") or "")
            for item in block.get("items", []):
                texts.append(item.get("text") or "")
        elif kind == "method":
            texts.extend(block.get("definitions", []))
            texts.extend(block.get("steps", []))
            for source in block.get("sources", []):
                texts.extend(
                    [
                        source.get("document") or "",
                        source.get("quote") or "",
                        source.get("location") or "",
                    ]
                )
        elif kind == "follow_ups":
            texts.extend(block.get("items", []))
    return [text for text in texts if text]


def suggestions_block(title: str, suggestions: list, values: dict[str, str]) -> dict | None:
    """The follow-ups the writer proposes."""
    if not suggestions:
        return None
    block: dict = {
        "items": [
            {"text": fill_labels(item.text, values), "confidence": item.confidence}
            for item in suggestions
        ]
    }
    if title:
        block["title"] = fill_labels(title, values)
    return {"type": "suggestions", **block}


def reading_block(filled_reading: str, show: bool) -> dict | None:
    """The filled reading, when the setting or a vague question asks for it."""
    if not show or not filled_reading:
        return None
    return {"type": "reading", "text": filled_reading}


def stop_title(reason: str) -> str:
    """The method's last step, in the owner's words."""
    if reason == "answered":
        return "The rounds answered the question."
    if reason == "rounds_done":
        return f"The rounds stopped after {MAX_ROUNDS} rounds."
    if reason == "finished":
        return "The rounds stopped because you clicked Finish now."
    if reason == "time_up":
        return "The rounds stopped because the thinking time limit was reached."
    return ""


def warn_notes(
    stop_reason: str, still_open: list[str], cannot_tell: list[str], dropped: list[str]
) -> list[dict]:
    """Early stops, what couldn't be checked, and the dropped filters."""
    notes = []
    if stop_reason == "finished":
        text = "I stopped early because you clicked Finish now."
        if still_open:
            text += " Still unknown: " + "; ".join(still_open) + "."
        notes.append({"type": "callout", "tone": "warn", "text": text})
    elif stop_reason == "time_up":
        text = "I stopped early because the thinking time limit was reached."
        if still_open:
            text += " Still unknown: " + "; ".join(still_open) + "."
        notes.append({"type": "callout", "tone": "warn", "text": text})
    if cannot_tell:
        notes.append(
            {
                "type": "callout",
                "tone": "warn",
                "text": "I couldn't check: " + "; ".join(cannot_tell) + ".",
            }
        )
    notes.extend({"type": "callout", "tone": "warn", "text": line} for line in dropped)
    return notes


def code_notes(
    anchor: str,
    period_notes: list[str],
    default_titles: list[str],
    corrections: list,
    new_measures: list[NotebookItem],
    stop_reason: str,
    still_open: list[str],
    values: dict[str, str],
) -> list[dict]:
    """The notes only code knows: anchor, periods, defaults, fixes, unknowns."""
    notes = []
    if anchor:
        notes.append({"type": "callout", "tone": "note", "text": anchor})
    notes.extend({"type": "callout", "tone": "note", "text": note} for note in period_notes)
    if len(default_titles) == 1:
        notes.append(
            {
                "type": "callout",
                "tone": "note",
                "text": f'I used the default meaning of "{default_titles[0]}". '
                "You can change it in Questions for you.",
            }
        )
    elif default_titles:
        joined = ", ".join(f'"{title}"' for title in default_titles)
        notes.append(
            {
                "type": "callout",
                "tone": "note",
                "text": f"I used the default meanings of {joined}. "
                "You can change them in Questions for you.",
            }
        )
    for old, new in corrections:
        sentence = (
            f"Correction: I first found [{old.label}] for {old.description}, "
            f"but {old.replace_reason}. This answer uses [{new.label}]."
        )
        notes.append({"type": "callout", "tone": "note", "text": fill_labels(sentence, values)})
    for item in new_measures:
        notes.append(
            {
                "type": "callout",
                "tone": "note",
                "text": f'"{item.description}" isn\'t a standard measure yet. '
                "I worked it out two ways and both agree. "
                "I've asked the Learner to add it to the knowledge base.",
            }
        )
    if still_open and stop_reason not in ("finished", "time_up"):
        notes.append(
            {
                "type": "callout",
                "tone": "note",
                "text": "Still unknown: " + "; ".join(still_open) + ".",
            }
        )
    return notes


def limited_method(session, message_id, chat_id, kb_version, labels, style="short"):
    """One earlier answer's method block, limited to labels (or all)."""
    stored = kb_version
    row = session.scalar(select(KbVersion.id).where(KbVersion.number == stored))
    kb = KbView.load(session, row if row is not None else stored)
    book = Notebook.load(session, message_id, chat_id)
    numbers = [
        item
        for item in book.items()
        if item.kind == "number" and (labels is None or item.label in labels)
    ]
    titles, meanings = kb.titles(), kb.meanings()
    used = []
    for card in numbers:
        key = (card.proof or {}).get("recipe_key")
        if key and key not in used:
            used.append(key)
    definitions = [
        f"{titles[key]}: {meanings[key]}" for key in used if key in titles and key in meanings
    ]
    definitions.extend(
        f"{card.description}: not a standard measure yet, worked out two ways that agree."
        for card in numbers
        if (card.proof or {}).get("way") == "A+B" and not (card.proof or {}).get("recipe_key")
    )
    steps = [
        row.title
        for row in session.scalars(
            select(ThinkingEvent)
            .where(ThinkingEvent.message_id == message_id, ThinkingEvent.kind == "step")
            .order_by(ThinkingEvent.seq)
        ).all()
        if (row.title or "").startswith("Round ")
    ]
    wanted: set[int] | None = None
    if labels is not None:
        wanted = set()
        for card in numbers:
            for run_id in (card.proof or {}).get("query_run_ids") or []:
                wanted.add(run_id)
    queries = []
    for row in session.scalars(
        select(QueryRun).where(QueryRun.message_id == message_id, QueryRun.status == "ok")
    ).all():
        if wanted is not None and row.id not in wanted:
            continue
        queries.append({"purpose": row.purpose, "sql": row.sql_text or ""})
    sources = []
    for card in book.items():
        if card.kind != "quote":
            continue
        quote = QuoteValue.model_validate(card.value)
        sources.append(
            {"document": quote.document, "quote": quote.text, "location": quote.location}
        )
    values = values_for(numbers, style)
    shown = [
        {
            "label": card.label,
            "text": values.get(card.label, ""),
            "description": card.description,
        }
        for card in numbers
    ]
    return method_block(definitions, steps, queries, sources), shown


def method_block(
    definitions: list[str], steps: list[str], queries: list[dict], sources: list[dict]
) -> dict:
    """How the answer was worked out: always true, because code builds it."""
    return {
        "type": "method",
        "definitions": definitions,
        "steps": steps,
        "queries": queries,
        "sources": sources,
    }


def follow_ups_block(
    drop: str | None,
    rise: str | None,
    last_year_used: bool,
    first_period: str,
    unsplit: tuple[str, str] | None,
) -> dict | None:
    """Up to 3 next questions; fewer than 2 applying means no block."""
    items = []
    if drop:
        items.append(f"Why did {drop} drop?")
    if rise:
        items.append(f"What drove the growth at {rise}?")
    if not last_year_used and first_period:
        items.append(f"How does {first_period} compare with the same time last year?")
    if unsplit is not None:
        items.append(f"Show {unsplit[0]} by {unsplit[1]} for {first_period}.")
    if len(items) < 2:
        return None
    return {"type": "follow_ups", "items": items[:3]}


def prompt_text(short: str) -> str:
    """The notebook part of the writer prompt, with its header and end."""
    body = short.strip() or "(no checked numbers yet)"
    return f"## Notebook\n{body}\n## END"


VAGUE_KINDS = ("vague_with_default", "vague_no_default", "two_meanings")


def _mover(lines: list[dict], word: str) -> str | None:
    """The restaurant named after `word` in a `Found: …` line, or empty."""
    for line in lines:
        if line.get("kind") != "found":
            continue
        title = line.get("title") or ""
        if f"The biggest {word} is " in title:
            return title.split(f"The biggest {word} is ", 1)[1].rstrip(".") or None
    return None


def _default_title(word: str, titles: dict[str, str], kb) -> str:
    """The default's meaning in the owner's words (understand's rule)."""
    value = kb.defaults().get(word)
    text = value.value if value is not None else word
    if text in titles:
        return titles[text]
    return text.replace("_", " ")


@dataclass
class AnswerInputs:
    """Everything the block builders read: cards, texts, settings, stops."""

    items: list = field(default_factory=list)
    replaced: list = field(default_factory=list)
    corrections: list = field(default_factory=list)
    new_measures: list = field(default_factory=list)
    cards: dict = field(default_factory=dict)
    values: dict = field(default_factory=dict)
    view: str = ""
    style: str = "short"
    titles: dict = field(default_factory=dict)
    meanings: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    default_titles: list = field(default_factory=list)
    periods: list = field(default_factory=list)
    anchor: str = ""
    lines: list = field(default_factory=list)
    queries: list = field(default_factory=list)
    show: bool = False
    kind: str = ""
    stop_reason: str = ""
    still_open: list = field(default_factory=list)
    cannot_tell: list = field(default_factory=list)
    filled_reading: str = ""
    data_through: object = None


def _load_inputs(session, ctx) -> AnswerInputs:
    """Load every block input in one session."""
    kb = KbView.load(session, ctx.kb_version_id)
    book = Notebook.load(session, ctx.message_id, ctx.chat_id)
    items = book.items()
    cards = {item.label: item for item in items if item.label}
    style = (ctx.settings or {}).get("number_format", "short")
    values = values_for(items, style)
    replaced = book.items(status="replaced")
    values.update(values_for(replaced, style))
    titles, meanings, metrics = kb.titles(), kb.meanings(), kb.metrics()
    default_words = [used.removeprefix("default.") for used in ctx.understanding.defaults_used]
    periods = ctx.periods.periods if ctx.periods is not None else []
    lines = ctx.log.lines()
    queries = [
        {"purpose": row.purpose, "sql": row.sql_text or ""}
        for row in session.scalars(
            select(QueryRun).where(QueryRun.message_id == ctx.message_id, QueryRun.status == "ok")
        ).all()
    ]
    reading_values = {
        label: values[label]
        for label in labels_in(ctx.understanding.reading or "")
        if label in values
    }
    corrections = []
    for old in replaced:
        if not old.replaced_by:
            continue
        try:
            corrections.append((old, book.get(old.replaced_by)))
        except NotebookError:
            continue
    return AnswerInputs(
        items=items,
        replaced=replaced,
        corrections=corrections,
        new_measures=[
            card
            for card in items
            if (card.proof or {}).get("way") == "A+B" and not (card.proof or {}).get("recipe_key")
        ],
        cards=cards,
        values=values,
        view=book.labelled_view(),
        style=style,
        titles=titles,
        meanings=meanings,
        metrics=metrics,
        default_titles=[_default_title(word, titles, kb) for word in default_words],
        periods=periods,
        anchor=ctx.periods.anchor_note if ctx.periods is not None else "",
        lines=lines,
        queries=queries,
        show=bool(get_setting(session, "show_reading")),
        kind=ctx.understanding.kind or "",
        stop_reason=ctx.stop_reason or "",
        still_open=list(ctx.still_open),
        cannot_tell=list(ctx.cannot_tell),
        filled_reading=fill_labels(ctx.understanding.reading or "", reading_values),
        data_through=ctx.data_through if hasattr(ctx, "data_through") else None,
    )


def _render_ai(draft, g: AnswerInputs) -> list[dict]:
    """The AI's blocks filled and rendered, skipping empty ones."""
    ai_blocks = []
    for block in draft.blocks:
        if block.type == "text":
            made = text_block(block.sentences, g.values)
        elif block.type == "kpis":
            made = kpi_block(block.kpis, g.cards, g.values)
        elif block.type == "chart" and block.chart is not None:
            made = chart_block(block.chart, g.cards, g.values, g.style)
        elif block.type == "table" and block.table is not None:
            made = table_block(block.table, g.cards, g.values, g.style)
        elif block.type == "tree":
            made = tree_block(block.tree_title, block.tree_nodes, g.values)
        elif block.type == "callout":
            made = (
                {
                    "type": "callout",
                    "tone": block.callout_tone,
                    "text": fill_labels(block.callout_text, g.values),
                }
                if block.callout_text
                else None
            )
        elif block.type == "suggestions":
            made = suggestions_block(block.suggestions_title, block.suggestions, g.values)
        else:
            made = None
        if made is not None:
            ai_blocks.append(made)
    return ai_blocks


def _assemble(g: AnswerInputs, ai_blocks: list[dict], extra_shown: list[str]):
    """Reading, warns, the AI's blocks, notes, method and follow-ups, in order."""
    reading = reading_block(g.filled_reading, g.show or g.kind in VAGUE_KINDS)
    dropped = [
        line.get("title") or ""
        for line in g.lines
        if line.get("kind") == "note" and "left it out" in (line.get("title") or "")
    ]
    warns = warn_notes(g.stop_reason, g.still_open, g.cannot_tell, dropped)
    period_notes = [period.note for period in g.periods if getattr(period, "note", "")]
    notes = code_notes(
        g.anchor,
        period_notes,
        g.default_titles,
        g.corrections,
        g.new_measures,
        g.stop_reason,
        g.still_open,
        g.values,
    )
    used_metrics: list[str] = []
    for card in g.items:
        key = (card.proof or {}).get("recipe_key")
        if key and key not in used_metrics:
            used_metrics.append(key)
    definitions = [
        f"{g.titles[key]}: {g.meanings[key]}"
        for key in used_metrics
        if key in g.titles and key in g.meanings
    ]
    definitions.extend(
        f"{card.description}: not a standard measure yet, worked out two ways that agree."
        for card in g.new_measures
    )
    steps = [
        line.get("title") or ""
        for line in g.lines
        if line.get("kind") == "step" and (line.get("title") or "").startswith("Round ")
    ]
    title = stop_title(g.stop_reason)
    if title:
        steps.append(title)
    sources = []
    for card in g.items:
        if card.kind != "quote":
            continue
        quote = QuoteValue.model_validate(card.value)
        sources.append(
            {"document": quote.document, "quote": quote.text, "location": quote.location}
        )
    method = method_block(definitions, steps, g.queries, sources)
    drop = _mover(g.lines, "drop")
    rise = _mover(g.lines, "rise")
    first_period = next((period.text for period in g.periods if getattr(period, "text", "")), "")
    unsplit = None
    for card in g.items:
        fact = (card.proof or {}).get("fact_key") or {}
        key = (card.proof or {}).get("recipe_key")
        if key and fact.get("split") == {} and key in g.metrics:
            dims = g.metrics[key].get("dimensions") or []
            if dims and isinstance(dims[0], dict) and dims[0].get("title"):
                unsplit = (g.titles.get(key, key), dims[0]["title"])
                break
    follow = follow_ups_block(drop, rise, _last_year_used(g), first_period, unsplit)
    blocks = ([reading] if reading is not None else []) + warns + ai_blocks + notes + [method]
    if follow is not None:
        blocks.append(follow)
    shown = list(extra_shown)
    shown.extend(old.label for old, _ in g.corrections)
    shown.extend(new.label for _, new in g.corrections)
    shown.extend(card.label for card in g.items if card.kind == "quote")
    return blocks, list(dict.fromkeys(shown))


def _last_year_used(g: AnswerInputs) -> bool:
    """Whether any period already covers the same time last year."""
    year = g.data_through.year if getattr(g.data_through, "year", None) else None
    if year is None:
        return True
    last_year = year - 1
    return any(str(last_year) in (period.expression or "") for period in g.periods)


def render_answer(draft, ctx) -> tuple[list[dict], list[str]] | None:
    """The final 09 blocks with filled labels, or None when the draft fails.

    The gate keeps raw labels off the screen; the 10 checks run after.
    """
    with session_scope() as session:
        g = _load_inputs(session, ctx)
        for label in used_labels(draft):
            if label not in g.cards:
                return None
        for text in ai_texts(draft):
            if not check_matches(text, g.view):
                return None
        return _assemble(g, _render_ai(draft, g), used_labels(draft))


def fallback_blocks(ctx, failures=None) -> tuple[list[dict], list[str]]:  # noqa: ARG001
    """The checked numbers and tables when no draft passes, all marked shown."""
    with session_scope() as session:
        g = _load_inputs(session, ctx)
    warn = {
        "type": "callout",
        "tone": "warn",
        "text": "I couldn't write a fully checked explanation, so I'm showing the checked numbers.",
    }
    numbered = [card for card in g.items if card.kind == "number"]
    rows = []
    for card in numbered:
        amount = _dec(str(card.value.get("value")))
        if amount is None:
            continue
        number = NumberValue(
            value=str(amount),
            unit=card.value.get("unit") or "count",
            currency=card.value.get("currency") or "",
        )
        rows.append(
            {
                "what": card.description,
                "value": {"v": float(amount), "f": _format_number(number, g.style)},
            }
        )
    checked = {
        "type": "table",
        "title": "Checked numbers",
        "columns": [
            {"key": "what", "label": "What"},
            {"key": "value", "label": "Value"},
        ],
        "rows": rows,
    }
    tables = []
    for card in g.items:
        if card.kind != "table":
            continue
        value = TableValue.model_validate(card.value)
        made = table_block(
            SimpleNamespace(
                title=card.description,
                table=card.label,
                columns=[column.key for column in value.columns],
            ),
            g.cards,
            g.values,
            g.style,
        )
        if made is not None:
            tables.append(made)
    blocks, shown = _assemble(g, [checked] + tables, [])
    reading = reading_block(g.filled_reading, g.show or g.kind in VAGUE_KINDS)
    ordered = ([reading] if reading is not None else []) + [warn]
    ordered.extend(block for block in blocks if block.get("type") != "reading")
    shown.extend(card.label for card in numbered)
    shown.extend(card.label for card in g.items if card.kind == "table")
    return ordered, list(dict.fromkeys(shown))


def render_blocks(draft, ctx) -> list[dict]:
    """The final blocks, or empty when the draft fails its gate."""
    found = render_answer(draft, ctx)
    return found[0] if found is not None else []
