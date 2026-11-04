"""Fixtures for the LLM suite."""

from __future__ import annotations

import pytest

from charie.config import Settings
from llm_fixture import build_settings


@pytest.fixture
def llm_settings() -> Settings:
    return build_settings()
