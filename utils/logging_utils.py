"""
Logging utilities for the Playwright stress test application.
"""
import logging
import os
import json
import time
import random
from pathlib import Path
from datetime import datetime

# Debug logging path is determined dynamically relative to the script's location, inside a '.cursor' folder
DEBUG_LOG_PATH = str(Path(__file__).parent.parent / ".cursor" / "debug.log")

# Global logging configuration
LOG_FILENAME = None  # Will be set on first log

def debug_log(hypothesis_id, location, message, data=None, session_id=None, run_id="initial"):
    """Write debug log entry in NDJSON format."""
    try:
        # Ensure the directory exists
        log_dir = os.path.dirname(DEBUG_LOG_PATH)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        log_entry = {
            "id": f"log_{int(time.time() * 1000)}_{random.randint(1000, 9999)}",
            "timestamp": int(time.time() * 1000),
            "location": location,
            "message": message,
            "data": data or {},
            "sessionId": session_id or "unknown",
            "runId": run_id,
            "hypothesisId": hypothesis_id
        }
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        # Silently fail to avoid breaking main flow, but log to standard logging in debug mode
        logging.debug(f"Debug log write failed: {e}")

def setup_logging():
    """Setup logging to both console and file."""
    global LOG_FILENAME
    
    # Generate log filename with timestamp
    if LOG_FILENAME is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        LOG_FILENAME = f"stress_test_{timestamp}.log"
    
    # Create root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create formatters
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler
    try:
        file_handler = logging.FileHandler(LOG_FILENAME, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logging.info(f"📝 Logging to file: {LOG_FILENAME}")
    except Exception as e:
        logging.warning(f"Could not setup file logging: {e}")
    
    return LOG_FILENAME

# Setup logging at startup
LOG_FILENAME = setup_logging()
logging.info(f"Logging initialized - Log file: {LOG_FILENAME}")