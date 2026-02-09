from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)

    # Store logs in per-user app data so installed builds can write without admin rights.
    log_dir = Path.home() / ".seedscope" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "seedscope.log"

    handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    handler.setFormatter(formatter)
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
