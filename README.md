# NUC Playwright - Chatbot Stress Testing Tool

A Playwright-based automation tool for stress testing chatbot interactions on Canvas LMS (Instructure). This tool simulates multiple concurrent user sessions, each interacting with course chatbots, and provides comprehensive metrics and logging.

## Features

- **Concurrent Session Testing**: Run multiple user sessions simultaneously to stress test the chatbot system
- **Dual Course Support**: Automatically opens and tests chatbots in two different courses in parallel
- **Comprehensive Metrics**: Tracks response times, WebSocket connections, API calls, and round-by-round performance
- **Question Pool Management**: Supports course-specific and general question pools with random selection
- **Network Monitoring**: Monitors WebSocket connections and API requests for performance analysis
- **Flexible Configuration**: Easy-to-modify configuration for stress test parameters

## Requirements

- Python 3.12+
- Playwright browser binaries

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd NUC_playwright
```

2. Install dependencies using `uv` (recommended) or `pip`:
```bash
# Using uv
uv sync

# Or using pip
pip install -r requirements.txt
```

3. Install Playwright browsers:
```bash
playwright install chromium
```

## Configuration

### Users

The system uses **5 fixed users** (defined in `config.py`). These users are static and cannot be changed via API. To modify users, edit the `USERS` list in `config.py`.

### Stress Test Configuration

Edit the `STRESS_TEST_CONFIG` dictionary in `config.py`:

```python
STRESS_TEST_CONFIG = {
    'enabled': True,  # Set to False for normal single session mode
    'concurrent_sessions': 10,  # Number of concurrent sessions per iteration
    'iterations': 3,  # Number of iterations to run
    'delay_between_iterations': 5,  # Seconds to wait between iterations
}
```

### User Credentials

The system uses **5 fixed users** defined in the `USERS` list in `config.py`. To modify users, edit this list:

```python
USERS = [
    {
        'username': 'user@example.com',
        'password': 'password123',
    },
    # Add more users...
]
```

### Question Configuration

Configure question handling parameters:

```python
QUESTION_CONFIG = {
    'questions_per_session': 3,  # Number of questions to ask per session
    'min_response_wait': 5,  # Minimum seconds to wait for response
    'max_response_wait': 30,  # Maximum seconds to wait for response
    'response_check_interval': 2,  # Check every N seconds if response appeared
}
```

### Question Pools

- **Course 1 Questions**: Add course-specific questions to `course_1_questions`
- **Course 2 Questions**: Add course-specific questions to `course_2_questions`
- **General Questions**: Add general questions to `general_questions`

Questions are randomly selected and assigned to each session based on the course.

## Usage

### Running Stress Tests

By default, the script runs in stress test mode:

```bash
python main.py
```

This will:
1. Launch a Chromium browser (visible, not headless)
2. Create multiple concurrent sessions (as configured)
3. Each session will:
   - Log in with a user credential
   - Open two courses in parallel
   - Interact with chatbots in both courses simultaneously
   - Ask multiple questions and measure response times
4. Generate comprehensive metrics and logs

### Running Single Session Mode

Set `STRESS_TEST_CONFIG['enabled'] = False` in `main.py` to run in normal single session mode, which processes users sequentially.

### Running the REST API

The application includes a FastAPI-based REST API for remote monitoring and control:

```bash
# Run the API server
python api.py

# Or using uvicorn directly
uvicorn api:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000` with interactive API documentation at `http://localhost:8000/docs`.

## REST API Endpoints

### Health Check

**GET** `/health`

Check the health status of the API service.

**Sample Request:**
```bash
curl http://localhost:8000/health
```

