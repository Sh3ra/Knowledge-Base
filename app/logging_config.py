"""Centralized logging configuration (stdout + optional file)."""

import logging
from pathlib import Path

from app.config import LOG_FILE


def configure_logging() -> None:
    """Configure root logger: level, format, and optional file handler."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger(__name__)
    if LOG_FILE:
        try:
            Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
            fh.setLevel(logging.INFO)
            fh.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
            )
            logging.getLogger().addHandler(fh)
            logger.info("Logging to file: %s", LOG_FILE)
        except OSError as e:
            logger.warning(
                "Could not open log file %s: %s. Logs go to stdout only.", LOG_FILE, e
            )
