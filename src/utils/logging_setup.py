# START OF FILE: src/utils/logging_setup.py (Fixed Config Loading)

import logging
import logging.handlers
from pathlib import Path
import sys
# <<< ADDED import >>>
from config.settings import load_config, get_config_value

DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_CONSOLE_LEVEL = logging.INFO
DEFAULT_LOG_FILE = 'data/logs/app.log'  # Fallback default
DEFAULT_ERROR_FILE = 'data/logs/errors.log'  # Fallback default
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

# <<< MODIFIED: Removed default args, load config inside >>>


def setup_logging(config_override: dict = None):
    """
    Configures logging using parameters from the loaded configuration file.
    """
    try:
        # --- Load Configuration ---
        # Use override if provided (for testing), otherwise load default config
        config = config_override if config_override is not None else load_config()
        if not config:
            # Basic fallback if config loading fails entirely
            logging.basicConfig(level=logging.WARNING)
            logging.critical("Failed to load configuration for logging setup.")
            print(
                "CRITICAL: Failed to load configuration for logging setup.", file=sys.stderr)
            return

        # --- Get Logging Parameters from Config ---
        log_level_str = get_config_value(config, ('logging', 'level'), 'INFO')
        log_level = getattr(logging, log_level_str.upper(), DEFAULT_LOG_LEVEL)

        console_level_str = get_config_value(
            config, ('logging', 'console_level'), 'INFO')
        console_log_level = getattr(
            logging, console_level_str.upper(), DEFAULT_CONSOLE_LEVEL)

        log_file_rel = get_config_value(
            config, ('logging', 'trader_log_path'), DEFAULT_LOG_FILE)
        error_log_file_rel = get_config_value(
            config, ('logging', 'error_log_path'), DEFAULT_ERROR_FILE)

        max_bytes = int(get_config_value(
            config, ('logging', 'max_bytes'), DEFAULT_MAX_BYTES))
        backup_count = int(get_config_value(
            config, ('logging', 'backup_count'), DEFAULT_BACKUP_COUNT))

        # Assume console logging is always wanted unless explicitly configured otherwise
        console_logging = True

        # --- Resolve Paths (relative to project root) ---
        # Find project root relative to this file's location
        project_root = Path(__file__).resolve().parent.parent.parent
        log_file_path = project_root / log_file_rel
        error_log_file_path = project_root / error_log_file_rel

        # Ensure directories exist
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        error_log_file_path.parent.mkdir(parents=True, exist_ok=True)

        # --- Configure Root Logger ---
        root_logger = logging.getLogger()
        # Set root logger low to allow handlers to filter up
        root_logger.setLevel(logging.DEBUG)

        # Prevent multiple handlers if called again
        if root_logger.hasHandlers():
            # Check if handlers are already configured to avoid duplicate setup messages
            # This check might be basic, could refine if needed
            if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root_logger.handlers):
                # logging.debug("Logging handlers already seem to be configured. Skipping setup.")
                # return # Exit if already set up? Or clear and re-setup? Clearing is safer.
                root_logger.handlers.clear()
                logging.debug(
                    "Cleared existing logging handlers before re-setup.")
            else:
                root_logger.handlers.clear()

        # --- Formatter for Files ---
        file_formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)-20s:%(lineno)4d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # --- 1. Main File Handler (Rotating) ---
        main_file_handler = logging.handlers.RotatingFileHandler(
            log_file_path, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
        )
        main_file_handler.setFormatter(file_formatter)
        main_file_handler.setLevel(log_level)  # Use level from config
        root_logger.addHandler(main_file_handler)

        # --- 2. Error File Handler (Rotating) ---
        error_file_handler = logging.handlers.RotatingFileHandler(
            error_log_file_path, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
        )
        error_file_handler.setFormatter(file_formatter)
        # Only WARNING+ to error log
        error_file_handler.setLevel(logging.WARNING)
        root_logger.addHandler(error_file_handler)

        # --- 3. Console Handler ---
        if console_logging:
            console_formatter = ColorFormatter()
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(console_formatter)
            # Use console level from config
            console_handler.setLevel(console_log_level)
            root_logger.addHandler(console_handler)

        # Use the logger *after* handlers are added
        logging.getLogger(__name__).info(  # Log from this module's logger
            f"Logging initialized. Root Level: DEBUG. Main File ({log_level_str}): {log_file_path}, Error File (WARNING+): {error_log_file_path}, Console Level: {console_level_str}")

    except Exception as e:
        # Basic fallback if anything goes wrong during setup
        logging.basicConfig(level=logging.WARNING)
        logging.critical(f"Failed to configure logging: {e}", exc_info=True)
        print(f"CRITICAL: Failed to set up logging: {e}", file=sys.stderr)


# Example usage / Test block
if __name__ == '__main__':
    # Example of using override for testing
    test_config = {
        'logging': {
            'level': 'DEBUG',
            'console_level': 'INFO',
            'trader_log_path': 'temp_main.log',
            'error_log_path': 'temp_error.log',
            'max_bytes': 1024,  # Small size for testing rotation
            'backup_count': 1
        }
        # Add other sections if needed by get_config_value fallbacks
    }
    setup_logging(config_override=test_config)

    test_logger = logging.getLogger("TestModule")
    test_logger.debug("Debug msg - MAIN LOG ONLY")
    test_logger.info("Info msg - MAIN LOG + CONSOLE")
    test_logger.warning("Warning msg - ALL LOGS")
    test_logger.error("Error msg - ALL LOGS")
    test_logger.critical("Critical msg - ALL LOGS")
    print("\nCheck 'temp_main.log' (DEBUG+)")
    print("Check 'temp_error.log' (WARNING+)")
    print("Check console output (INFO+)")
    # Try rotating
    for i in range(5):
        test_logger.warning(
            f"This is a long message to test rotation padding {i}................................................................................................................................................................................................................................................")
    print("Check log rotation (temp_main.log.1, temp_error.log.1)")

    try:
        Path('temp_main.log').unlink(missing_ok=True)
        Path('temp_main.log.1').unlink(missing_ok=True)
        Path('temp_error.log').unlink(missing_ok=True)
        Path('temp_error.log.1').unlink(missing_ok=True)
    except OSError:
        pass
# EOF src/utils/logging_setup.py
