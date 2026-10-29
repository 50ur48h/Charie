"""The shared AI layer: every AI call goes through here (architecture 03)."""

from charie.shared.ai.client import AiClient, get_ai

__all__ = ["AiClient", "get_ai"]
