import logging
import os
import sys
import time
from datetime import datetime

# Flag to track if logging has been set up
_LOGGING_INITIALIZED = False
# Keep track of the current log file
_CURRENT_LOG_FILE = None

def setup_logging():
    """Configure application-wide logging to file and console (singleton pattern)."""
    global _LOGGING_INITIALIZED, _CURRENT_LOG_FILE
    
    # Only set up logging once per application run
    if _LOGGING_INITIALIZED:
        # Return the existing log file path
        return _CURRENT_LOG_FILE
    
    # Create logs directory if it doesn't exist
    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)
    
    # Create a timestamped log filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(logs_dir, f"video_analysis_{timestamp}.log")
    _CURRENT_LOG_FILE = log_file
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Clear any existing handlers to avoid duplication
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # File handler with detailed formatting
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-20s | Line:%(lineno)d | %(message)s'
    )
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler with simpler formatting
    console_formatter = logging.Formatter('%(levelname)-8s | %(message)s')
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)
    
    # Add handlers to root logger
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Configure and silence third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    
    # Mark logging as initialized
    _LOGGING_INITIALIZED = True
    
    # Log that logging has been initialized
    logging.getLogger(__name__).info(f"Logging initialized. Log file: {log_file}")
    
    # Return the path to the logfile for reference
    return log_file

def log_session_state(logger, session_state, prefix=""):
    """Log relevant session state variables for debugging."""
    logger.debug(f"{prefix}Session state summary:")
    try:
        # Log phase and mode information
        logger.debug(f"{prefix}Current phase: {session_state.current_phase}")
        logger.debug(f"{prefix}File or URL mode: {session_state.file_or_url}")
        
        # Log file info if present
        if hasattr(session_state, 'video_file') and session_state.video_file is not None:
            logger.debug(f"{prefix}Video file: {session_state.video_file.name} ({session_state.video_file.size} bytes)")
        
        # Log URL if present
        if hasattr(session_state, 'video_url') and session_state.video_url:
            logger.debug(f"{prefix}Video URL: {session_state.video_url}")
        
        # Log analysis stats
        analyses_count = len(session_state.analyses) if hasattr(session_state, 'analyses') else 0
        logger.debug(f"{prefix}Analysis count: {analyses_count}")
        
        # Log current analyses
        current_analyses_count = len(session_state.current_analyses) if hasattr(session_state, 'current_analyses') else 0
        logger.debug(f"{prefix}Current analyses: {current_analyses_count}")
        
    except Exception as e:
        logger.error(f"Error logging session state: {str(e)}")

class TimerLog:
    """Context manager for timing operations with automatic logging."""
    def __init__(self, logger, operation_name):
        self.logger = logger
        self.operation_name = operation_name
        
    def __enter__(self):
        self.start_time = time.time()
        self.logger.info(f"Starting {self.operation_name}...")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_time = time.time() - self.start_time
        if exc_type is None:
            self.logger.info(f"Completed {self.operation_name} in {elapsed_time:.2f} seconds")
        else:
            self.logger.error(f"Failed {self.operation_name} after {elapsed_time:.2f} seconds: {exc_val}")
        return False  # Don't suppress exceptions
