"""
Page monitoring utilities for network requests and errors.
"""
import time
import logging
from datetime import datetime
from config import STRESS_TEST_CONFIG
from shared_state import PAGE_ERRORS


def setup_network_monitoring(page, tab_name, session_id=None, username=None):
    """Setup network monitoring for WebSocket and API calls.
    
    Args:
        page: Page object to monitor
        tab_name: Name of the tab/course for logging
        session_id: Optional session identifier for logging
        username: Optional username for logging
    """
    # Check if network monitoring is enabled
    if not STRESS_TEST_CONFIG.get('enable_network_monitoring', True):
        logging.info(f"[{tab_name}] Network monitoring is disabled in configuration")
        return [], [], {}
    
    # Check if we should monitor all users or just first few
    monitor_all = STRESS_TEST_CONFIG.get('monitor_all_users', True)
    if not monitor_all:
        logging.warning(f"[{tab_name}] Network monitoring limited to first users (monitor_all_users=False)")
        return [], [], {}
    
    websocket_requests = []
    api_requests = []
    websocket_timings = {}
    
    # Create log prefix with session and user info
    if session_id and username:
        log_prefix = f"[{session_id}] [{username}] [{tab_name}]"
    elif session_id:
        log_prefix = f"[{session_id}] [{tab_name}]"
    elif username:
        log_prefix = f"[{username}] [{tab_name}]"
    else:
        log_prefix = f"[{tab_name}]"
    
    def handle_request(request):
        url = request.url
        request_time = time.time()
        
        if 'chatbot_websocket' in url or 'websocket' in url.lower():
            websocket_requests.append({
                'url': url,
                'method': request.method,
                'timestamp': request_time,
                'headers': dict(request.headers)
            })
            websocket_timings[url] = {'request_start': request_time}
            logging.info(f"{log_prefix} [NETWORK] WebSocket Request: {url}")
            logging.debug(f"{log_prefix} [NETWORK]   Headers: {dict(request.headers)}")
        elif 'nucaiapi' in url or 'nucapi' in url:
            api_requests.append({
                'url': url,
                'method': request.method,
                'timestamp': request_time
            })
            logging.info(f"{log_prefix} [NETWORK] API Request: {url} - Method: {request.method}")
    
    def handle_response(response):
        url = response.url
        response_time = time.time()
        status = response.status
        
        # Log HTTP error responses (4xx, 5xx)
        if status >= 400:
            if status >= 500:
                logging.error(f"{log_prefix} [NETWORK] [HTTP ERROR] {status} {url}")
            elif status == 404:
                logging.warning(f"{log_prefix} [NETWORK] [HTTP 404] Not Found: {url}")
            elif status == 403:
                logging.warning(f"{log_prefix} [NETWORK] [HTTP 403] Forbidden: {url}")
            elif status == 401:
                logging.warning(f"{log_prefix} [NETWORK] [HTTP 401] Unauthorized: {url}")
            else:
                logging.warning(f"{log_prefix} [NETWORK] [HTTP {status}] {url}")
        
        try:
            if 'chatbot_websocket' in url or 'websocket' in url.lower():
                if url in websocket_timings:
                    websocket_timings[url]['response_time'] = response_time
                    connection_time = (response_time - websocket_timings[url]['request_start']) * 1000
                    logging.info(f"{log_prefix} [NETWORK] WebSocket Connected: {url}")
                    logging.info(f"{log_prefix} [NETWORK]   Connection Time: {connection_time:.2f}ms")
                    logging.info(f"{log_prefix} [NETWORK]   Status: {response.status}")
            elif 'nucaiapi' in url or 'nucapi' in url:
                timing = response.request.timing
                response_time_ms = timing.get('responseEnd', 0) - timing.get('requestStart', 0)
                logging.info(f"{log_prefix} [NETWORK] API Response: {url}")
                logging.info(f"{log_prefix} [NETWORK]   Status: {response.status}")
                logging.info(f"{log_prefix} [NETWORK]   Response Time: {response_time_ms:.2f}ms")
                if timing.get('responseStart', 0) > 0:
                    ttfb = timing.get('responseStart', 0) - timing.get('requestStart', 0)
                    logging.info(f"{log_prefix} [NETWORK]   Time to First Byte (TTFB): {ttfb:.2f}ms")
        except Exception as e:
            logging.debug(f"{log_prefix} [NETWORK] Error handling response: {e}")
    
    # Set up event listeners
    try:
        page.on('request', handle_request)
        page.on('response', handle_response)
        logging.info(f"{log_prefix} [NETWORK] Network monitoring enabled successfully")
    except Exception as e:
        logging.error(f"{log_prefix} [NETWORK] Failed to setup network monitoring: {e}")
        import traceback
        logging.error(traceback.format_exc())
    
    return websocket_requests, api_requests, websocket_timings


