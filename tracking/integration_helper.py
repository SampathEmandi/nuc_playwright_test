"""
Helper functions for integrating session tracking into the main application.
These functions can be called from main.py to track session activity.
"""
from tracking.session_tracker import get_tracker
from config import STRESS_TEST_CONFIG


def track_question_asked(session_id: str, question_text: str = None):
    """Track that a question was asked in a session."""
    if STRESS_TEST_CONFIG.get('enable_session_tracking', True):
        tracker = get_tracker()
        tracker.update_session_activity(
            session_id,
            'question_asked',
            question_text=question_text[:100] if question_text else None
        )


def track_question_answered(session_id: str, response_time_ms: float = None, question_text: str = None):
    """Track that a question was answered in a session."""
    if STRESS_TEST_CONFIG.get('enable_session_tracking', True):
        tracker = get_tracker()
        tracker.update_session_activity(
            session_id,
            'question_answered',
            response_time_ms=response_time_ms,
            question_text=question_text[:100] if question_text else None
        )


def track_cycle_completed(session_id: str):
    """Track that a Q&A cycle was completed in a session."""
    if STRESS_TEST_CONFIG.get('enable_session_tracking', True):
        tracker = get_tracker()
        tracker.update_session_activity(session_id, 'cycle_completed')


def track_session_error(session_id: str, error_message: str = None):
    """Track an error in a session."""
    if STRESS_TEST_CONFIG.get('enable_session_tracking', True):
        tracker = get_tracker()
        tracker.update_session_activity(
            session_id,
            'error',
            error_message=error_message[:200] if error_message else None
        )


def register_session(session_id: str, username: str, course_numbers: list = None):
    """Register a new session with the tracker."""
    if STRESS_TEST_CONFIG.get('enable_session_tracking', True):
        tracker = get_tracker()
        tracker.register_session(session_id, username, course_numbers)


def unregister_session(session_id: str, reason: str = 'completed'):
    """Unregister a session from tracking."""
    if STRESS_TEST_CONFIG.get('enable_session_tracking', True):
        tracker = get_tracker()
        tracker.unregister_session(session_id, reason)


def start_tracking():
    """Start the periodic reporting task."""
    if STRESS_TEST_CONFIG.get('enable_session_tracking', True):
        tracker = get_tracker()
        report_interval = STRESS_TEST_CONFIG.get('tracking_report_interval', 300)
        if tracker.report_interval != report_interval:
            # Reinitialize if interval changed
            from tracking.session_tracker import initialize_tracker
            tracker = initialize_tracker(report_interval=report_interval)
        tracker.start_tracking()


async def stop_tracking():
    """Stop the periodic reporting task."""
    if STRESS_TEST_CONFIG.get('enable_session_tracking', True):
        tracker = get_tracker()
        await tracker.stop_tracking()