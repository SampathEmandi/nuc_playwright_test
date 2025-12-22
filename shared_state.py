"""
Shared state module for global data structures used across modules.
This includes CSV metrics, session logs, and related tracking.
"""
from datetime import datetime

# Global list to store CSV metrics
CSV_METRICS = []

# Global list to store page errors and warnings for CSV
PAGE_ERRORS = []

# Global list to store session-level logs and errors for CSV
SESSION_LOGS = []

# Track last CSV export time for incremental exports
LAST_CSV_EXPORT_TIME = None
CSV_EXPORT_FILENAME = None
SESSION_CSV_EXPORT_FILENAME = None
ERRORS_CSV_EXPORT_FILENAME = None