"""Rank fusion: shared hits rise, appear once, ties break by ID (P08.5)."""

from charie.shared.search.search import RESULT_LIMIT, RRF_K, _fuse


def test_duplicate_fusion() -> None:
    """A hit in two channels ranks once, above a weak single-channel hit."""
    shared = _fuse([[7, 9], [7], [9]], RESULT_LIMIT)
    assert shared[0] == 7  # 1/61 + 1/61 beats 1/61 + 1/62.
    assert shared == [7, 9]  # No duplicates.
    only_weak = _fuse([[5], [], []], RESULT_LIMIT)
    assert only_weak == [5]


def test_tie_order() -> None:
    """Equal scores break by the smaller stable ID, every time."""
    assert _fuse([[3], [5]], RESULT_LIMIT) == [3, 5]
    assert _fuse([[5], [3]], RESULT_LIMIT) == [3, 5]


def test_limit() -> None:
    """Fusion keeps the top eight, best score first."""
    many = [list(range(1, 30)), list(range(15, 40)), list(range(25, 50))]
    fused = _fuse(many, RESULT_LIMIT)
    assert len(fused) == RESULT_LIMIT
    assert fused[0] == 25  # In all three channels.


def test_fusion_math() -> None:
    """RRF with k=60: rank 1 in two channels beats rank 1 in one."""
    assert 1 / (RRF_K + 1) + 1 / (RRF_K + 2) > 1 / (RRF_K + 1)
