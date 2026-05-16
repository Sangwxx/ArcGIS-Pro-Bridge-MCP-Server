from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "tool_name"):
            log_data["tool_name"] = record.tool_name
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        if hasattr(record, "params"):
            log_data["params"] = record.params
        if record.exc_info:
            log_data["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_data, default=str)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("arcgis_mcp")
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
    return logger


_default_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _default_logger
    if _default_logger is None:
        _default_logger = setup_logging()
    return _default_logger


class OperationLogger:
    def __init__(self, name: str = "arcgis_mcp"):
        self.logger = logging.getLogger(name)
        self._start_time: float | None = None

    def log_operation(
        self,
        tool_name: str,
        params: dict[str, Any] | None = None,
        success: bool = True,
        error: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        extra: dict[str, Any] = {"tool_name": tool_name}
        if duration_ms is not None:
            extra["duration_ms"] = duration_ms
        if params is not None:
            extra["params"] = {k: str(v) for k, v in params.items()}
        if not success and error:
            self.logger.error(f"MCP tool '{tool_name}' failed: {error}", extra=extra)
        elif success:
            self.logger.info(f"MCP tool '{tool_name}' succeeded", extra=extra)

    def start_timer(self) -> None:
        self._start_time = time.perf_counter()

    def stop_timer(self) -> float:
        if self._start_time is None:
            return 0.0
        elapsed = (time.perf_counter() - self._start_time) * 1000
        self._start_time = None
        return elapsed


_operation_logger: OperationLogger | None = None


def get_operation_logger() -> OperationLogger:
    global _operation_logger
    if _operation_logger is None:
        _operation_logger = OperationLogger()
    return _operation_logger