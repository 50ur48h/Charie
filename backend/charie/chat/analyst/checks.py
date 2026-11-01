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


@dataclass
class CheckInputs:
    """Everything the checks read: the cards, the kind, the known words."""

    items: list = field(default_factory=list)
    kind: str = ""
    allowed_tokens: list[str] = field(default_factory=list)
    required_notes: list = field(default_factory=list)
    section_texts: list = field(default_factory=list)
    earlier_numbers: list = field(default_factory=list)


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
    first = blocks[0].get("type") if blocks else ""
    if first == "reading":
        return []
    return [
        CheckFailure(
            check=10,
            name="missing_reading",
            message="Block 1: The question was vague, so the answer must start "
            'with "I read this as…".',
            where="Block 1",
        )
    ]


#: Every check in order, each reading only the draft, the blocks and the inputs.
CHECKS = [
    _check_1_typed_numbers,
    _check_2_labels,
    _check_3_proof,
    _check_4_careful_words,
    _check_5_trends,
    _check_10_reading,
]


def run_checks(draft, blocks: list[dict], inputs: CheckInputs) -> list[CheckFailure]:
    """Every failure in check order."""
    failures = []
    for check in CHECKS:
        failures.extend(check(draft, blocks, inputs))
    return failures


def check_inputs(ctx) -> CheckInputs:
    """The cards, the kind and the known words for this question."""
    from charie.chat.analyst.kb_view import KbView
    from charie.chat.analyst.notebook import Notebook
    from charie.shared.db import session_scope

    with session_scope() as session:
        kb = KbView.load(session, ctx.kb_version_id)
        book = Notebook.load(session, ctx.message_id, ctx.chat_id)
        items = book.items()
        titles = list(kb.titles().values())
        meanings = list(kb.meanings().values())
        names = kb.name_spellings() + list(kb.defaults())
    texts = list(titles) + list(meanings) + names
    for item in items:
        texts.append(item.description)
        if item.kind == "quote":
            from charie.chat.analyst.notebook import QuoteValue

            texts.append(QuoteValue.model_validate(item.value).text)
        elif item.kind == "table":
            for row in TableValue.model_validate(item.value).rows:
                texts.extend("" if cell is None else str(cell) for cell in row)
    return CheckInputs(
        items=items,
        kind=ctx.understanding.kind if ctx.understanding is not None else "",
        allowed_tokens=mixed_tokens(texts),
    )
