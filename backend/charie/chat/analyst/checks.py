"""Answer checks 1–5 and 10: numbers, labels, proof, wording, trends (P10.10/11).

Each check reads only the draft, the rendered blocks and `CheckInputs`:
never the AI, never the database. A check only reports; it never fixes.
"""

import re
from dataclasses import dataclass, field

from charie.chat.analyst.labels import labels_in, mixed_tokens, stray_digits
from charie.chat.analyst.notebook import TableValue
from charie.shared.calc.core import CalcError
from charie.shared.calc.core import trend as calc_trend

#: Sentence kinds that must point to proof.
PROOF_KINDS = ("fact", "conclusion")

#: Careful words for a possible reason, whole words, any case.
CAREFUL = ("may", "might", "possibly", "a likely reason", "could")

#: Trend words, whole words, any case. "grew" and "up 6%" are not trends.
TREND_UP = ("rising", "growing", "increasing", "climbing", "trending up", "upward trend")
TREND_DOWN = ("falling", "declining", "decreasing", "shrinking", "trending down", "downward trend")

#: Question kinds that must start with the reading block.
VAGUE_KINDS = ("vague_with_default", "vague_no_default", "two_meanings")


@dataclass
class CheckFailure:
    """One failed check: which check, where, and the owner's words."""

    check: int
    name: str
    message: str
    where: str
    ai_text: str = ""


@dataclass
class CheckInputs:
    """Everything the checks read: the cards, the kind, the known words."""

    items: list = field(default_factory=list)
    kind: str = ""
    meanings: list = field(default_factory=list)
    allowed_tokens: list[str] = field(default_factory=list)
    required_notes: list = field(default_factory=list)
    section_texts: list = field(default_factory=list)
    earlier_numbers: list = field(default_factory=list)
    query_runs: list = field(default_factory=list)
    question: str = ""
    data_through: object = None
    kb_version_id: int | None = None
    values: dict[str, str] = field(default_factory=dict)


def _cards(inputs: CheckInputs) -> dict:
    """The current cards by label."""
    return {item.label: item for item in inputs.items if item.label}


def _fields(draft) -> list[tuple[str, str]]:
    """Every AI text field with its `where`."""
    found = []
    for number, block in enumerate(draft.blocks, start=1):
        if block.type == "text":
            for pos, sentence in enumerate(block.sentences, start=1):
                found.append((f"Block {number}, sentence {pos}", sentence.text))
        elif block.type == "kpis":
            for kpi in block.kpis:
                found.append((f"Block {number}", kpi.title))
        elif block.type == "chart" and block.chart is not None:
            found.append((f"Block {number}", block.chart.title))
            found.append((f"Block {number}", block.chart.subtitle))
        elif block.type == "table" and block.table is not None:
            found.append((f"Block {number}", block.table.title))
        elif block.type == "tree":
            found.append((f"Block {number}", block.tree_title))
            for node in block.tree_nodes:
                found.append((f"Block {number}", node.label))
        elif block.type == "callout":
            found.append((f"Block {number}", block.callout_text))
        elif block.type == "suggestions":
            found.append((f"Block {number}", block.suggestions_title))
            for suggestion in block.suggestions:
                found.append((f"Block {number}", suggestion.text))
    return [(where, text) for where, text in found if text]


def _check_1_typed_numbers(draft, blocks, inputs: CheckInputs) -> list[CheckFailure]:  # noqa: ARG001
    """No numbers typed by the AI: every stray digit word fails."""
    failures = []
    for where, text in _fields(draft):
        for token in stray_digits(text, inputs.allowed_tokens):
            failures.append(
                CheckFailure(
                    check=1,
                    name="typed_number",
                    message=f'{where}: "{token}" is a number the writer typed. '
                    "Use a label like [n1] instead.",
                    where=where,
                    ai_text=token,
                )
            )
    return failures


def _label_kind(label: str) -> str:
    """The card kind one letter names."""
    return label[:1]


