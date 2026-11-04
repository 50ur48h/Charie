"""Can this API reach that address at all?"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime

from charie.connectors.sanitizer import sanitize_exception

__all__ = ["DEFAULT_TIMEOUT_SECONDS", "Reachability", "check_reachable"]

#: Short on purpose: a request is waiting on this.
DEFAULT_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class Reachability:
    """What the probe saw. ``detail`` is already sanitized and safe to return."""

    reachable: bool
    detail: str
    checked_at: datetime


async def check_reachable(
    *, host: str, port: int, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
) -> Reachability:
    """Open a TCP connection to ``host:port`` and close it again."""
    now = datetime.now(UTC)

    try:
        async with asyncio.timeout(timeout_seconds):
            _, writer = await asyncio.open_connection(host, port)
    except TimeoutError:
        return Reachability(
            reachable=False,
            detail=(
                f"No answer within {timeout_seconds:.0f}s. Check the host and port, "
                "and whether a firewall allows this service to reach them."
            ),
            checked_at=now,
        )
    except OSError as error:
        # ConnectionRefusedError, socket.gaierror and friends.
        return Reachability(
            reachable=False,
            detail=sanitize_exception(error, known=(host,)),
            checked_at=now,
        )

    writer.close()
    # The probe already has its answer; a tidy close is courtesy to the far end.
    with contextlib.suppress(OSError):
        await writer.wait_closed()

    return Reachability(
        reachable=True,
        detail=(
            "The address accepted a connection. Credentials and read-only "
            "verification are checked once the connector ships (WP3.2)."
        ),
        checked_at=now,
    )
