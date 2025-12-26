"""
FastAPI-based REST API for remote control and monitoring of the stress test system.

Provides endpoints for:
- System maintenance and health monitoring
- Session management and status
- Metrics retrieval
- Configuration management
- Stress test control
"""
import time
import psutil
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright

# Import configuration
from config import STRESS_TEST_CONFIG, USERS, QUESTION_CONFIG

# Import shared state
from shared_state import (
    CSV_METRICS, 
    PAGE_ERRORS, 
    SESSION_LOGS,
    CSV_EXPORT_FILENAME,
    SESSION_CSV_EXPORT_FILENAME,
    ERRORS_CSV_EXPORT_FILENAME,
    LAST_CSV_EXPORT_TIME
)

# Import tracking and reporting
from tracking.session_tracker import get_tracker
from reporting.csv_reporter import write_csv_report, write_session_logs_csv

# Initialize FastAPI app
app = FastAPI(
    title="NUC Playwright Stress Test API",
    description="REST API for monitoring and controlling the chatbot stress testing system",
    version="1.0.0"
)

# Track API start time for uptime calculation
_api_start_time = time.time()

# Track stress test status
_stress_test_running = False
_stress_test_task: Optional[asyncio.Task] = None
_stress_test_start_time: Optional[float] = None


class HealthStatus(BaseModel):
    """Health status response model."""
    status: str
    timestamp: str
    uptime_seconds: float


class SystemMetrics(BaseModel):
    """System metrics response model."""
    cpu_percent: float
    memory_percent: float
    memory_available_gb: float
    memory_used_gb: float
    memory_total_gb: float


class SessionSummary(BaseModel):
    """Session summary response model."""
    timestamp: Optional[str] = None
    total_active_sessions: int
    total_inactive_sessions: int
    total_sessions_tracked: int
    total_questions_asked: int
    total_questions_answered: int
    total_cycles_completed: int
    total_errors: int
    average_response_time_ms: float
    sessions_by_user: Dict[str, int]
    active_session_details: List[Dict]


class MaintenanceStatus(BaseModel):
    """Maintenance status response model."""
    health: HealthStatus
    system_metrics: SystemMetrics
    configuration: Dict
    session_summary: Optional[SessionSummary]
    csv_export_status: Dict
    metrics_summary: Dict


@app.get("/", response_model=Dict)
async def root():
    """Root endpoint with API information."""
    return {
        "name": "NUC Playwright Stress Test API",
        "version": "1.0.0",
        "description": "REST API for monitoring and controlling the chatbot stress testing system",
        "endpoints": {
            "health": "/health",
            "maintenance": "/maintenance",
            "sessions": "/sessions",
            "metrics": "/metrics",
            "config": "/config",
            "csv_status": "/csv-status",
            "stress_test_start": "/stress-test/start",
            "stress_test_status": "/stress-test/status",
            "stress_test_stop": "/stress-test/stop",
            "stress_test_configure": "/stress-test/configure"
        }
    }


# @app.get("/health", response_model=HealthStatus)
# async def health_check():
#     """
#     Health check endpoint.
    
#     Returns:
#         Health status with uptime information
#     """
#     uptime = time.time() - _api_start_time
#     return HealthStatus(
#         status="healthy",
#         timestamp=datetime.now().isoformat(),
#         uptime_seconds=round(uptime, 2)
#     )


# @app.get("/maintenance", response_model=MaintenanceStatus)
# async def maintenance_status():
#     """
#     Comprehensive maintenance endpoint providing system status, metrics, and configuration.
    
#     This endpoint aggregates:
#     - System health and uptime
#     - System resource usage (CPU, memory)
#     - Stress test configuration
#     - Active session summary and metrics
#     - CSV export status
#     - Metrics summary
    
#     Returns:
#         Complete maintenance status including all system information
#     """
#     try:
#         # Health status
#         uptime = time.time() - _api_start_time
#         health = HealthStatus(
#             status="healthy",
#             timestamp=datetime.now().isoformat(),
#             uptime_seconds=round(uptime, 2)
#         )
        
#         # System metrics
#         cpu_percent = psutil.cpu_percent(interval=0.1)
#         memory = psutil.virtual_memory()
#         system_metrics = SystemMetrics(
#             cpu_percent=round(cpu_percent, 2),
#             memory_percent=round(memory.percent, 2),
#             memory_available_gb=round(memory.available / (1024**3), 2),
#             memory_used_gb=round(memory.used / (1024**3), 2),
#             memory_total_gb=round(memory.total / (1024**3), 2)
#         )
        
#         # Configuration (sanitized - remove passwords)
#         config_sanitized = {}
#         for key, value in STRESS_TEST_CONFIG.items():
#             config_sanitized[key] = value
        
