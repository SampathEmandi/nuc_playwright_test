"""
Categorized CSV reporting module for separate error tracking.
Maintains separate CSV files for:
- Session errors
- Login errors
- Chat/Response errors
"""
import csv
import os
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from threading import Lock

# Thread-safe storage for categorized errors
SESSION_ERRORS: List[Dict[str, Any]] = []
LOGIN_ERRORS: List[Dict[str, Any]] = []
CHAT_RESPONSE_ERRORS: List[Dict[str, Any]] = []

# CSV file names
SESSION_ERRORS_CSV_FILENAME: Optional[str] = None
LOGIN_ERRORS_CSV_FILENAME: Optional[str] = None
CHAT_RESPONSE_ERRORS_CSV_FILENAME: Optional[str] = None

# Thread locks for thread-safe operations
SESSION_ERRORS_LOCK = Lock()
LOGIN_ERRORS_LOCK = Lock()
CHAT_RESPONSE_ERRORS_LOCK = Lock()


def log_session_error(
    session_id: str,
    username: Optional[str] = None,
    error_message: str = "",
    error_type: str = "",
    stage: str = "",
    traceback_text: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None
):
    """
    Log a session-level error.
    
    Args:
        session_id: Session identifier
        username: Username associated with session
        error_message: Error message
        error_type: Type of error
        stage: Stage where error occurred
        traceback_text: Full traceback if applicable
        extra_data: Additional metadata
    """
    error_entry = {
        'session_id': session_id,
        'username': username or '',
        'error_message': error_message[:500] if error_message else '',
        'error_type': error_type,
        'stage': stage,
        'traceback': (traceback_text[:2000] if traceback_text else ''),
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
        **(extra_data or {})
    }
    
    with SESSION_ERRORS_LOCK:
        SESSION_ERRORS.append(error_entry)


def log_login_error(
    session_id: str,
    username: Optional[str] = None,
    error_message: str = "",
    attempt: Optional[int] = None,
    error_code: Optional[str] = None,
    traceback_text: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None
):
    """
    Log a login error.
    
    Args:
        session_id: Session identifier
        username: Username attempting to login
        error_message: Error message
        attempt: Login attempt number
        error_code: Error code if applicable
        traceback_text: Full traceback if applicable
        extra_data: Additional metadata
    """
    error_entry = {
        'session_id': session_id,
        'username': username or '',
        'error_message': error_message[:500] if error_message else '',
        'attempt': attempt or '',
        'error_code': error_code or '',
        'traceback': (traceback_text[:2000] if traceback_text else ''),
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
        **(extra_data or {})
    }
    
    with LOGIN_ERRORS_LOCK:
        LOGIN_ERRORS.append(error_entry)


def log_chat_response_error(
    session_id: str,
    username: Optional[str] = None,
    tab_name: Optional[str] = None,
    question_num: Optional[int] = None,
    error_message: str = "",
    error_type: str = "",
    question_text: Optional[str] = None,
    response_wait_time_ms: Optional[float] = None,
    traceback_text: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None
):
    """
    Log a chat/response error.
    
    Args:
        session_id: Session identifier
        username: Username associated with session
        tab_name: Tab/window name
        question_num: Question number if applicable
        error_message: Error message
        error_type: Type of error
        question_text: Question text if applicable
        response_wait_time_ms: Response wait time if applicable
        traceback_text: Full traceback if applicable
        extra_data: Additional metadata
    """
    error_entry = {
        'session_id': session_id,
        'username': username or '',
        'tab_name': tab_name or '',
        'question_num': question_num or '',
        'error_message': error_message[:500] if error_message else '',
        'error_type': error_type,
        'question_text': (question_text[:200] if question_text else ''),
        'response_wait_time_ms': response_wait_time_ms or '',
        'traceback': (traceback_text[:2000] if traceback_text else ''),
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
        **(extra_data or {})
    }
    
    with CHAT_RESPONSE_ERRORS_LOCK:
        CHAT_RESPONSE_ERRORS.append(error_entry)


