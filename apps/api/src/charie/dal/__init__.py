"""The data access layer — the only path from the agent to customer data."""

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