#         config_sanitized['users_count'] = len(USERS)
#         config_sanitized['users'] = [
#             {'username': user['username'], 'questions_count': len(user.get('questions', []))}
#             for user in USERS
#         ]
#         config_sanitized['question_config'] = QUESTION_CONFIG
        
#         # Session summary (if tracker is available)
#         session_summary = None
#         try:
#             tracker = get_tracker()
#             if tracker:
#                 summary_dict = tracker.get_session_summary()
#                 session_summary = SessionSummary(**summary_dict)
#         except Exception as e:
#             # Tracker might not be initialized, that's okay
#             pass
        
#         # CSV export status
#         csv_status = {
#             'csv_metrics_count': len(CSV_METRICS),
#             'page_errors_count': len(PAGE_ERRORS),
#             'session_logs_count': len(SESSION_LOGS),
#             'csv_export_filename': CSV_EXPORT_FILENAME,
#             'session_csv_export_filename': SESSION_CSV_EXPORT_FILENAME,
#             'errors_csv_export_filename': ERRORS_CSV_EXPORT_FILENAME,
#             'last_csv_export_time': (
#                 LAST_CSV_EXPORT_TIME.isoformat() if LAST_CSV_EXPORT_TIME and hasattr(LAST_CSV_EXPORT_TIME, 'isoformat')
#                 else datetime.fromtimestamp(LAST_CSV_EXPORT_TIME).isoformat() if LAST_CSV_EXPORT_TIME and isinstance(LAST_CSV_EXPORT_TIME, (int, float))
#                 else str(LAST_CSV_EXPORT_TIME) if LAST_CSV_EXPORT_TIME 
#                 else None
#             ),
#             'incremental_export_enabled': STRESS_TEST_CONFIG.get('incremental_csv_export', False),
#             'csv_export_interval': STRESS_TEST_CONFIG.get('csv_export_interval', 300)
#         }
        
#         # Metrics summary
#         metrics_summary = {
#             'total_metrics': len(CSV_METRICS),
#             'total_errors': len(PAGE_ERRORS),
#             'total_session_logs': len(SESSION_LOGS),
#             'recent_metrics_count': len([m for m in CSV_METRICS if m.get('timestamp')])  # Count with timestamps
#         }
        
#         # Calculate additional metrics if CSV_METRICS has data
#         if CSV_METRICS:
#             successful_responses = sum(1 for m in CSV_METRICS if m.get('response_received', False))
#             metrics_summary['successful_responses'] = successful_responses
#             metrics_summary['response_success_rate'] = round((successful_responses / len(CSV_METRICS)) * 100, 2) if CSV_METRICS else 0
            
#             # Average response times
#             response_times = [m.get('response_wait_time_ms', 0) for m in CSV_METRICS if m.get('response_wait_time_ms', 0) > 0]
#             if response_times:
#                 metrics_summary['average_response_time_ms'] = round(sum(response_times) / len(response_times), 2)
#                 metrics_summary['min_response_time_ms'] = round(min(response_times), 2)
#                 metrics_summary['max_response_time_ms'] = round(max(response_times), 2)
        
#         return MaintenanceStatus(
#             health=health,
#             system_metrics=system_metrics,
#             configuration=config_sanitized,
#             session_summary=session_summary,
#             csv_export_status=csv_status,
#             metrics_summary=metrics_summary
#         )
        
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error generating maintenance status: {str(e)}")


# @app.get("/sessions", response_model=Dict)
# async def get_sessions():
#     """
#     Get detailed session information.
    
#     Returns:
#         Detailed session summary including active and inactive sessions
#     """
#     try:
#         tracker = get_tracker()
#         if tracker:
#             return tracker.get_session_summary()
#         else:
#             return {
#                 "error": "Session tracker not initialized",
#                 "total_active_sessions": 0,
#                 "total_sessions_tracked": 0
#             }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error retrieving sessions: {str(e)}")


# @app.get("/metrics", response_model=Dict)
# async def get_metrics():
#     """
#     Get aggregated metrics summary.
    
#     Returns:
#         Summary of collected metrics
#     """
#     try:
#         metrics_summary = {
#             'total_metrics': len(CSV_METRICS),
#             'total_errors': len(PAGE_ERRORS),
#             'total_session_logs': len(SESSION_LOGS),
#             'timestamp': datetime.now().isoformat()
#         }
        
#         if CSV_METRICS:
#             successful_responses = sum(1 for m in CSV_METRICS if m.get('response_received', False))
#             metrics_summary['successful_responses'] = successful_responses
#             metrics_summary['failed_responses'] = len(CSV_METRICS) - successful_responses
#             metrics_summary['response_success_rate'] = round((successful_responses / len(CSV_METRICS)) * 100, 2) if CSV_METRICS else 0
            
