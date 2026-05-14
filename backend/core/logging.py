"""Centralized logging using loguru."""
import sys
from loguru import logger

from backend.core.config import settings


def setup_logging() -> None:
    """Configure loguru for the whole app."""
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
            "- <level>{message}</level>"
        ),
        enqueue=True,
    )


__all__ = ["logger", "setup_logging"]
