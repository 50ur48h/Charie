"""Charie calls only Meta models, and Meta offers no embedding model."""

from __future__ import annotations

from charie.knowledge import embeddings
from llm_fixture import build_settings


def test_no_embedder_is_built_so_search_is_by_wording() -> None:
    assert embeddings.get_embedder(build_settings()) is None
    assert embeddings.get_embedder() is None
