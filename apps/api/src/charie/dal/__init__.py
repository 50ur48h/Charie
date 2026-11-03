"""The data access layer — the only path from the agent to customer data.

Architecture Part 7.1: everything the model influences arrives here as text and
leaves as a ``ValidatedQuery`` or a refusal. Nothing else in the application may
build one, and no connector will run anything else.

``validator`` decides; ``policy`` loads what it decides against; ``executor``
runs it and ``masking`` bounds what comes back. Persisting the record of a run —
``query_executions``, the stored artifact and the audit row — is WP5.2b.
"""

from __future__ import annotations

from charie.dal.errors import PolicyViolation, ViolationCode
from charie.dal.executor import Execution
from charie.dal.masking import MaskedFrame
from charie.dal.policy import SourcePolicy, source_policy
from charie.dal.service import run
from charie.dal.validator import ColumnRef, Projection, TableRef, Validated, validate

__all__ = [
    "ColumnRef",
    "Execution",
    "MaskedFrame",
    "PolicyViolation",
    "Projection",
    "SourcePolicy",
    "TableRef",
    "Validated",
    "ViolationCode",
    "run",
    "source_policy",
    "validate",
]
