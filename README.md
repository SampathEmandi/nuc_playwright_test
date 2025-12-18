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

### Stress Test Configuration

Edit the `STRESS_TEST_CONFIG` dictionary in `main.py`:

```python
STRESS_TEST_CONFIG = {
    'enabled': True,  # Set to False for normal single session mode
    'concurrent_sessions': 10,  # Number of concurrent sessions per iteration
    'iterations': 3,  # Number of iterations to run
    'delay_between_iterations': 5,  # Seconds to wait between iterations
}
```

### User Credentials

Add your test user credentials to the `USERS` list:

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
├── pyproject.toml          # Project dependencies
├── README.md               # This file
├── tampermonkey_scripts.js # Tampermonkey scripts (if used)
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