def write_session_errors_csv(append_mode: bool = False):
    """Write session errors to CSV file."""
    global SESSION_ERRORS_CSV_FILENAME
    
    # Check if CSV export is enabled
    from config import STRESS_TEST_CONFIG
    if not STRESS_TEST_CONFIG.get('enable_csv_export', True):
        if not append_mode:
            logging.info("[CAT:SYSTEM] [SRC:UTILS] CSV export disabled - skipping session errors CSV write")
        return
    
    cwd = os.getcwd()
    
    with SESSION_ERRORS_LOCK:
        if not SESSION_ERRORS:
            if not append_mode:
                logging.info("[CAT:SYSTEM] [SRC:UTILS] No session errors to write to CSV")
            return
        
        # Generate filename with timestamp (only on first write)
        if SESSION_ERRORS_CSV_FILENAME is None or not append_mode:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            SESSION_ERRORS_CSV_FILENAME = f"session_errors_{timestamp}.csv"
        
        csv_filepath = os.path.join(cwd, SESSION_ERRORS_CSV_FILENAME)
        
        fieldnames = [
            'session_id',
            'username',
            'error_message',
            'error_type',
            'stage',
            'traceback',
            'timestamp'
        ]
        
        try:
            if not hasattr(write_session_errors_csv, '_written_indices'):
                write_session_errors_csv._written_indices = set()
            
            if append_mode:
                errors_to_write = [error for i, error in enumerate(SESSION_ERRORS) 
                                 if i not in write_session_errors_csv._written_indices]
                if not errors_to_write:
                    return
                mode = 'a'
            else:
                errors_to_write = SESSION_ERRORS
                mode = 'w'
                write_session_errors_csv._written_indices = set()
            
            logging.info(f"[CAT:SYSTEM] [SRC:UTILS] Writing session errors CSV to: {csv_filepath} (mode: {mode}, records: {len(errors_to_write)})")
            with open(csv_filepath, mode, newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
                
                if not append_mode:
                    writer.writeheader()
                
                start_index = len(write_session_errors_csv._written_indices)
                for i, error_entry in enumerate(errors_to_write):
                    entry_index = start_index + i
                    write_session_errors_csv._written_indices.add(entry_index)
                    writer.writerow(error_entry)
            
            if append_mode:
                logging.info(f"[CAT:SYSTEM] [SRC:UTILS] ✓ Session errors CSV updated (appended): {csv_filepath}")
            else:
                logging.info(f"[CAT:SYSTEM] [SRC:UTILS] ✓ Session errors CSV written successfully: {csv_filepath}")
                logging.info(f"[CAT:SYSTEM] [SRC:UTILS]   Total session error records: {len(SESSION_ERRORS)}")
                
        except Exception as e:
            logging.error(f"[CAT:ERROR] [SRC:UTILS] ✗ Error writing session errors CSV: {e}")
            import traceback
            logging.error(traceback.format_exc())


def write_login_errors_csv(append_mode: bool = False):
    """Write login errors to CSV file."""
    global LOGIN_ERRORS_CSV_FILENAME
    
    # Check if CSV export is enabled
    from config import STRESS_TEST_CONFIG
    if not STRESS_TEST_CONFIG.get('enable_csv_export', True):
        if not append_mode:
            logging.info("[CAT:SYSTEM] [SRC:UTILS] CSV export disabled - skipping login errors CSV write")
        return
    
    cwd = os.getcwd()
    
    with LOGIN_ERRORS_LOCK:
        if not LOGIN_ERRORS:
            if not append_mode:
                logging.info("[CAT:SYSTEM] [SRC:UTILS] No login errors to write to CSV")
            return
        
        # Generate filename with timestamp (only on first write)
        if LOGIN_ERRORS_CSV_FILENAME is None or not append_mode:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            LOGIN_ERRORS_CSV_FILENAME = f"login_errors_{timestamp}.csv"
        
        csv_filepath = os.path.join(cwd, LOGIN_ERRORS_CSV_FILENAME)
        
        fieldnames = [
            'session_id',
            'username',
            'error_message',
            'attempt',
            'error_code',
            'traceback',
            'timestamp'
        ]
        
        try:
            if not hasattr(write_login_errors_csv, '_written_indices'):
                write_login_errors_csv._written_indices = set()
            
            if append_mode:
                errors_to_write = [error for i, error in enumerate(LOGIN_ERRORS) 
                                 if i not in write_login_errors_csv._written_indices]
                if not errors_to_write:
                    return
                mode = 'a'
            else:
                errors_to_write = LOGIN_ERRORS
                mode = 'w'
                write_login_errors_csv._written_indices = set()
            
            logging.info(f"[CAT:SYSTEM] [SRC:UTILS] Writing login errors CSV to: {csv_filepath} (mode: {mode}, records: {len(errors_to_write)})")
            with open(csv_filepath, mode, newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
                
                if not append_mode:
                    writer.writeheader()
                
                start_index = len(write_login_errors_csv._written_indices)
                for i, error_entry in enumerate(errors_to_write):
                    entry_index = start_index + i
                    write_login_errors_csv._written_indices.add(entry_index)
                    writer.writerow(error_entry)
            
            if append_mode:
                logging.info(f"[CAT:SYSTEM] [SRC:UTILS] ✓ Login errors CSV updated (appended): {csv_filepath}")
            else:
                logging.info(f"[CAT:SYSTEM] [SRC:UTILS] ✓ Login errors CSV written successfully: {csv_filepath}")
                logging.info(f"[CAT:SYSTEM] [SRC:UTILS]   Total login error records: {len(LOGIN_ERRORS)}")
                
        except Exception as e:
            logging.error(f"[CAT:ERROR] [SRC:UTILS] ✗ Error writing login errors CSV: {e}")
            import traceback
            logging.error(traceback.format_exc())


def write_chat_response_errors_csv(append_mode: bool = False):
    """Write chat/response errors to CSV file."""
    global CHAT_RESPONSE_ERRORS_CSV_FILENAME
    
    # Check if CSV export is enabled
    from config import STRESS_TEST_CONFIG
    if not STRESS_TEST_CONFIG.get('enable_csv_export', True):
        if not append_mode:
            logging.info("[CAT:SYSTEM] [SRC:UTILS] CSV export disabled - skipping chat/response errors CSV write")
        return
    
    cwd = os.getcwd()
    
    with CHAT_RESPONSE_ERRORS_LOCK:
        if not CHAT_RESPONSE_ERRORS:
            if not append_mode:
                logging.info("[CAT:SYSTEM] [SRC:UTILS] No chat/response errors to write to CSV")
            return
        
        # Generate filename with timestamp (only on first write)
        if CHAT_RESPONSE_ERRORS_CSV_FILENAME is None or not append_mode:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            CHAT_RESPONSE_ERRORS_CSV_FILENAME = f"chat_response_errors_{timestamp}.csv"
        
        csv_filepath = os.path.join(cwd, CHAT_RESPONSE_ERRORS_CSV_FILENAME)
        
        fieldnames = [
            'session_id',
            'username',
            'tab_name',
            'question_num',
            'error_message',
            'error_type',
            'question_text',
            'response_wait_time_ms',
            'traceback',
            'timestamp'
        ]
        
        try:
            if not hasattr(write_chat_response_errors_csv, '_written_indices'):
                write_chat_response_errors_csv._written_indices = set()
            
            if append_mode:
                errors_to_write = [error for i, error in enumerate(CHAT_RESPONSE_ERRORS) 
                                 if i not in write_chat_response_errors_csv._written_indices]
                if not errors_to_write:
                    return
                mode = 'a'
            else:
                errors_to_write = CHAT_RESPONSE_ERRORS
                mode = 'w'
                write_chat_response_errors_csv._written_indices = set()
            
            logging.info(f"[CAT:SYSTEM] [SRC:UTILS] Writing chat/response errors CSV to: {csv_filepath} (mode: {mode}, records: {len(errors_to_write)})")
            with open(csv_filepath, mode, newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
                
                if not append_mode:
                    writer.writeheader()
                
                start_index = len(write_chat_response_errors_csv._written_indices)
                for i, error_entry in enumerate(errors_to_write):
                    entry_index = start_index + i
                    write_chat_response_errors_csv._written_indices.add(entry_index)
                    writer.writerow(error_entry)
            
            if append_mode:
                logging.info(f"[CAT:SYSTEM] [SRC:UTILS] ✓ Chat/response errors CSV updated (appended): {csv_filepath}")
            else:
                logging.info(f"[CAT:SYSTEM] [SRC:UTILS] ✓ Chat/response errors CSV written successfully: {csv_filepath}")
                logging.info(f"[CAT:SYSTEM] [SRC:UTILS]   Total chat/response error records: {len(CHAT_RESPONSE_ERRORS)}")
                
        except Exception as e:
            logging.error(f"[CAT:ERROR] [SRC:UTILS] ✗ Error writing chat/response errors CSV: {e}")
            import traceback
            logging.error(traceback.format_exc())


def write_all_categorized_csvs(append_mode: bool = False):
    """Write all categorized CSV files."""
    write_session_errors_csv(append_mode=append_mode)
    write_login_errors_csv(append_mode=append_mode)
    write_chat_response_errors_csv(append_mode=append_mode)


def get_error_counts() -> Dict[str, int]:
    """Get counts of errors by category."""
    with SESSION_ERRORS_LOCK, LOGIN_ERRORS_LOCK, CHAT_RESPONSE_ERRORS_LOCK:
        return {
            'session_errors': len(SESSION_ERRORS),
            'login_errors': len(LOGIN_ERRORS),
            'chat_response_errors': len(CHAT_RESPONSE_ERRORS),
            'total_errors': len(SESSION_ERRORS) + len(LOGIN_ERRORS) + len(CHAT_RESPONSE_ERRORS)
        }

