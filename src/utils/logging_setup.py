# src/utils/logging_setup.py

import logging
import logging.handlers
import os
import sys

# Attempt to import settings, handle potential ImportError during early setup/testing
try:
    from config.settings import settings, PROJECT_ROOT
except ImportError:
    print("FATAL: Could not import settings for logging setup. Ensure settings.py exists and PYTHONPATH is correct.", file=sys.stderr)
    # Define minimal defaults so basic logging might work, but this indicates a setup problem
    settings = {'logging': {'level': 'INFO', 'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'}}
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) # Guess project root


def setup_logging():
    """
    Configures the root logger for the application based on config settings.
    Sets up console and rotating file handlers.
    """
    log_config = settings.get('logging', {})
    log_level_str = log_config.get('level', 'INFO').upper()
    log_format_str = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_filepath_rel = log_config.get('file_path', 'data/logs/trader.log') # Relative path from project root
    max_bytes = int(log_config.get('max_bytes', 10485760)) # Default 10MB
    backup_count = int(log_config.get('backup_count', 5))

    # --- Convert log level string to logging constant ---
    log_level = getattr(logging, log_level_str, logging.INFO)
    if not isinstance(log_level, int):
        print(f"WARN: Invalid logging level '{log_level_str}' in config. Defaulting to INFO.", file=sys.stderr)
        log_level = logging.INFO

    # --- Create Formatter ---
    formatter = logging.Formatter(log_format_str)

    # --- Get Root Logger ---
    # Configure the root logger, affecting all module loggers unless they override
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level) # Set the minimum level for the root logger

    # --- Remove existing handlers (important for re-configuration) ---
    # This prevents adding duplicate handlers if setup_logging is called multiple times (e.g., in tests)
    # Be cautious if other libraries might add handlers you want to keep.
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        # Optionally close handler if needed: handler.close()

    # --- Configure Console Handler ---
    console_handler = logging.StreamHandler(sys.stdout) # Log to stdout
    console_handler.setLevel(log_level) # Console logs at the configured level
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # --- Configure Rotating File Handler ---
    try:
        # Construct absolute path for the log file
        log_filepath_abs = os.path.join(PROJECT_ROOT, log_filepath_rel)
        # Ensure the directory for the log file exists
        log_dir = os.path.dirname(log_filepath_abs)
        os.makedirs(log_dir, exist_ok=True)

        # Create the rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            log_filepath_abs,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8' # Explicitly use UTF-8
        )
        file_handler.setLevel(log_level) # File logs at the configured level
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        print(f"INFO: Logging configured. Level: {log_level_str}, File: '{log_filepath_abs}'", file=sys.stderr)

    except Exception as e:
        # Fallback: Log error to stderr if file handler setup fails
        print(f"ERROR: Failed to configure file logging handler: {e}", file=sys.stderr)
        # The console handler should still work


# --- Example Usage (for testing when run directly via python -m src.utils.logging_setup) ---
if __name__ == '__main__':
    print("--- Testing Logging Setup ---")
    # Configure logging using the function
    setup_logging()

    # Get a logger instance for this test scope
    test_log = logging.getLogger(__name__) # Gets logger named '__main__' here

    # Test logging at different levels
    test_log.debug("This is a debug message (should not appear if level is INFO).")
    test_log.info("This is an info message.")
    test_log.warning("This is a warning message.")
    test_log.error("This is an error message.")
    try:
        1 / 0
    except ZeroDivisionError:
        test_log.exception("This is an exception message (includes traceback).")

    print(f"\nCheck the console output above and the log file specified in config.yaml (default: {settings.get('logging', {}).get('file_path')})")