def _check_2_labels(draft, blocks, inputs: CheckInputs) -> list[CheckFailure]:  # noqa: ARG001
    """Every label exists, is current, and fits its card field."""
    cards = _cards(inputs)
    failures: list[CheckFailure] = []

    def _report(label: str, where: str, want: str) -> None:
        card = cards.get(label)
        if card is None:
            failures.append(
                CheckFailure(
                    check=2,
                    name="unknown_label",
                    message=f"{where}: Label [{label}] isn't in this question's notebook.",
                    where=where,
                )
            )
        elif card.status == "replaced":
            failures.append(
                CheckFailure(
                    check=2,
                    name="replaced_label",
                    message=(
                        f"{where}: Label [{label}] was replaced; use [{card.replaced_by}] instead."
                    ),
                    where=where,
                )
            )
        elif want == "number" and _label_kind(label) != "n":
            failures.append(
                CheckFailure(
                    check=2,
                    name="wrong_kind",
                    message=f"{where}: A number card needs a number label (n…), not [{label}].",
                    where=where,
                )
            )
        elif want == "table" and _label_kind(label) != "t":
            failures.append(
                CheckFailure(
                    check=2,
                    name="wrong_kind",
                    message=f"{where}: A chart or table needs a table label (t…), not [{label}].",
                    where=where,
                )
            )

    for number, block in enumerate(draft.blocks, start=1):
        where = f"Block {number}"
        if block.type == "kpis":
            for kpi in block.kpis:
                for label in [kpi.value, kpi.change]:
                    if label:
                        _report(label, where, "number")
                if kpi.spark:
                    _report(kpi.spark, where, "table")
        elif block.type == "chart" and block.chart is not None and block.chart.table:
            _report(block.chart.table, where, "table")
        elif block.type == "table" and block.table is not None and block.table.table:
            _report(block.table.table, where, "table")
    for where, text in _fields(draft):
        for label in labels_in(text):
            _report(label, where, "any")
    for number, block in enumerate(draft.blocks, start=1):
        if block.type == "text":
            for pos, sentence in enumerate(block.sentences, start=1):
                for label in sentence.proof:
                    _report(label, f"Block {number}, sentence {pos}", "any")
    seen: list[tuple] = []
    unique = []
    for failure in failures:
        key = (failure.check, failure.name, failure.message, failure.where)
        if key not in seen:
            seen.append(key)
            unique.append(failure)
    return unique


def _check_3_proof(draft, blocks, inputs: CheckInputs) -> list[CheckFailure]:  # noqa: ARG001
    """Every fact and conclusion points to at least one n, t or q label."""
    failures = []
    for number, block in enumerate(draft.blocks, start=1):
        if block.type != "text":
            continue
        for pos, sentence in enumerate(block.sentences, start=1):
            if sentence.kind not in PROOF_KINDS:
                continue
            if not any(_label_kind(label) in ("n", "t", "q") for label in sentence.proof):
                where = f"Block {number}, sentence {pos}"
                failures.append(
                    CheckFailure(
                        check=3,
                        name="missing_proof",
                        message=f"{where}: This {sentence.kind} has no proof. "
                        "Add at least one n, t or q label to its proof.",
                        where=where,
                    )
                )
    return failures


def _careful(text: str) -> bool:
    """A possible reason sounds possible: one careful word, whole words."""
    words = re.findall(r"[a-z]+", text.lower())
    joined = " ".join(words)
    return (
        any(word in ("may", "might", "possibly", "could") for word in words)
        or "a likely reason" in joined
    )


def _check_4_careful_words(draft, blocks, inputs: CheckInputs) -> list[CheckFailure]:  # noqa: ARG001
    """A possible reason must sound possible."""
    failures = []
    for number, block in enumerate(draft.blocks, start=1):
        if block.type != "text":
            continue
        for pos, sentence in enumerate(block.sentences, start=1):
            if sentence.kind == "possible_reason" and not _careful(sentence.text):
                where = f"Block {number}, sentence {pos}"
                failures.append(
                    CheckFailure(
                        check=4,
                        name="careless_reason",
                        message=f"{where}: A possible reason must sound possible. "
                        'Use "may", "might", "possibly", "a likely reason" or "could".',
                        where=where,
                    )
                )
    return failures


