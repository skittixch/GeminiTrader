# src/utils/logging_setup.py

import logging
import logging.handlers
from pathlib import Path
import sys

DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_BACKUP_COUNT = 5


class ColorFormatter(logging.Formatter):
    """Adds color to console log levels."""
    grey = "\x1b[38;21m"
    yellow = "\x1b[33;21m"
    red = "\x1b[31;21m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format_str = "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s:%(lineno)d - %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    FORMATS = {
        logging.DEBUG: grey + format_str + reset, logging.INFO: grey + format_str + reset,
        logging.WARNING: yellow + format_str + reset, logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, self.format_str)
        formatter = logging.Formatter(log_fmt, datefmt=self.datefmt)
        return formatter.format(record)


def setup_logging(
    log_level=logging.INFO,  # Default level for the main log file
    log_file='data/logs/app.log',
    max_bytes=DEFAULT_MAX_BYTES,
    backup_count=DEFAULT_BACKUP_COUNT,
    console_logging=True,
    console_log_level=logging.INFO,  # Default level for console
    error_log_file='data/logs/errors.log'  # New parameter for error file
):
    """
    Configures logging with handlers for console, main file, and error file.
    """
    try:
        log_file_path = Path(log_file)
        error_log_file_path = Path(error_log_file)  # New error file path

        # Ensure directories exist
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        # Ensure error log dir exists (might be the same or different)
        error_log_file_path.parent.mkdir(parents=True, exist_ok=True)

        root_logger = logging.getLogger()
        # Set root logger low to allow handlers to filter up
        root_logger.setLevel(logging.DEBUG)

        # Prevent multiple handlers if called again
        if root_logger.hasHandlers():
            root_logger.handlers.clear()

        # --- Formatter for Files (More Detail) ---
        file_formatter = logging.Formatter(
            # Adjusted name width
            '%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)-20s:%(lineno)4d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # --- 1. Main File Handler (Rotating) ---
        main_file_handler = logging.handlers.RotatingFileHandler(
            log_file_path, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
        )
        main_file_handler.setFormatter(file_formatter)
        main_file_handler.setLevel(log_level)  # Level for the main file
        root_logger.addHandler(main_file_handler)

        # --- 2. Error File Handler (Rotating) ---
        # Only logs WARNING and above
        error_file_handler = logging.handlers.RotatingFileHandler(
            error_log_file_path, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
        )
        # Use the same detailed format
        error_file_handler.setFormatter(file_formatter)
        # <<< Set level to WARNING
        error_file_handler.setLevel(logging.WARNING)
        root_logger.addHandler(error_file_handler)

        # --- 3. Console Handler (Optional) ---
        if console_logging:
            console_formatter = ColorFormatter()
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(console_formatter)
            # Use specified console level
            console_handler.setLevel(console_log_level)
            root_logger.addHandler(console_handler)

        root_logger.info(
            f"Logging initialized. Main file: {log_file_path}, Error file: {error_log_file_path}")

    except Exception as e:
        logging.basicConfig(level=logging.WARNING)
        logging.critical(f"Failed to configure logging: {e}", exc_info=True)
        print(f"CRITICAL: Failed to set up logging: {e}", file=sys.stderr)


# Example usage
if __name__ == '__main__':
    setup_logging(
        log_level=logging.DEBUG,        # Main file gets DEBUG+
        log_file='temp_main.log',
        console_logging=True,
        console_log_level=logging.INFO,  # Console gets INFO+
        error_log_file='temp_error.log'  # Error file gets WARNING+
    )
    test_logger = logging.getLogger("TestModule")
    test_logger.debug("Debug msg - MAIN LOG ONLY")
    test_logger.info("Info msg - MAIN LOG + CONSOLE")
    test_logger.warning("Warning msg - ALL LOGS")
    test_logger.error("Error msg - ALL LOGS")
    test_logger.critical("Critical msg - ALL LOGS")
    print("\nCheck 'temp_main.log' (DEBUG+)")
    print("Check 'temp_error.log' (WARNING+)")
    print("Check console output (INFO+)")
    try:
        Path('temp_main.log').unlink()
        Path('temp_error.log').unlink()
    except OSError:
        pass
