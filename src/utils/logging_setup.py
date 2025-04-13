# src/utils/logging_setup.py
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(
    log_level=logging.INFO,
    log_format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    log_file: Path = None,  # Takes a Path object for the full file path
    max_bytes=10*1024*1024,  # 10 MB
    backup_count=5,
    console_logging=True
):
    """Configures logging for the application."""

    # Get the root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)  # Set root logger level

    # Prevent multiple handlers being added if called again
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(log_format)

    # Console Handler
    if console_logging:
        ch = logging.StreamHandler()
        ch.setLevel(log_level)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    # File Handler
    if log_file:
        # Ensure log directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Use RotatingFileHandler
        fh = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        fh.setLevel(log_level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        logging.info(f"Logging initialized. Log file: {log_file}")
    elif not console_logging:
        # Basic config if no file and no console specified, logs to stderr
        logging.basicConfig(level=log_level, format=log_format)
        logging.warning(
            "Logging to stderr because no log_file was specified and console_logging is False.")

    # Example: Quiet down overly verbose libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("binance").setLevel(logging.INFO)  # Or WARNING
