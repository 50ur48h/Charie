"""One connection to the customer database, held for the length of a run."""

from __future__ import annotations

import uuid
from contextlib import suppress

from charie.connectors.base import Connector


class ConnectionLease:
    """A connector built at most once per run, and closed with it."""

    __slots__ = ("_connector", "_data_source_id", "_org_id")

    def __init__(self, org_id: uuid.UUID, data_source_id: uuid.UUID) -> None:
        self._org_id = org_id
        self._data_source_id = data_source_id
        self._connector: Connector | None = None

    async def connector(self) -> Connector:
        """The run's connection, opening it on first use."""
        if self._connector is None:
            # Imported here rather than at module scope.
            from charie.datasources import service as datasources

            view = await datasources.get_data_source(self._org_id, self._data_source_id)
            self._connector = await datasources.connector_for_view(view)
        return self._connector

    def matches(self, org_id: uuid.UUID, data_source_id: uuid.UUID) -> bool:
        """Whether this lease is for the source being asked about."""
        return self._org_id == org_id and self._data_source_id == data_source_id

    async def forget(self) -> None:
        """Drop the connection, so the next query builds a fresh one."""
        connector, self._connector = self._connector, None
        if connector is not None:
            # Closing an already-broken socket can itself raise.
            with suppress(Exception):
                await connector.aclose()

    async def aclose(self) -> None:
        """Close the run's connection. Safe to call when none was ever opened."""
        await self.forget()
