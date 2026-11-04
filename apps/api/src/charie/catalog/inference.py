"""Join relationships a database does not declare, found by measuring (B-145)."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from charie.connectors.base import ColumnInfo, Connector, ExecLimits, TableRef
from charie.connectors.introspection import (
    POSTGRES,
    pg_column_stats,
    pg_orphan_count,
    tsql_column_stats,
    tsql_orphan_count,
)

#: The SQL lives in `introspection`, not here.

#: Below this the check will not rely on an edge (`capability.MIN_CONFIDENCE`).
_STRONG = 0.95
_ADEQUATE = 0.92
_TOO_LITTLE_DATA = 0.80

#: How many non-null child values make containment mean something.
_CONFIDENT_ROWS = 100
_MINIMUM_ROWS = 10

#: The work cap. Each candidate costs one pass over the child column's distinct values.
MAX_PAIRS_CHECKED = 400
#: Raised from 120 once the containment scan started walking distinct values instead of rows.
BUDGET_SECONDS = 240.0

#: How much of the parent the child has to use.
COVERAGE_FLOOR = 0.9

#: A column contained in this many different parent tables is telling you its domain is generic.
MAX_PARENTS_PER_CHILD_COLUMN = 12


@dataclass(frozen=True, slots=True)
class ColumnStats:
    """What one column is, measured exactly rather than sampled."""

    schema: str
    table: str
    name: str
    rows: int
    non_null: int
    distinct: int

    @property
    def unique(self) -> bool:
        """Every value that exists, exists once."""
        return self.non_null > 1 and self.distinct == self.non_null

    @property
    def repeats(self) -> bool:
        """Some value occurs more than once — the fan-in a join is made of."""
        return self.non_null > self.distinct


@dataclass(frozen=True, slots=True)
class InferredKey:
    """One edge, and the measurements that justify it."""

    from_schema: str
    from_table: str
    from_column: str
    to_schema: str
    to_table: str
    to_column: str
    confidence: float
    evidence: dict[str, object]

    @property
    def constraint_name(self) -> str:
        """A name that says where it came from, since no constraint exists."""
        return f"inferred_{self.from_table}_{self.from_column}_{self.to_table}_{self.to_column}"[
            :255
        ]


@dataclass(slots=True)
class InferenceReport:
    """What was found, and what was not looked at."""

    keys: tuple[InferredKey, ...] = ()
    pairs_considered: int = 0
    pairs_measured: int = 0
    stopped_early: bool = False
    notes: list[str] = field(default_factory=list[str])


def _family(data_type: str) -> str:
    """A coarse type family, used only to skip pairs that cannot possibly join."""
    t = data_type.lower()
    if any(k in t for k in ("int", "serial", "numeric", "decimal", "real", "double", "float")):
        return "number"
    if any(k in t for k in ("timestamp", "date", "time")):
        return "temporal"
    if any(k in t for k in ("bool",)):
        return "boolean"
    return "text"


async def _measure_columns(
    connector: Connector,
    dialect: str,
    table: TableRef,
    columns: Sequence[ColumnInfo],
) -> tuple[ColumnStats, ...]:
    """Row count, non-null count and distinct count for every column, in one query."""
    if not columns:
        return ()

    build = pg_column_stats if dialect == POSTGRES else tsql_column_stats
    query = build(table.schema, table.name, [column.name for column in columns])
    frame = await connector.execute(query, ExecLimits(max_rows=1, timeout_seconds=60.0))
    if not frame.rows:
        return ()

    row = frame.rows[0]

    def count_at(position: int) -> int:
        """A count out of an untyped result row."""
        value = row[position] if position < len(row) else None
        return int(value) if isinstance(value, (int, float)) else 0

    total = count_at(0)
    stats: list[ColumnStats] = []
    for index, column in enumerate(columns):
        non_null = count_at(1 + index * 2)
        distinct = count_at(2 + index * 2)
        stats.append(
            ColumnStats(
                schema=column.schema,
                table=column.table,
                name=column.name,
                rows=total,
                non_null=non_null,
                distinct=distinct,
            )
        )
    return tuple(stats)


async def _orphan_count(
    connector: Connector,
    dialect: str,
    child: ColumnStats,
    parent: ColumnStats,
) -> int:
    """How many non-null child values have no match in the parent."""
    build = pg_orphan_count if dialect == POSTGRES else tsql_orphan_count
    query = build(child.schema, child.table, child.name, parent.schema, parent.table, parent.name)
    frame = await connector.execute(query, ExecLimits(max_rows=1, timeout_seconds=60.0))
    if not frame.rows:
        return -1
    value = frame.rows[0][0]
    # Not a number means the test did not run.
    return int(value) if isinstance(value, (int, float)) else -1


def _child_rows(key: InferredKey) -> int:
    """How much data stood behind an edge, read back out of its evidence."""
    value = key.evidence.get("child_non_null")
    return value if isinstance(value, int) else 0


def _confidence(child: ColumnStats) -> float:
    """How much the containment result is worth, given how much was checked."""
    if child.non_null >= _CONFIDENT_ROWS:
        return _STRONG
    if child.non_null >= _MINIMUM_ROWS:
        return _ADEQUATE
    return _TOO_LITTLE_DATA


async def infer_relationships(
    connector: Connector,
    tables: Sequence[TableRef],
    columns_by_table: dict[tuple[str, str], tuple[ColumnInfo, ...]],
    declared: Sequence[tuple[str, str, str, str]],
    *,
    dialect: str = POSTGRES,
    max_pairs: int = MAX_PAIRS_CHECKED,
    budget_seconds: float = BUDGET_SECONDS,
) -> InferenceReport:
    """Measure the database for join relationships it does not declare."""
    started = time.monotonic()
    report = InferenceReport()

    # Phase 1 — what every column is. One scan per table.
    stats: list[ColumnStats] = []
    for table in tables:
        if time.monotonic() - started > budget_seconds:
            report.stopped_early = True
            report.notes.append("stopped before measuring every table")
            break
        columns = columns_by_table.get((table.schema, table.name), ())
        try:
            stats.extend(await _measure_columns(connector, dialect, table, columns))
        except Exception:
            # A table that will not aggregate — a permission, an exotic type.
            report.notes.append(f"could not measure {table.schema}.{table.name}")

    parents = [s for s in stats if s.unique]
    already = {(f.lower(), fc.lower(), t.lower(), tc.lower()) for f, fc, t, tc in declared}

    # Phase 2 — pairs worth measuring. Cheap arithmetic only; no scans yet.
    candidates: list[tuple[ColumnStats, ColumnStats]] = []
    for parent in parents:
        p_family = _family(
            next(
                (
                    c.data_type
                    for c in columns_by_table.get((parent.schema, parent.table), ())
                    if c.name == parent.name
                ),
                "text",
            )
        )
        for child in stats:
            if (child.schema, child.table) == (parent.schema, parent.table):
                continue
            if child.non_null == 0:
                continue
            # A contained child cannot hold more distinct values than its parent.
            if child.distinct > parent.distinct:
                continue
            # ...nor meaningfully fewer. `COVERAGE_FLOOR` is where the first live run went wrong.
            if child.distinct < parent.distinct * COVERAGE_FLOOR:
                continue
            # ...and the child has to actually fan in.
            if not child.repeats:
                continue
            c_family = _family(
                next(
                    (
                        c.data_type
                        for c in columns_by_table.get((child.schema, child.table), ())
                        if c.name == child.name
                    ),
                    "text",
                )
            )
            if c_family != p_family:
                continue
            pair_key = (
                child.table.lower(),
                child.name.lower(),
                parent.table.lower(),
                parent.name.lower(),
            )
            if pair_key in already:
                continue
            candidates.append((child, parent))

    report.pairs_considered = len(candidates)

    # Phase 3 — grouped by child column, because that is the unit ambiguity is about.
    by_child: dict[tuple[str, str, str], list[tuple[ColumnStats, ColumnStats]]] = {}
    for child, parent in candidates:
        by_child.setdefault((child.schema, child.table, child.name), []).append((child, parent))

    ordered = sorted(
        by_child.items(),
        key=lambda item: item[1][0][0].non_null,
        reverse=True,
    )

    found: list[InferredKey] = []
    measurements = 0
    for _, options in ordered:
        if time.monotonic() - started > budget_seconds or measurements >= max_pairs:
            report.stopped_early = True
            report.notes.append("stopped before measuring every candidate")
            break

        child = options[0][0]
        parent_tables = {(p.schema, p.table) for _, p in options}
        if len(parent_tables) > MAX_PARENTS_PER_CHILD_COLUMN:
            report.notes.append(
                f"skipped {child.table}.{child.name}: fits {len(parent_tables)} tables, "
                f"so containment identifies none of them"
            )
            continue

        # Best surviving candidate per parent table.
        best: dict[tuple[str, str], tuple[ColumnStats, float]] = {}
        for _, parent in options:
            try:
                orphans = await _orphan_count(connector, dialect, child, parent)
            except Exception as error:
                # A pair that will not measure costs its own edge and nothing else.
                report.notes.append(
                    f"could not test {child.table}.{child.name} -> "
                    f"{parent.table}.{parent.name}: {type(error).__name__}"
                )
                continue
            measurements += 1
            if orphans != 0:
                continue
            coverage = child.distinct / parent.distinct if parent.distinct else 0.0
            key = (parent.schema, parent.table)
            if key not in best or coverage > best[key][1]:
                best[key] = (parent, coverage)

        if not best:
            continue
        ranked = sorted(best.values(), key=lambda item: item[1], reverse=True)
        if len(ranked) > 1 and ranked[0][1] <= ranked[1][1]:
            report.notes.append(
                f"no edge for {child.table}.{child.name}: contained in "
                f"{ranked[0][0].table} and {ranked[1][0].table} equally well"
            )
            continue

        parent, coverage = ranked[0]
        found.append(
            InferredKey(
                from_schema=child.schema,
                from_table=child.table,
                from_column=child.name,
                to_schema=parent.schema,
                to_table=parent.table,
                to_column=parent.name,
                confidence=_confidence(child),
                evidence={
                    "method": "exact",
                    "measured_at": datetime.now(UTC).isoformat(),
                    "parent_rows": parent.rows,
                    "parent_non_null": parent.non_null,
                    "parent_distinct": parent.distinct,
                    "parent_unique": parent.unique,
                    "child_rows": child.rows,
                    "child_non_null": child.non_null,
                    "child_distinct": child.distinct,
                    "orphans": 0,
                    "coverage": round(coverage, 6),
                    # What else fitted, and how well.
                    "runners_up": [
                        {"table": other.table, "column": other.name, "coverage": round(score, 6)}
                        for other, score in ranked[1:4]
                    ],
                },
            )
        )

    report.pairs_measured = measurements
    # One edge per table pair.
    seen: set[frozenset[str]] = set()
    deduped: list[InferredKey] = []
    for key in sorted(found, key=_child_rows, reverse=True):
        pair = frozenset((key.from_table, key.to_table))
        if pair in seen:
            continue
        seen.add(pair)
        deduped.append(key)
    found = deduped

    report.keys = tuple(found)
    return report


__all__ = [
    "BUDGET_SECONDS",
    "COVERAGE_FLOOR",
    "MAX_PAIRS_CHECKED",
    "MAX_PARENTS_PER_CHILD_COLUMN",
    "ColumnStats",
    "InferenceReport",
    "InferredKey",
    "infer_relationships",
]
