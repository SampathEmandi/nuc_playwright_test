"""
Session tracking module for monitoring concurrent chatbot sessions.
Tracks active sessions and provides periodic reports every 5 minutes.
"""
import asyncio
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict
from shared_state import SESSION_LOGS, CSV_METRICS


class SessionTracker:
    """Tracks concurrent chatbot sessions and their metrics."""
    
    def __init__(self, report_interval: int = 300):
        """
        Initialize the session tracker.
        
        Args:
            report_interval: Interval in seconds for periodic reports (default: 300 = 5 minutes)
        """
        self.report_interval = report_interval
        self.active_sessions: Dict[str, Dict] = {}  # session_id -> session_data
        self.session_metrics: Dict[str, List[Dict]] = defaultdict(list)  # session_id -> list of metrics
        self.periodic_reports: List[Dict] = []  # Store periodic report snapshots
        self.tracking_task: Optional[asyncio.Task] = None
        self.is_tracking = False
        self.start_time = None
        
    def register_session(self, session_id: str, username: str, course_numbers: List[int] = None):
        """
        Register a new active session.
        
        Args:
            session_id: Unique session identifier
            username: Username for the session
            course_numbers: List of course numbers this session is handling
        """
        self.active_sessions[session_id] = {
            'session_id': session_id,
            'username': username,
            'course_numbers': course_numbers or [],
            'start_time': time.time(),
            'last_activity': time.time(),
            'questions_asked': 0,
            'questions_answered': 0,
            'cycles_completed': 0,
            'total_response_time_ms': 0,
            'errors': 0,
            'status': 'active',
            'courses_active': len(course_numbers) if course_numbers else 0
        }
        logging.info(f"[TRACKER] Registered session: {session_id} (User: {username})")
    
    def update_session_activity(self, session_id: str, activity_type: str, **kwargs):
        """
        Update session activity metrics.
        
        Args:
            session_id: Session identifier
            activity_type: Type of activity ('question_asked', 'question_answered', 'cycle_completed', 'error')
            **kwargs: Additional metrics (response_time_ms, question_text, etc.)
        """
        if session_id not in self.active_sessions:
            return
        
        session = self.active_sessions[session_id]
        session['last_activity'] = time.time()
        
        if activity_type == 'question_asked':
            session['questions_asked'] += 1
        elif activity_type == 'question_answered':
            session['questions_answered'] += 1
            if 'response_time_ms' in kwargs:
                session['total_response_time_ms'] += kwargs['response_time_ms']
        elif activity_type == 'cycle_completed':
            session['cycles_completed'] += 1
        elif activity_type == 'error':
            session['errors'] += 1
        elif activity_type == 'status_change':
            if 'status' in kwargs:
                session['status'] = kwargs['status']
        
        # Store detailed metric
        metric = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            'activity_type': activity_type,
            **kwargs
        }
        self.session_metrics[session_id].append(metric)
    
    def unregister_session(self, session_id: str, reason: str = 'completed'):
        """
        Unregister a session (mark as inactive).
        
        Args:
            session_id: Session identifier
            reason: Reason for unregistering (completed, failed, timeout, etc.)
        """
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            session['status'] = 'inactive'
            session['end_time'] = time.time()
            session['duration_seconds'] = session['end_time'] - session['start_time']
            session['end_reason'] = reason
            
            logging.info(f"[TRACKER] Unregistered session: {session_id} (Reason: {reason}, Duration: {session['duration_seconds']:.2f}s)")
            
            # Keep session data for reporting but mark as inactive
            # Don't delete yet - will be cleaned up in periodic report
    
    def get_active_session_count(self) -> int:
        """Get count of currently active sessions."""
        return len([s for s in self.active_sessions.values() if s['status'] == 'active'])
    
    def get_session_summary(self) -> Dict:
        """
        Get current summary of all tracked sessions.
        
        Returns:
            Dictionary with summary statistics
        """
        active_sessions = [s for s in self.active_sessions.values() if s['status'] == 'active']
        inactive_sessions = [s for s in self.active_sessions.values() if s['status'] == 'inactive']
        
        total_questions_asked = sum(s['questions_asked'] for s in self.active_sessions.values())
        total_questions_answered = sum(s['questions_answered'] for s in self.active_sessions.values())
        total_cycles = sum(s['cycles_completed'] for s in self.active_sessions.values())
        total_errors = sum(s['errors'] for s in self.active_sessions.values())
        
        total_response_time = sum(s['total_response_time_ms'] for s in self.active_sessions.values())
        avg_response_time = (total_response_time / total_questions_answered) if total_questions_answered > 0 else 0
        
        # Group by username
        sessions_by_user = defaultdict(list)
        for session in self.active_sessions.values():
            sessions_by_user[session['username']].append(session)
        
        return {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            'total_active_sessions': len(active_sessions),
            'total_inactive_sessions': len(inactive_sessions),
            'total_sessions_tracked': len(self.active_sessions),
            'total_questions_asked': total_questions_asked,
            'total_questions_answered': total_questions_answered,
            'total_cycles_completed': total_cycles,
            'total_errors': total_errors,
            'average_response_time_ms': round(avg_response_time, 2),
            'sessions_by_user': {user: len(sessions) for user, sessions in sessions_by_user.items()},
            'active_session_details': [
                {
                    'session_id': s['session_id'],
                    'username': s['username'],
                    'questions_asked': s['questions_asked'],
                    'questions_answered': s['questions_answered'],
                    'cycles_completed': s['cycles_completed'],
                    'errors': s['errors'],
                    'duration_seconds': round(time.time() - s['start_time'], 2),
                    'courses_active': s['courses_active']
                }
                for s in active_sessions
            ]
        }
    
    def generate_periodic_report(self) -> Dict:
        """
        Generate a periodic report snapshot.
        
        Returns:
            Dictionary with report data
        """
        summary = self.get_session_summary()
        report = {
            'report_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'uptime_seconds': round(time.time() - self.start_time, 2) if self.start_time else 0,
            **summary
        }
        
        self.periodic_reports.append(report)
        return report
    
    def log_periodic_report(self, report: Dict):
        """Log the periodic report to console and file."""
        logging.info("\n" + "=" * 80)
        logging.info(f"PERIODIC SESSION TRACKING REPORT - {report['report_time']}")
        logging.info("=" * 80)
        logging.info(f"Uptime: {report['uptime_seconds']:.2f} seconds ({report['uptime_seconds']/60:.2f} minutes)")
        logging.info(f"Total Active Sessions: {report['total_active_sessions']}")
        logging.info(f"Total Inactive Sessions: {report['total_inactive_sessions']}")
        logging.info(f"Total Sessions Tracked: {report['total_sessions_tracked']}")
        logging.info(f"\nActivity Metrics:")
        logging.info(f"  Total Questions Asked: {report['total_questions_asked']}")
        logging.info(f"  Total Questions Answered: {report['total_questions_answered']}")
        logging.info(f"  Total Q&A Cycles Completed: {report['total_cycles_completed']}")
        logging.info(f"  Total Errors: {report['total_errors']}")
        logging.info(f"  Average Response Time: {report['average_response_time_ms']:.2f}ms")
        
        logging.info(f"\nSessions by User:")
        for user, count in report['sessions_by_user'].items():
            logging.info(f"  {user}: {count} session(s)")
        
        if report['active_session_details']:
            logging.info(f"\nActive Session Details:")
            for session in report['active_session_details']:
                logging.info(f"  Session: {session['session_id']}")
                logging.info(f"    User: {session['username']}")
                logging.info(f"    Questions: {session['questions_asked']} asked, {session['questions_answered']} answered")
                logging.info(f"    Cycles: {session['cycles_completed']}, Errors: {session['errors']}")
                logging.info(f"    Duration: {session['duration_seconds']:.2f}s, Courses: {session['courses_active']}")
        else:
            logging.info("\nNo active sessions")
        
        logging.info("=" * 80 + "\n")
    
    async def periodic_reporting_loop(self):
        """Background task that generates periodic reports every report_interval seconds."""
        self.start_time = time.time()
        logging.info(f"[TRACKER] Starting periodic reporting (interval: {self.report_interval}s)")
        
        while self.is_tracking:
            await asyncio.sleep(self.report_interval)
            
            if self.is_tracking:  # Check again after sleep
                report = self.generate_periodic_report()
                self.log_periodic_report(report)
                
                # Also write to CSV
                self.write_tracking_report_csv(report)
    
    def start_tracking(self):
        """Start the periodic reporting task."""
        if not self.is_tracking:
            self.is_tracking = True
            self.tracking_task = asyncio.create_task(self.periodic_reporting_loop())
            logging.info(f"[TRACKER] Session tracking started (reports every {self.report_interval}s)")
    
    async def stop_tracking(self):
        """Stop the periodic reporting task and generate final report."""
        if self.is_tracking:
            self.is_tracking = False
            if self.tracking_task:
                self.tracking_task.cancel()
                try:
                    await self.tracking_task
                except asyncio.CancelledError:
                    pass
            
            # Generate final report
            final_report = self.generate_periodic_report()
            self.log_periodic_report(final_report)
            self.write_tracking_report_csv(final_report)
            logging.info("[TRACKER] Session tracking stopped")
    
    def write_tracking_report_csv(self, report: Dict):
        """
        Write tracking report to CSV file.
        
        Args:
            report: Report dictionary to write
        """
        import csv
        import os
        
        filename = f"session_tracking_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join(os.getcwd(), filename)
        
        try:
            file_exists = os.path.exists(filepath)
            with open(filepath, 'a', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'report_time',
                    'uptime_seconds',
                    'total_active_sessions',
                    'total_inactive_sessions',
                    'total_sessions_tracked',
                    'total_questions_asked',
                    'total_questions_answered',
                    'total_cycles_completed',
                    'total_errors',
                    'average_response_time_ms'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
                
                if not file_exists:
                    writer.writeheader()
                
                writer.writerow(report)
            
            logging.info(f"[TRACKER] Report written to: {filepath}")
        except Exception as e:
            logging.error(f"[TRACKER] Error writing tracking report CSV: {e}")


# Global tracker instance
_tracker_instance: Optional[SessionTracker] = None


def get_tracker() -> SessionTracker:
    """Get or create the global session tracker instance."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = SessionTracker(report_interval=300)  # 5 minutes default
    return _tracker_instance


def initialize_tracker(report_interval: int = 300):
    """Initialize the global session tracker."""
    global _tracker_instance
    _tracker_instance = SessionTracker(report_interval=report_interval)
    return _tracker_instance