def _trend_words(text: str) -> list[tuple[str, str]]:
    """Every trend word with its direction, whole words, any case."""
    lowered = text.lower()
    found = []
    for word in TREND_UP:
        if re.search(r"\b" + re.escape(word) + r"\b", lowered):
            found.append((word, "up"))
    for word in TREND_DOWN:
        if re.search(r"\b" + re.escape(word) + r"\b", lowered):
            found.append((word, "down"))
    return found


def _series(table: TableValue) -> list | None:
    """The first number column in time order, or empty without a time split."""
    time_at = next((at for at, column in enumerate(table.columns) if column.is_time), None)
    if time_at is None or table.rows_total < 3:
        return None
    number_at = next(
        (
            at
            for at, column in enumerate(table.columns)
            if column.unit in ("money", "count", "percent", "ratio")
        ),
        None,
    )
    if number_at is None:
        return None
    ordered = sorted(table.rows, key=lambda row: str(row[time_at] or ""))
    values = []
    for row in ordered:
        raw = row[number_at] if number_at < len(row) else None
        if raw is None or raw == "":
            continue
        values.append(raw)
    return values or None


def _check_5_trends(draft, blocks, inputs: CheckInputs) -> list[CheckFailure]:  # noqa: ARG001
    """Trend words need a matching time series in their proof."""
    cards = _cards(inputs)
    failures = []
    for number, block in enumerate(draft.blocks, start=1):
        if block.type != "text":
            continue
        for pos, sentence in enumerate(block.sentences, start=1):
            for word, direction in _trend_words(sentence.text):
                where = f"Block {number}, sentence {pos}"
                candidates = [
                    label
                    for label in sentence.proof
                    if label in cards and cards[label].kind == "table"
                ]
                series = [
                    (label, made)
                    for label in candidates
                    if (made := _series(TableValue.model_validate(cards[label].value))) is not None
                ]
                if not series:
                    failures.append(
                        CheckFailure(
                            check=5,
                            name="trend_without_series",
                            message=f'{where}: "{word}" needs a time-series table as proof.',
                            where=where,
                        )
                    )
                    continue
                usable = []
                for label, values in series:
                    try:
                        usable.append((label, calc_trend(values)))
                    except CalcError:
                        continue
                if not usable:
                    failures.append(
                        CheckFailure(
                            check=5,
                            name="trend_without_series",
                            message=f'{where}: "{word}" needs a time-series table as proof.',
                            where=where,
                        )
                    )
                    continue
                bad = None
                for label, found in usable:
                    if found.is_real and found.direction == direction:
                        bad = None
                        break
                    bad = (label, found)
                if bad is None:
                    continue
                label, found = bad
                failures.append(
                    CheckFailure(
                        check=5,
                        name="fake_trend",
                        message=f'{where}: "{word}" doesn\'t match the data in [{label}]: '
                        f"it goes {found.direction} overall, "
                        f"with {found.steps_that_way} of {found.steps} steps going that way.",
                        where=where,
                    )
                )
    return failures


def _check_10_reading(draft, blocks, inputs: CheckInputs) -> list[CheckFailure]:
    """A vague question must start with the reading block."""
    if inputs.kind not in VAGUE_KINDS:
        return []
    failures: list[CheckFailure] = []
    first = blocks[0].get("type") if blocks else ""
    if first != "reading":
        failures.append(
            CheckFailure(
                check=10,
                name="missing_reading",
                message="Block 1: The question was vague, so the answer must start "
                'with "I read this as…".',
                where="Block 1",
            )
        )
    failures.extend(_check_10_meanings(inputs))
    return failures