#             # Response times
#             response_times = [m.get('response_wait_time_ms', 0) for m in CSV_METRICS if m.get('response_wait_time_ms', 0) > 0]
#             if response_times:
#                 metrics_summary['response_times'] = {
#                     'average_ms': round(sum(response_times) / len(response_times), 2),
#                     'min_ms': round(min(response_times), 2),
#                     'max_ms': round(max(response_times), 2),
#                     'count': len(response_times)
#                 }
            
#             # Group by course
#             course_metrics = {}
#             for metric in CSV_METRICS:
#                 course = metric.get('course_number', 'unknown')
#                 if course not in course_metrics:
#                     course_metrics[course] = {'count': 0, 'successful': 0}
#                 course_metrics[course]['count'] += 1
#                 if metric.get('response_received', False):
#                     course_metrics[course]['successful'] += 1
            
#             metrics_summary['by_course'] = course_metrics
        
#         return metrics_summary
        
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error retrieving metrics: {str(e)}")


# @app.get("/config", response_model=Dict)
# async def get_configuration():
#     """
#     Get current stress test configuration.
    
#     Returns:
#         Current configuration (passwords are sanitized)
#     """
#     try:
#         config = {
#             'stress_test_config': STRESS_TEST_CONFIG,
#             'question_config': QUESTION_CONFIG,
#             'users_count': len(USERS),
#             'users': [
#                 {'username': user['username'], 'questions_count': len(user.get('questions', []))}
#                 for user in USERS
#             ]
#         }
#         return config
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error retrieving configuration: {str(e)}")


# @app.get("/csv-status", response_model=Dict)
# async def get_csv_status():
#     """
#     Get CSV export status and information.
    
#     Returns:
#         CSV export status including file names and record counts
#     """
#     try:
#         return {
#             'csv_metrics_count': len(CSV_METRICS),
#             'page_errors_count': len(PAGE_ERRORS),
#             'session_logs_count': len(SESSION_LOGS),
#             'csv_export_filename': CSV_EXPORT_FILENAME,
#             'session_csv_export_filename': SESSION_CSV_EXPORT_FILENAME,
#             'errors_csv_export_filename': ERRORS_CSV_EXPORT_FILENAME,
#             'last_csv_export_time': (
#                 LAST_CSV_EXPORT_TIME.isoformat() if LAST_CSV_EXPORT_TIME and hasattr(LAST_CSV_EXPORT_TIME, 'isoformat')
#                 else datetime.fromtimestamp(LAST_CSV_EXPORT_TIME).isoformat() if LAST_CSV_EXPORT_TIME and isinstance(LAST_CSV_EXPORT_TIME, (int, float))
#                 else str(LAST_CSV_EXPORT_TIME) if LAST_CSV_EXPORT_TIME 
#                 else None
#             ),
#             'incremental_export_enabled': STRESS_TEST_CONFIG.get('incremental_csv_export', False),
#             'csv_export_interval': STRESS_TEST_CONFIG.get('csv_export_interval', 300),
#             'timestamp': datetime.now().isoformat()
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error retrieving CSV status: {str(e)}")


# @app.post("/export-csv", response_model=Dict)
# async def trigger_csv_export():
#     """
#     Manually trigger CSV export.
    
#     Returns:
#         Status of the export operation
#     """
#     try:
#         write_csv_report(append_mode=False)
#         write_session_logs_csv(append_mode=False)
        
#         return {
#             'status': 'success',
#             'message': 'CSV export triggered',
#             'csv_metrics_count': len(CSV_METRICS),
#             'page_errors_count': len(PAGE_ERRORS),
#             'session_logs_count': len(SESSION_LOGS),
#             'timestamp': datetime.now().isoformat()
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error triggering CSV export: {str(e)}")


async def run_stress_test_background():
    """
    Background task to run the stress test.
    This function runs the stress test in a separate async task.
    """
    global _stress_test_running, _stress_test_start_time
    
    try:
        # Setup logging if not already done
        try:
            from utils.logging_utils import setup_logging
            setup_logging()
        except:
            pass
        
        logging.info("=" * 80)
        logging.info("STRESS TEST STARTED VIA API")
        logging.info("=" * 80)
        
        async with async_playwright() as p:
            # Create browser - NOT headless to ensure all windows are visible for monitoring
            browser = await p.chromium.launch(
                headless=False,  # Always visible for monitoring and debugging
                args=['--start-maximized']  # Start maximized for better visibility
            )
            
            logging.info("Browser started")
            
            if STRESS_TEST_CONFIG['enabled']:
                # Import stress_test from main.py
                from main import stress_test
                await stress_test(browser=browser, users=USERS)
            else:
                # Run all users concurrently (normal mode)
                logging.info("Running in normal mode (concurrent users)")
                from main import run_session_with_context
                
                handle_both_courses = STRESS_TEST_CONFIG.get('handle_both_courses', True)
                tasks = []
                for i, user in enumerate(USERS):
                    user_questions = user.get('questions', [])
                    session_id = f"User_{i+1}_{user['username']}"
                    tasks.append(run_session_with_context(
                        browser, 
                        user, 
                        session_id, 
                        questions=user_questions,
                        handle_both_courses=handle_both_courses,
                        semaphore=None
                    ))
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            
            logging.info("Waiting before closing browser...")
            await asyncio.sleep(5)
            await browser.close()
            
        logging.info("=" * 80)
        logging.info("STRESS TEST COMPLETED")
        logging.info("=" * 80)
        
    except Exception as e:
        logging.error(f"Error in stress test: {e}")
        import traceback
        logging.error(traceback.format_exc())
    finally:
        _stress_test_running = False
        _stress_test_start_time = None


