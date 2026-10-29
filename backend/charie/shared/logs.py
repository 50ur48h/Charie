"""Plain-English logging. Never log passwords, keys or cookies."""

import logging


def setup_logging() -> None:
    """Log INFO lines as `time level name: message`."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