def _check_10_meanings(inputs: CheckInputs) -> list[CheckFailure]:
    """Two meanings need a shown number for each meaning."""
    if inputs.kind != "two_meanings" or not inputs.meanings:
        return []
    have: set[str] = set()
    for item in inputs.items or []:
        proof = getattr(item, "proof", None) or {}
        fact = proof.get("fact_key", {}) if isinstance(proof, dict) else {}
        metric = fact.get("metric") if isinstance(fact, dict) else None
        if getattr(item, "kind", "") == "number" and metric:
            have.add(metric)
    missing = [m for m in inputs.meanings if m.get("metric_key") not in have]
    if not missing:
        return []
    labels = " and ".join(str(m.get("label", "each meaning")) for m in inputs.meanings)
    return [
        CheckFailure(
            check=10,
            name="meaning_without_number",
            message=f"Show a number for both meanings: {labels}.",
            where="Block 1",
        )
    ]


def _chart_pairs(draft, blocks) -> list[tuple[int, object, dict]]:
    """Each draft chart with its rendered chart, in order."""
    rendered = [
        (position, block)
        for position, block in enumerate(blocks, start=1)
        if isinstance(block, dict) and block.get("type") == "chart"
    ]
    pairs = []
    found = 0
    for chart in [block.chart for block in draft.blocks if block.type == "chart"]:
        if chart is None or found >= len(rendered):
            continue
        position, block = rendered[found]
        found += 1
        pairs.append((position, chart, block))
    return pairs


def _check_6_charts(draft, blocks, inputs: CheckInputs) -> list[CheckFailure]:
    """Charts make sense: real tables, ordered bars, one unit, real highlights."""
    cards = _cards(inputs)
    failures = []
    for position, chart, block in _chart_pairs(draft, blocks):
        where = f"Block {position}"
        card = cards.get(chart.table or "")
        if card is None or card.kind != "table":
            failures.append(
                CheckFailure(
                    check=6,
                    name="unknown_chart_table",
                    message=f"{where}: The chart's table [{chart.table}] isn't in the notebook.",
                    where=where,
                )
            )
            continue
        table = TableValue.model_validate(card.value)
        columns = {column.key: column for column in table.columns}
        rows = block.get("data", {}).get("rows", [])
        if not rows:
            continue
        if columns.get(block.get("x")) is not None and columns[block["x"]].is_time:
            names = [str(row[0]) for row in rows]
            if names != sorted(names):
                failures.append(
                    CheckFailure(
                        check=6,
                        name="time_out_of_order",
                        message=f"{where}: Time must run left to right, oldest first.",
                        where=where,
                    )
                )
        else:
            values = [row[1].get("v") if isinstance(row[1], dict) else row[1] for row in rows]
            if values != sorted(values, reverse=True):
                failures.append(
                    CheckFailure(
                        check=6,
                        name="bars_unsorted",
                        message=f"{where}: Bars must be sorted by value.",
                        where=where,
                    )
                )
        y_column = columns.get(block.get("y"))
        if (
            y_column is None
            or block.get("unit") != y_column.unit
            or block.get("currency", "") != (y_column.currency or "")
        ):
            failures.append(
                CheckFailure(
                    check=6,
                    name="mixed_units",
                    message=f"{where}: One axis mixes units or currencies.",
                    where=where,
                )
            )
        names = {str(row[0]) for row in rows}
        for name in chart.highlight or []:
            if name not in names:
                failures.append(
                    CheckFailure(
                        check=6,
                        name="missing_highlight",
                        message=f'{where}: "{name}" is highlighted but isn\'t in the data.',
                        where=where,
                    )
                )
        if len(rows) > 30:
            failures.append(
                CheckFailure(
                    check=6,
                    name="too_many_bars",
                    message=f"{where}: A chart can show at most 30 bars.",
                    where=where,
                )
            )
    return failures


def _answer_words(draft, blocks) -> str:  # noqa: ARG001
    """Every filled word of the rendered answer."""
    from charie.chat.analyst.render import ai_filled_texts

    return "\n".join(text for text in ai_filled_texts(blocks) if text)


