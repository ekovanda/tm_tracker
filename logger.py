"""Structured JSON logging compatible with Google Cloud Logging and local stdout."""

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

RESERVED_RECORD_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects with GCP Cloud Logging severity."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "timestamp": datetime.now(UTC).isoformat(),
            "logger": record.name,
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            payload["exception"] = record.exc_text

        for key, value in record.__dict__.items():
            if key not in RESERVED_RECORD_ATTRS and not key.startswith("_"):
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = str(value)

        return json.dumps(payload)


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger streaming JSON records to standard output."""

    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_name, logging.INFO)
        logger.setLevel(log_level)
    return logger