**Sample Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:45.123456",
  "uptime_seconds": 3600.5
}
```

### Maintenance Status

**GET** `/maintenance`

Comprehensive maintenance endpoint providing system status, metrics, and configuration. This is the main endpoint for monitoring the stress test system.

**Sample Request:**
```bash
curl http://localhost:8000/maintenance
```

**Sample Response:**
```json
{
  "health": {
    "status": "healthy",
    "timestamp": "2024-01-15T10:30:45.123456",
    "uptime_seconds": 3600.5
  },
  "system_metrics": {
    "cpu_percent": 45.2,
    "memory_percent": 62.5,
    "memory_available_gb": 8.5,
    "memory_used_gb": 14.2,
    "memory_total_gb": 22.7
  },
  "configuration": {
    "enabled": true,
    "sessions_per_user": 10,
    "max_concurrent_contexts": 10000,
    "handle_both_courses": true,
    "users_count": 5,
    "users": [
      {"username": "user@example.com", "questions_count": 30}
    ]
  },
  "session_summary": {
    "timestamp": "2024-01-15 10:30:45.123",
    "total_active_sessions": 25,
    "total_inactive_sessions": 75,
    "total_sessions_tracked": 100,
    "total_questions_asked": 1250,
    "total_questions_answered": 1200,
    "total_cycles_completed": 50,
    "total_errors": 5,
    "average_response_time_ms": 1250.5,
    "sessions_by_user": {
      "user@example.com": 20
    },
    "active_session_details": [...]
  },
  "csv_export_status": {
    "csv_metrics_count": 1250,
    "page_errors_count": 10,
    "session_logs_count": 100,
    "csv_export_filename": "stress_test_results_20240115_103000.csv",
    "last_csv_export_time": "2024-01-15T10:25:00.000000",
    "incremental_export_enabled": true,
    "csv_export_interval": 300
  },
  "metrics_summary": {
    "total_metrics": 1250,
    "total_errors": 10,
    "total_session_logs": 100,
    "successful_responses": 1200,
    "response_success_rate": 96.0,
    "average_response_time_ms": 1250.5,
    "min_response_time_ms": 450.2,
    "max_response_time_ms": 3500.8
  }
}
```

### Get Sessions

**GET** `/sessions`

Get detailed session information and statistics.

**Sample Request:**
```bash
curl http://localhost:8000/sessions
```

**Sample Response:**
```json
{
  "timestamp": "2024-01-15 10:30:45.123",
  "total_active_sessions": 25,
  "total_inactive_sessions": 75,
  "total_sessions_tracked": 100,
  "total_questions_asked": 1250,
  "total_questions_answered": 1200,
  "total_cycles_completed": 50,
  "total_errors": 5,
  "average_response_time_ms": 1250.5,
  "sessions_by_user": {
    "user1@example.com": 10,
    "user2@example.com": 15
  },
  "active_session_details": [
    {
      "session_id": "Session_1_user1@example.com",
      "username": "user1@example.com",
      "questions_asked": 15,
      "questions_answered": 14,
      "cycles_completed": 1,
      "errors": 0,
      "duration_seconds": 125.5,
      "courses_active": 2
    }
  ]
}
```

### Get Metrics

**GET** `/metrics`

Get aggregated metrics summary including response times and success rates.

**Sample Request:**
```bash
curl http://localhost:8000/metrics
```

**Sample Response:**
```json
{
  "total_metrics": 1250,
  "total_errors": 10,
  "total_session_logs": 100,
  "timestamp": "2024-01-15T10:30:45.123456",
  "successful_responses": 1200,
  "failed_responses": 50,
  "response_success_rate": 96.0,
  "response_times": {
    "average_ms": 1250.5,
    "min_ms": 450.2,
    "max_ms": 3500.8,
    "count": 1200
  },
  "by_course": {
    "1": {"count": 600, "successful": 580},
    "2": {"count": 650, "successful": 620}
  }
}
```

### Get Configuration

**GET** `/config`

Get current stress test configuration (passwords are sanitized for security).

**Sample Request:**
```bash
curl http://localhost:8000/config
```

**Sample Response:**
```json
{
  "stress_test_config": {
    "enabled": true,
    "sessions_per_user": 10,
    "delay_between_questions": 0,
    "handle_both_courses": true,
    "max_concurrent_contexts": 10000,
    "dynamic_resource_calculation": true,
    "websocket_stress_mode": true,
    "continuous_mode": true
  },
  "question_config": {
    "questions_per_session": null,
    "min_response_wait": 5,
    "max_response_wait": 30,
    "response_check_interval": 2
  },
  "users_count": 5,
  "users": [
    {
      "username": "user@example.com",
      "questions_count": 30
    }
  ]
}
```

### Get CSV Status

**GET** `/csv-status`

Get CSV export status and file information.

**Sample Request:**
```bash
curl http://localhost:8000/csv-status
```

**Sample Response:**
```json
{
  "csv_metrics_count": 1250,
  "page_errors_count": 10,
  "session_logs_count": 100,
  "csv_export_filename": "stress_test_results_20240115_103000.csv",
  "session_csv_export_filename": "session_logs_20240115_103000.csv",
  "errors_csv_export_filename": "stress_test_errors_20240115_103000.csv",
  "last_csv_export_time": "2024-01-15T10:25:00.000000",
  "incremental_export_enabled": true,
  "csv_export_interval": 300,
  "timestamp": "2024-01-15T10:30:45.123456"
}
```

### Trigger CSV Export

**POST** `/export-csv`

Manually trigger CSV export of all collected metrics and logs.

**Sample Request:**
```bash
curl -X POST http://localhost:8000/export-csv
```

**Sample Response:**
```json
{
  "status": "success",
  "message": "CSV export triggered",
  "csv_metrics_count": 1250,
  "page_errors_count": 10,
  "session_logs_count": 100,
  "timestamp": "2024-01-15T10:30:45.123456"
}
```

### Start Stress Test

**POST** `/stress-test/start`

Start the stress test remotely via API. The stress test will run in the background.

You can configure and start the test in a single request by passing configuration parameters in the request body.

**Parameters (all optional):**
- `sessions_per_user`: Number of sessions per user
- `batch_enabled`: Enable batch processing (true/false)
- `users_per_batch`: Number of users per batch (5 users total, fixed)
- `delay_between_batches`: Delay between batches in seconds
- `wait_for_completion`: Wait for batch to complete before starting next (true/false)

**Sample Request (start with default config):**
```bash
curl -X POST http://localhost:8000/stress-test/start
```

**Sample Request (start with configuration):**
```bash
curl -X POST "http://localhost:8000/stress-test/start" \
  -H "Content-Type: application/json" \
  -d '{
    "sessions_per_user": 5,
    "batch_enabled": true,
    "users_per_batch": 3,
    "delay_between_batches": 10,
    "wait_for_completion": true
  }'
