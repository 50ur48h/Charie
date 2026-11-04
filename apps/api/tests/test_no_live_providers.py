"""The guard that stops a test spending real money (B-040)."""

from __future__ import annotations

import pytest

from charie.llm import registry
from charie.llm.base import Completion, LLMRequest, ProviderCaps


class _PretendLiveProvider:
    """Claims not to be a stub, and would be a real API in production."""

    def capabilities(self) -> ProviderCaps:
        return ProviderCaps(name="pretend-live", supports_response_schema=True, is_stub=False)

    async def complete(self, request: LLMRequest) -> Completion:  # pragma: no cover - never reached
        raise AssertionError("the guard should have stopped this before any call")

    async def aclose(self) -> None:  # pragma: no cover - never reached
        return None


@pytest.fixture
def pretend_live() -> object:
    registry.register_provider("pretend-live", _PretendLiveProvider)
    try:
        yield
    finally:
        registry.clear_provider_cache()


def test_asking_for_a_non_stub_provider_is_refused(
    pretend_live: object, expected_live_provider_refusal: None
) -> None:
    """The first mechanism: it raises, so nothing leaves the machine."""
    with pytest.raises(RuntimeError, match="live provider"):
        registry.get_provider("pretend-live")


def test_the_refusal_says_how_to_fix_it(
    pretend_live: object, expected_live_provider_refusal: None
) -> None:
    """A guard whose message does not say what to do next gets worked around."""
    with pytest.raises(RuntimeError) as raised:
        registry.get_provider("pretend-live")

    message = str(raised.value)
    assert "build_settings()" in message
    assert "live_provider" in message


def test_a_stub_provider_passes_straight_through(fake_llm: object) -> None:
    """The guard must be invisible to the suite it protects."""
    provider = registry.get_provider("fake")

    assert provider.capabilities().is_stub


@pytest.mark.live_provider
def test_a_marked_test_may_use_a_live_provider(pretend_live: object) -> None:
    """The opt-out exists so the guard is a control rather than an obstacle."""
    provider = registry.get_provider("pretend-live")

    assert provider.capabilities().is_stub is False