class StressTestConfig(BaseModel):
    """Stress test configuration model."""
    sessions_per_user: Optional[int] = None
    batch_enabled: Optional[bool] = None
    users_per_batch: Optional[int] = None
    delay_between_batches: Optional[int] = None
    wait_for_completion: Optional[bool] = None


@app.post("/stress-test/start", response_model=Dict)
async def start_stress_test(config: Optional[StressTestConfig] = None):
    """
    Start the stress test with optional configuration.
    
    You can configure and start the test in a single request by passing configuration parameters.
    If no configuration is provided, uses current settings from config.py.
    
    Args:
        config: Optional stress test configuration (sessions_per_user, batch settings, etc.)
    
    Returns:
        Status of the stress test start operation with applied configuration
    """
    global _stress_test_running, _stress_test_task, _stress_test_start_time
    
    if _stress_test_running:
        raise HTTPException(
            status_code=409, 
            detail="Stress test is already running. Use /stress-test/status to check status."
        )
    
    try:
        # Apply configuration if provided
        applied_config = {}
        if config:
            if config.sessions_per_user is not None:
                STRESS_TEST_CONFIG['sessions_per_user'] = config.sessions_per_user
                applied_config['sessions_per_user'] = config.sessions_per_user
                # Disable dynamic resource calculation when sessions_per_user is explicitly set via API
                STRESS_TEST_CONFIG['dynamic_resource_calculation'] = False
                applied_config['dynamic_resource_calculation'] = False
                logging.info(f"Configured sessions_per_user: {config.sessions_per_user}")
                logging.info("Disabled dynamic_resource_calculation to preserve API-set sessions_per_user")
            
            if config.batch_enabled is not None or config.users_per_batch is not None or config.delay_between_batches is not None or config.wait_for_completion is not None:
                if 'batch_processing' not in STRESS_TEST_CONFIG:
                    STRESS_TEST_CONFIG['batch_processing'] = {}
                
                if config.batch_enabled is not None:
                    STRESS_TEST_CONFIG['batch_processing']['enabled'] = config.batch_enabled
                    applied_config['batch_enabled'] = config.batch_enabled
                    logging.info(f"Configured batch_enabled: {config.batch_enabled}")
                
                if config.users_per_batch is not None:
                    STRESS_TEST_CONFIG['batch_processing']['users_per_batch'] = config.users_per_batch
                    applied_config['users_per_batch'] = config.users_per_batch
                    logging.info(f"Configured users_per_batch: {config.users_per_batch}")
                
                if config.delay_between_batches is not None:
                    STRESS_TEST_CONFIG['batch_processing']['delay_between_batches'] = config.delay_between_batches
                    applied_config['delay_between_batches'] = config.delay_between_batches
                    logging.info(f"Configured delay_between_batches: {config.delay_between_batches}")
                
                if config.wait_for_completion is not None:
                    STRESS_TEST_CONFIG['batch_processing']['wait_for_completion'] = config.wait_for_completion
                    applied_config['wait_for_completion'] = config.wait_for_completion
                    logging.info(f"Configured wait_for_completion: {config.wait_for_completion}")
        
        _stress_test_running = True
        _stress_test_start_time = time.time()
        _stress_test_task = asyncio.create_task(run_stress_test_background())
        
        return {
            'status': 'started',
            'message': 'Stress test started successfully',
            'timestamp': datetime.now().isoformat(),
            'config': {
                'enabled': STRESS_TEST_CONFIG.get('enabled', False),
                'sessions_per_user': STRESS_TEST_CONFIG.get('sessions_per_user', 1),
                'users_count': len(USERS),
                'batch_processing': STRESS_TEST_CONFIG.get('batch_processing', {}),
                'applied_config': applied_config if applied_config else 'using existing config'
            }
        }
    except Exception as e:
        _stress_test_running = False
        _stress_test_start_time = None
        raise HTTPException(status_code=500, detail=f"Error starting stress test: {str(e)}")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

