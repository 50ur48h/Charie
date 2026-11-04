"""How the data access layer refuses (architecture Part 7.4, 7.5)."""

from __future__ import annotations

from enum import StrEnum

__all__ = ["PolicyViolation", "ViolationCode"]


class ViolationCode(StrEnum):
    """Every way the validator can say no. Append-only in spirit."""

    #: The statement did not parse in the data source's own dialect.
    PARSE_ERROR = "parse_error"
    #: Nothing to run: empty string, or only a comment.
    EMPTY_STATEMENT = "empty_statement"
    #: More than one statement.
    MULTIPLE_STATEMENTS = "multiple_statements"
    #: The top-level statement is not a SELECT (or an EXPLAIN of one).
    STATEMENT_NOT_READ_ONLY = "statement_not_read_only"
    #: A write, a schema change or transaction control found anywhere in the tree.
    WRITE_OPERATION = "write_operation"
    #: A schema the engine keeps for itself.
    SYSTEM_SCHEMA = "system_schema"
    #: A function on the deny list: file access, sleeps, remote execution.
    DENIED_FUNCTION = "denied_function"
    #: A function this validator cannot identify.
    UNKNOWN_FUNCTION = "unknown_function"
    #: A table-valued function where a table belongs.
    TABLE_FUNCTION = "table_function"
    #: A three-part name reaching for another database on the same server.
    CROSS_DATABASE = "cross_database"
    #: No such table in this data source's catalog. The anti-hallucination gate.
    UNKNOWN_TABLE = "unknown_table"
    #: The name matches catalogued tables in more than one schema.
    AMBIGUOUS_TABLE = "ambiguous_table"
    #: No such column on any table this query reads.
    UNKNOWN_COLUMN = "unknown_column"
    #: The name exists on more than one of this query's tables.
    AMBIGUOUS_COLUMN = "ambiguous_column"
    #: An Admin marked this column unqueryable.
    DENIED_COLUMN = "denied_column"
    #: Too long, or nested too deeply to be checked without running the validator itself out of...
    TOO_COMPLEX = "too_complex"
    #: The query parsed and broke no rule, and still could not be resolved against the catalog.
    UNRESOLVABLE = "unresolvable"


# N818 wants an `Error` suffix. The name is `PolicyViolation` in the plan.
class PolicyViolation(Exception):  # noqa: N818
    """A query that will not be run, and the reason, in both languages."""

    def __init__(self, code: ViolationCode, message: str, *, subject: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        #: The identifier the refusal is about, when there is one: a table name, a column.
        self.subject = subject

    def as_dict(self) -> dict[str, str | None]:
        """The shape the agent, the audit row and the API error body all use."""
        return {"code": str(self.code), "message": self.message, "subject": self.subject}

    def __repr__(self) -> str:
        return f"PolicyViolation(code={self.code!r}, subject={self.subject!r})"
