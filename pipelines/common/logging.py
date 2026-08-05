"""Structured JSON logging.

Every pipeline log line carries machine-readable context (batch id, run id,
stage, row counts) so that a run can be reconstructed from logs alone. Human
readable output is available by setting `LOG_FORMAT=console` while developing.

Logs go to stderr, leaving stdout free for pipeline data output and CLI results.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.typing import FilteringBoundLogger, Processor

_configured = False


def configure_logging(
    level: str = "INFO",
    fmt: str = "json",
    *,
    force: bool = False,
) -> None:
    """Configure structlog once per process.

    Args:
        level: Standard logging level name (DEBUG, INFO, WARNING, ERROR).
        fmt: `json` for machine-readable output, `console` for local development.
        force: Reconfigure even if already configured. Used by tests.
    """
    global _configured
    if _configured and not force:
        return

    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    # Note: these are the `structlog.processors` variants, not the
    # `structlog.stdlib` ones. The stdlib processors expect a real
    # `logging.Logger` underneath and blow up on PrintLoggerFactory's
    # lightweight logger. The logger name is bound explicitly in `get_logger`
    # instead, which achieves the same result without the coupling.
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level.upper()]
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str, **initial_context: Any) -> FilteringBoundLogger:
    """Return a logger bound to `name` plus any initial context.

    Example:
        log = get_logger(__name__, batch_id=batch.id, stage="ingestion")
        log.info("bronze_written", rows=len(frame), path=str(target))
    """
    logger: FilteringBoundLogger = structlog.get_logger(name).bind(logger=name)
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger
