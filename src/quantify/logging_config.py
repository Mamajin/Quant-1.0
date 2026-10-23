"""Structured JSON logging with rotation (manual sec 4.6: 'Structured JSON
logging; log rotation; alert on pipeline failure (Telegram); a simple local
metrics page'). The console stays human-readable; the rotated file is JSON
so it's machine-parseable if you ever feed it into a log aggregator.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from pathlib import Path

from .config import REPO_ROOT

LOG_DIR = REPO_ROOT / "data" / "logs"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO, log_file: str = "quantify.log",
                       log_dir: Path | None = None) -> None:
    """Idempotent: safe to call from every entrypoint (CLI, scheduler, API)
    without stacking duplicate handlers if something imports more than one."""
    root = logging.getLogger()
    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        return
    root.setLevel(level)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(console)

    target_dir = log_dir or LOG_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        target_dir / log_file, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(JsonFormatter())
    root.addHandler(file_handler)
