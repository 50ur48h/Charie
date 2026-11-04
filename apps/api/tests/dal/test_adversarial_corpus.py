"""The adversarial corpus, run (plan §6 WP5.3, architecture Part 7.5)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from catalog_fixture import build_source

from charie.dal import executor
from charie.dal.errors import PolicyViolation, ViolationCode
from charie.dal.policy import SourcePolicy

CORPUS = Path(__file__).parent / "adversarial_corpus.yaml"

#: The corpus names dialects the way sqlglot does.
DIALECT_ENGINES = {"postgres": "pg", "tsql": "mssql"}


class RefusingConnector:
    """Records anything it is asked to run. It must never be asked."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    async def execute(self, query: Any, limits: Any) -> Any:
        self.seen.append(query.sql)
        raise AssertionError("the corpus sent a statement to a connector")

    async def aclose(self) -> None:
        return None

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(name)


def _cases() -> list[dict[str, Any]]:
    loaded = yaml.safe_load(CORPUS.read_text(encoding="utf-8"))
    return list(loaded["cases"])


def _expanded() -> list[tuple[str, str, str, str]]:
    """One entry per case per dialect it applies to: (id, dialect, sql, code)."""
    expanded: list[tuple[str, str, str, str]] = []
    for case in _cases():
        for dialect in case.get("dialects", list(DIALECT_ENGINES)):
            expanded.append((case["id"], dialect, case["sql"], case["expect"]))
    return expanded


CASES = _expanded()


@pytest.mark.parametrize(
    ("case_id", "dialect", "sql", "expected"),
    CASES,
    ids=[f"{case_id}[{dialect}]" for case_id, dialect, _, _ in CASES],
)
async def test_every_corpus_case_is_refused_and_never_sent(
    case_id: str, dialect: str, sql: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = build_source(DIALECT_ENGINES[dialect])
    connector = RefusingConnector()

    async def fake_policy(*_: object, **__: object) -> SourcePolicy:
        return source

    monkeypatch.setattr(executor, "source_policy", fake_policy)

    with pytest.raises(PolicyViolation) as caught:
        await executor.execute(
            org_id=uuid.uuid4(),
            data_source_id=uuid.uuid4(),
            sql=sql,
            connector=connector,  # pyright: ignore[reportArgumentType]
        )

    assert caught.value.code == expected, (
        f"{case_id} on {dialect} was refused as {caught.value.code}, "
        f"and the corpus says {expected}. If the new code is right, the change "
        f"that caused it is what needs justifying — not this line."
    )
    assert connector.seen == [], f"{case_id} reached a connector before being refused"


# --- guards on the corpus itself --------------------------------------------


def test_case_ids_are_unique() -> None:
    """Ids are how a failure is discussed and how history is kept."""
    ids = [case["id"] for case in _cases()]

    assert len(ids) == len(set(ids)), sorted({name for name in ids if ids.count(name) > 1})


def test_every_case_names_a_real_violation_code() -> None:
    known = {str(code) for code in ViolationCode}
    named = {case["expect"] for case in _cases()}

    assert named <= known, f"corpus expects codes that do not exist: {sorted(named - known)}"


def test_every_violation_code_has_at_least_one_attack() -> None:
    """A rule with no attack case is a rule nobody has tried to break."""
    exempt = {ViolationCode.TOO_COMPLEX, ViolationCode.UNRESOLVABLE}
    covered = {case["expect"] for case in _cases()}
    expected = {str(code) for code in ViolationCode} - {str(code) for code in exempt}

    assert expected <= covered, f"no corpus case produces: {sorted(expected - covered)}"


def test_the_corpus_only_grows() -> None:
    """Append-only is a review rule, and this is the part of it a machine can hold."""
    assert len(_cases()) >= 63, (
        "the corpus has shrunk. Cases are appended, never deleted — a case that "
        "has become wrong is evidence about the validator, not a nuisance."
    )
