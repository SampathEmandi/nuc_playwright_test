# Session Tracking Module

## Purpose

Tracks concurrent chatbot sessions running continuously with Q&A, generating periodic reports every 5 minutes.

## Features

- **Real-time Session Tracking**: Monitors all active chatbot sessions
- **Periodic Reports**: Generates comprehensive reports every 5 minutes (configurable)
- **Metrics Tracking**:
  - Active session count
  - Questions asked/answered per session
  - Q&A cycles completed
  - Response times
  - Error counts
- **CSV Export**: Exports tracking data to CSV files
- **Per-Session Details**: Tracks individual session metrics

## Usage

### Basic Usage

```python
from tracking.session_tracker import get_tracker

tracker = get_tracker()
tracker.start_tracking()

# Register a session
tracker.register_session("session_1", "user@example.com", [1, 2])

# Track activities
tracker.update_session_activity("session_1", "question_asked")
tracker.update_session_activity("session_1", "question_answered", response_time_ms=2000)
tracker.update_session_activity("session_1", "cycle_completed")

# Generate report
report = tracker.generate_periodic_report()
tracker.log_periodic_report(report)

# Stop tracking
await tracker.stop_tracking()
```

### Using Integration Helper

For easier integration with main.py:

```python
from tracking.integration_helper import (
    start_tracking,
    register_session,
    track_question_asked,
    track_question_answered,
    track_cycle_completed,
    stop_tracking
)

# Start tracking
start_tracking()

# In your session code
register_session(session_id, username, [1, 2])
track_question_asked(session_id, question_text)
track_question_answered(session_id, response_time_ms=2000)
track_cycle_completed(session_id)

# Stop tracking
await stop_tracking()
```

## Configuration

Configure in `config.py`:

```python
STRESS_TEST_CONFIG = {
    'enable_session_tracking': True,
    'tracking_report_interval': 300,  # 5 minutes in seconds
}
```

## Output Files

- `session_tracking_report_YYYYMMDD_HHMMSS.csv` - Periodic reports
- Console logs with detailed session metrics

## API Reference

### SessionTracker Class

- `register_session(session_id, username, course_numbers)` - Register new session
- `update_session_activity(session_id, activity_type, **kwargs)` - Update activity
- `unregister_session(session_id, reason)` - Mark session as inactive
- `get_active_session_count()` - Get count of active sessions
- `get_session_summary()` - Get current summary
- `generate_periodic_report()` - Generate report snapshot
- `start_tracking()` - Start periodic reporting
- `stop_tracking()` - Stop reporting and generate final report
