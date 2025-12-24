"""
Examples of using structured logging in the stress test application.
"""
from utils.structured_logger import (
    get_logger,
    log_websocket,
    log_login,
    log_question,
    log_response,
    log_error,
    LogCategory,
    LogSource
)

# Example 1: Login logging
def example_login_logging(username: str, session_id: str):
    """Example of logging login events."""
    # Success
    log_login(
        "Login attempt started",
        username=username,
        session_id=session_id,
        extra_data={"attempt": 1, "max_retries": 3}
    )
    
    # Error
    log_login(
        "Login failed - invalid credentials",
        username=username,
        session_id=session_id,
        level="error",
        extra_data={"attempt": 2, "error_code": "INVALID_CREDENTIALS"}
    )
    
    # Success
    log_login(
        "Login successful",
        username=username,
        session_id=session_id,
        extra_data={"attempt": 1, "duration_ms": 1234}
    )


# Example 2: WebSocket logging
def example_websocket_logging(username: str, session_id: str, tab_name: str):
    """Example of logging websocket events."""
    # WebSocket connection
    log_websocket(
        "WebSocket connection established",
        username=username,
        session_id=session_id,
        tab_name=tab_name,
        extra_data={"url": "wss://example.com/ws", "protocol": "websocket"}
    )
    
    # WebSocket message sent
    log_websocket(
        "Question sent via WebSocket",
        username=username,
        session_id=session_id,
        tab_name=tab_name,
        extra_data={"message_type": "question", "question_id": "q123"}
    )
    
    # WebSocket message received
    log_websocket(
        "Response received via WebSocket",
        username=username,
        session_id=session_id,
        tab_name=tab_name,
        extra_data={"message_type": "response", "response_time_ms": 567}
    )
    
    # WebSocket error
    log_websocket(
        "WebSocket connection error",
        username=username,
        session_id=session_id,
        tab_name=tab_name,
        level="error",
        extra_data={"error": "Connection closed unexpectedly", "code": 1006}
    )


# Example 3: Question logging
def example_question_logging(username: str, session_id: str, tab_name: str):
    """Example of logging question events."""
    # Question sent
    log_question(
        "Question submitted to chatbot",
        username=username,
        session_id=session_id,
        tab_name=tab_name,
        question_num=1,
        extra_data={"question": "What is this course about?", "submit_time_ms": 123}
    )
    
    # Waiting for response
    log_question(
        "Waiting for bot response",
        username=username,
        session_id=session_id,
        tab_name=tab_name,
        question_num=1,
        extra_data={"min_wait": 5, "max_wait": 30}
    )
    
    # Question completed
    log_question(
        "Question processing completed",
        username=username,
        session_id=session_id,
        tab_name=tab_name,
        question_num=1,
        extra_data={"total_time_ms": 3456, "response_received": True}
    )


# Example 4: Response logging
def example_response_logging(username: str, session_id: str, tab_name: str):
    """Example of logging response events."""
    # Response detected
    log_response(
        "Response detected and verified",
        username=username,
        session_id=session_id,
        tab_name=tab_name,
        question_num=1,
        extra_data={"wait_time_ms": 2345, "response_length": 500}
    )
    
    # Response timeout
    log_response(
        "Response timeout - max wait time reached",
        username=username,
        session_id=session_id,
        tab_name=tab_name,
        question_num=2,
        level="warning",
        extra_data={"max_wait": 30, "actual_wait": 30}
    )


# Example 5: Using logger directly with context
def example_direct_logger_usage():
    """Example of using logger directly with context."""
    # Create logger with context
    logger = get_logger(
        username="user@example.com",
        session_id="User1_Session1_user@example.com",
        tab_name="Course 1",
        category=LogCategory.CHATBOT,
        source=LogSource.CHATBOT
    )
    
    # Use logger
    logger.info("Chatbot interface initialized")
    logger.warning("Slow response detected", extra_data={"response_time_ms": 5000})
    logger.error("Failed to send question", extra_data={"error": "Network timeout"}, exc_info=True)
    
    # Create logger with different context
    nav_logger = logger.with_context(
        category=LogCategory.NAVIGATION,
        source=LogSource.SESSION
    )
    nav_logger.info("Navigating to course page", extra_data={"course_number": 1})


# Example 6: Error logging with full context
def example_error_logging(username: str, session_id: str, tab_name: str):
    """Example of logging errors with full context."""
    try:
        # Some operation that might fail
        raise ValueError("Example error")
    except Exception as e:
        log_error(
            "Failed to process question",
            username=username,
            session_id=session_id,
            tab_name=tab_name,
            category=LogCategory.ERROR,
            source=LogSource.CHATBOT,
            extra_data={"question_num": 3, "error_type": type(e).__name__},
            exc_info=True
        )


# Example output format:
# 2024-01-01 12:00:00 | INFO     | [CAT:LOGIN] [SRC:SESSION] [USER:user@example.com] [SESSION:Session1] Login attempt started | DATA: {"attempt": 1, "max_retries": 3}
# 2024-01-01 12:00:01 | ERROR    | [CAT:WEBSOCKET] [SRC:NETWORK_MONITOR] [USER:user@example.com] [SESSION:Session1] [TAB:Course 1] WebSocket connection error | DATA: {"error": "Connection closed", "code": 1006}
# 2024-01-01 12:00:02 | INFO     | [CAT:QUESTION] [SRC:CHATBOT] [USER:user@example.com] [SESSION:Session1] [TAB:Course 1] Question submitted to chatbot | DATA: {"question_number": 1, "question": "What is this course about?"}

