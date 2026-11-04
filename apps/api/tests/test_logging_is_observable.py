"""The application's loggers are still switched on after the session migrates."""

from __future__ import annotations

import logging
from types import ModuleType

import pytest
from sqlalchemy import URL

from charie.agent import runner, scheduler
from charie.auth import audit, jwt_validator
from charie.db import security_events

#: The modules whose log line is the record of last resort.
LAST_RESORT: tuple[ModuleType, ...] = (audit, security_events, jwt_validator, scheduler, runner)


def test_no_application_logger_is_disabled(migrated_database: URL) -> None:
    """`migrated_database` is requested for its side effect."""
    assert migrated_database is not None

    disabled = sorted(
        name
        for name, entry in logging.Logger.manager.loggerDict.items()
        if name.startswith("charie") and isinstance(entry, logging.Logger) and entry.disabled
    )

    assert not disabled, (
        f"{disabled} are disabled, so nothing they log can be observed and every "
        "assertion that they logged nothing is vacuous. The usual cause is a "
        "`logging.config.fileConfig`/`dictConfig` call with the default "
        "`disable_existing_loggers=True` — alembic/env.py is the one this "
        "repository already had (B-127)."
    )


@pytest.mark.parametrize("module", LAST_RESORT, ids=lambda m: m.__name__)
def test_each_last_resort_logger_actually_emits(
    module: ModuleType, migrated_database: URL, caplog: pytest.LogCaptureFixture
) -> None:
    """The other direction, and the one the control cases needed."""
    assert migrated_database is not None
    name = str(module.logger.name)  # pyright: ignore[reportAttributeAccessIssue]

    with caplog.at_level(logging.WARNING, logger=name):
        logging.getLogger(name).warning("probe from %s", module.__name__)

    assert caplog.records, (
        f"{name} emitted nothing. Its log line is the record kept when the "
        "durable write has already failed, so a silent logger there means a "
        "failure with no record anywhere."
    )
