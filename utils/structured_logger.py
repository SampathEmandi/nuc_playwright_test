"""
Structured logging utility with categories, sources, user, and session context.
"""
import logging
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from pathlib import Path


class LogCategory(Enum):
    """Log categories for better organization."""
    WEBSOCKET = "websocket"
    LOGIN = "login"
    QUESTION = "question"
    RESPONSE = "response"
    NAVIGATION = "navigation"
    ERROR = "error"
    NETWORK = "network"
    SESSION = "session"
    BROWSER = "browser"
    CONFIG = "config"
    METRICS = "metrics"
    SYSTEM = "system"
    AUTH = "auth"
    COURSE = "course"
    CHATBOT = "chatbot"


class LogSource(Enum):
    """Source of the log entry."""
    MAIN = "main"
    STRESS_TEST = "stress_test"
    SESSION = "session"
    CHATBOT = "chatbot"
    NETWORK_MONITOR = "network_monitor"
    PAGE_MONITOR = "page_monitor"
    COURSE_HANDLER = "course_handler"
    API = "api"
    UTILS = "utils"


class StructuredLogger:
    """Structured logger with context information."""
    
    def __init__(
        self,
        logger_name: str = "playwright_stress_test",
        username: Optional[str] = None,
        session_id: Optional[str] = None,
        tab_name: Optional[str] = None,
        category: Optional[LogCategory] = None,
        source: Optional[LogSource] = None
    ):
        """
        Initialize structured logger with context.
        
        Args:
            logger_name: Name of the logger
            username: Username for context
            session_id: Session ID for context
            tab_name: Tab/window name for context
            category: Log category
            source: Log source
        """
        self.logger = logging.getLogger(logger_name)
        self.username = username
        self.session_id = session_id
        self.tab_name = tab_name
        self.category = category
        self.source = source
    
    def _format_message(
        self,
        message: str,
        category: Optional[LogCategory] = None,
        source: Optional[LogSource] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format message with structured context."""
        # Use instance defaults if not provided
        category = category or self.category
        source = source or self.source
        
        # Build context parts
        context_parts = []
        
        if category:
            context_parts.append(f"[CAT:{category.value.upper()}]")
        
        if source:
            context_parts.append(f"[SRC:{source.value.upper()}]")
        
        if self.username:
            context_parts.append(f"[USER:{self.username}]")
        
        if self.session_id:
            # Extract session number if available
            session_display = self.session_id
            if "_Session" in self.session_id:
                try:
                    parts = self.session_id.split("_Session")
                    if len(parts) > 1:
                        session_num = parts[1].split("_")[0]
                        session_display = f"Session{session_num}"
                except:
                    pass
            context_parts.append(f"[SESSION:{session_display}]")
        
        if self.tab_name:
            context_parts.append(f"[TAB:{self.tab_name}]")
        
        # Build full message
        context_str = " ".join(context_parts) if context_parts else ""
        formatted_message = f"{context_str} {message}" if context_str else message
        
        # Add extra data as JSON if provided
        if extra_data:
            try:
                data_str = json.dumps(extra_data, default=str)
                formatted_message += f" | DATA: {data_str}"
            except:
                formatted_message += f" | DATA: {str(extra_data)}"
        
        return formatted_message
    
    def info(
        self,
        message: str,
        category: Optional[LogCategory] = None,
        source: Optional[LogSource] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ):
        """Log info message with context."""
        formatted = self._format_message(message, category, source, extra_data)
        self.logger.info(formatted)
    
    def error(
        self,
        message: str,
        category: Optional[LogCategory] = None,
        source: Optional[LogSource] = None,
        extra_data: Optional[Dict[str, Any]] = None,
        exc_info: bool = False
    ):
        """Log error message with context."""
        formatted = self._format_message(message, category, source, extra_data)
        self.logger.error(formatted, exc_info=exc_info)
    
    def warning(
        self,
        message: str,
        category: Optional[LogCategory] = None,
        source: Optional[LogSource] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ):
        """Log warning message with context."""
        formatted = self._format_message(message, category, source, extra_data)
        self.logger.warning(formatted)
    
    def debug(
        self,
        message: str,
        category: Optional[LogCategory] = None,
        source: Optional[LogSource] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ):
        """Log debug message with context."""
        formatted = self._format_message(message, category, source, extra_data)
        self.logger.debug(formatted)
    
    def critical(
        self,
        message: str,
        category: Optional[LogCategory] = None,
        source: Optional[LogSource] = None,
        extra_data: Optional[Dict[str, Any]] = None,
        exc_info: bool = False
    ):
        """Log critical message with context."""
        formatted = self._format_message(message, category, source, extra_data)
        self.logger.critical(formatted, exc_info=exc_info)
    
    def with_context(
        self,
        username: Optional[str] = None,
        session_id: Optional[str] = None,
        tab_name: Optional[str] = None,
        category: Optional[LogCategory] = None,
        source: Optional[LogSource] = None
    ) -> 'StructuredLogger':
        """
        Create a new logger instance with updated context.
        
        Returns:
            New StructuredLogger instance with updated context
        """
        return StructuredLogger(
            logger_name=self.logger.name,
            username=username or self.username,
            session_id=session_id or self.session_id,
            tab_name=tab_name or self.tab_name,
            category=category or self.category,
            source=source or self.source
        )


# Global structured logger instance
_global_logger = StructuredLogger()

# Setup structured logging formatter
def setup_structured_logging(log_file: Optional[str] = None):
    """
    Setup structured logging with enhanced formatter.
    
    Args:
        log_file: Optional log file path (auto-generated if None)
    """
    if log_file is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = f"stress_test_{timestamp}.log"
    
    # Create root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Enhanced formatter with structured information
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler
    try:
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        logger.info(f"[CAT:SYSTEM] [SRC:UTILS] Logging initialized | DATA: {{\"log_file\": \"{log_file}\"}}")
    except Exception as e:
        logger.warning(f"[CAT:SYSTEM] [SRC:UTILS] Could not setup file logging: {e}")
    
    return log_file


def get_logger(
    username: Optional[str] = None,
    session_id: Optional[str] = None,
    tab_name: Optional[str] = None,
    category: Optional[LogCategory] = None,
    source: Optional[LogSource] = None
) -> StructuredLogger:
    """
    Get a structured logger with context.
    
    Args:
        username: Username for context
        session_id: Session ID for context
        tab_name: Tab/window name for context
        category: Log category
        source: Log source
    
    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(
        username=username,
        session_id=session_id,
        tab_name=tab_name,
        category=category,
        source=source
    )


# Convenience functions for common logging scenarios
def log_websocket(
    message: str,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
    tab_name: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None,
    level: str = "info"
):
    """Log websocket-related message."""
    logger = get_logger(
        username=username,
        session_id=session_id,
        tab_name=tab_name,
        category=LogCategory.WEBSOCKET,
        source=LogSource.NETWORK_MONITOR
    )
    getattr(logger, level)(message, extra_data=extra_data)


def log_login(
    message: str,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None,
    level: str = "info"
):
    """Log login-related message and write errors to CSV."""
    logger = get_logger(
        username=username,
        session_id=session_id,
        category=LogCategory.LOGIN,
        source=LogSource.SESSION
    )
    getattr(logger, level)(message, extra_data=extra_data)
    
    # Write login errors to CSV
    if level == "error":
        try:
            from reporting.categorized_csv_reporter import log_login_error
            import traceback as tb
            
            log_login_error(
                session_id=session_id or '',
                username=username,
                error_message=message,
                attempt=extra_data.get('attempt') if extra_data else None,
                error_code=extra_data.get('error_code') if extra_data else None,
                traceback_text=''.join(tb.format_exc()) if extra_data and extra_data.get('exc_info') else None,
                extra_data=extra_data
            )
        except ImportError:
            pass
        except Exception:
            pass


def log_question(
    message: str,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
    tab_name: Optional[str] = None,
    question_num: Optional[int] = None,
    extra_data: Optional[Dict[str, Any]] = None,
    level: str = "info"
):
    """Log question-related message."""
    data = extra_data or {}
    if question_num is not None:
        data["question_number"] = question_num
    
    logger = get_logger(
        username=username,
        session_id=session_id,
        tab_name=tab_name,
        category=LogCategory.QUESTION,
        source=LogSource.CHATBOT
    )
    getattr(logger, level)(message, extra_data=data if data else None)


def log_error(
    message: str,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
    tab_name: Optional[str] = None,
    category: Optional[LogCategory] = None,
    source: Optional[LogSource] = None,
    extra_data: Optional[Dict[str, Any]] = None,
    exc_info: bool = False
):
    """Log error message with full context and write to appropriate CSV."""
    logger = get_logger(
        username=username,
        session_id=session_id,
        tab_name=tab_name,
        category=category or LogCategory.ERROR,
        source=source
    )
    logger.error(message, extra_data=extra_data, exc_info=exc_info)
    
    # Write to categorized CSV based on category
    try:
        from reporting.categorized_csv_reporter import (
            log_session_error,
            log_login_error,
            log_chat_response_error
        )
        import traceback as tb
        
        error_category = category or LogCategory.ERROR
        traceback_text = None
        if exc_info:
            traceback_text = ''.join(tb.format_exc())
        
        if error_category == LogCategory.LOGIN:
            log_login_error(
                session_id=session_id or '',
                username=username,
                error_message=message,
                attempt=extra_data.get('attempt') if extra_data else None,
                error_code=extra_data.get('error_code') if extra_data else None,
                traceback_text=traceback_text,
                extra_data=extra_data
            )
        elif error_category in [LogCategory.QUESTION, LogCategory.RESPONSE, LogCategory.CHATBOT]:
            log_chat_response_error(
                session_id=session_id or '',
                username=username,
                tab_name=tab_name,
                question_num=extra_data.get('question_number') if extra_data else None,
                error_message=message,
                error_type=error_category.value,
                question_text=extra_data.get('question') if extra_data else None,
                response_wait_time_ms=extra_data.get('response_wait_time_ms') if extra_data else None,
                traceback_text=traceback_text,
                extra_data=extra_data
            )
        else:
            # Session errors for other categories
            log_session_error(
                session_id=session_id or '',
                username=username,
                error_message=message,
                error_type=error_category.value,
                stage=extra_data.get('stage') if extra_data else '',
                traceback_text=traceback_text,
                extra_data=extra_data
            )
    except ImportError:
        # Categorized CSV reporter not available, skip
        pass
    except Exception as e:
        # Don't break logging if CSV write fails
        logger.debug(f"Failed to write error to categorized CSV: {e}")


def log_response(
    message: str,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
    tab_name: Optional[str] = None,
    question_num: Optional[int] = None,
    extra_data: Optional[Dict[str, Any]] = None,
    level: str = "info"
):
    """Log response-related message."""
    data = extra_data or {}
    if question_num is not None:
        data["question_number"] = question_num
    
    logger = get_logger(
        username=username,
        session_id=session_id,
        tab_name=tab_name,
        category=LogCategory.RESPONSE,
        source=LogSource.CHATBOT
    )
    getattr(logger, level)(message, extra_data=data if data else None)