```

**Sample Response:**
```json
{
  "status": "started",
  "message": "Stress test started successfully",
  "timestamp": "2024-01-15T10:30:45.123456",
  "config": {
    "enabled": true,
    "sessions_per_user": 5,
    "users_count": 5,
    "batch_processing": {
      "enabled": true,
      "users_per_batch": 3,
      "delay_between_batches": 10,
      "wait_for_completion": true
    },
    "applied_config": {
      "sessions_per_user": 5,
      "batch_enabled": true,
      "users_per_batch": 3,
      "delay_between_batches": 10,
      "wait_for_completion": true
    }
  }
}
```

**Sample Response (using existing config):**
```json
{
  "status": "started",
  "message": "Stress test started successfully",
  "timestamp": "2024-01-15T10:30:45.123456",
  "config": {
    "enabled": true,
    "sessions_per_user": 1,
    "users_count": 5,
    "batch_processing": {
      "enabled": false
    },
    "applied_config": "using existing config"
  }
}
```

**Error Response (if already running):**
```json
{
  "detail": "Stress test is already running. Use /stress-test/status to check status."
}
```

### Get Stress Test Status

**GET** `/stress-test/status`

Check if a stress test is currently running and get its status.

**Sample Request:**
```bash
curl http://localhost:8000/stress-test/status
```

**Sample Response (when running):**
```json
{
  "running": true,
  "timestamp": "2024-01-15T10:30:45.123456",
  "elapsed_seconds": 125.5,
  "elapsed_minutes": 2.09,
  "task_done": false
}
```

**Sample Response (when not running):**
```json
{
  "running": false,
  "timestamp": "2024-01-15T10:30:45.123456",
  "message": "No stress test is currently running"
}
```

**Sample Response (when completed):**
```json
{
  "running": false,
  "timestamp": "2024-01-15T10:30:45.123456",
  "task_done": true,
  "completed": true
}
```

### Stop Stress Test

**POST** `/stress-test/stop`

Stop the currently running stress test. Browser cleanup may take a few moments.

**Sample Request:**
```bash
curl -X POST http://localhost:8000/stress-test/stop
```

**Sample Response:**
```json
{
  "status": "stopped",
  "message": "Stress test stop requested. Browser cleanup may take a few moments.",
  "timestamp": "2024-01-15T10:30:45.123456"
}
```

**Sample Response (when not running):**
```json
{
  "status": "not_running",
  "message": "No stress test is currently running",
  "timestamp": "2024-01-15T10:30:45.123456"
}
```

### Configure Stress Test

**POST** `/stress-test/configure`

Configure stress test parameters including batch processing settings.

**Parameters:**
- `sessions_per_user` (optional): Number of sessions per user
- `batch_enabled` (optional): Enable batch processing (true/false)
- `users_per_batch` (optional): Number of users per batch
- `delay_between_batches` (optional): Delay between batches in seconds
- `wait_for_completion` (optional): Wait for batch to complete before starting next (true/false)

**Sample Request:**
```bash
curl -X POST "http://localhost:8000/stress-test/configure" \
  -H "Content-Type: application/json" \
  -d '{
    "sessions_per_user": 5,
    "batch_enabled": true,
    "users_per_batch": 3,
    "delay_between_batches": 10,
    "wait_for_completion": true
  }'
