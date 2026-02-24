from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from app.context import get_correlation_id


_BASE_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__.keys())
_KNOWN_FIELDS = {
    "method",
    "path",
    "status_code",
    "duration_ms",
    "job_id",
    "job_type",
    "status",
    "error",
}


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "correlation_id", None):
            record.correlation_id = get_correlation_id()
        return True


_DEFAULT_RECORD_FACTORY = logging.getLogRecordFactory()


def _record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _DEFAULT_RECORD_FACTORY(*args, **kwargs)
    if not getattr(record, "correlation_id", None):
        record.correlation_id = get_correlation_id()
    return record


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        correlation_id = getattr(record, "correlation_id", None)
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "correlation_id": correlation_id,
        }

        extras: dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key.startswith("_"):
                continue
            if key in _BASE_RECORD_KEYS:
                continue
            if key in {"args", "msg"}:
                continue
            if key in _KNOWN_FIELDS:
                extras[key] = value

        if record.exc_info:
            extras["exception"] = self.formatException(record.exc_info)

        error_value = extras.get("error")
        if isinstance(error_value, str):
            extras["error"] = error_value[:500]

        payload["fields"] = extras
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    root_logger = logging.getLogger()
    if getattr(root_logger, "_nexa_configured", False):
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(JsonLogFormatter())
    handler.addFilter(CorrelationIdFilter())

    root_logger.handlers.clear()
    root_logger.filters.clear()
    root_logger.setLevel(level)
    logging.setLogRecordFactory(_record_factory)
    root_logger.addHandler(handler)
    root_logger._nexa_configured = True  # type: ignore[attr-defined]
