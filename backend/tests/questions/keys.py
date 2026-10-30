"""Run a question's answer key on the practice database (read-only)."""

from decimal import Decimal

from charie.shared.config import require_env
from charie.shared.connectors.base import ConnectorError
from charie.shared.connectors.postgres import PostgresConnector
from charie.shared.safety.catalog import Catalog
from charie.shared.safety.list_tables import list_tables
from tests.questions.format import Question


class AnswerKeyError(Exception):
    """The key query didn't return one row per expected number, in plain words."""


def run_answer_key(question: Question) -> list[Decimal]:
    """Run the key through the read-only checked connector; one value per number."""
    if not question.answer_key_sql.strip():
        raise AnswerKeyError(f"{question.id} has no answer key.")
    connector = PostgresConnector.from_url(require_env("PRACTICE_DB_URL"))
    catalog = Catalog(tables=list_tables(connector))
    try:
        result = connector.run_checked(question.answer_key_sql, catalog)
    except ConnectorError as err:
        raise AnswerKeyError(f"{question.id}: the query failed: {err}") from err
    if result.row_count != 1 or len(result.columns) != len(question.expect.numbers):
        raise AnswerKeyError(
            f"{question.id}: the key must return exactly 1 row with "
            f"{len(question.expect.numbers)} columns."
        )
    values: list[Decimal] = []
    for raw in result.rows[0]:
        if raw is None:
            raise AnswerKeyError(f"{question.id}: the key returned an empty value.")
        try:
            values.append(Decimal(str(raw)))
        except Exception:
            raise AnswerKeyError(f"{question.id}: the key returned `{raw}`.") from None
    return values


def key_matches(question: Question, values: list[Decimal]) -> bool:
    """Every value lands within its tolerance of the stored number."""
    if len(values) != len(question.expect.numbers):
        return False
    return all(
        abs(actual - expected.value) <= expected.tolerance
        for actual, expected in zip(values, question.expect.numbers, strict=True)
    )
