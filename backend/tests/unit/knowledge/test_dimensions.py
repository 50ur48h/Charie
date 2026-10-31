"""Uniqueness proofs for overlapping splits (P09.3b, unit)."""

from charie.learner.steps.business_numbers import (
    DimensionCandidate,
    _validate_candidate,
)
from charie.shared.knowledge.dimensions import (
    AMBIGUOUS,
    FAILED,
    NO_OVERLAP,
    NO_PATH,
    PROVEN,
    infer_unique_with,
)
from charie.shared.knowledge.query_builder import JoinLink

LINK = JoinLink(
    from_table="shop.orders",
    to_table="shop.restaurants",
    from_column="restaurant_id",
    to_column="id",
    multiplicity="many_to_one",
    tested=True,
)

BRIDGE = JoinLink(
    from_table="shop.sessions",
    to_table="shop.session_channels",
    from_column="id",
    to_column="session_id",
    multiplicity="one_to_many",
    tested=True,
)

KNOWN = {
    ("shop", "orders", "status"): {"type": "text"},
    ("shop", "orders", "created_at"): {"type": "timestamp with time zone"},
    ("shop", "restaurants", "name"): {"type": "text"},
}


def _candidate(**overrides) -> DimensionCandidate:
    data = {"term": "term.net_sales", "table": "shop.orders", "column": "status"}
    data.update(overrides)
    return DimensionCandidate(**data)


def test_real_columns_only() -> None:
    checked, _ = _validate_candidate(_candidate(), True, KNOWN)
    assert checked is not None
    assert checked["column"] == "status"
    assert _validate_candidate(_candidate(table="shop.missing"), True, KNOWN)[0] is None
    assert _validate_candidate(_candidate(column="missing"), True, KNOWN)[0] is None
    assert _validate_candidate(_candidate(), False, KNOWN)[0] is None
    assert _validate_candidate(_candidate(grain="century"), True, KNOWN)[0] is None
    assert _validate_candidate(_candidate(grain="month"), True, KNOWN)[0] is None
    checked, _ = _validate_candidate(_candidate(column="created_at", grain="month"), True, KNOWN)
    assert checked is not None
    assert _validate_candidate(_candidate(label_column="missing"), True, KNOWN)[0] is None
    checked, _ = _validate_candidate(
        _candidate(table="shop.restaurants", column="name", label_column="name"),
        True,
        KNOWN,
    )
    assert checked is not None


def test_composite_key() -> None:
    seen = []

    def run(sql: str):
        seen.append(sql)
        if sql.startswith("SELECT COUNT(DISTINCT"):
            return [(2,)]
        return [(4, 2)]

    proof, info = infer_unique_with(run, "shop.pairs", ["a", "b"], "shop.tags", "tag", [LINK])
    assert proof is None
    assert info["reason"] == NO_PATH
    pair_link = JoinLink(
        from_table="shop.pairs",
        to_table="shop.tags",
        from_column="id",
        to_column="pair_id",
        multiplicity="one_to_many",
        tested=True,
    )
    proof, info = infer_unique_with(run, "shop.pairs", ["a", "b"], "shop.tags", "tag", [pair_link])
    assert proof is not None
    assert info["reason"] == PROVEN
    assert proof.base_key_columns == ["a", "b"]
    assert proof.link_keys == ["shop.tags"]
    assert proof.exact is True
    assert any("COUNT(DISTINCT (t0.a, t0.b))" in sql for sql in seen)


def test_timeout_unproven() -> None:
    def run(sql: str):
        raise TimeoutError("The customer database timed out.")

    proof, info = infer_unique_with(
        run, "shop.sessions", ["id"], "shop.session_channels", "channel", [BRIDGE]
    )
    assert proof is None
    assert info["reason"] == FAILED


def test_ambiguous_path_refused() -> None:
    detour = JoinLink(
        from_table="shop.sessions",
        to_table="shop.orders",
        from_column="id",
        to_column="session_id",
        multiplicity="many_to_one",
        tested=True,
    )
    hop = JoinLink(
        from_table="shop.orders",
        to_table="shop.session_channels",
        from_column="id",
        to_column="session_id",
        multiplicity="many_to_one",
        tested=True,
    )

    def run(sql: str):  # pragma: no cover (ambiguity stops before SQL)
        raise AssertionError(f"Should not query: {sql}")

    proof, info = infer_unique_with(
        run, "shop.sessions", ["id"], "shop.session_channels", "channel", [BRIDGE, detour, hop]
    )
    assert proof is None
    assert info["reason"] == AMBIGUOUS


def test_no_overlap_needs_no_proof() -> None:
    def run(sql: str):
        if sql.startswith("SELECT COUNT(DISTINCT"):
            return [(3,)]
        return [(3, 3)]

    proof, info = infer_unique_with(run, "shop.orders", ["id"], "shop.restaurants", "name", [LINK])
    assert proof is None
    assert info["reason"] == NO_OVERLAP
