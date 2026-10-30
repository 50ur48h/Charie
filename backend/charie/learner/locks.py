"""One critical section for learning runs and drafts.

Starts, resumes and draft creation race across requests, workers and tabs:
each reads "is there an active run / an open draft" and then inserts. The
fix is a transaction-scoped Postgres advisory lock taken before the read
and held until commit or rollback, so the read-check-insert sequence is
atomic. One blocked transaction waits for the holder instead of inserting
a duplicate; a stuck holder resolves to a clear conflict, never a hang.
"""

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

# Arbitrary stable key (ASCII "LEARN"); nothing else here takes advisory locks.
LEARNING_RUN_LOCK_KEY = 0x4C4541524E

LOCK_TIMEOUT = "10s"


class RunActiveError(Exception):
    """A learning run is already going (or another request is starting one)."""


def serialize_learning_runs(session: Session) -> None:
    """Hold the learning lock for this transaction; refuse when it is stuck.

    Raises `RunActiveError` when another transaction holds the lock past
    `LOCK_TIMEOUT`, instead of blocking the request forever.
    """
    session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
    try:
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LEARNING_RUN_LOCK_KEY})
    except OperationalError as err:
        if getattr(getattr(err, "orig", None), "pgcode", None) == "55P03":
            raise RunActiveError(
                "Another request is changing the learning run. Try again."
            ) from err
        raise