def _check_7_required_notes(draft, blocks, inputs: CheckInputs) -> list[CheckFailure]:
    """A required note appears whenever its tables or words do."""
    failures = []
    if not inputs.required_notes:
        return failures
    tables: set[str] = set()
    for run in inputs.query_runs:
        for table in (run.get("check_report") or {}).get("tables", []):
            tables.add(table)
    haystack = ((inputs.question or "") + "\n" + _answer_words(draft, blocks)).lower()
    for rule in inputs.required_notes:
        note = rule.get("note_text") or ""
        if not note:
            continue
        trigger = next(
            (table for table in rule.get("applies_to_tables") or [] if table in tables),
            "",
        )
        if not trigger:
            trigger = next(
                (word for word in rule.get("applies_to_words") or [] if word.lower() in haystack),
                "",
            )
        if not trigger or note.lower() in haystack:
            continue
        failures.append(
            CheckFailure(
                check=7,
                name="missing_required_note",
                message=f'This answer uses {trigger}, so it must include the note "{note}".',
                where="answer",
            )
        )
    return failures


def _first_use(draft, label: str) -> str:
    """Where one label is first cited: sentence, card field, or proof."""
    for number, block in enumerate(draft.blocks, start=1):
        if block.type == "text":
            for pos, sentence in enumerate(block.sentences, start=1):
                if label in labels_in(sentence.text) or label in sentence.proof:
                    return f"Block {number}, sentence {pos}"
        elif block.type == "kpis":
            for kpi in block.kpis:
                if label in (kpi.value, kpi.change, kpi.spark):
                    return f"Block {number}"
        elif (
            block.type == "chart"
            and block.chart is not None
            and label == block.chart.table
            or block.type == "table"
            and block.table is not None
            and label == block.table.table
        ):
            return f"Block {number}"
    return "Block 1"


def _passages(text: str) -> list[str]:
    """Quoted passages of 4 or more words, either quote style."""
    found = re.findall(r"“([^”]*)”", text) + re.findall(r'"([^"]*)"', text)
    return [passage for passage in found if len(passage.split()) >= 4]


def _check_8_quotes(draft, blocks, inputs: CheckInputs) -> list[CheckFailure]:  # noqa: ARG001
    """Quotes are word for word, and long passages are checked quotes."""
    from charie.shared.text.quotes import quote_appears

    cards = _cards(inputs)
    failures = []
    quotes = {label: _quote_value(card) for label, card in cards.items() if card.kind == "quote"}
    sections = {entry.get("label"): entry for entry in inputs.section_texts}
    for label, quote in quotes.items():
        if label not in {used for text in _fields(draft) for used in labels_in(text[1])} | set(
            _refs(draft)
        ):
            continue
        text = (sections.get(label) or {}).get("text", "")
        if not quote_appears(quote.text, text):
            failures.append(
                CheckFailure(
                    check=8,
                    name="altered_quote",
                    message=f"Quote [{label}] doesn't appear word for word in {quote.document}.",
                    where=_first_use(draft, label),
                )
            )
    known = {quote.text for quote in quotes.values()}
    for where, text in _fields(draft):
        for passage in _passages(text):
            if passage not in known:
                failures.append(
                    CheckFailure(
                        check=8,
                        name="unchecked_quote_passage",
                        message=f'{where}: "{passage}" isn\'t a checked quote. '
                        "Use a quote label like [q1].",
                        where=where,
                        ai_text=passage,
                    )
                )
    return failures


def _differs(new: str, old: str) -> bool:
    """Contradiction means more than 0.5% or 0.01 apart."""
    from decimal import Decimal, InvalidOperation

    try:
        new_value, old_value = Decimal(str(new)), Decimal(str(old))
    except InvalidOperation:
        return False
    gap = abs(new_value - old_value)
    if old_value == 0:
        return gap > Decimal("0.01")
    return gap > abs(old_value) * Decimal("0.005") or gap > Decimal("0.01")


