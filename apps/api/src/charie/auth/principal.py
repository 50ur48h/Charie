"""Who the caller is, according to the identity provider."""

from __future__ import annotations

from dataclasses import dataclass


class TokenError(Exception):
    """A bearer token that cannot be trusted."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    email: str | None = None
    name: str | None = None
