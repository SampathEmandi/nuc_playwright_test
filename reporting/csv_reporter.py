"""
CSV reporting module for exporting metrics and logs.
"""
import csv
import os
import logging
from datetime import datetime
from shared_state import CSV_METRICS, PAGE_ERRORS, SESSION_LOGS, CSV_EXPORT_FILENAME, SESSION_CSV_EXPORT_FILENAME, ERRORS_CSV_EXPORT_FILENAME


def log_session_event(session_id, event_type, message, error=None, traceback_text=None, username=None, **kwargs):
    """Log a session-level event to SESSION_LOGS for CSV export.
    
    Args:
        session_id: Session identifier
        event_type: Type of event (e.g., 'SESSION_START', 'SESSION_END', 'ERROR', 'WARNING', 'INFO')
        message: Event message
        error: Error message if applicable
        traceback_text: Full traceback if applicable
        username: Username associated with session
        **kwargs: Additional metadata
    """
    SESSION_LOGS.append({
        'session_id': session_id,
        'username': username or '',
        'event_type': event_type,
        'message': message,
        'error': error or '',
        'traceback': traceback_text or '',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
        **kwargs
    })


def write_session_logs_csv(append_mode=False):
    """Write session logs to CSV file."""
    global SESSION_CSV_EXPORT_FILENAME
    
    cwd = os.getcwd()
    
    if not SESSION_LOGS:
        if not append_mode:
            logging.warning("No session logs collected to write to CSV")
        return
    
    if SESSION_CSV_EXPORT_FILENAME is None or not append_mode:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        SESSION_CSV_EXPORT_FILENAME = f"session_logs_{timestamp}.csv"
    
    session_csv_filepath = os.path.join(cwd, SESSION_CSV_EXPORT_FILENAME)
    
    fieldnames = [
        'session_id',
        'username',
        'event_type',
        'message',
        'error',
        'traceback',
        'timestamp',
        'stage',
        'session_duration_ms',
        'success',
        'questions_count',
        'handle_both_courses',
        'pages_closed'
    ]
    
    try:
        if not hasattr(write_session_logs_csv, '_written_indices'):
            write_session_logs_csv._written_indices = set()
        
        if append_mode:
            entries_to_write = [log_entry for i, log_entry in enumerate(SESSION_LOGS) 
                               if i not in write_session_logs_csv._written_indices]
            if not entries_to_write:
                return
            mode = 'a'
        else:
            entries_to_write = SESSION_LOGS
            mode = 'w'
            write_session_logs_csv._written_indices = set()
        
        logging.info(f"📝 Writing session logs CSV to: {session_csv_filepath} (mode: {mode}, records: {len(entries_to_write)})")
        with open(session_csv_filepath, mode, newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
            
            if not append_mode:
                writer.writeheader()
            
            start_index = len(write_session_logs_csv._written_indices)
            for i, log_entry in enumerate(entries_to_write):
                entry_index = start_index + i
                write_session_logs_csv._written_indices.add(entry_index)
                row = {
                    'session_id': log_entry.get('session_id', ''),
                    'username': log_entry.get('username', ''),
                    'event_type': log_entry.get('event_type', ''),
                    'message': log_entry.get('message', '')[:500],
                    'error': log_entry.get('error', '')[:500],
                    'traceback': log_entry.get('traceback', '')[:2000] if log_entry.get('traceback') else '',
                    'stage': log_entry.get('stage', ''),
                    'timestamp': log_entry.get('timestamp', ''),
                    'session_duration_ms': log_entry.get('session_duration_ms', ''),
                    'success': log_entry.get('success', ''),
                    'questions_count': log_entry.get('questions_count', ''),
                    'handle_both_courses': log_entry.get('handle_both_courses', ''),
                    'pages_closed': log_entry.get('pages_closed', ''),
                }
                writer.writerow(row)
        
        if append_mode:
            logging.info(f"✓ Session logs CSV report updated (appended): {session_csv_filepath}")
        else:
            logging.info(f"✓ Session logs CSV report written successfully: {session_csv_filepath}")
            logging.info(f"  Total session log records: {len(SESSION_LOGS)}")
            
    except Exception as e:
        logging.error(f"✗ Error writing session logs CSV report: {e}")
        import traceback
        logging.error(traceback.format_exc())


def write_csv_report(append_mode=False):
    """Write collected metrics to CSV file."""
    global CSV_EXPORT_FILENAME, ERRORS_CSV_EXPORT_FILENAME
    
    cwd = os.getcwd()
    
    if not CSV_METRICS and not PAGE_ERRORS:
        if not append_mode:
            logging.warning("No metrics collected to write to CSV")
        return
    
    if CSV_EXPORT_FILENAME is None or not append_mode:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        CSV_EXPORT_FILENAME = f"stress_test_results_{timestamp}.csv"
        ERRORS_CSV_EXPORT_FILENAME = f"stress_test_errors_{timestamp}.csv"
    
    csv_filepath = os.path.join(cwd, CSV_EXPORT_FILENAME)
    
    fieldnames = [
        'session_id',
        'user',
        'course_number',
        'question_number',
        'question_text',
        'question_submit_time_ms',
        'response_wait_time_ms',
        'question_total_time_ms',
        'response_received',
        'login_time_ms',
        'course_open_time_ms',
        'error',
        'timestamp'
    ]
    
    try:
        if not hasattr(write_csv_report, '_written_indices'):
            write_csv_report._written_indices = set()
        
        if append_mode:
            metrics_to_write = [metric for i, metric in enumerate(CSV_METRICS) 
                               if i not in write_csv_report._written_indices]
            mode = 'a'
        else:
            metrics_to_write = CSV_METRICS
            mode = 'w'
            write_csv_report._written_indices = set()
        
        logging.info(f"📝 Writing CSV to: {csv_filepath} (mode: {mode}, records: {len(metrics_to_write)})")
        with open(csv_filepath, mode, newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            if not append_mode:
                writer.writeheader()
            
            start_index = len(write_csv_report._written_indices)
            for i, metric in enumerate(metrics_to_write):
                entry_index = start_index + i
                write_csv_report._written_indices.add(entry_index)
                
                session_id = metric.get('session_id', '')
                user = 'Unknown'
                if session_id:
                    parts = session_id.split('_')
                    if len(parts) >= 3:
                        user = '_'.join(parts[2:])
                
                row = {
                    'session_id': session_id,
                    'user': user,
                    'course_number': metric.get('course_number', ''),
                    'question_number': metric.get('question_number', ''),
                    'question_text': metric.get('question_text', ''),
                    'question_submit_time_ms': metric.get('question_submit_time_ms', 0),
                    'response_wait_time_ms': metric.get('response_wait_time_ms', 0),
                    'question_total_time_ms': metric.get('question_total_time_ms', 0),
                    'response_received': metric.get('response_received', False),
                    'login_time_ms': metric.get('login_time_ms', ''),
                    'course_open_time_ms': metric.get('course_open_time_ms', ''),
                    'error': metric.get('error', ''),
                    'timestamp': metric.get('timestamp', '')
                }
                writer.writerow(row)
        
        if append_mode:
            logging.info(f"✓ CSV report updated (appended): {csv_filepath}")
        else:
            logging.info(f"✓ CSV report written successfully: {csv_filepath}")
            logging.info(f"  Total records: {len(CSV_METRICS)}")
        
        # Write errors CSV if there are any errors
        if PAGE_ERRORS:
            errors_csv_filepath = os.path.join(cwd, ERRORS_CSV_EXPORT_FILENAME)
            error_fieldnames = [
                'type',
                'message',
                'location',
                'url',
                'method',
                'error',
                'stack',
                'tab_name',
                'session_id',
                'username',
                'timestamp'
            ]
            
            try:
                if not hasattr(write_csv_report, '_error_written_indices'):
                    write_csv_report._error_written_indices = set()
                
                if append_mode:
                    errors_to_write = [error for i, error in enumerate(PAGE_ERRORS) 
                                     if i not in write_csv_report._error_written_indices]
                    error_mode = 'a'
                else:
                    errors_to_write = PAGE_ERRORS
                    error_mode = 'w'
                    write_csv_report._error_written_indices = set()
                
                logging.info(f"📝 Writing errors CSV to: {errors_csv_filepath} (mode: {error_mode}, records: {len(errors_to_write)})")
                with open(errors_csv_filepath, error_mode, newline='', encoding='utf-8') as errors_csvfile:
                    writer = csv.DictWriter(errors_csvfile, fieldnames=error_fieldnames)
                    
                    if not append_mode:
                        writer.writeheader()
                    
                    error_start_index = len(write_csv_report._error_written_indices)
                    for i, error in enumerate(errors_to_write):
                        error_entry_index = error_start_index + i
                        write_csv_report._error_written_indices.add(error_entry_index)
                        row = {
                            'type': error.get('type', ''),
                            'message': error.get('message', '')[:500],
                            'location': error.get('location', ''),
                            'url': error.get('url', ''),
                            'method': error.get('method', ''),
                            'error': error.get('error', ''),
                            'stack': error.get('stack', '')[:1000] if error.get('stack') else '',
                            'tab_name': error.get('tab_name', ''),
                            'session_id': error.get('session_id', ''),
                            'username': error.get('username', ''),
                            'timestamp': error.get('timestamp', '')
                        }
                        writer.writerow(row)
                
                if append_mode:
                    logging.info(f"✓ Errors CSV report updated (appended): {errors_csv_filepath}")
                else:
                    logging.info(f"✓ Errors CSV report written successfully: {errors_csv_filepath}")
                    logging.info(f"  Total error records: {len(PAGE_ERRORS)}")
                    
            except Exception as e:
                logging.error(f"✗ Error writing errors CSV report: {e}")
                import traceback
                logging.error(traceback.format_exc())
        
    except Exception as e:
        logging.error(f"✗ Error writing CSV report: {e}")
        import traceback
        logging.error(traceback.format_exc())
    
    # Write session logs CSV in parallel
    write_session_logs_csv()