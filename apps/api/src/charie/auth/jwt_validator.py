"""Bearer token validation."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import jwt

from charie.auth.jwks import JwksCache
from charie.auth.principal import Principal, TokenError

logger = logging.getLogger(__name__)

ALGORITHMS = ["RS256"]

#: Tolerance for clock drift between us and the identity provider.
LEEWAY_SECONDS = 30


def _first_string(claims: dict[str, Any], *names: str) -> str | None:
    for name in names:
        value = claims.get(name)
        if isinstance(value, str) and value:
            return value
    return None


class TokenValidator:
    def __init__(self, issuer: str | None, audience: str | Sequence[str], jwks: JwksCache) -> None:
        """``issuer`` pins the expected issuer; None means "trust discovery"."""
        self._issuer = issuer
        self._audience = audience
        self._jwks = jwks

    async def validate(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as error:
            raise TokenError("malformed", "Token header could not be read") from error

        if header.get("alg") not in ALGORITHMS:
            # Checked before touching the key material.
            raise TokenError("bad_algorithm", "Token algorithm is not permitted")

        kid = header.get("kid")
        if not kid:
            raise TokenError("missing_kid", "Token does not name a signing key")

        key = await self._jwks.key_for(kid)

        # After key_for, discovery has run at least once.
        expected_issuer = self._issuer or self._jwks.discovered_issuer
        if not expected_issuer:  # pragma: no cover - only if discovery is empty
            raise TokenError("no_issuer", "No issuer is configured or discoverable")

        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,  # type: ignore[arg-type]
                algorithms=ALGORITHMS,
                audience=self._audience,
                issuer=expected_issuer,
                leeway=LEEWAY_SECONDS,
                options={"require": ["exp", "iss", "aud", "sub"], "verify_signature": True},
            )
        except jwt.ExpiredSignatureError as error:
            raise TokenError("expired", "Token has expired") from error
        except jwt.ImmatureSignatureError as error:
            raise TokenError("not_yet_valid", "Token is not valid yet") from error
        except jwt.InvalidAudienceError as error:
            raise TokenError("bad_audience", "Token was issued for another audience") from error
        except jwt.InvalidIssuerError as error:
            raise TokenError("bad_issuer", "Token was issued by another issuer") from error
        except jwt.InvalidSignatureError as error:
            raise TokenError("bad_signature", "Token signature does not verify") from error
        except jwt.MissingRequiredClaimError as error:
            raise TokenError("missing_claim", "Token is missing a required claim") from error
        except jwt.PyJWTError as error:
            raise TokenError("invalid", "Token is not valid") from error

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise TokenError("missing_claim", "Token has no usable subject")

        # Entra populates one of these depending on tenant type and which optional claims the...
        email = _first_string(claims, "email", "preferred_username", "upn")
        name = _first_string(claims, "name", "given_name")
        if email is None:
            # Names only, never values: a token's claim values are personal data and some are...
            logger.warning(
                "token carried no email-like claim; claims present: %s",
                ", ".join(sorted(claims)),
            )

        return Principal(subject=subject, email=email, name=name)
