"""Uniqueness proofs for overlapping splits (P09.3b).

Code-owned evidence: the builder deduplicates (base-key, dimension)
pairs only when this module certifies the path and the overlap. A
sample-only check never proves anything: only a full read-only scan
that completes may set `exact`, and anything inconclusive proves nothing.
"""

import datetime

from charie.shared.knowledge.query_builder import JoinLink, on
from charie.shared.knowledge.recipe import DimensionProof

NO_PATH = "no-tested-path"
AMBIGUOUS = "ambiguous-path"
NO_BASE_KEY = "no-base-key"
NO_OVERLAP = "no-overlap"
PARTIAL = "partial-coverage"
FAILED = "check-failed"
PROVEN = "proven"


def _hops(links: list[JoinLink]) -> list[JoinLink]:
    """Tested links between two different tables."""
    return [link for link in links if link.tested and link.from_table != link.to_table]


def _paths(links: list[JoinLink], start: str, goal: str) -> list[list[str]]:
    """Tested table paths from start to goal, stopping after two."""
    found: list[list[str]] = []
    frontier = [[start]]
    while frontier and len(found) < 2:
        path = frontier.pop(0)
        for link in _hops(links):
            if link.from_table == path[-1] and link.to_table not in path:
                extended = [*path, link.to_table]
            elif link.to_table == path[-1] and link.from_table not in path:
                extended = [*path, link.from_table]
            else:
                continue
            if extended[-1] == goal:
                found.append(extended)
            else:
                frontier.append(extended)
    return found


def _oriented(before: str, after: str, links: list[JoinLink]) -> JoinLink:
    """The hop from `before` to `after`, facing forward."""
    link = next(
        link for link in _hops(links) if {link.from_table, link.to_table} == {before, after}
    )
    if link.from_table == after:
        return link.model_copy(
            update={
                "from_table": link.to_table,
                "to_table": link.from_table,
                "from_column": link.to_column,
                "to_column": link.from_column,
                "multiplicity": (
                    "one_to_many" if link.multiplicity == "many_to_one" else "many_to_one"
                ),
            }
        )
    return link


def _from_sql(
    base_table: str, base_key_columns: list[str], path: list[str], links: list[JoinLink]
) -> tuple[str, str]:
    """The FROM clause for one table path, plus the key list."""
    aliases = [f"t{index}" for index in range(len(path))]
    clauses = [f"{base_table} AS {aliases[0]}"]
    for index, (before, after) in enumerate(zip(path, path[1:], strict=False)):
        oriented = _oriented(before, after, links)
        clauses.append(
            f"JOIN {after} AS {aliases[index + 1]} "
            f"ON {on(aliases[index], oriented, aliases[index + 1])}"
        )
    keys = ", ".join(f"{aliases[0]}.{column}" for column in base_key_columns)
    return " ".join(clauses), keys


def infer_unique_with(
    run,
    base_table: str,
    base_key_columns: list[str],
    dim_table: str,
    dim_column: str,
    links: list[JoinLink],
) -> tuple[DimensionProof | None, dict]:
    """A uniqueness proof for one dimension, or why there is none.

    `run` takes read-only SQL and returns its rows. Paths run over
    tested links only; two routes to the same table prove nothing.
    """
    bare: dict = {"reason": FAILED, "pairs": None, "keys": None, "total_keys": None}
    if not base_key_columns:
        return None, {**bare, "reason": NO_BASE_KEY}
    found = _paths(links, base_table, dim_table)
    if not found:
        return None, {**bare, "reason": NO_PATH}
    if len(found) > 1:
        return None, {**bare, "reason": AMBIGUOUS}
    from_sql, keys = _from_sql(base_table, base_key_columns, found[0], links)
    try:
        total = run(f"SELECT COUNT(DISTINCT ({keys})) AS total FROM {base_table} AS t0")[0][0]
        rows, joined = run(
            f"SELECT COUNT(*) AS rows, COUNT(DISTINCT ({keys})) AS keys FROM {from_sql}"
        )[0]
    except Exception:  # noqa: BLE001 (a timeout is inconclusive, never proof)
        return None, bare
    info = {"reason": FAILED, "pairs": rows, "keys": joined, "total_keys": total}
    if joined < total:
        return None, {**info, "reason": PARTIAL}
    if rows <= joined:
        return None, {**info, "reason": NO_OVERLAP}
    return (
        DimensionProof(
            base_table=base_table,
            base_key_columns=list(base_key_columns),
            dimension_expression=f"{dim_table.split('.')[-1]}.{dim_column}",
            link_keys=found[0][1:],
            checked_at=datetime.datetime.now(datetime.UTC).isoformat(),
            exact=True,
        ),
        {**info, "reason": PROVEN},
    )