def _check_9_no_contradictions(draft, blocks, inputs: CheckInputs) -> list[CheckFailure]:  # noqa: ARG001
    """An earlier answer's number stands unless the past changed or a note says so."""

    cards = _cards(inputs)
    shown = [
        label
        for label in labels_in("\n".join(text for _, text in _fields(draft)))
        if label.startswith("n")
    ]
    shown.extend(
        label
        for block in draft.blocks
        if block.type == "kpis"
        for kpi in block.kpis
        for label in (kpi.value, kpi.change)
        if label and label.startswith("n")
    )
    failures = []
    for label in dict.fromkeys(shown):
        card = cards.get(label)
        if card is None or card.kind != "number":
            continue
        for earlier in inputs.earlier_numbers:
            if earlier.get("fact_key") != (card.proof or {}).get("fact_key"):
                continue
            if not _differs(str(card.value.get("value")), str(earlier.get("raw"))):
                continue
            through = earlier.get("data_through")
            changed_data = _iso(inputs.data_through) != through
            changed_kb = inputs.kb_version_id != earlier.get("kb_version")
            if not changed_data and not changed_kb:
                failures.append(
                    CheckFailure(
                        check=9,
                        name="contradiction",
                        message=(
                            f"This says {inputs.values.get(label, card.value.get('value'))} "
                            f"for {card.description}, but an earlier answer in this chat "
                            f"said {earlier.get('text')}."
                        ),
                        where=_first_use(draft, label),
                    )
                )
                continue
            if not _note_cites(draft, label):
                if changed_data:
                    date = _display_date(inputs.data_through or through)
                    reason = (
                        " Explain the change in a note sentence that cites "
                        f"[{label}]: the data now goes up to {date}."
                    )
                else:
                    reason = (
                        " Explain the change in a note sentence that cites "
                        f"[{label}]: the knowledge base changed since then."
                    )
                failures.append(
                    CheckFailure(
                        check=9,
                        name="unexplained_change",
                        message=(
                            f"This says {inputs.values.get(label, card.value.get('value'))} "
                            f"for {card.description}, but an earlier answer in this chat "
                            f"said {earlier.get('text')}.{reason}"
                        ),
                        where=_first_use(draft, label),
                    )
                )
    return failures


def _iso(moment) -> str | None:
    """One ISO day, or empty when there is none."""
    if moment is None:
        return None
    if hasattr(moment, "isoformat"):
        return moment.isoformat()
    return str(moment)


def _display_date(moment) -> str:
    """'31 Dec 2025' for a datetime, date or ISO string."""
    from charie.shared.text.numbers import format_date

    if hasattr(moment, "date") and callable(moment.date):
        return format_date(moment.date().isoformat())
    if hasattr(moment, "isoformat"):
        return format_date(moment.isoformat()[:10])
    return format_date(str(moment)[:10])


def _note_cites(draft, label: str) -> bool:
    """A note sentence cites the label in its text or its proof."""
    for block in draft.blocks:
        if block.type != "text":
            continue
        for sentence in block.sentences:
            if sentence.kind == "note" and (
                label in labels_in(sentence.text) or label in sentence.proof
            ):
                return True
    return False


def _quote_value(card):
    """The card's quote value."""
    from charie.chat.analyst.notebook import QuoteValue

    return QuoteValue.model_validate(card.value)


def _refs(draft) -> list[str]:
    """Labels the blocks use without writing them: kpis, charts, tables."""
    from charie.chat.analyst.render import block_refs

    return block_refs(draft)


#: Every check in order, each reading only the draft, the blocks and the inputs.
CHECKS = [
    _check_1_typed_numbers,
    _check_2_labels,
    _check_3_proof,
    _check_4_careful_words,
    _check_5_trends,
    _check_6_charts,
    _check_7_required_notes,
    _check_8_quotes,
    _check_9_no_contradictions,
    _check_10_reading,
]


def run_checks(draft, blocks: list[dict], inputs: CheckInputs) -> list[CheckFailure]:
    """Every failure in check order."""
    failures = []
    for check in CHECKS:
        failures.extend(check(draft, blocks, inputs))
    return failures


