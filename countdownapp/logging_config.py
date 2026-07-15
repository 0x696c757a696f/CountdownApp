from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .resources import install_dir


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("countdownapp")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    log_dir = install_dir() / "Logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / "countdown.log",
            maxBytes=512_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    return logger
