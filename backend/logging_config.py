"""Central logging configuration for the Kopi backend."""

from __future__ import annotations

import logging
import os


def setup_logging() -> None:
    level_name = os.environ.get("KOPI_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s level=%(levelname)s logger=%(name)s %(message)s"
        )
    )
    root.addHandler(handler)
    root.setLevel(level)