def check_body(failures: list[CheckFailure], inputs: CheckInputs) -> list[str]:
    """The check line's body: AI text with stray digits is left out."""
    lines = []
    for failure in failures:
        if failure.ai_text and stray_digits(failure.ai_text, inputs.allowed_tokens):
            continue
        lines.append(failure.message)
    return lines


def check_inputs(ctx) -> CheckInputs:
    """The cards, the kind and the known words for this question."""
    from sqlalchemy import select

    from charie.chat.analyst.kb_view import KbView
    from charie.chat.analyst.notebook import Notebook, QuoteValue
    from charie.chat.analyst.render import values_for
    from charie.shared.db import session_scope
    from charie.shared.tables.chat import QueryRun
    from charie.shared.tables.sources import DocumentSection

    with session_scope() as session:
        kb = KbView.load(session, ctx.kb_version_id)
        book = Notebook.load(session, ctx.message_id, ctx.chat_id)
        items = book.items()
        style = (ctx.settings or {}).get("number_format", "short")
        values = values_for(items, style)
        titles = list(kb.titles().values())
        meanings = list(kb.meanings().values())
        names = kb.name_spellings() + list(kb.defaults())
        required = [
            details
            for details in kb.rules().values()
            if isinstance(details, dict) and details.get("rule_type") == "required_note"
        ]
        sections = []
        for item in items:
            if item.kind != "quote":
                continue
            quote = QuoteValue.model_validate(item.value)
            row = session.get(DocumentSection, quote.section_id)
            sections.append(
                {
                    "label": item.label,
                    "text": row.text_ if row is not None else "",
                    "document": quote.document,
                }
            )
        runs = [
            {"check_report": row.check_report or {}}
            for row in session.scalars(
                select(QueryRun).where(
                    QueryRun.message_id == ctx.message_id, QueryRun.status == "ok"
                )
            ).all()
        ]
        earlier = _earlier_numbers(session, ctx, values)
    texts = list(titles) + list(meanings) + names
    for item in items:
        texts.append(item.description)
        if item.kind == "quote":
            texts.append(QuoteValue.model_validate(item.value).text)
        elif item.kind == "table":
            for row in TableValue.model_validate(item.value).rows:
                texts.extend("" if cell is None else str(cell) for cell in row)
    understanding = ctx.understanding
    raw_meanings = getattr(understanding, "meanings", None) or []
    meanings = [
        meaning if isinstance(meaning, dict) else meaning.model_dump() for meaning in raw_meanings
    ]
    return CheckInputs(
        items=items,
        kind=understanding.kind if understanding is not None else "",
        meanings=meanings,
        allowed_tokens=mixed_tokens(texts),
        required_notes=required,
        section_texts=sections,
        earlier_numbers=earlier,
        query_runs=runs,
        question=ctx.question,
        data_through=ctx.data_through if hasattr(ctx, "data_through") else None,
        kb_version_id=ctx.kb_version_id,
        values=values,
    )


def _earlier_numbers(session, ctx, values: dict[str, str]) -> list[dict]:
    """Done earlier answers' ok numbers with their facts, in chat order."""
    from sqlalchemy import select

    from charie.chat.analyst.notebook import Notebook
    from charie.shared.tables.chat import Message

    earlier = []
    messages = session.scalars(
        select(Message)
        .where(
            Message.chat_id == ctx.chat_id,
            Message.role == "assistant",
            Message.status == "done",
            Message.id != ctx.message_id,
        )
        .order_by(Message.id)
    ).all()
    for message in messages:
        if not message.answer:
            continue
        book = Notebook.load(session, message.id, ctx.chat_id)
        for card in book.items():
            fact = (card.proof or {}).get("fact_key")
            if card.kind != "number" or not fact:
                continue
            raw = str(card.value.get("value"))
            earlier.append(
                {
                    "fact_key": fact,
                    "raw": raw,
                    "text": values.get(card.label, raw),
                    "description": card.description,
                    "data_through": _iso(message.data_through),
                    "kb_version": message.kb_version_id,
                    "message_id": message.id,
                }
            )
    return earlier