```

**Sample Response:**
```json
{
  "status": "success",
  "message": "Configuration updated",
  "config": {
    "sessions_per_user": 5,
    "batch_processing": {
      "enabled": true,
      "users_per_batch": 3,
      "delay_between_batches": 10,
      "wait_for_completion": true
    }
  },
  "timestamp": "2024-01-15T10:30:45.123456"
}
```

**Batch Processing Example (5 users total, fixed):**
- With `users_per_batch: 3`, `sessions_per_user: 5`:
  - Batch 1: Users 1-3 × 5 sessions = 15 sessions → wait 10 seconds
  - Batch 2: Users 4-5 × 5 sessions = 10 sessions
- With `users_per_batch: 2`, `sessions_per_user: 10`:
  - Batch 1: Users 1-2 × 10 sessions = 20 sessions → wait 10 seconds
  - Batch 2: Users 3-4 × 10 sessions = 20 sessions → wait 10 seconds
  - Batch 3: User 5 × 10 sessions = 10 sessions
- If `wait_for_completion: false`, batches run concurrently (old batches keep running)
- **Note:** The system always uses 5 fixed users (defined in config.py)

### Using the API with Python

```python
import requests

# Base URL
BASE_URL = "http://localhost:8000"

# Get maintenance status
response = requests.get(f"{BASE_URL}/maintenance")
maintenance_data = response.json()
print(f"Active sessions: {maintenance_data['session_summary']['total_active_sessions']}")
print(f"CPU usage: {maintenance_data['system_metrics']['cpu_percent']}%")

# Get metrics
response = requests.get(f"{BASE_URL}/metrics")
metrics = response.json()
print(f"Success rate: {metrics['response_success_rate']}%")

# Trigger CSV export
response = requests.post(f"{BASE_URL}/export-csv")
print(response.json()['message'])

# Start stress test with default config
response = requests.post(f"{BASE_URL}/stress-test/start")
print(response.json()['message'])

# Start stress test with configuration (configure and start in one request)
response = requests.post(f"{BASE_URL}/stress-test/start", json={
    "sessions_per_user": 5,
    "batch_enabled": True,
    "users_per_batch": 3,
    "delay_between_batches": 10,
    "wait_for_completion": True
})
print(response.json()['message'])
print(f"Applied config: {response.json()['config']['applied_config']}")

# Check stress test status
response = requests.get(f"{BASE_URL}/stress-test/status")
status = response.json()
if status['running']:
    print(f"Stress test running for {status.get('elapsed_seconds', 0)} seconds")
else:
    print("No stress test running")

# Stop stress test
response = requests.post(f"{BASE_URL}/stress-test/stop")
print(response.json()['message'])