def setup_page_error_logging(page, tab_name, session_id=None, username=None):
    """Setup error and console logging for a page.
    
    Args:
        page: Page object to monitor
        tab_name: Name of the tab/course for logging
        session_id: Optional session identifier for logging
        username: Optional username for logging
    """
    # Create log prefix with session and user info
    if session_id and username:
        log_prefix = f"[{session_id}] [{username}] [{tab_name}]"
    elif session_id:
        log_prefix = f"[{session_id}] [{tab_name}]"
    elif username:
        log_prefix = f"[{username}] [{tab_name}]"
    else:
        log_prefix = f"[{tab_name}]"
    
    def handle_console(msg):
        msg_type = msg.type
        msg_text = msg.text
        
        if msg_type == 'error':
            logging.error(f"{log_prefix} [CONSOLE ERROR] {msg_text}")
            PAGE_ERRORS.append({
                'type': 'CONSOLE_ERROR',
                'message': msg_text,
                'location': f'{tab_name} - Console',
                'tab_name': tab_name,
                'session_id': session_id or '',
                'username': username or '',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            })
        elif msg_type == 'warning':
            logging.warning(f"{log_prefix} [CONSOLE WARNING] {msg_text}")
            PAGE_ERRORS.append({
                'type': 'CONSOLE_WARNING',
                'message': msg_text,
                'location': f'{tab_name} - Console',
                'tab_name': tab_name,
                'session_id': session_id or '',
                'username': username or '',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            })
    
    def handle_page_error(error):
        error_message = str(error)
        logging.error(f"{log_prefix} [PAGE ERROR] {error_message}")
        PAGE_ERRORS.append({
            'type': 'PAGE_ERROR',
            'message': error_message,
            'location': tab_name,
            'tab_name': tab_name,
            'session_id': session_id or '',
            'username': username or '',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        })
    
    def handle_request_failed(request):
        url = request.url
        failure = request.failure
        method = request.method
        error_text = str(failure) if failure else 'Unknown failure'
        logging.error(f"{log_prefix} [REQUEST FAILED] {method} {url}")
        logging.error(f"{log_prefix}   Error: {error_text}")
        if request.post_data:
            logging.debug(f"{log_prefix}   Post Data: {request.post_data[:200]}")  # Limit length
        PAGE_ERRORS.append({
            'type': 'REQUEST_FAILED',
            'message': f"{method} {url} - {error_text}",
            'url': url,
            'method': method,
            'error': error_text,
            'location': tab_name,
            'tab_name': tab_name,
            'session_id': session_id or '',
            'username': username or '',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        })
    
    # Attach all listeners
    try:
        page.on('console', handle_console)
        page.on('pageerror', handle_page_error)
        page.on('requestfailed', handle_request_failed)
        logging.debug(f"{log_prefix} Page error logging setup completed")
    except Exception as e:
        logging.warning(f"{log_prefix} Failed to setup page error logging: {e}")


def setup_iframe_error_logging(iframe, tab_name, session_id=None, username=None):
    """Setup error and console logging for an iframe.
    
    Args:
        iframe: Iframe frame object to monitor
        tab_name: Name of the tab/course for logging
        session_id: Optional session identifier for logging
        username: Optional username for logging
    """
    # Create log prefix with session and user info
    if session_id and username:
        log_prefix = f"[{session_id}] [{username}] [{tab_name}]"
    elif session_id:
        log_prefix = f"[{session_id}] [{tab_name}]"
    elif username:
        log_prefix = f"[{username}] [{tab_name}]"
    else:
        log_prefix = f"[{tab_name}]"
    
    def handle_iframe_console(msg):
        msg_type = msg.type
        msg_text = msg.text
        
        if msg_type == 'error':
            logging.error(f"{log_prefix} [IFRAME CONSOLE ERROR] {msg_text}")
            PAGE_ERRORS.append({
                'type': 'IFRAME_CONSOLE_ERROR',
                'message': msg_text,
                'location': f'{tab_name} - Iframe Console',
                'tab_name': tab_name,
                'session_id': session_id or '',
                'username': username or '',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            })
        elif msg_type == 'warning':
            logging.warning(f"{log_prefix} [IFRAME CONSOLE WARNING] {msg_text}")
            PAGE_ERRORS.append({
                'type': 'IFRAME_CONSOLE_WARNING',
                'message': msg_text,
                'location': f'{tab_name} - Iframe Console',
                'tab_name': tab_name,
                'session_id': session_id or '',
                'username': username or '',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            })
    
    def handle_iframe_page_error(error):
        error_message = str(error)
        error_stack = error.stack if hasattr(error, 'stack') else ''
        logging.error(f"{log_prefix} [IFRAME PAGE ERROR] {error_message}")
        if error_stack:
            logging.debug(f"{log_prefix}   Stack: {error_stack}")
        PAGE_ERRORS.append({
            'type': 'IFRAME_PAGE_ERROR',
            'message': error_message,
            'stack': error_stack if error_stack else '',
            'tab_name': tab_name,
            'session_id': session_id or '',
            'username': username or '',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        })
    
    def handle_iframe_request_failed(request):
        url = request.url
        failure = request.failure
        method = request.method
        error_text = str(failure) if failure else 'Unknown failure'
        logging.error(f"{log_prefix} [REQUEST FAILED] {method} {url}")
        logging.error(f"{log_prefix}   Error: {error_text}")
        if request.post_data:
            logging.debug(f"{log_prefix}   Post Data: {request.post_data[:200]}")  # Limit length
        PAGE_ERRORS.append({
            'type': 'IFRAME_REQUEST_FAILED',
            'message': f"{method} {url} - {error_text}",
            'url': url,
            'method': method,
            'error': error_text,
            'tab_name': tab_name,
            'session_id': session_id or '',
            'username': username or '',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        })
    
    # Attach all listeners to iframe
    try:
        iframe.on('console', handle_iframe_console)
        iframe.on('pageerror', handle_iframe_page_error)
        iframe.on('requestfailed', handle_iframe_request_failed)
        logging.debug(f"{log_prefix} Iframe error logging setup completed")
    except Exception as e:
        logging.warning(f"{log_prefix} Failed to setup iframe error logging: {e}")