# Configure batch processing
response = requests.post(f"{BASE_URL}/stress-test/configure", json={
    "sessions_per_user": 5,
    "batch_enabled": True,
    "users_per_batch": 3,
    "delay_between_batches": 10,
    "wait_for_completion": True
})
print(response.json()['message'])
```

### Using the API with cURL (Command Line)

```bash
# Health check
curl http://localhost:8000/health

# Get maintenance status (formatted)
curl http://localhost:8000/maintenance | python -m json.tool

# Get sessions
curl http://localhost:8000/sessions

# Get metrics
curl http://localhost:8000/metrics

# Get configuration
curl http://localhost:8000/config

# Get CSV status
curl http://localhost:8000/csv-status

# Trigger CSV export
curl -X POST http://localhost:8000/export-csv

# Start stress test with default config
curl -X POST http://localhost:8000/stress-test/start

# Start stress test with configuration (configure and start in one request)
curl -X POST "http://localhost:8000/stress-test/start" \
  -H "Content-Type: application/json" \
  -d '{"sessions_per_user": 5, "batch_enabled": true, "users_per_batch": 3, "delay_between_batches": 10}'

# Check stress test status
curl http://localhost:8000/stress-test/status

# Stop stress test
curl -X POST http://localhost:8000/stress-test/stop

# Configure stress test (batch processing: 3 users per batch, 5 sessions per user, 10s delay)
curl -X POST "http://localhost:8000/stress-test/configure" \
  -H "Content-Type: application/json" \
  -d '{"sessions_per_user": 5, "batch_enabled": true, "users_per_batch": 3, "delay_between_batches": 10}'
```

## How It Works

1. **Session Creation**: Each concurrent session gets its own browser context (separate window)
2. **Login**: Sessions authenticate using provided credentials
3. **Course Navigation**: Opens Course 1 and Course 2 in parallel tabs
4. **Chatbot Interaction**:
   - Clicks the chatbot button
   - Handles authorization if needed
   - Asks questions from the question pool
   - Waits for responses and measures timing
5. **Metrics Collection**: Tracks:
   - Question submission times
   - Response wait times
   - WebSocket connection times
   - API request/response times
   - Round-by-round performance

## Metrics and Logging

The tool provides detailed logging including:

- **Session Metrics**: Total session time, successful/failed sessions
- **Round Metrics**: Per-question timing and response status
- **Network Metrics**: WebSocket connections and API calls
- **Performance Summary**: Average, min, and max iteration times

All logs are output to the console with timestamps and session identifiers.

## Project Structure

```
NUC_playwright/
├── main.py                 # Main script with all automation logic
├── main_modular.py         # Modular entry point
├── api.py                  # FastAPI REST API for monitoring and control
├── config.py               # Configuration constants
├── pyproject.toml          # Project dependencies
├── README.md               # This file
├── browser/                # Browser utilities and monitoring
├── session/                # Session management modules
├── tracking/               # Session tracking and reporting
├── reporting/              # CSV reporting and metrics export
├── utils/                  # Utility functions and helpers
└── .venv/                  # Virtual environment (not in repo)
```

## Key Functions

- `open_course()`: Opens a course in a new tab
- `interact_with_chatbot()`: Handles chatbot interactions and question asking
- `run_user_session()`: Runs a complete user session (login + chatbot interactions)
- `stress_test()`: Orchestrates multiple concurrent sessions
- `get_iframe_content_frame()`: Helper for reliable iframe access
- `select_questions_for_course()`: Helper for question selection logic

## Troubleshooting

### Browser Not Launching
- Ensure Playwright browsers are installed: `playwright install chromium`
- Check that no other processes are using the browser

### Timeout Errors
- Increase timeout values in the code if your network is slow
- Check that the Canvas LMS instance is accessible

### Iframe Access Issues
- The script includes retry logic for iframe access
- Check browser console for JavaScript errors

### Session Failures
- Verify user credentials are correct
- Ensure courses are available in the dashboard
- Check network connectivity

## Notes

- The browser runs in visible mode (`headless=False`) for debugging
- Each concurrent session uses a separate browser context to ensure isolation
- Questions are randomly selected and shuffled for each session
- The script includes comprehensive error handling and retry logic

## License

[Add your license information here]

## Contributing

[Add contribution guidelines if applicable]
