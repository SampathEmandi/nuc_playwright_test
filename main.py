# Standard library imports
import asyncio
import csv
import json
import logging
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

# Third-party imports
from playwright.async_api import async_playwright

# Local imports
from browser.page_monitoring import setup_network_monitoring
from config import (
    STRESS_TEST_CONFIG,
    USERS,
    QUESTION_CONFIG,
    QUESTION_POOL,
    course_1_questions,
    course_2_questions,
    general_questions
)
from utils.config_optimizer import update_stress_test_config

# Debug logging path is determined dynamically relative to the script's location, inside a '.cursor' folder
DEBUG_LOG_PATH = str(Path(__file__).parent / ".cursor" / "debug.log")

def debug_log(hypothesis_id, location, message, data=None, session_id=None, run_id="initial"):
    """Write debug log entry in NDJSON format."""
    try:
        # Ensure the directory exists
        log_dir = os.path.dirname(DEBUG_LOG_PATH)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        log_entry = {
            "id": f"log_{int(time.time() * 1000)}_{random.randint(1000, 9999)}",
            "timestamp": int(time.time() * 1000),
            "location": location,
            "message": message,
            "data": data or {},
            "sessionId": session_id or "unknown",
            "runId": run_id,
            "hypothesisId": hypothesis_id
        }
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        # Silently fail to avoid breaking main flow, but log to standard logging in debug mode
        logging.debug(f"Debug log write failed: {e}")

# Configure logging - both console and file
LOG_FILENAME = None  # Will be set on first log

def setup_logging():
    """Setup logging to both console and file."""
    global LOG_FILENAME
    
    # Generate log filename with timestamp
    if LOG_FILENAME is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        LOG_FILENAME = f"stress_test_{timestamp}.log"
    
    # Create root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create formatters
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler
    try:
        file_handler = logging.FileHandler(LOG_FILENAME, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logging.info(f"📝 Logging to file: {LOG_FILENAME}")
    except Exception as e:
        logging.warning(f"Could not setup file logging: {e}")
    
    return LOG_FILENAME

# Setup logging at startup
LOG_FILENAME = setup_logging()

# Import structured logger after setup
from utils.structured_logger import (
    get_logger,
    log_websocket,
    log_login,
    log_question,
    log_response,
    log_error,
    LogCategory,
    LogSource,
    setup_structured_logging
)

# Setup structured logging
LOG_FILENAME = setup_structured_logging(LOG_FILENAME)

# Global list to store CSV metrics
CSV_METRICS = []

# Global list to store page errors and warnings for CSV
PAGE_ERRORS = []

# Global list to store session-level logs and errors for CSV
SESSION_LOGS = []

# Track last CSV export time for incremental exports
LAST_CSV_EXPORT_TIME = None
CSV_EXPORT_FILENAME = None
SESSION_CSV_EXPORT_FILENAME = None
ERRORS_CSV_EXPORT_FILENAME = None

# Thread pool executor for CPU-bound or blocking operations
THREAD_POOL = ThreadPoolExecutor(max_workers=20, thread_name_prefix="playwright_worker")

# Lock for thread-safe operations
CSV_LOCK = threading.Lock()

# ============================================================================
# Helper Functions
# ============================================================================

async def get_iframe_content_frame(page, tab_name, max_attempts=5):
    """Helper function to get iframe content frame with retry logic and refresh on error."""
    iframe_locator = page.locator('iframe._chatbot_iframe_')
    
    for attempt in range(max_attempts):
        try:
            # Wait for iframe to be attached
            await iframe_locator.wait_for(state='attached', timeout=30000)
            
            # Get iframe element and content frame
            iframe_element = await iframe_locator.element_handle()
            iframe = await iframe_element.content_frame()
            
            if iframe is not None:
                return iframe
            else:
                raise Exception("Iframe content frame is None")
                
        except Exception as e:
            logging.warning(f"[{tab_name}] Attempt {attempt + 1} to get iframe failed: {e}")
            
            if attempt < max_attempts - 1:
                # Refresh the page and retry
                logging.info(f"[{tab_name}] Refreshing page and retrying iframe access...")
                try:
                    await page.reload(wait_until='domcontentloaded', timeout=30000)
                    await asyncio.sleep(2)  # Wait for page to stabilize
                except Exception as refresh_error:
                    logging.warning(f"[{tab_name}] Page refresh failed: {refresh_error}")
                    await asyncio.sleep(2)  # Wait anyway before retry
            else:
                raise Exception(f"Could not get content frame from iframe after {max_attempts} attempts: {e}")
    
    raise Exception(f"Could not get content frame from iframe after {max_attempts} attempts")

def select_questions_for_course(course_questions, general_questions, num_questions):
    """Helper function to select questions for a course, mixing with general questions if needed."""
    pool = course_questions.copy() if course_questions else []
    if len(pool) < num_questions:
        pool.extend(general_questions)
    num_to_select = min(num_questions, len(pool))
    selected = random.sample(pool, num_to_select)
    random.shuffle(selected)
    return selected

async def run_concurrent_with_timeout(coroutines, timeout=None, return_exceptions=True):
    """Run multiple coroutines concurrently with optional timeout.
    
    This ensures all operations run in parallel without blocking each other.
    Uses asyncio.create_task to ensure true parallelism.
    
    Args:
        coroutines: List of coroutines to run
        timeout: Optional timeout in seconds
        return_exceptions: If True, exceptions are returned as results
    
    Returns:
        List of results
    """
    # Create tasks immediately to ensure they start running in parallel
    tasks = [asyncio.create_task(coro) for coro in coroutines]
    
    if timeout:
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=return_exceptions),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            # Cancel all tasks on timeout
            for task in tasks:
                if not task.done():
                    task.cancel()
            raise
    else:
        results = await asyncio.gather(*tasks, return_exceptions=return_exceptions)
    
    return results

async def handle_csrf_token_error(page, tab_name, session_id=None, username=None, iframe=None, max_refresh_attempts=3):
    """Check for CSRF token errors and refresh the page if detected.
    
    Args:
        page: Page object
        tab_name: Name of the tab/course
        session_id: Session identifier for logging
        username: Username for logging
        iframe: Optional iframe to check for CSRF errors
        max_refresh_attempts: Maximum number of refresh attempts
    
    Returns:
        bool: True if CSRF error was detected and page was refreshed, False otherwise
    """
    try:
        log_prefix = f"[{session_id}] [{username}] [{tab_name}]" if session_id and username else f"[{tab_name}]"
        csrf_detected = False
        
        # Check for CSRF token error in page content
        try:
            page_content = await page.content()
            if "Invalid custom CSRF token" in page_content or ("CSRF token" in page_content and "Invalid" in page_content):
                csrf_detected = True
                logging.warning(f"{log_prefix} CSRF token error detected in page content")
        except:
            pass
        
        # Check for CSRF token error in iframe content if provided
        if iframe and not csrf_detected:
            try:
                iframe_content = await iframe.content()
                if "Invalid custom CSRF token" in iframe_content or ("CSRF token" in iframe_content and "Invalid" in iframe_content):
                    csrf_detected = True
                    logging.warning(f"{log_prefix} CSRF token error detected in iframe content")
            except:
                pass
        
        if csrf_detected:
            logging.warning(f"{log_prefix} CSRF token error detected, refreshing page...")
            
            try:
                await page.reload(wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(2)  # Wait for page to stabilize
                logging.info(f"{log_prefix} Page refreshed successfully after CSRF token error")
                return True
            except Exception as refresh_error:
                logging.error(f"{log_prefix} Failed to refresh page after CSRF error: {refresh_error}")
                return False
    except Exception as e:
        # Silently fail - this is a check, not critical
        pass
    return False

def distribute_questions_by_course(user_questions, course_1_questions, course_2_questions, general_questions):
    """Distribute user questions between Course 1 and Course 2 based on question type.
    
    Distribution rules:
    - Course 1 questions → Course 1 only
    - Course 2 questions → Course 2 only
    - General questions → BOTH courses (added to both lists)
    
    Returns:
        dict: {
            'course_1': [list of questions for Course 1],
            'course_2': [list of questions for Course 2]
        }
    """
    course_1_list = []
    course_2_list = []
    
    # Convert to sets for faster lookup
    course_1_set = set(course_1_questions)
    course_2_set = set(course_2_questions)
    general_set = set(general_questions)
    
    for question in user_questions:
        if question in course_1_set:
            # Course 1 questions go to Course 1 only
            course_1_list.append(question)
        elif question in course_2_set:
            # Course 2 questions go to Course 2 only
            course_2_list.append(question)
        elif question in general_set:
            # General questions go to BOTH courses
            course_1_list.append(question)
            course_2_list.append(question)
        else:
            # Unknown question type - add to both courses as fallback
            logging.warning(f"Unknown question type, adding to both courses: {question[:50]}...")
            course_1_list.append(question)
            course_2_list.append(question)
    
    # Ensure both courses have at least some questions if user has questions
    if user_questions and not course_1_list and not course_2_list:
        # If no course-specific questions found, split evenly
        mid = len(user_questions) // 2
        course_1_list = user_questions[:mid] if mid > 0 else user_questions[:1]
        course_2_list = user_questions[mid:] if mid > 0 else []
    
    return {
        'course_1': course_1_list,
        'course_2': course_2_list
    }

async def open_course(context, course_number, tab_name, session_id=None, username=None):
    """Open a course in a new tab by navigating to dashboard and clicking.
    
    Args:
        context: Browser context
        course_number: Course number (1 or 2)
        tab_name: Name of the tab/course
        session_id: Session identifier for logging
        username: Username for logging
    """
    try:
        # Check if context is still valid (with retry)
        browser_connected = False
        for attempt in range(3):
            try:
                if context.browser and context.browser.is_connected():
                    browser_connected = True
                    break
            except Exception:
                pass
            if attempt < 2:
                await asyncio.sleep(0.3)
        
        if not browser_connected:
            raise Exception(f"Browser disconnected before opening course {course_number} (after retries)")
        
        logging.info(f"Opening course {course_number} in {tab_name}...")
        page = await context.new_page()
        
        # Setup error and console logging for course page
        setup_page_error_logging(page, tab_name, session_id=session_id, username=username)
        
        # Setup network monitoring EARLY - before any navigation/network activity
        # This ensures ALL users get monitoring, not just the first 1-2
        monitoring_setup_start = time.time()
        websocket_requests, api_requests, websocket_timings = setup_network_monitoring(
            page, tab_name, session_id=session_id, username=username
        )
        monitoring_setup_time = (time.time() - monitoring_setup_start) * 1000
        
        debug_log("H5", f"open_course:{307}", "Network monitoring setup completed", {
            "session_id": session_id,
            "username": username,
            "tab_name": tab_name,
            "course_number": course_number,
            "setup_time_ms": monitoring_setup_time,
            "monitoring_enabled": STRESS_TEST_CONFIG.get('enable_network_monitoring', True),
            "monitor_all_users": STRESS_TEST_CONFIG.get('monitor_all_users', True)
        }, session_id=session_id)
        
        # Verify monitoring is active
        if STRESS_TEST_CONFIG.get('enable_network_monitoring', True) and STRESS_TEST_CONFIG.get('monitor_all_users', True):
            logging.info(f"[{tab_name}] ✓ Network monitoring active for course page (user: {username or 'unknown'})")
        
        # Check again before navigation (with retry)
        browser_connected = False
        for attempt in range(3):
            try:
                if context.browser and context.browser.is_connected():
                    browser_connected = True
                    break
            except Exception:
                pass
            if attempt < 2:
                await asyncio.sleep(0.3)
        
        if not browser_connected:
            await page.close()
            raise Exception(f"Browser disconnected before navigation to course {course_number} (after retries)")
        
        # Navigate to dashboard
        logging.info(f"[{tab_name}] Navigating to dashboard...")
        try:
            await page.goto('https://development.instructure.com', wait_until='domcontentloaded', timeout=60000)
            logging.info(f"[{tab_name}] Dashboard navigation completed")
        except Exception as nav_error:
            error_str = str(nav_error)
            if "Target page, context or browser has been closed" in error_str or "context or browser has been closed" in error_str:
                logging.error(f"[{tab_name}] Page/context closed during navigation: {nav_error}")
                raise Exception(f"Page/context closed during navigation: {nav_error}")
            raise
        
        # Check for CSRF token error and refresh if needed
        csrf_refreshed = await handle_csrf_token_error(page, tab_name, session_id=session_id, username=username, iframe=None)
        if csrf_refreshed:
            # Wait for page to stabilize after refresh
            await page.wait_for_load_state('domcontentloaded', timeout=30000)
            await asyncio.sleep(1)
            logging.info(f"[{tab_name}] Page refreshed due to CSRF token error")
        
        # Wait for dashboard container to be attached
        logging.info(f"[{tab_name}] Waiting for dashboard container...")
        try:
            await page.locator('#DashboardCard_Container').wait_for(state='attached', timeout=30000)
            logging.info(f"[{tab_name}] Dashboard container found")
        except Exception as container_error:
            logging.error(f"[{tab_name}] Dashboard container not found: {container_error}")
            # Try to check current URL
            try:
                current_url = page.url
                logging.info(f"[{tab_name}] Current URL: {current_url}")
            except:
                pass
            raise
        
        # Try multiple selector strategies
        course_1_selectors = [
            '#DashboardCard_Container > div > div > div:nth-child(1) > div > a',
            '#DashboardCard_Container > div > div > div:nth-child(1) > div > a > div',
            '#DashboardCard_Container div:nth-child(1) > div > a',
            'a[href*="/courses/"]:nth-of-type(1)'
        ]
        course_2_selectors = [
            '#DashboardCard_Container > div > div > div:nth-child(2) > div > a',
            '#DashboardCard_Container > div > div > div:nth-child(2) > div > a > div',
            '#DashboardCard_Container div:nth-child(2) > div > a',
            'a[href*="/courses/"]:nth-of-type(2)'
        ]
        
        # Try to wait for cards with retry logic
        cards_visible = False
        course_1_card = None
        course_2_card = None
        
        for attempt in range(5):  # Increased attempts
            try:
                # Try different selectors
                for selector_idx, (sel1, sel2) in enumerate(zip(course_1_selectors, course_2_selectors)):
                    try:
                        course_1_card = page.locator(sel1)
                        course_2_card = page.locator(sel2)
                        
                        # Wait for both cards with shorter timeout per attempt
                        await course_1_card.wait_for(state='visible', timeout=15000)
                        await course_2_card.wait_for(state='visible', timeout=15000)
                        cards_visible = True
                        logging.info(f"[{tab_name}] Both course cards visible on attempt {attempt + 1} with selector {selector_idx + 1}")
                        break
                    except Exception as selector_error:
                        if selector_idx < len(course_1_selectors) - 1:
                            logging.debug(f"[{tab_name}] Selector {selector_idx + 1} failed, trying next: {selector_error}")
                            continue
                        else:
                            raise selector_error
                
                if cards_visible:
                    break
                    
            except Exception as e:
                logging.warning(f"[{tab_name}] Course cards not visible on attempt {attempt + 1}: {e}")
                
                # Check if page is still valid
                page_valid = True
                try:
                    page_valid = not page.is_closed()
                except Exception:
                    page_valid = False
                
                if not page_valid:
                    error_msg = "Page is closed - cannot proceed"
                    logging.error(f"[{tab_name}] {error_msg}")
                    raise Exception(error_msg)
                
                if attempt < 4:  # Don't reload on last attempt
                    # Refresh page and retry
                    logging.info(f"[{tab_name}] Refreshing page and retrying (attempt {attempt + 1}/5)...")
                    try:
                        await page.reload(wait_until='domcontentloaded', timeout=30000)
                        await asyncio.sleep(2)
                        # Re-wait for dashboard container
                        await page.locator('#DashboardCard_Container').wait_for(state='attached', timeout=30000)
                    except Exception as reload_error:
                        error_str = str(reload_error)
                        if "Target page, context or browser has been closed" in error_str or "context or browser has been closed" in error_str:
                            logging.error(f"[{tab_name}] Page/context closed during reload: {reload_error}")
                            raise Exception(f"Page/context closed during reload: {reload_error}")
                        raise
                else:
                    # Last attempt - try to proceed with target course only
                    logging.warning(f"[{tab_name}] Could not wait for both cards after 5 attempts, trying target course only...")
                    try:
                        # Try all selectors for target course
                        target_selectors = course_1_selectors if course_number == 1 else course_2_selectors
                        for selector in target_selectors:
                            try:
                                target_card = page.locator(selector)
                                await target_card.wait_for(state='visible', timeout=10000)
                                cards_visible = True
                                logging.info(f"[{tab_name}] Target course card found with fallback selector")
                                break
                            except:
                                continue
                    except Exception as fallback_error:
                        logging.warning(f"[{tab_name}] Fallback also failed: {fallback_error}")
                        # Will try to click anyway
                    await asyncio.sleep(2)
        # Check if page is still valid before clicking
        page_valid = True
        try:
            page_valid = not page.is_closed()
        except Exception:
            # If checking is_closed() throws an error, assume page is invalid
            page_valid = False
        
        if not page_valid:
            error_msg = "Page is closed - cannot click course link"
            logging.error(f"[{tab_name}] {error_msg}")
            raise Exception(error_msg)
        
        # Wait a bit for page to fully load
        await asyncio.sleep(1)
        
        # Try multiple selectors for clicking the course link
        course_link_selectors = [
            f'#DashboardCard_Container > div > div > div:nth-child({course_number}) > div > a',
            f'#DashboardCard_Container > div > div > div:nth-child({course_number}) > div > a > div',
            f'#DashboardCard_Container div:nth-child({course_number}) > div > a',
            f'a[href*="/courses/"]:nth-of-type({course_number})',
            f'#DashboardCard_Container a[href*="/courses/"]:nth-child({course_number})',
            f'#DashboardCard_Container a[href*="/courses/"]',  # Fallback: any course link
        ]
        
        clicked = False
        last_error = None
        for selector in course_link_selectors:
            try:
                course_locator = page.locator(selector)
                # Count how many elements match
                count = await course_locator.count()
                logging.info(f"[{tab_name}] Selector '{selector[:60]}...' found {count} element(s)")
                
                if count == 0:
                    logging.debug(f"[{tab_name}] Selector found no elements, trying next...")
                    continue
                
                # If multiple links found and we want a specific course, try to get the right one
                if count > 1 and course_number <= count:
                    course_locator = course_locator.nth(course_number - 1)
                
                # Wait for it to be visible and enabled
                await course_locator.wait_for(state='visible', timeout=15000)
                logging.info(f"[{tab_name}] Course link is visible, clicking...")
                await course_locator.click(timeout=30000)
                # Wait for navigation after click
                await page.wait_for_load_state('domcontentloaded', timeout=30000)
                logging.info(f"✓ Course {course_number} opened in {tab_name} using selector: {selector[:50]}...")
                clicked = True
                break
            except Exception as click_error:
                error_str = str(click_error)
                if "Target page, context or browser has been closed" in error_str or "context or browser has been closed" in error_str:
                    logging.error(f"✗ Page/context closed during course click: {click_error}")
                    raise Exception(f"Page/context closed during course click: {click_error}")
                last_error = click_error
                # Try next selector
                logging.warning(f"[{tab_name}] Selector failed: {selector[:50]}... - {click_error}")
                continue
        
        if not clicked:
            # Last resort: try to find any course link and click it
            logging.warning(f"[{tab_name}] All specific selectors failed, trying to find any course link...")
            try:
                all_course_links = page.locator('#DashboardCard_Container a[href*="/courses/"]')
                count = await all_course_links.count()
                if count > 0:
                    target_link = all_course_links.nth(course_number - 1) if course_number <= count else all_course_links.first
                    await target_link.wait_for(state='visible', timeout=10000)
                    await target_link.click(timeout=30000)
                    await page.wait_for_load_state('domcontentloaded', timeout=30000)
                    logging.info(f"✓ Course {course_number} opened in {tab_name} using fallback selector")
                    clicked = True
            except Exception as fallback_error:
                logging.error(f"[{tab_name}] Fallback also failed: {fallback_error}")
        
        if not clicked:
            raise Exception(f"Failed to click course {course_number} link with all selectors. Last error: {last_error}")
        
        return page
    except Exception as e:
        logging.error(f"✗ Error opening course {course_number} in {tab_name}: {e}")
        raise

def setup_page_error_logging(page, tab_name, session_id=None, username=None):
    """Setup logging for console messages, page errors, and failed requests.
    
    Args:
        page: Page object
        tab_name: Name of the tab/course
        session_id: Session identifier for logging
        username: Username for logging
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
        """Handle console messages from the page."""
        msg_type = msg.type
        msg_text = msg.text
        location = f"{msg.location.get('url', 'unknown')}:{msg.location.get('lineNumber', '?')}:{msg.location.get('columnNumber', '?')}"
        
        if msg_type == 'error':
            logging.error(f"{log_prefix} [CONSOLE ERROR] {msg_text}")
            logging.error(f"{log_prefix}   Location: {location}")
            if msg.args:
                try:
                    args_text = ' '.join([str(arg) for arg in msg.args])
                    logging.error(f"{log_prefix}   Args: {args_text}")
                except:
                    pass
            
            # Check for CSRF token error - log it (refresh will be handled before critical operations)
            if "Invalid custom CSRF token" in msg_text or "CSRF token" in msg_text:
                logging.warning(f"{log_prefix} CSRF token error detected in console - will refresh on next operation")
            
            # Store in PAGE_ERRORS for CSV
            PAGE_ERRORS.append({
                'type': 'CONSOLE_ERROR',
                'message': msg_text,
                'location': location,
                'tab_name': tab_name,
                'session_id': session_id or '',
                'username': username or '',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            })
        elif msg_type == 'warning':
            logging.warning(f"{log_prefix} [CONSOLE WARNING] {msg_text}")
            logging.warning(f"{log_prefix}   Location: {location}")
            # Store in PAGE_ERRORS for CSV
            PAGE_ERRORS.append({
                'type': 'CONSOLE_WARNING',
                'message': msg_text,
                'location': location,
                'tab_name': tab_name,
                'session_id': session_id or '',
                'username': username or '',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            })
        elif msg_type == 'log':
            logging.info(f"{log_prefix} [CONSOLE LOG] {msg_text}")
        else:
            logging.info(f"{log_prefix} [CONSOLE {msg_type.upper()}] {msg_text}")
            logging.info(f"{log_prefix}   Location: {location}")
    
    def handle_page_error(error):
        """Handle JavaScript errors on the page."""
        error_message = str(error)
        error_stack = getattr(error, 'stack', None)
        logging.error(f"{log_prefix} [PAGE ERROR] {error_message}")
        if error_stack:
            logging.error(f"{log_prefix}   Stack: {error_stack}")
        
        # Check for CSRF token error and refresh page
        if "Invalid custom CSRF token" in error_message or "CSRF token" in error_message:
            logging.warning(f"{log_prefix} CSRF token error detected in page error, refreshing page...")
            try:
                asyncio.create_task(page.reload(wait_until='domcontentloaded', timeout=30000))
                asyncio.create_task(asyncio.sleep(2))  # Wait for page to stabilize
            except Exception as refresh_error:
                logging.error(f"{log_prefix} Failed to refresh page after CSRF error: {refresh_error}")
        
        # Store in PAGE_ERRORS for CSV
        PAGE_ERRORS.append({
            'type': 'PAGE_ERROR',
            'message': error_message,
            'stack': error_stack if error_stack else '',
            'tab_name': tab_name,
            'session_id': session_id or '',
            'username': username or '',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        })
    
    def handle_request_failed(request):
        """Handle failed network requests."""
        url = request.url
        failure = request.failure
        method = request.method
        error_text = str(failure) if failure else 'Unknown failure'
        logging.error(f"{log_prefix} [REQUEST FAILED] {method} {url}")
        logging.error(f"{log_prefix}   Error: {error_text}")
        if request.post_data:
            logging.debug(f"{log_prefix}   Post Data: {request.post_data[:200]}")  # Limit length
        # Store in PAGE_ERRORS for CSV
        PAGE_ERRORS.append({
            'type': 'REQUEST_FAILED',
            'message': f"{method} {url} - {error_text}",
            'url': url,
            'method': method,
            'error': error_text,
            'tab_name': tab_name,
            'session_id': session_id or '',
            'username': username or '',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        })
    
    # Attach all listeners
    page.on('console', handle_console)
    page.on('pageerror', handle_page_error)
    page.on('requestfailed', handle_request_failed)

def setup_iframe_error_logging(iframe, tab_name, session_id=None, username=None):
    """Setup logging for console messages, errors, and warnings from iframe content.
    
    Args:
        iframe: Frame object (content frame of the iframe)
        tab_name: Name of the tab/course
        session_id: Session identifier for logging
        username: Username for logging
    """
    if iframe is None:
        return
    
    # Create log prefix with session and user info
    if session_id and username:
        log_prefix = f"[{session_id}] [{username}] [{tab_name}] [IFRAME]"
    elif session_id:
        log_prefix = f"[{session_id}] [{tab_name}] [IFRAME]"
    elif username:
        log_prefix = f"[{username}] [{tab_name}] [IFRAME]"
    else:
        log_prefix = f"[{tab_name}] [IFRAME]"
    
    def handle_iframe_console(msg):
        """Handle console messages from the iframe."""
        msg_type = msg.type
        msg_text = msg.text
        location = f"{msg.location.get('url', 'unknown')}:{msg.location.get('lineNumber', '?')}:{msg.location.get('columnNumber', '?')}"
        
        if msg_type == 'error':
            logging.error(f"{log_prefix} [CONSOLE ERROR] {msg_text}")
            logging.error(f"{log_prefix}   Location: {location}")
            if msg.args:
                try:
                    args_text = ' '.join([str(arg) for arg in msg.args])
                    logging.error(f"{log_prefix}   Args: {args_text}")
                except:
                    pass
            # Store in PAGE_ERRORS for CSV
            PAGE_ERRORS.append({
                'type': 'IFRAME_CONSOLE_ERROR',
                'message': msg_text,
                'location': location,
                'tab_name': tab_name,
                'session_id': session_id or '',
                'username': username or '',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            })
        elif msg_type == 'warning':
            logging.warning(f"{log_prefix} [CONSOLE WARNING] {msg_text}")
            logging.warning(f"{log_prefix}   Location: {location}")
            # Store in PAGE_ERRORS for CSV
            PAGE_ERRORS.append({
                'type': 'IFRAME_CONSOLE_WARNING',
                'message': msg_text,
                'location': location,
                'tab_name': tab_name,
                'session_id': session_id or '',
                'username': username or '',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            })
        elif msg_type == 'log':
            logging.info(f"{log_prefix} [CONSOLE LOG] {msg_text}")
        else:
            logging.info(f"{log_prefix} [CONSOLE {msg_type.upper()}] {msg_text}")
            logging.info(f"{log_prefix}   Location: {location}")
    
    def handle_iframe_page_error(error):
        """Handle JavaScript errors in the iframe."""
        error_message = str(error)
        error_stack = getattr(error, 'stack', None)
        logging.error(f"{log_prefix} [PAGE ERROR] {error_message}")
        if error_stack:
            logging.error(f"{log_prefix}   Stack: {error_stack}")
        # Store in PAGE_ERRORS for CSV
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
        """Handle failed network requests from the iframe."""
        url = request.url
        failure = request.failure
        method = request.method
        error_text = str(failure) if failure else 'Unknown failure'
        logging.error(f"{log_prefix} [REQUEST FAILED] {method} {url}")
        logging.error(f"{log_prefix}   Error: {error_text}")
        if request.post_data:
            logging.debug(f"{log_prefix}   Post Data: {request.post_data[:200]}")  # Limit length
        # Store in PAGE_ERRORS for CSV
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

async def ask_single_question(page, iframe, tab_name, question, question_num, session_id=None, course_number=None, username=None, question_metrics=None):
    """Ask a single question to the chatbot concurrently.
    
    Returns a metric dictionary for the question.
    """
    question_start = time.time()
    try:
        logging.info(f"[{tab_name}] ========== Question {question_num} (Concurrent) ==========")
        
        # Check for CSRF token error and refresh if needed before getting iframe
        csrf_refreshed = await handle_csrf_token_error(page, tab_name, session_id=session_id, username=username, iframe=None)
        if csrf_refreshed:
            # Wait for page to stabilize after refresh
            await page.wait_for_load_state('domcontentloaded', timeout=30000)
            await asyncio.sleep(1)
        
        # Re-acquire iframe for each question in case it changed
        try:
            iframe = await get_iframe_content_frame(page, tab_name)
            # Re-setup iframe error logging in case iframe reloaded
            setup_iframe_error_logging(iframe, tab_name, session_id=session_id, username=username)
        except Exception as e:
            logging.warning(f"[{tab_name}] Could not get iframe for question {question_num}, refreshing and retrying...")
            try:
                # Refresh page and retry
                await page.reload(wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(2)
                iframe = await get_iframe_content_frame(page, tab_name)
                logging.info(f"[{tab_name}] Successfully got iframe after refresh")
            except Exception as retry_error:
                logging.error(f"[{tab_name}] Failed to get iframe even after refresh: {retry_error}")
                return {
                    'question_number': question_num,
                    'question': question,
                    'question_submit_time': 0,
                    'response_wait_time': 0,
                    'question_total_time': 0,
                    'response_received': False,
                    'error': f'Could not get iframe after refresh: {str(retry_error)}'
                }
        
        # Wait for question box to be ready with robust retry logic and refresh on error
        question_box = None
        for attempt in range(10):  # More attempts for better reliability
            try:
                # Re-acquire iframe first (it might have reloaded)
                iframe = await get_iframe_content_frame(page, tab_name)
                # Re-setup iframe error logging in case iframe reloaded
                setup_iframe_error_logging(iframe, tab_name, session_id=session_id, username=username)
                
                # Try to find question box with multiple strategies
                question_box = iframe.get_by_role('textbox', name='Enter your question here')
                
                # Wait for it to be visible and enabled
                await question_box.wait_for(state='visible', timeout=15000)
                
                # Verify it's actually usable
                is_visible = await question_box.is_visible()
                is_enabled = await question_box.is_enabled()
                
                if is_visible and is_enabled:
                    logging.info(f"[{tab_name}] Question {question_num} - Question box found and ready on attempt {attempt + 1}")
                    break
                else:
                    raise Exception(f"Question box not usable: visible={is_visible}, enabled={is_enabled}")
                    
            except Exception as e:
                logging.debug(f"[{tab_name}] Attempt {attempt + 1} to find question box for question {question_num} failed: {e}")
                if attempt < 9:
                    # Progressive backoff: wait longer with each attempt
                    wait_time = 0.5 + (attempt * 0.3)  # Shorter wait for concurrent mode
                    await asyncio.sleep(wait_time)
                else:
                    logging.warning(f"[{tab_name}] Could not find question box for question {question_num} after {attempt + 1} attempts")
                    question_box = None
        
        if question_box is None:
            logging.warning(f"[{tab_name}] Skipping question {question_num} - question box not available")
            return {
                'question_number': question_num,
                'question': question,
                'question_submit_time': 0,
                'response_wait_time': 0,
                'question_total_time': (time.time() - question_start) * 1000,
                'response_received': False,
                'error': 'Question box not available'
            }
        
        # Clear previous question if any - with retry
        question_box_click_success = False
        question_click_max_retries = 3
        question_click_retry_delay = 0.5
        
        for question_click_attempt in range(1, question_click_max_retries + 1):
            try:
                # Ensure question box is still visible and enabled before clicking
                is_visible = await question_box.is_visible()
                is_enabled = await question_box.is_enabled()
                
                if not is_visible or not is_enabled:
                    if question_click_attempt < question_click_max_retries:
                        logging.debug(f"[{tab_name}] Question box not ready (visible={is_visible}, enabled={is_enabled}), retrying...")
                        await asyncio.sleep(question_click_retry_delay)
                        # Re-acquire question box
                        question_box = iframe.get_by_role('textbox', name='Enter your question here')
                        await question_box.wait_for(state='visible', timeout=5000)
                        continue
                    else:
                        raise Exception(f"Question box not usable: visible={is_visible}, enabled={is_enabled}")
                
                # #region agent log
                debug_log("QUESTION_CLICK", f"ask_single_question:{874}", "Question box click attempt", {
                    "session_id": session_id,
                    "username": username,
                    "tab_name": tab_name,
                    "question_num": question_num,
                    "attempt": question_click_attempt
                }, session_id=session_id)
                # #endregion
                
                await question_box.click()
                await question_box.fill('')  # Clear field
                question_box_click_success = True
                
                # #region agent log
                debug_log("QUESTION_CLICK", f"ask_single_question:{888}", "Question box click successful", {
                    "session_id": session_id,
                    "username": username,
                    "tab_name": tab_name,
                    "question_num": question_num,
                    "attempt": question_click_attempt
                }, session_id=session_id)
                # #endregion
                
                break
            except Exception as e:
                logging.debug(f"[{tab_name}] Question box click attempt {question_click_attempt} failed: {e}")
                
                # #region agent log
                debug_log("QUESTION_CLICK", f"ask_single_question:{902}", "Question box click failed", {
                    "session_id": session_id,
                    "username": username,
                    "tab_name": tab_name,
                    "question_num": question_num,
                    "attempt": question_click_attempt,
                    "error": str(e)
                }, session_id=session_id)
                # #endregion
                
                if question_click_attempt < question_click_max_retries:
                    await asyncio.sleep(question_click_retry_delay)
                    # Re-acquire question box
                    try:
                        question_box = iframe.get_by_role('textbox', name='Enter your question here')
                        await question_box.wait_for(state='visible', timeout=5000)
                    except:
                        pass
                    continue
                else:
                    logging.warning(f"[{tab_name}] Could not clear question box after {question_click_max_retries} attempts: {e}")
                    # Continue anyway - might still work
        
        # Time the question submission
        question_submit_start = time.time()
        await question_box.fill(question)
        await question_box.press('Enter')  # Submit question
        question_submit_time = (time.time() - question_submit_start) * 1000
        logging.info(f"[{tab_name}] Question {question_num} - Question: {question}")
        logging.info(f"[{tab_name}] Question {question_num} - Question submitted in {question_submit_time:.2f}ms (CONCURRENT MODE)")
        
        # Wait for bot response - monitor for response indicators
        logging.info(f"[{tab_name}] Question {question_num} - Waiting for bot response...")
        response_wait_start = time.time()
        
        # Dynamic wait for response - check periodically if response appeared
        min_wait = QUESTION_CONFIG['min_response_wait']
        max_wait = QUESTION_CONFIG['max_response_wait']
        check_interval = QUESTION_CONFIG['response_check_interval']
        waited_time = 0
        response_received = False
        
        # Wait minimum time first
        await asyncio.sleep(min_wait)
        waited_time = min_wait
        
        # Then check periodically for response - verify after each question
        while waited_time < max_wait:
            try:
                # Re-acquire iframe in case it reloaded
                try:
                    iframe = await get_iframe_content_frame(page, tab_name)
                    # Re-setup iframe error logging in case iframe reloaded
                    setup_iframe_error_logging(iframe, tab_name, session_id=session_id, username=username)
                except:
                    pass
                
                # Try to detect if response appeared by checking if question box is ready again
                question_box_check = iframe.get_by_role('textbox', name='Enter your question here')
                is_visible = await question_box_check.is_visible()
                is_enabled = await question_box_check.is_enabled()
                
                # If question box is visible and enabled after minimum wait, response likely completed
                if waited_time >= min_wait and is_visible and is_enabled:
                    # Additional check: verify response is complete by checking if we can interact
                    try:
                        # Try to click/focus the question box to ensure UI is ready
                        await question_box_check.click(timeout=2000)
                        await asyncio.sleep(1)  # Small delay to ensure response is fully rendered
                        response_received = True
                        logging.info(f"[{tab_name}] Question {question_num} - Response detected and verified after {waited_time + 1}s")
                        break
                    except Exception as e:
                        logging.debug(f"[{tab_name}] Question {question_num} - Response check interaction failed: {e}")
                        # Continue waiting
            except Exception as e:
                logging.debug(f"[{tab_name}] Question {question_num} - Error checking response: {e}")
            
            await asyncio.sleep(check_interval)
            waited_time += check_interval
        
        # If we've reached max wait time, assume response received
        if not response_received and waited_time >= max_wait:
            response_received = True
            logging.info(f"[{tab_name}] Question {question_num} - Max wait time reached, assuming response received")
        
        response_wait_time = (time.time() - response_wait_start) * 1000
        question_total_time = (time.time() - question_start) * 1000
        
        question_metric = {
            'question_number': question_num,
            'question': question,
            'question_submit_time': question_submit_time,
            'response_wait_time': response_wait_time,
            'question_total_time': question_total_time,
            'response_received': response_received
        }
        
        # Store in CSV metrics if session_id and course_number provided
        if session_id and course_number:
            CSV_METRICS.append({
                'session_id': session_id,
                'course_number': course_number,
                'question_number': question_num,
                'question_text': question[:200] if len(question) > 200 else question,
                'question_submit_time_ms': round(question_submit_time, 2),
                'response_wait_time_ms': round(response_wait_time, 2),
                'question_total_time_ms': round(question_total_time, 2),
                'response_received': response_received,
                'error': '',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            })
        
        logging.info(f"[{tab_name}] Question {question_num} - Response wait time: {response_wait_time:.2f}ms")
        logging.info(f"[{tab_name}] Question {question_num} - Total question time: {question_total_time:.2f}ms")
        logging.info(f"[{tab_name}] Question {question_num} - Response received: {response_received}")
        
        return question_metric
        
    except Exception as question_error:
        logging.error(f"[{tab_name}] Error in question {question_num}: {question_error}")
        question_total_time = (time.time() - question_start) * 1000
        question_metric = {
            'question_number': question_num,
            'question': question,
            'question_submit_time': 0,
            'response_wait_time': 0,
            'question_total_time': question_total_time,
            'response_received': False,
            'error': str(question_error)
        }
        
        # Store error in CSV metrics
        if session_id and course_number:
            CSV_METRICS.append({
                'session_id': session_id,
                'course_number': course_number,
                'question_number': question_num,
                'question_text': question,
                'question_submit_time_ms': 0,
                'response_wait_time_ms': 0,
                'question_total_time_ms': round(question_total_time, 2),
                'response_received': False,
                'error': str(question_error),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            })
        
        return question_metric

async def interact_with_chatbot(page, tab_name, questions=None, session_id=None, course_number=None, username=None, continuous_mode=False, continuous_iterations=None):
    """Interact with chatbot on a given page.
    
    Args:
        page: Page object
        tab_name: Name of the tab/course
        questions: List of questions to ask
        session_id: Session identifier for CSV logging
        course_number: Course number (1 or 2) for CSV logging
        username: Username for logging
        continuous_mode: If True, continuously loop through questions
        continuous_iterations: Number of cycles to run (None = run until stopped/infinite)
    """
    try:
        logging.info(f"Interacting with chatbot in {tab_name}...")
        
        # Use provided questions or default pool
        if questions is None:
            num_questions = QUESTION_CONFIG['questions_per_session'] if QUESTION_CONFIG['questions_per_session'] is not None else len(QUESTION_POOL)
            questions = select_questions_for_course(QUESTION_POOL, [], num_questions)
        
        logging.info(f"[{tab_name}] Questions assigned: {questions}")
        
        # Setup error and console logging
        setup_page_error_logging(page, tab_name, session_id=session_id, username=username)
        
        # Setup network monitoring - ensure it's set up BEFORE any network activity
        # This ensures all users get monitoring, not just the first 1-2
        monitoring_setup_start = time.time()
        websocket_requests, api_requests, websocket_timings = setup_network_monitoring(
            page, tab_name, session_id=session_id, username=username
        )
        monitoring_setup_time = (time.time() - monitoring_setup_start) * 1000
        
        # #region agent log
        debug_log("H5", f"interact_with_chatbot:{899}", "Network monitoring setup in chatbot interaction", {
            "session_id": session_id,
            "username": username,
            "tab_name": tab_name,
            "setup_time_ms": monitoring_setup_time,
            "monitoring_enabled": STRESS_TEST_CONFIG.get('enable_network_monitoring', True),
            "monitor_all_users": STRESS_TEST_CONFIG.get('monitor_all_users', True)
        }, session_id=session_id)
        # #endregion
        
        # Verify monitoring is active
        if STRESS_TEST_CONFIG.get('enable_network_monitoring', True) and STRESS_TEST_CONFIG.get('monitor_all_users', True):
            logging.info(f"[{tab_name}] ✓ Network monitoring active for user: {username or 'unknown'}")
        
        # Wait for page to fully load
        await page.wait_for_load_state('domcontentloaded', timeout=30000)
        
        # Click the chatbot button using class selector (matches the working JS code) - with retry
        chatbot_btn = page.locator('._chatbot_btn_in_iframe')
        chatbot_click_success = False
        chatbot_max_retries = 3
        chatbot_retry_delay = 1
        
        for chatbot_attempt in range(1, chatbot_max_retries + 1):
            try:
                # Wait for visibility before each attempt
                await chatbot_btn.wait_for(state='visible', timeout=30000)
                await chatbot_btn.scroll_into_view_if_needed()
                
                # #region agent log
                debug_log("CHATBOT_CLICK", f"interact_with_chatbot:{1036}", "Chatbot button click attempt", {
                    "session_id": session_id,
                    "username": username,
                    "tab_name": tab_name,
                    "attempt": chatbot_attempt,
                    "max_retries": chatbot_max_retries
                }, session_id=session_id)
                # #endregion
                
                # Time the chatbot button click
                click_start = time.time()
                await chatbot_btn.click(timeout=10000)
                click_time = (time.time() - click_start) * 1000
                
                # Verify click was successful by checking if iframe appeared
                await asyncio.sleep(0.5)  # Brief wait for iframe to appear
                iframe_check = page.locator('iframe._chatbot_iframe_')
                try:
                    await iframe_check.wait_for(state='attached', timeout=5000)
                    chatbot_click_success = True
                    logging.info(f"[{tab_name}] ✓ Chatbot button clicked successfully on attempt {chatbot_attempt} in {click_time:.2f}ms")
                    
                    # #region agent log
                    debug_log("CHATBOT_CLICK", f"interact_with_chatbot:{1043}", "Chatbot button click successful", {
                        "session_id": session_id,
                        "username": username,
                        "tab_name": tab_name,
                        "attempt": chatbot_attempt,
                        "click_time_ms": click_time
                    }, session_id=session_id)
                    # #endregion
                    
                    # Check for CSRF token error after clicking chatbot button and refresh if needed
                    csrf_refreshed = await handle_csrf_token_error(page, tab_name, session_id=session_id, username=username)
                    if csrf_refreshed:
                        logging.info(f"[{tab_name}] Page refreshed due to CSRF token error, waiting for page to stabilize...")
                        await page.wait_for_load_state('domcontentloaded', timeout=30000)
                        await asyncio.sleep(2)
                        # Re-click chatbot button after refresh
                        await chatbot_btn.wait_for(state='visible', timeout=30000)
                        await chatbot_btn.click(timeout=10000)
                        await asyncio.sleep(0.5)  # Brief wait for iframe to appear
                    
                    break
                except:
                    # Iframe didn't appear, click may have failed
                    logging.warning(f"[{tab_name}] Chatbot button clicked but iframe not detected on attempt {chatbot_attempt}")
                    if chatbot_attempt < chatbot_max_retries:
                        await asyncio.sleep(chatbot_retry_delay)
                        continue
                    else:
                        raise Exception("Chatbot button clicked but iframe never appeared")
                        
            except Exception as chatbot_click_error:
                logging.warning(f"[{tab_name}] Chatbot button click attempt {chatbot_attempt} failed: {chatbot_click_error}")
                
                # #region agent log
                debug_log("CHATBOT_CLICK", f"interact_with_chatbot:{1060}", "Chatbot button click failed", {
                    "session_id": session_id,
                    "username": username,
                    "tab_name": tab_name,
                    "attempt": chatbot_attempt,
                    "error": str(chatbot_click_error)
                }, session_id=session_id)
                # #endregion
                
                if chatbot_attempt < chatbot_max_retries:
                    logging.info(f"[{tab_name}] Retrying chatbot button click in {chatbot_retry_delay}s...")
                    await asyncio.sleep(chatbot_retry_delay)
                    continue
                else:
                    raise Exception(f"Failed to click chatbot button after {chatbot_max_retries} attempts: {chatbot_click_error}")
        
        if not chatbot_click_success:
            raise Exception(f"Chatbot button click failed after {chatbot_max_retries} attempts")
        
        # Wait for the chatbot interface to load - wait a bit and then re-acquire iframe
        logging.info(f"Waiting for chatbot interface to load in {tab_name}...")
        await asyncio.sleep(2)  # Give time for the chatbot interface to initialize
        
        # Wait for chatbot iframe to be ready and get content frame
        iframe = await get_iframe_content_frame(page, tab_name)
        
        # Setup iframe error and console logging to capture warnings/errors from iframe
        setup_iframe_error_logging(iframe, tab_name, session_id=session_id, username=username)
        
        # Wait for authorize button in iframe and click - with retry
        logging.info(f"Waiting for authorize button in {tab_name}...")
        authorize_btn = iframe.get_by_role('button', name='Authorize')
        authorize_click_success = False
        authorize_max_retries = 3
        authorize_retry_delay = 1
        
        for auth_attempt in range(1, authorize_max_retries + 1):
            try:
                # Wait for visibility before each attempt
                await authorize_btn.wait_for(state='visible', timeout=30000)
                
                # #region agent log
                debug_log("AUTHORIZE_CLICK", f"interact_with_chatbot:{1057}", "Authorize button click attempt", {
                    "session_id": session_id,
                    "username": username,
                    "tab_name": tab_name,
                    "attempt": auth_attempt,
                    "max_retries": authorize_max_retries
                }, session_id=session_id)
                # #endregion
                
                # Time the authorize click
                auth_start = time.time()
                await authorize_btn.click()
                auth_time = (time.time() - auth_start) * 1000
                
                # Verify click was successful by waiting a bit and checking if button disappeared or iframe reloaded
                await asyncio.sleep(1)  # Wait for authorization to process
                
                # Check if button is still visible (might mean auth failed) or iframe reloaded (success)
                try:
                    # If button is gone or iframe reloaded, auth likely succeeded
                    is_still_visible = await authorize_btn.is_visible(timeout=2000)
                    if not is_still_visible:
                        authorize_click_success = True
                        logging.info(f"[{tab_name}] ✓ Authorize button clicked successfully on attempt {auth_attempt} in {auth_time:.2f}ms")
                        
                        # #region agent log
                        debug_log("AUTHORIZE_CLICK", f"interact_with_chatbot:{1064}", "Authorize button click successful", {
                            "session_id": session_id,
                            "username": username,
                            "tab_name": tab_name,
                            "attempt": auth_attempt,
                            "click_time_ms": auth_time
                        }, session_id=session_id)
                        # #endregion
                        
                        # Check for CSRF token error after clicking authorize button and refresh if needed
                        # Get iframe to check for CSRF errors inside it
                        try:
                            iframe_for_csrf = await get_iframe_content_frame(page, tab_name)
                        except:
                            iframe_for_csrf = iframe  # Use existing iframe if available
                        
                        csrf_refreshed = await handle_csrf_token_error(page, tab_name, session_id=session_id, username=username, iframe=iframe_for_csrf)
                        if csrf_refreshed:
                            logging.info(f"[{tab_name}] Page refreshed due to CSRF token error after authorize, waiting for page to stabilize...")
                            await page.wait_for_load_state('domcontentloaded', timeout=30000)
                            await asyncio.sleep(2)
                            # Need to re-click chatbot and authorize buttons after refresh
                            await chatbot_btn.wait_for(state='visible', timeout=30000)
                            await chatbot_btn.click(timeout=10000)
                            await asyncio.sleep(0.5)
                            iframe = await get_iframe_content_frame(page, tab_name)
                            authorize_btn = iframe.get_by_role('button', name='Authorize')
                            await authorize_btn.wait_for(state='visible', timeout=30000)
                            await authorize_btn.click(timeout=10000)
                            await asyncio.sleep(0.5)
                        
                        break
                    else:
                        # Button still visible - might need to retry
                        logging.warning(f"[{tab_name}] Authorize button still visible after click on attempt {auth_attempt}")
                        if auth_attempt < authorize_max_retries:
                            await asyncio.sleep(authorize_retry_delay)
                            continue
                except:
                    # Button check failed - likely means iframe reloaded (success)
                    authorize_click_success = True
                    logging.info(f"[{tab_name}] ✓ Authorize button clicked successfully on attempt {auth_attempt} in {auth_time:.2f}ms (iframe likely reloaded)")
                    break
                    
            except Exception as auth_click_error:
                logging.warning(f"[{tab_name}] Authorize button click attempt {auth_attempt} failed: {auth_click_error}")
                
                # #region agent log
                debug_log("AUTHORIZE_CLICK", f"interact_with_chatbot:{1095}", "Authorize button click failed", {
                    "session_id": session_id,
                    "username": username,
                    "tab_name": tab_name,
                    "attempt": auth_attempt,
                    "error": str(auth_click_error)
                }, session_id=session_id)
                # #endregion
                
                if auth_attempt < authorize_max_retries:
                    logging.info(f"[{tab_name}] Retrying authorize button click in {authorize_retry_delay}s...")
                    await asyncio.sleep(authorize_retry_delay)
                    # Re-acquire iframe in case it changed
                    try:
                        iframe = await get_iframe_content_frame(page, tab_name)
                        authorize_btn = iframe.get_by_role('button', name='Authorize')
                    except:
                        pass
                    continue
                else:
                    raise Exception(f"Failed to click authorize button after {authorize_max_retries} attempts: {auth_click_error}")
        
        if not authorize_click_success:
            raise Exception(f"Authorize button click failed after {authorize_max_retries} attempts")
        
        # Wait for the chatbot interface to reload after authorization
        logging.info(f"Waiting for chatbot interface to reload after authorization in {tab_name}...")
        await asyncio.sleep(2)
        
        # Re-acquire the iframe in case it reloaded after authorization
        iframe = await get_iframe_content_frame(page, tab_name)
        
        # Re-setup iframe error logging in case iframe reloaded
        setup_iframe_error_logging(iframe, tab_name, session_id=session_id, username=username)
        
        # Track metrics for each question
        question_metrics = []
        total_interaction_start = time.time()
        
        # Use all questions if questions_per_session is None, otherwise limit
        if QUESTION_CONFIG['questions_per_session'] is None:
            questions_to_use = questions  # Use all questions
        else:
            questions_to_use = questions[:QUESTION_CONFIG['questions_per_session']]
        logging.info(f"[{tab_name}] Using {len(questions_to_use)} questions: {questions_to_use}")
        
        # Check if concurrent questions mode is enabled
        concurrent_questions = STRESS_TEST_CONFIG.get('concurrent_questions', False)
        
        # Continuous mode: loop through questions multiple times
        cycle_count = 0
        cycle_delay = STRESS_TEST_CONFIG.get('continuous_cycle_delay', 5)
        
        if continuous_mode:
            logging.info(f"[{tab_name}] Continuous mode enabled - will loop through questions continuously")
            if continuous_iterations:
                logging.info(f"[{tab_name}] Will run {continuous_iterations} cycles")
            else:
                logging.info(f"[{tab_name}] Will run infinite cycles until stopped")
        
        if concurrent_questions:
            logging.info(f"[{tab_name}] ⚡ CONCURRENT QUESTIONS MODE ENABLED - All questions will be asked simultaneously")
        
        # PIPELINE MODE for constant load: In continuous mode with concurrent questions, use pipeline approach
        if concurrent_questions and continuous_mode:
            # CONTINUOUS PIPELINE: Maintain constant load by continuously processing questions
            # As soon as one question completes, start the next one immediately
            logging.info(f"[{tab_name}] 🚀 Starting continuous pipeline mode - maintaining CONSTANT load...")
            
            question_counter = {'value': 0}  # Use dict to allow modification in nested function
            question_pool = questions_to_use.copy()
            total_questions_processed = {'value': 0}
            should_continue = {'value': True}
            counter_lock = asyncio.Lock()
            
            async def process_question_pipeline():
                while should_continue['value']:
                    # Get next question atomically
                    async with counter_lock:
                        # Check iteration limit
                        if continuous_iterations and total_questions_processed['value'] >= continuous_iterations * len(question_pool):
                            should_continue['value'] = False
                            break
                        
                        # Get next question from pool (cycle through)
                        question_idx = question_counter['value'] % len(question_pool)
                        question = question_pool[question_idx]
                        question_counter['value'] += 1
                        question_num = question_counter['value']
                        total_questions_processed['value'] += 1
                        
                        # Shuffle pool periodically for variety (every full cycle)
                        if question_counter['value'] % len(question_pool) == 0:
                            random.shuffle(question_pool)
                            logging.debug(f"[{tab_name}] Shuffled question pool after {question_counter['value']} questions")
                    
                    # Process question outside lock to allow concurrent processing
                    try:
                        metric = await ask_single_question(
                            page, iframe, tab_name, question, question_num,
                            session_id=session_id, course_number=course_number,
                            username=username, question_metrics=question_metrics
                        )
                        question_metrics.append(metric)
                    
                    except Exception as e:
                        logging.error(f"[{tab_name}] Question {question_num} failed: {e}")
                        question_metrics.append({
                            'question_number': question_num,
                            'question': question,
                            'question_submit_time': 0,
                            'response_wait_time': 0,
                            'question_total_time': 0,
                            'response_received': False,
                            'error': str(e)
                        })
            
            # Launch multiple pipeline workers to maintain constant load
            # Each worker continuously processes questions - as one completes, it immediately starts the next
            num_workers = min(len(questions_to_use), 10)  # Use multiple workers to maintain constant load
            logging.info(f"[{tab_name}] Launching {num_workers} pipeline workers for constant load...")
            
            pipeline_tasks = [
                process_question_pipeline() 
                for _ in range(num_workers)
            ]
            
            # Run pipeline continuously - this maintains constant load
            try:
                await asyncio.gather(*pipeline_tasks, return_exceptions=True)
            except Exception as e:
                logging.error(f"[{tab_name}] Pipeline error: {e}")
                should_continue['value'] = False
            
            logging.info(f"[{tab_name}] Pipeline completed - processed {total_questions_processed['value']} questions")
            return  # Exit function - pipeline handled everything
        
        # STANDARD MODE: Original cycle-based approach for non-continuous or non-concurrent modes
        while True:
            try:
                cycle_count += 1
                if continuous_mode:
                    logging.info(f"[{tab_name}] ========== Starting Question Cycle {cycle_count} ==========")
                
                if concurrent_questions:
                    # CONCURRENT MODE: Ask all questions simultaneously (single cycle)
                    logging.info(f"[{tab_name}] 🚀 Launching {len(questions_to_use)} questions concurrently...")
                    question_tasks = []
                    for question_num, question in enumerate(questions_to_use, 1):
                        question_tasks.append(
                            ask_single_question(
                                page, iframe, tab_name, question, question_num,
                                session_id=session_id, course_number=course_number,
                                username=username, question_metrics=question_metrics
                            )
                        )
                    
                    # Launch all questions concurrently
                    cycle_question_start = time.time()
                    results = await asyncio.gather(*question_tasks, return_exceptions=True)
                    cycle_question_time = (time.time() - cycle_question_start) * 1000
                    
                    # Process results
                    for result in results:
                        if isinstance(result, Exception):
                            logging.error(f"[{tab_name}] Question task failed with exception: {result}")
                            question_metrics.append({
                                'question_number': len(question_metrics) + 1,
                                'question': 'Unknown',
                                'question_submit_time': 0,
                                'response_wait_time': 0,
                                'question_total_time': 0,
                                'response_received': False,
                                'error': str(result)
                            })
                        elif isinstance(result, dict):
                            question_metrics.append(result)
                    
                    logging.info(f"[{tab_name}] ✅ All {len(questions_to_use)} questions completed concurrently in {cycle_question_time:.2f}ms")
                else:
                    # SEQUENTIAL MODE: Ask questions one by one (original behavior)
                    for question_num, question in enumerate(questions_to_use, 1):
                        metric = await ask_single_question(
                            page, iframe, tab_name, question, question_num,
                            session_id=session_id, course_number=course_number,
                            username=username, question_metrics=question_metrics
                        )
                        question_metrics.append(metric)
                        
                        # Delay between questions - configurable for WebSocket stress testing
                        if question_num < len(questions_to_use):
                            # Check if rapid fire mode is enabled for WebSocket stress
                            if STRESS_TEST_CONFIG.get('websocket_rapid_fire', False):
                                # NO DELAY - Maximum performance mode
                                delay = 0
                                logging.info(f"[{tab_name}] Rapid fire mode - NO DELAY - maximum performance...")
                            else:
                                # Use configured delay
                                delay = STRESS_TEST_CONFIG.get('delay_between_questions', 0)
                                if delay > 0:
                                    logging.info(f"[{tab_name}] Waiting {delay}s before next question...")
                            if delay > 0:
                                await asyncio.sleep(delay)
            
                # After completing all questions in cycle (both concurrent and sequential modes)
                if continuous_mode:
                    # Check if we should continue
                    if continuous_iterations and cycle_count >= continuous_iterations:
                        logging.info(f"[{tab_name}] Completed {cycle_count} cycles (requested: {continuous_iterations}), stopping continuous mode")
                        break
                    else:
                        if cycle_delay > 0:
                            logging.info(f"[{tab_name}] Completed cycle {cycle_count}, waiting {cycle_delay}s before next cycle...")
                            await asyncio.sleep(cycle_delay)
                        else:
                            logging.info(f"[{tab_name}] Completed cycle {cycle_count}, NO DELAY - starting next cycle immediately (maximum performance)...")
                        # Shuffle questions for next cycle to add variety
                        random.shuffle(questions_to_use)
                        logging.info(f"[{tab_name}] Starting next cycle with shuffled questions")
                else:
                    # Not in continuous mode, exit after one cycle
                    break
            except Exception as cycle_error:
                # Handle errors in continuous mode - log but continue if in continuous mode
                import traceback
                logging.error(f"[{tab_name}] Error in cycle {cycle_count}: {cycle_error}")
                logging.error(f"[{tab_name}] Traceback: {traceback.format_exc()}")
                
                if continuous_mode:
                    # In continuous mode, try to recover and continue
                    if continuous_iterations and cycle_count >= continuous_iterations:
                        logging.warning(f"[{tab_name}] Error occurred but reached max iterations, stopping")
                        break
                    else:
                        if cycle_delay > 0:
                            logging.warning(f"[{tab_name}] Error in cycle, waiting {cycle_delay}s before retrying...")
                            await asyncio.sleep(cycle_delay)
                        else:
                            logging.warning(f"[{tab_name}] Error in cycle, NO DELAY - retrying immediately (maximum performance)...")
                        # Continue to next cycle instead of breaking
                        continue
                else:
                    # Not in continuous mode, re-raise to exit
                    raise
        
        total_interaction_time = (time.time() - total_interaction_start) * 1000
        
        # Log comprehensive metrics summary
        logging.info(f"[{tab_name}] ========== COMPREHENSIVE METRICS SUMMARY ==========")
        logging.info(f"[{tab_name}] Total Questions: {len(question_metrics)}")
        logging.info(f"[{tab_name}] Total Interaction Time: {total_interaction_time:.2f}ms ({total_interaction_time/1000:.2f}s)")
        
        # Question-by-question metrics
        logging.info(f"[{tab_name}] --- Question-by-Question Metrics ---")
        total_question_time = 0
        total_response_time = 0
        for metric in question_metrics:
            logging.info(f"[{tab_name}] Question {metric['question_number']}:")
            logging.info(f"[{tab_name}]   Question: {metric['question']}")
            logging.info(f"[{tab_name}]   Question Submit Time: {metric['question_submit_time']:.2f}ms")
            logging.info(f"[{tab_name}]   Response Wait Time: {metric['response_wait_time']:.2f}ms ({metric['response_wait_time']/1000:.2f}s)")
            logging.info(f"[{tab_name}]   Question Total Time: {metric['question_total_time']:.2f}ms ({metric['question_total_time']/1000:.2f}s)")
            logging.info(f"[{tab_name}]   Response Received: {metric['response_received']}")
            total_question_time += metric['question_submit_time']
            total_response_time += metric['response_wait_time']
        
        # Average metrics
        avg_question_time = total_question_time / len(question_metrics) if question_metrics else 0
        avg_response_time = total_response_time / len(question_metrics) if question_metrics else 0
        avg_question_total_time = sum(m['question_total_time'] for m in question_metrics) / len(question_metrics) if question_metrics else 0
        
        logging.info(f"[{tab_name}] --- Average Metrics ---")
        logging.info(f"[{tab_name}]   Average Question Submit Time: {avg_question_time:.2f}ms")
        logging.info(f"[{tab_name}]   Average Response Wait Time: {avg_response_time:.2f}ms ({avg_response_time/1000:.2f}s)")
        logging.info(f"[{tab_name}]   Average Question Total Time: {avg_question_total_time:.2f}ms ({avg_question_total_time/1000:.2f}s)")
        
        # Network metrics
        logging.info(f"[{tab_name}] --- Network Metrics ---")
        logging.info(f"[{tab_name}] WebSocket Connections: {len(websocket_requests)}")
        for ws_req in websocket_requests:
            logging.info(f"[{tab_name}]   - URL: {ws_req['url']}")
            logging.info(f"[{tab_name}]     Timestamp: {datetime.fromtimestamp(ws_req['timestamp']).strftime('%H:%M:%S.%f')}")
            if ws_req['url'] in websocket_timings and 'response_time' in websocket_timings[ws_req['url']]:
                conn_time = (websocket_timings[ws_req['url']]['response_time'] - websocket_timings[ws_req['url']]['request_start']) * 1000
                logging.info(f"[{tab_name}]     Connection Time: {conn_time:.2f}ms")
        
        logging.info(f"[{tab_name}] API Requests: {len(api_requests)}")
        for api_req in api_requests:
            logging.info(f"[{tab_name}]   - {api_req['method']} {api_req['url']}")
        
        logging.info(f"[{tab_name}] =====================================================")
        
        logging.info(f"✓ Chatbot interaction completed in {tab_name}")
    except Exception as e:
        logging.error(f"✗ Error interacting with chatbot in {tab_name}: {e}")
        import traceback
        logging.error(traceback.format_exc())

async def run_user_session(context, user, questions=None, handle_both_courses=True, session_id=None):
    """Run a single user session to ask multiple questions in both courses.
    
    Args:
        context: Browser context for this session
        user: User credentials and questions
        questions: List of questions to ask (optional, uses user['questions'] if not provided)
        handle_both_courses: If True, opens both Course 1 and Course 2 and chats concurrently
        session_id: Session identifier for logging
    """
    username = user['username']
    password = user['password']
    
    # Extract user index from session_id for tracking
    user_index_from_session = None
    try:
        if session_id and session_id.startswith("User"):
            parts = session_id.split("_")
            if len(parts) > 0:
                user_part = parts[0]  # "User1", "User2", etc.
                user_index_from_session = int(user_part.replace("User", "")) - 1  # Convert to 0-based
    except (ValueError, AttributeError, IndexError):
        pass
    
    debug_log("H4", f"run_user_session:{1471}", "User session function entry - H4: Browser disconnection", {
        "session_id": session_id,
        "username": username,
        "handle_both_courses": handle_both_courses,
        "questions_count": len(questions) if questions else 0,
        "user_index": user_index_from_session,
        "browser_connected": context.browser.is_connected() if context and context.browser else False
    }, session_id=session_id)
    
    # Handle both single question (backward compatibility) and list of questions
    if questions is None:
        questions = user.get('questions', [])
    elif isinstance(questions, str):
        questions = [questions]
    elif not isinstance(questions, list):
        questions = [questions]
    
    # Create log prefix with user and session info
    log_prefix = f"[{session_id}] [{username}]" if session_id else f"[{username}]"
    
    logging.info(f"{log_prefix} Starting session - Questions: {len(questions)} question(s)")
    if questions:
        logging.info(f"{log_prefix} Questions to ask: {questions}")
    
    # Log session start in user session
    log_session_event(
        session_id, 
        'INFO', 
        f'User session started - {len(questions)} questions, handle_both_courses={handle_both_courses}',
        username=username,
        stage='user_session_start',
        questions_count=len(questions),
        handle_both_courses=handle_both_courses
    )
    
    # Check if context is still valid (with retry)
    browser_connected = False
    for attempt in range(3):
        try:
            if context.browser and context.browser.is_connected():
                browser_connected = True
                break
        except Exception:
            pass
        if attempt < 2:
            await asyncio.sleep(0.3)
    
    if not browser_connected:
        error_msg = "Browser is not connected (after retries)"
        log_session_event(
            session_id, 
            'ERROR', 
            error_msg,
            error=error_msg,
            username=username,
            stage='context_validation'
        )
        logging.error(f"{log_prefix} ✗ {error_msg}")
        return
    
    # Create login page
    login_page = None
    course_1_page = None
    course_2_page = None
    
    # Track timing metrics
    login_start_time = None
    login_end_time = None
    login_time_ms = 0
    course_open_start_time = None
    course_open_end_time = None
    course_open_time_ms = 0
    
    try:
        # Check context before creating page (with retry)
        browser_connected = False
        for attempt in range(3):
            try:
                if context.browser and context.browser.is_connected():
                    browser_connected = True
                    break
            except Exception:
                pass
            if attempt < 2:
                await asyncio.sleep(0.3)
        
        if not browser_connected:
            raise Exception("Browser disconnected before creating login page (after retries)")
        
        login_page = await context.new_page()
        
        # Track login errors and warnings
        login_errors = []
        login_warnings = []
        login_errors_start_count = len(PAGE_ERRORS)  # Track errors before login
        
        # Setup error and console logging for login page
        setup_page_error_logging(login_page, "Login Page", session_id=session_id, username=username)
        
        # Login with retry logic
        login_max_retries = 3
        login_retry_delay = 2  # seconds between retries
        login_successful = False
        login_start_time = time.time()
        
        log_session_event(
            session_id, 
            'INFO', 
            'Starting login process',
            username=username,
            stage='login_start'
        )
        
        for login_attempt in range(1, login_max_retries + 1):
            logging.info(f"{log_prefix} Login attempt {login_attempt}/{login_max_retries}...")
            
            # #region agent log
            debug_log("LOGIN_RETRY", f"run_user_session:{1365}", "Login attempt start", {
                "session_id": session_id,
                "username": username,
                "attempt": login_attempt,
                "max_retries": login_max_retries
            }, session_id=session_id)
            # #endregion
            
            # Check again before navigation (with retry)
            browser_connected = False
            for attempt in range(3):
                try:
                    if context.browser and context.browser.is_connected():
                        browser_connected = True
                        break
                except Exception:
                    pass
                if attempt < 2:
                    await asyncio.sleep(0.3)
            
            if not browser_connected:
                logging.warning(f"{log_prefix} Browser disconnected before login attempt {login_attempt}")
                if login_attempt < login_max_retries:
                    await asyncio.sleep(login_retry_delay)
                    continue
                else:
                    raise Exception("Browser disconnected before navigation (after retries)")
            
            try:
                # Navigate to login page
                await login_page.goto('https://development.instructure.com/login/ldap', wait_until='domcontentloaded', timeout=60000)
                
                # Fill login credentials
                await login_page.fill("#pseudonym_session_unique_id", username)
                await login_page.fill("#pseudonym_session_password", password)
                
                # Click login button
                await login_page.click("#login_form > div.ic-Login__actions > div.ic-Form-control.ic-Form-control--login > input")
                
                # Wait for dashboard to load - this confirms login was successful
                logging.info(f"{log_prefix} Waiting for dashboard to load (attempt {login_attempt})...")
                dashboard_locator = login_page.locator('#DashboardCard_Container')
                
                try:
                    await dashboard_locator.wait_for(state='visible', timeout=60000)
                    # Dashboard is visible - login successful!
                    login_successful = True
                    
                    # #region agent log
                    debug_log("H3", f"run_user_session:{1649}", "Login successful - H3: Login failures", {
                        "session_id": session_id,
                        "username": username,
                        "attempt": login_attempt,
                        "user_index": user_index_from_session if 'user_index_from_session' in locals() else None
                    }, session_id=session_id)
                    # #endregion
                    
                    logging.info(f"{log_prefix} ✓ Login successful on attempt {login_attempt}")
                    
                    # Collect any errors/warnings that occurred during login
                    login_errors_end_count = len(PAGE_ERRORS)
                    for error_idx in range(login_errors_start_count, login_errors_end_count):
                        error = PAGE_ERRORS[error_idx]
                        if error.get('tab_name') == 'Login Page' or error.get('session_id') == session_id:
                            if error.get('type') in ['CONSOLE_ERROR', 'PAGE_ERROR', 'REQUEST_FAILED']:
                                login_errors.append(error)
                            elif error.get('type') == 'CONSOLE_WARNING':
                                login_warnings.append(error)
                    
                    break  # Exit retry loop
                except Exception as dashboard_error:
                    # Dashboard didn't appear - login likely failed
                    error_msg = f"Dashboard not visible after login attempt {login_attempt}: {dashboard_error}"
                    logging.warning(f"{log_prefix} {error_msg}")
                    
                    # Record as warning
                    login_warnings.append({
                        'type': 'LOGIN_WARNING',
                        'message': error_msg,
                        'attempt': login_attempt,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    })
                    
                    # Check if we're still on login page (login failed) or error page
                    current_url = login_page.url
                    page_content = await login_page.content()
                    
                    # #region agent log
                    debug_log("LOGIN_RETRY", f"run_user_session:{1415}", "Login failed - dashboard not visible", {
                        "session_id": session_id,
                        "username": username,
                        "attempt": login_attempt,
                        "current_url": current_url,
                        "error": str(dashboard_error)
                    }, session_id=session_id)
                    # #endregion
                    
                    if login_attempt < login_max_retries:
                        logging.info(f"{log_prefix} Retrying login in {login_retry_delay}s...")
                        await asyncio.sleep(login_retry_delay)
                        # Reload login page for next attempt
                        await login_page.reload(wait_until='domcontentloaded', timeout=30000)
                        continue
                    else:
                        raise Exception(f"Login failed after {login_max_retries} attempts: Dashboard not visible. Last error: {dashboard_error}")
                        
            except Exception as login_error:
                import traceback
                error_msg = str(login_error)
                logging.warning(f"{log_prefix} Login attempt {login_attempt} failed: {error_msg}")
                
                # Record error
                login_errors.append({
                    'type': 'LOGIN_ERROR',
                    'message': error_msg,
                    'attempt': login_attempt,
                    'traceback': traceback.format_exc(),
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                })
                
                # Collect any page errors that occurred during this attempt
                login_errors_end_count = len(PAGE_ERRORS)
                for error_idx in range(login_errors_start_count, login_errors_end_count):
                    error = PAGE_ERRORS[error_idx]
                    if error.get('tab_name') == 'Login Page' or error.get('session_id') == session_id:
                        if error.get('type') in ['CONSOLE_ERROR', 'PAGE_ERROR', 'REQUEST_FAILED']:
                            if error not in login_errors:  # Avoid duplicates
                                login_errors.append(error)
                        elif error.get('type') == 'CONSOLE_WARNING':
                            if error not in login_warnings:  # Avoid duplicates
                                login_warnings.append(error)
                
                # #region agent log
                debug_log("LOGIN_RETRY", f"run_user_session:{1430}", "Login attempt exception", {
                    "session_id": session_id,
                    "username": username,
                    "attempt": login_attempt,
                    "error": error_msg
                }, session_id=session_id)
                # #endregion
                
                if login_attempt < login_max_retries:
                    logging.info(f"{log_prefix} Retrying login in {login_retry_delay}s...")
                    await asyncio.sleep(login_retry_delay)
                    # Reload login page for next attempt
                    try:
                        await login_page.reload(wait_until='domcontentloaded', timeout=30000)
                    except:
                        pass  # If reload fails, next attempt will navigate again
                    continue
                else:
                    # Last attempt failed - record all errors/warnings at session level
                    errors_summary = f"{len(login_errors)} error(s), {len(login_warnings)} warning(s)"
                    error_details = {
                        'errors': login_errors,
                        'warnings': login_warnings,
                        'total_errors': len(login_errors),
                        'total_warnings': len(login_warnings)
                    }
                    
                    log_session_event(
                        session_id, 
                        'ERROR', 
                        f'Login failed after {login_max_retries} attempts: {error_msg}. {errors_summary}',
                        error=error_msg,
                        traceback_text=traceback.format_exc(),
                        username=username,
                        stage='login_process',
                        login_attempts=login_max_retries,
                        login_errors=login_errors,
                        login_warnings=login_warnings,
                        **error_details
                    )
                    raise Exception(f"Login failed after {login_max_retries} attempts: {error_msg}")
        
        if not login_successful:
            # Collect final errors/warnings even if login failed
            login_errors_end_count = len(PAGE_ERRORS)
            for error_idx in range(login_errors_start_count, login_errors_end_count):
                error = PAGE_ERRORS[error_idx]
                if error.get('tab_name') == 'Login Page' or error.get('session_id') == session_id:
                    if error.get('type') in ['CONSOLE_ERROR', 'PAGE_ERROR', 'REQUEST_FAILED']:
                        if error not in login_errors:
                            login_errors.append(error)
                    elif error.get('type') == 'CONSOLE_WARNING':
                        if error not in login_warnings:
                            login_warnings.append(error)
            
            # Record at session level
            errors_summary = f"{len(login_errors)} error(s), {len(login_warnings)} warning(s)"
            log_session_event(
                session_id,
                'ERROR',
                f'Login failed after {login_max_retries} attempts - dashboard never appeared. {errors_summary}',
                error=f'Dashboard never appeared after {login_max_retries} attempts',
                username=username,
                stage='login_process',
                login_attempts=login_max_retries,
                login_errors=login_errors,
                login_warnings=login_warnings,
                total_errors=len(login_errors),
                total_warnings=len(login_warnings)
            )
            raise Exception(f"Login failed after {login_max_retries} attempts - dashboard never appeared")
        
        # Wait for both course cards to be visible with retry logic
        logging.info(f"{log_prefix} Waiting for Course 1 and Course 2 cards to be visible...")
        course_1_card = login_page.locator('#DashboardCard_Container > div > div > div:nth-child(1) > div > a')
        course_2_card = login_page.locator('#DashboardCard_Container > div > div > div:nth-child(2) > div > a')
        
        cards_visible = False
        for attempt in range(3):
            try:
                await course_1_card.wait_for(state='visible', timeout=45000)
                await course_2_card.wait_for(state='visible', timeout=45000)
                cards_visible = True
                logging.info(f"{log_prefix} Both course cards visible on attempt {attempt + 1}")
                break
            except Exception as e:
                logging.warning(f"{log_prefix} Course cards not visible on attempt {attempt + 1}: {e}")
                if attempt < 2:
                    # Refresh page and retry
                    logging.info(f"{log_prefix} Refreshing page and retrying...")
                    await login_page.reload(wait_until='domcontentloaded', timeout=30000)
                    await asyncio.sleep(2)
                    await dashboard_locator.wait_for(state='visible', timeout=30000)
                else:
                    logging.warning(f"{log_prefix} Could not wait for both cards, but dashboard is loaded - proceeding...")
                    break
        
        logging.info(f"{log_prefix} Dashboard loaded successfully")
        login_end_time = time.time()
        login_time_ms = (login_end_time - login_start_time) * 1000 if login_start_time else 0
        
        # Final collection of errors/warnings after successful login
        login_errors_end_count = len(PAGE_ERRORS)
        for error_idx in range(login_errors_start_count, login_errors_end_count):
            error = PAGE_ERRORS[error_idx]
            if error.get('tab_name') == 'Login Page' or error.get('session_id') == session_id:
                if error.get('type') in ['CONSOLE_ERROR', 'PAGE_ERROR', 'REQUEST_FAILED']:
                    if error not in login_errors:
                        login_errors.append(error)
                elif error.get('type') == 'CONSOLE_WARNING':
                    if error not in login_warnings:
                        login_warnings.append(error)
        
        # Record login completion with errors/warnings summary at session level
        errors_summary = ""
        if login_errors or login_warnings:
            errors_summary = f" ({len(login_errors)} error(s), {len(login_warnings)} warning(s) during login)"
            if login_errors:
                logging.warning(f"{log_prefix} Login completed with {len(login_errors)} error(s):")
                for err in login_errors:
                    logging.warning(f"{log_prefix}   - {err.get('type', 'UNKNOWN')}: {err.get('message', 'No message')[:100]}")
            if login_warnings:
                logging.info(f"{log_prefix} Login completed with {len(login_warnings)} warning(s)")
        
        log_session_event(
            session_id, 
            'INFO', 
            f'Login completed successfully in {login_time_ms:.2f}ms{errors_summary}',
            username=username,
            stage='login_complete',
            login_time_ms=round(login_time_ms, 2),
            login_errors=login_errors if login_errors else [],
            login_warnings=login_warnings if login_warnings else [],
            total_login_errors=len(login_errors),
            total_login_warnings=len(login_warnings)
        )
        
        # Close login page (no longer needed)
        await login_page.close()
        
        session_start = time.time()
        course_open_start_time = time.time()
        log_session_event(
            session_id, 
            'INFO', 
            'Starting course opening process',
            username=username,
            stage='course_open_start'
        )
        
        # Get course number from config (default to 1)
        course_number = STRESS_TEST_CONFIG.get('course_for_questions', 1) if not handle_both_courses else 1
        
        if handle_both_courses and questions:
            # Distribute questions between Course 1 and Course 2
            question_distribution = distribute_questions_by_course(
                questions, 
                course_1_questions, 
                course_2_questions, 
                general_questions
            )
            
            course_1_questions_list = question_distribution['course_1']
            course_2_questions_list = question_distribution['course_2']
            
            logging.info(f"{log_prefix} Question distribution:")
            logging.info(f"{log_prefix}   Course 1: {len(course_1_questions_list)} questions - {course_1_questions_list}")
            logging.info(f"{log_prefix}   Course 2: {len(course_2_questions_list)} questions - {course_2_questions_list}")
            
            # Open both courses in parallel (one login, multiple courses)
            logging.info(f"{log_prefix} Opening Course 1 and Course 2 in parallel...")
            
            try:
                # Create tasks immediately to ensure true parallelism
                course_1_task = asyncio.create_task(open_course(context, 1, f"Course 1", session_id=session_id, username=username))
                course_2_task = asyncio.create_task(open_course(context, 2, f"Course 2", session_id=session_id, username=username))
                
                # Wait for both with exception handling
                results = await asyncio.gather(course_1_task, course_2_task, return_exceptions=True)
                
                # Check for exceptions and handle closed page/context errors
                course_1_page = None
                course_2_page = None
                course_1_error = None
                course_2_error = None
                
                if isinstance(results[0], Exception):
                    course_1_error = results[0]
                    error_msg = str(course_1_error)
                    if "Target page, context or browser has been closed" in error_msg or "context or browser has been closed" in error_msg:
                        logging.warning(f"{log_prefix} Course 1 opening failed due to closed context - attempting recovery...")
                        # Try to recover by checking context and retrying
                        if context and not context.pages:
                            logging.error(f"{log_prefix} Context has no pages - cannot recover")
                        else:
                            # Retry once
                            try:
                                course_1_page = await open_course(context, 1, f"Course 1", session_id=session_id, username=username)
                                logging.info(f"{log_prefix} Course 1 recovery successful")
                            except Exception as retry_error:
                                logging.error(f"{log_prefix} Course 1 recovery failed: {retry_error}")
                                course_1_error = retry_error
                    else:
                        logging.error(f"{log_prefix} Course 1 opening failed: {course_1_error}")
                else:
                    course_1_page = results[0]
                
                if isinstance(results[1], Exception):
                    course_2_error = results[1]
                    error_msg = str(course_2_error)
                    if "Target page, context or browser has been closed" in error_msg or "context or browser has been closed" in error_msg:
                        logging.warning(f"{log_prefix} Course 2 opening failed due to closed context - attempting recovery...")
                        # Try to recover by checking context and retrying
                        if context and not context.pages:
                            logging.error(f"{log_prefix} Context has no pages - cannot recover")
                        else:
                            # Retry once
                            try:
                                course_2_page = await open_course(context, 2, f"Course 2", session_id=session_id, username=username)
                                logging.info(f"{log_prefix} Course 2 recovery successful")
                            except Exception as retry_error:
                                logging.error(f"{log_prefix} Course 2 recovery failed: {retry_error}")
                                course_2_error = retry_error
                    else:
                        logging.error(f"{log_prefix} Course 2 opening failed: {course_2_error}")
                else:
                    course_2_page = results[1]
                
                # If both failed, raise an error
                if course_1_error and course_2_error:
                    error_msg = f"Both courses failed to open. Course 1: {course_1_error}, Course 2: {course_2_error}"
                    # #region agent log
                    debug_log("H5", f"run_user_session:{1923}", "Course opening failed - H5: Resource exhaustion", {
                        "session_id": session_id,
                        "username": username,
                        "user_index": user_index_from_session if 'user_index_from_session' in locals() else None,
                        "error": error_msg,
                        "browser_connected": context.browser.is_connected() if context and context.browser else False
                    }, session_id=session_id)
                    # #endregion
                    raise Exception(error_msg)
                
                # If only one failed, log warning but continue with the successful one
                if course_1_error:
                    logging.warning(f"{log_prefix} Course 1 failed but continuing with Course 2: {course_1_error}")
                if course_2_error:
                    logging.warning(f"{log_prefix} Course 2 failed but continuing with Course 1: {course_2_error}")
                
                # #region agent log
                debug_log("H5", f"run_user_session:{1923}", "Courses opened (with recovery) - H5: Resource exhaustion", {
                    "session_id": session_id,
                    "username": username,
                    "user_index": user_index_from_session if 'user_index_from_session' in locals() else None,
                    "course_1_page_exists": course_1_page is not None,
                    "course_2_page_exists": course_2_page is not None,
                    "course_1_error": str(course_1_error) if course_1_error else None,
                    "course_2_error": str(course_2_error) if course_2_error else None,
                    "browser_connected": context.browser.is_connected() if context and context.browser else False
                }, session_id=session_id)
                # #endregion
            except Exception as course_open_error:
                # #region agent log
                debug_log("H5", f"run_user_session:{1923}", "Course opening failed - H5: Resource exhaustion", {
                    "session_id": session_id,
                    "username": username,
                    "user_index": user_index_from_session if 'user_index_from_session' in locals() else None,
                    "error": str(course_open_error),
                    "browser_connected": context.browser.is_connected() if context and context.browser else False
                }, session_id=session_id)
                # #endregion
                raise
            
            course_open_end_time = time.time()
            course_open_time_ms = (course_open_end_time - course_open_start_time) * 1000 if course_open_start_time else 0
            log_session_event(
                session_id, 
                'INFO', 
                f'Courses opened successfully in {course_open_time_ms:.2f}ms - Course 1: {len(course_1_questions_list)} questions, Course 2: {len(course_2_questions_list)} questions',
                username=username,
                stage='course_open_complete',
                course_open_time_ms=round(course_open_time_ms, 2),
                course_1_questions=len(course_1_questions_list),
                course_2_questions=len(course_2_questions_list)
            )
            
            # Run chatbot interactions concurrently for both courses
            chatbot_tasks = []
            continuous_mode = STRESS_TEST_CONFIG.get('continuous_mode', False)
            continuous_iterations = STRESS_TEST_CONFIG.get('continuous_iterations', None)
            
            if course_1_questions_list:
                chatbot_tasks.append(
                    interact_with_chatbot(course_1_page, "Course 1", course_1_questions_list, session_id=session_id, course_number=1, username=username, continuous_mode=continuous_mode, continuous_iterations=continuous_iterations)
                )
            
            if course_2_questions_list:
                chatbot_tasks.append(
                    interact_with_chatbot(course_2_page, "Course 2", course_2_questions_list, session_id=session_id, course_number=2, username=username, continuous_mode=continuous_mode, continuous_iterations=continuous_iterations)
                )
            
            if chatbot_tasks:
                logging.info(f"{log_prefix} Starting concurrent chatbot interactions for both courses...")
                
                # #region agent log
                debug_log("H5", f"run_user_session:{1952}", "Conversation start - H5: Resource exhaustion", {
                    "session_id": session_id,
                    "username": username,
                    "user_index": user_index_from_session if 'user_index_from_session' in locals() else None,
                    "course_1_questions": len(course_1_questions_list) if course_1_questions_list else 0,
                    "course_2_questions": len(course_2_questions_list) if course_2_questions_list else 0,
                    "chatbot_tasks_count": len(chatbot_tasks),
                    "browser_connected": context.browser.is_connected() if context and context.browser else False
                }, session_id=session_id)
                # #endregion
                
                log_session_event(
                    session_id, 
                    'INFO', 
                    'Starting chatbot interactions for both courses concurrently',
                    username=username,
                    stage='chatbot_interaction_start'
                )
                chatbot_start = time.time()
                try:
                    # Run chatbot tasks concurrently with timeout to ensure they don't block each other
                    await run_concurrent_with_timeout(
                        chatbot_tasks,
                        timeout=None,  # No timeout for chatbot interactions (they can take a while)
                        return_exceptions=True
                    )
                    chatbot_total_time = (time.time() - chatbot_start) * 1000
                    logging.info(f"{log_prefix} ✓ All questions answered in both courses in {chatbot_total_time:.2f}ms")
                    log_session_event(
                        session_id, 
                        'INFO', 
                        f'Chatbot interactions completed in {chatbot_total_time:.2f}ms',
                        username=username,
                        stage='chatbot_interaction_complete',
                        chatbot_time_ms=round(chatbot_total_time, 2)
                    )
                except Exception as chatbot_error:
                    import traceback
                    chatbot_total_time = (time.time() - chatbot_start) * 1000
                    log_session_event(
                        session_id, 
                        'ERROR', 
                        f'Chatbot interaction failed: {str(chatbot_error)}',
                        error=str(chatbot_error),
                        traceback_text=traceback.format_exc(),
                        username=username,
                        stage='chatbot_interaction_error',
                        chatbot_time_ms=round(chatbot_total_time, 2)
                    )
                    raise
        else:
            # Single course mode - open only one course per session
            logging.info(f"{log_prefix} Opening course {course_number} (single course mode)...")
            course_1_page = await open_course(context, course_number, f"Course {course_number}")
            course_open_end_time = time.time()
            course_open_time_ms = (course_open_end_time - course_open_start_time) * 1000 if course_open_start_time else 0
            log_session_event(
                session_id, 
                'INFO', 
                f'Course {course_number} opened successfully in {course_open_time_ms:.2f}ms',
                username=username,
                stage='course_open_complete',
                course_open_time_ms=round(course_open_time_ms, 2),
                course_number=course_number
            )
            
            if questions:
                logging.info(f"{log_prefix} Asking {len(questions)} question(s) in Course {course_number}...")
                
                # #region agent log
                debug_log("H5", f"run_user_session:{1989}", "Conversation start - H5: Resource exhaustion", {
                    "session_id": session_id,
                    "username": username,
                    "user_index": user_index_from_session if 'user_index_from_session' in locals() else None,
                    "course_number": course_number,
                    "questions_count": len(questions),
                    "browser_connected": context.browser.is_connected() if context and context.browser else False
                }, session_id=session_id)
                # #endregion
                
                log_session_event(
                    session_id, 
                    'INFO', 
                    f'Starting chatbot interactions for Course {course_number}',
                    username=username,
                    stage='chatbot_interaction_start',
                    course_number=course_number
                )
                chatbot_start = time.time()
                continuous_mode = STRESS_TEST_CONFIG.get('continuous_mode', False)
                continuous_iterations = STRESS_TEST_CONFIG.get('continuous_iterations', None)
                try:
                    await interact_with_chatbot(course_1_page, f"Course {course_number}", questions, session_id=session_id, course_number=course_number, username=username, continuous_mode=continuous_mode, continuous_iterations=continuous_iterations)
                    chatbot_total_time = (time.time() - chatbot_start) * 1000
                    logging.info(f"{log_prefix} ✓ All questions answered in Course {course_number} in {chatbot_total_time:.2f}ms")
                    log_session_event(
                        session_id, 
                        'INFO', 
                        f'Chatbot interactions completed for Course {course_number} in {chatbot_total_time:.2f}ms',
                        username=username,
                        stage='chatbot_interaction_complete',
                        course_number=course_number,
                        chatbot_time_ms=round(chatbot_total_time, 2)
                    )
                except Exception as chatbot_error:
                    import traceback
                    chatbot_total_time = (time.time() - chatbot_start) * 1000
                    log_session_event(
                        session_id, 
                        'ERROR', 
                        f'Chatbot interaction failed for Course {course_number}: {str(chatbot_error)}',
                        error=str(chatbot_error),
                        traceback_text=traceback.format_exc(),
                        username=username,
                        stage='chatbot_interaction_error',
                        course_number=course_number,
                        chatbot_time_ms=round(chatbot_total_time, 2)
                    )
                    raise
        
        session_total_time = (time.time() - session_start) * 1000
        logging.info(f"{log_prefix} ✓ Session completed in {session_total_time:.2f}ms")
        log_session_event(
            session_id, 
            'INFO', 
            f'User session completed successfully - Total time: {session_total_time:.2f}ms',
            username=username,
            stage='user_session_complete',
            session_total_time_ms=round(session_total_time, 2)
        )
        
        # Store session summary in CSV metrics
        if session_id:
            CSV_METRICS.append({
                'session_id': session_id,
                'course_number': 'ALL' if handle_both_courses else str(course_number),
                'question_number': 'SESSION_SUMMARY',
                'question_text': f'Session completed - {len(questions)} questions total',
                'question_submit_time_ms': 0,
                'response_wait_time_ms': 0,
                'question_total_time_ms': round(session_total_time, 2),
                'response_received': True,
                'error': '',
                'login_time_ms': round(login_time_ms, 2) if login_time_ms > 0 else '',
                'course_open_time_ms': round(course_open_time_ms, 2) if course_open_time_ms > 0 else '',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            })
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback_text = traceback.format_exc()
        logging.error(f"{log_prefix} ✗ Error: {error_msg}")
        logging.error(f"✗ Full error traceback for {username}:")
        logging.error(traceback_text)
        log_session_event(
            session_id, 
            'ERROR', 
            f'User session error: {error_msg}',
            error=error_msg,
            traceback_text=traceback_text,
            username=username,
            stage='user_session_error'
        )
        # Don't close context here - let run_session_with_context handle it
        raise  # Re-raise to let run_session_with_context handle cleanup
    finally:
        # Close all pages safely
        pages_to_close = []
        if login_page:
            try:
                if not login_page.is_closed():
                    pages_to_close.append(login_page)
            except:
                pass
        if course_1_page:
            try:
                if not course_1_page.is_closed():
                    pages_to_close.append(course_1_page)
            except:
                pass
        if course_2_page:
            try:
                if not course_2_page.is_closed():
                    pages_to_close.append(course_2_page)
            except:
                pass
        
        for p in pages_to_close:
            try:
                # Check if context is still valid before closing page
                if context.browser and context.browser.is_connected():
                    await p.close()
            except Exception as e:
                logging.debug(f"Error closing page (may be already closed): {e}")

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
    import traceback as tb
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

async def run_session_with_context(browser, user, session_id, questions=None, question=None, handle_both_courses=True, semaphore=None):
    """Run a user session with its own browser context to ask questions.
    
    Args:
        questions: List of questions to ask (preferred)
        question: Single question (for backward compatibility, will be converted to list)
        handle_both_courses: If True, opens both Course 1 and Course 2 and chats concurrently
    """
    context = None
    session_start_time = time.time()
    username = user.get('username', '')
    
    # Log session start
    log_session_event(
        session_id, 
        'SESSION_START', 
        f'Session started for user {username}',
        username=username,
        questions_count=len(questions) if questions else 0,
        handle_both_courses=handle_both_courses
    )
    
    # Extract user index from session_id for tracking
    user_index_from_session = None
    try:
        # session_id format: "User{index}_Session{idx}_{username}"
        if session_id and session_id.startswith("User"):
            parts = session_id.split("_")
            if len(parts) > 0:
                user_part = parts[0]  # "User1", "User2", etc.
                user_index_from_session = int(user_part.replace("User", "")) - 1  # Convert to 0-based
    except (ValueError, AttributeError, IndexError):
        pass
    
        # Acquire semaphore only for creating browser context (limit concurrent context creation)
        semaphore_wait_start = time.time()
        if semaphore:
            # #region agent log
            debug_log("H2", f"run_session:{2167}", "Semaphore acquire attempt start - H2: Semaphore starvation", {
                "session_id": session_id,
                "semaphore_available_before": semaphore._value if hasattr(semaphore, '_value') else 'unknown',
                "username": username,
                "user_index": user_index_from_session,
                "wait_start_time": semaphore_wait_start
            }, session_id=session_id)
            # #endregion
        
        await semaphore.acquire()
        semaphore_acquired = True
        semaphore_wait_time = (time.time() - semaphore_wait_start) * 1000
        
        # #region agent log
        debug_log("H1", f"run_session:{1603}", "Semaphore acquired", {
            "session_id": session_id,
            "wait_time_ms": semaphore_wait_time,
            "semaphore_available_after": semaphore._value if hasattr(semaphore, '_value') else 'unknown',
            "username": username,
            "user_index": user_index_from_session
        }, session_id=session_id)
        # #endregion
    else:
        semaphore_acquired = False
        # #region agent log
        debug_log("H1", f"run_session:{1605}", "No semaphore (None)", {
            "session_id": session_id,
            "username": username,
            "user_index": user_index_from_session
        }, session_id=session_id)
        # #endregion
    
    # Handle backward compatibility: if question is provided but questions is not, use question
    if questions is None and question is not None:
        questions = [question]
    
    try:
        # Check if browser is still open before proceeding (with retry)
        browser_check_attempts = 3
        browser_connected = False
        for attempt in range(browser_check_attempts):
            try:
                if browser.is_connected():
                    browser_connected = True
                    break
            except Exception as e:
                logging.debug(f"Session {session_id}: Browser check attempt {attempt + 1} failed: {e}")
                if attempt < browser_check_attempts - 1:
                    await asyncio.sleep(0.5)  # Wait before retry
        
        if not browser_connected:
            error_msg = 'Browser is not connected (after retries)'
            
            # #region agent log
            debug_log("H4", f"run_session:{2218}", "Browser not connected - H4: Browser disconnection", {
                "session_id": session_id,
                "username": username,
                "user_index": user_index_from_session,
                "error": error_msg
            }, session_id=session_id)
            # #endregion
            
            log_session_event(
                session_id, 
                'ERROR', 
                error_msg,
                error=error_msg,
                username=username,
                stage='browser_check'
            )
            logging.error(f"Session {session_id}: {error_msg}")
            if semaphore_acquired:
                semaphore.release()
            return {'session_id': session_id, 'success': False, 'error': error_msg}
        
        # Create a new browser context for this session (separate window)
        try:
            context_creation_start = time.time()
            
            # Get current context count before creation
            current_context_count = 0
            try:
                if hasattr(browser, 'contexts'):
                    current_context_count = len(browser.contexts)
            except:
                pass
            
            # #region agent log
            debug_log("H1", f"run_session:{2234}", "Context creation start - H1: Browser context limit", {
                "session_id": session_id,
                "username": username,
                "semaphore_held": semaphore_acquired,
                "user_index": user_index_from_session,
                "browser_connected": browser.is_connected() if browser else False,
                "browser_contexts_count_before": current_context_count,
                "max_concurrent_contexts": STRESS_TEST_CONFIG.get('max_concurrent_contexts', 100)
            }, session_id=session_id)
            # #endregion
            
            # #region agent log
            debug_log("H4", f"run_session:{2234}", "Context creation start - H4: Browser disconnection", {
                "session_id": session_id,
                "username": username,
                "browser_connected": browser.is_connected() if browser else False,
                "user_index": user_index_from_session
            }, session_id=session_id)
            # #endregion
            
            context = await browser.new_context()
            context_creation_time = (time.time() - context_creation_start) * 1000
            
            # Get context count after creation
            context_count_after = 0
            try:
                if hasattr(browser, 'contexts'):
                    context_count_after = len(browser.contexts)
            except:
                pass
            
            # #region agent log
            debug_log("H1", f"run_session:{2246}", "Context created successfully - H1: Browser context limit", {
                "session_id": session_id,
                "context_creation_time_ms": context_creation_time,
                "username": username,
                "user_index": user_index_from_session,
                "browser_connected": browser.is_connected() if browser else False,
                "browser_contexts_count_before": current_context_count,
                "browser_contexts_count_after": context_count_after,
                "max_concurrent_contexts": STRESS_TEST_CONFIG.get('max_concurrent_contexts', 100)
            }, session_id=session_id)
            # #endregion
            
            logging.info(f"Session {session_id}: Created new browser context")
            
            # Release semaphore immediately after context creation to allow other sessions to proceed
            # The context is already created, so we don't need to hold the semaphore anymore
            if semaphore_acquired:
                semaphore.release()
                semaphore_acquired = False
                
                # #region agent log
                debug_log("H1", f"run_session:{1598}", "Semaphore released after context creation", {
                    "session_id": session_id,
                    "semaphore_available_after_release": semaphore._value if hasattr(semaphore, '_value') else 'unknown',
                    "username": username
                }, session_id=session_id)
                # #endregion
                
                logging.debug(f"Session {session_id}: Released semaphore after context creation")
            log_session_event(
                session_id, 
                'INFO', 
                'Browser context created successfully',
                username=username,
                stage='context_creation'
            )
        except Exception as e:
            import traceback
            error_msg = f'Context creation failed: {str(e)}'
            
            # Get context count on failure
            context_count_on_error = 0
            try:
                if hasattr(browser, 'contexts'):
                    context_count_on_error = len(browser.contexts)
            except:
                pass
            
            # #region agent log
            debug_log("H1", f"run_session:{2282}", "Context creation failed - H1: Browser context limit", {
                "session_id": session_id,
                "username": username,
                "user_index": user_index_from_session,
                "error": str(e),
                "browser_contexts_count_on_error": context_count_on_error,
                "max_concurrent_contexts": STRESS_TEST_CONFIG.get('max_concurrent_contexts', 100)
            }, session_id=session_id)
            # #endregion
            
            log_session_event(
                session_id, 
                'ERROR', 
                error_msg,
                error=str(e),
                traceback_text=traceback.format_exc(),
                username=username,
                stage='context_creation'
            )
            logging.error(f"Session {session_id}: {error_msg}")
            if semaphore_acquired:
                semaphore.release()
            return {'session_id': session_id, 'success': False, 'error': error_msg}
        
        # Verify context was created successfully
        if context is None:
            error_msg = 'Context creation returned None'
            log_session_event(
                session_id, 
                'ERROR', 
                error_msg,
                error=error_msg,
                username=username,
                stage='context_verification'
            )
            logging.error(f"Session {session_id}: {error_msg}")
            if semaphore_acquired:
                semaphore.release()
            return {'session_id': session_id, 'success': False, 'error': error_msg}
        
        # Small delay to ensure context is ready
        await asyncio.sleep(0.2)
        
        # Verify browser is still connected before running session (with retry)
        browser_check_attempts = 3
        browser_connected = False
        for attempt in range(browser_check_attempts):
            try:
                if browser.is_connected():
                    browser_connected = True
                    break
            except Exception as e:
                logging.debug(f"Session {session_id}: Browser check attempt {attempt + 1} failed: {e}")
                if attempt < browser_check_attempts - 1:
                    await asyncio.sleep(0.5)  # Wait before retry
        
        if not browser_connected:
            error_msg = 'Browser disconnected before session start (after retries)'
            
            # #region agent log
            debug_log("H4", f"run_session:{2331}", "Browser disconnected before session start - H4: Browser disconnection", {
                "session_id": session_id,
                "username": username,
                "user_index": user_index_from_session,
                "error": error_msg
            }, session_id=session_id)
            # #endregion
            
            log_session_event(
                session_id, 
                'ERROR', 
                error_msg,
                error=error_msg,
                username=username,
                stage='pre_session_check'
            )
            logging.error(f"Session {session_id}: {error_msg}")
            return {'session_id': session_id, 'success': False, 'error': error_msg}
        
        # Run the session with the questions (handles both courses if enabled)
        try:
            # #region agent log
            debug_log("H4", f"run_session:{1826}", "About to execute user session", {
                "session_id": session_id,
                "username": username,
                "user_index": user_index_from_session,
                "questions_count": len(questions) if questions else 0
            }, session_id=session_id)
            # #endregion
            
            log_session_event(
                session_id, 
                'INFO', 
                'Starting user session execution',
                username=username,
                stage='session_execution_start'
            )
            await run_user_session(context, user, questions, handle_both_courses, session_id=session_id)
            
            # #region agent log
            debug_log("H4", f"run_session:{1834}", "User session execution completed", {
                "session_id": session_id,
                "username": username,
                "user_index": user_index_from_session
            }, session_id=session_id)
            # #endregion
            session_duration = (time.time() - session_start_time) * 1000
            log_session_event(
                session_id, 
                'SESSION_END', 
                f'Session completed successfully in {session_duration:.2f}ms',
                username=username,
                stage='session_complete',
                session_duration_ms=round(session_duration, 2),
                success=True
            )
            logging.info(f"Session {session_id}: Completed successfully")
            return {'session_id': session_id, 'success': True, 'duration_ms': session_duration}
        except Exception as session_error:
            import traceback
            session_duration = (time.time() - session_start_time) * 1000
            error_msg = str(session_error)
            traceback_text = traceback.format_exc()
            log_session_event(
                session_id, 
                'ERROR', 
                f'Session execution failed: {error_msg}',
                error=error_msg,
                traceback_text=traceback_text,
                username=username,
                stage='session_execution',
                session_duration_ms=round(session_duration, 2),
                success=False
            )
            logging.error(f"Session {session_id}: Error during session execution: {session_error}")
            logging.error(f"Session {session_id}: Traceback: {traceback_text}")
            return {'session_id': session_id, 'success': False, 'error': error_msg, 'duration_ms': session_duration}
    except Exception as e:
        import traceback
        session_duration = (time.time() - session_start_time) * 1000 if 'session_start_time' in locals() else 0
        error_msg = str(e)
        traceback_text = traceback.format_exc()
        log_session_event(
            session_id, 
            'ERROR', 
            f'Session setup failed: {error_msg}',
            error=error_msg,
            traceback_text=traceback_text,
            username=username,
            stage='session_setup',
            session_duration_ms=round(session_duration, 2),
            success=False
        )
        logging.error(f"Session {session_id}: Error setting up session: {e}")
        logging.error(traceback.format_exc())
        return {'session_id': session_id, 'success': False, 'error': error_msg, 'duration_ms': session_duration}
    finally:
        # Close the context (browser window) for this session - only after session completes or fails
        # BUT: Check if continuous mode is active - if so, don't close immediately
        continuous_mode = STRESS_TEST_CONFIG.get('continuous_mode', False)
        continuous_iterations = STRESS_TEST_CONFIG.get('continuous_iterations', None)
        
        # Only close if not in infinite continuous mode, or if session explicitly completed/failed
        should_close = True
        if continuous_mode and continuous_iterations is None:
            # Infinite continuous mode - check if session actually completed
            # If we're in finally due to normal completion, we should close
            # But if it's due to an error, we might want to keep it open for retry
            # For now, we'll close but log a warning
            logging.info(f"Session {session_id}: Continuous mode was active, but session ended - closing context")
        
        if context and should_close:
            try:
                logging.info(f"Session {session_id}: Starting cleanup...")
                log_session_event(
                    session_id, 
                    'INFO', 
                    'Starting session cleanup',
                    username=username,
                    stage='cleanup_start'
                )
                # Check if browser is still connected before cleanup
                browser_connected = False
                try:
                    if context.browser and context.browser.is_connected():
                        browser_connected = True
                except Exception as e:
                    logging.debug(f"Session {session_id}: Could not check browser connection: {e}")
                
                if browser_connected:
                    # Close all pages first
                    pages_closed = 0
                    for page in context.pages:
                        try:
                            if not page.is_closed():
                                await page.close()
                                pages_closed += 1
                        except Exception as e:
                            logging.debug(f"Session {session_id}: Error closing page during cleanup: {e}")
                            log_session_event(
                                session_id, 
                                'WARNING', 
                                f'Error closing page during cleanup: {str(e)}',
                                error=str(e),
                                username=username,
                                stage='cleanup_pages'
                            )
                    
                    logging.info(f"Session {session_id}: Closed {pages_closed} page(s)")
                    
                    # Wait a bit to ensure all operations complete
                    await asyncio.sleep(0.5)
                    
                    # Close context only if browser is still connected
                    try:
                        if context.browser.is_connected():
                            await context.close()
                            logging.info(f"Session {session_id}: Closed browser context (session completed or failed)")
                            log_session_event(
                                session_id, 
                                'INFO', 
                                'Session cleanup completed successfully',
                                username=username,
                                stage='cleanup_complete',
                                pages_closed=pages_closed
                            )
                        else:
                            logging.warning(f"Session {session_id}: Browser disconnected, skipping context close")
                            log_session_event(
                                session_id, 
                                'WARNING', 
                                'Browser disconnected during cleanup, skipping context close',
                                username=username,
                                stage='cleanup_skip'
                            )
                    except Exception as e:
                        logging.warning(f"Session {session_id}: Error checking/closing context: {e}")
                else:
                    logging.debug(f"Session {session_id}: Browser not connected, skipping context cleanup")
                    log_session_event(
                        session_id, 
                        'WARNING', 
                        'Browser not connected, skipping context cleanup',
                        username=username,
                        stage='cleanup_skip'
                    )
            except Exception as e:
                import traceback
                logging.warning(f"Session {session_id}: Error closing context: {e}")
                log_session_event(
                    session_id, 
                    'ERROR', 
                    f'Error during cleanup: {str(e)}',
                    error=str(e),
                    traceback_text=traceback.format_exc(),
                    username=username,
                    stage='cleanup_error'
                )
        # Semaphore was already released after context creation, but release again if somehow still held
        if semaphore_acquired and semaphore:
            semaphore.release()
            logging.debug(f"Session {session_id}: Released semaphore in finally block")

def write_session_logs_csv(append_mode=False):
    """Write session-level logs and errors to CSV file in parallel with other reports.
    
    Args:
        append_mode: If True, append to existing file. If False, create new file.
    """
    global SESSION_CSV_EXPORT_FILENAME
    
    # Check if CSV export is enabled
    if not STRESS_TEST_CONFIG.get('enable_csv_export', True):
        if not append_mode:
            logging.info("[CAT:SYSTEM] [SRC:UTILS] CSV export disabled - skipping session logs CSV write")
        return
    
    # Get current working directory for absolute path
    cwd = os.getcwd()
    
    if not SESSION_LOGS:
        if not append_mode:
            logging.warning("No session logs collected to write to CSV")
        return
    
    # Generate filename with timestamp (only on first write)
    if SESSION_CSV_EXPORT_FILENAME is None or not append_mode:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        SESSION_CSV_EXPORT_FILENAME = f"session_logs_{timestamp}.csv"
        logging.info(f"📊 Session logs CSV will be written to: {cwd}")
        logging.info(f"   - Session logs: {SESSION_CSV_EXPORT_FILENAME}")
    
    session_csv_filename = SESSION_CSV_EXPORT_FILENAME
    session_csv_filepath = os.path.join(cwd, session_csv_filename)
    
    # Define CSV columns for session logs
    fieldnames = [
        'session_id',
        'username',
        'event_type',
        'message',
        'error',
        'traceback',
        'stage',
        'timestamp',
        'session_duration_ms',
        'success',
        'questions_count',
        'handle_both_courses',
        'pages_closed',
        # Add any other dynamic fields
    ]
    
    try:
        # Determine which entries to write
        # Track written entries to avoid duplicates in append mode
        if not hasattr(write_session_logs_csv, '_written_indices'):
            write_session_logs_csv._written_indices = set()
        
        if append_mode:
            # In append mode, only write new entries
            entries_to_write = [log_entry for i, log_entry in enumerate(SESSION_LOGS) 
                               if i not in write_session_logs_csv._written_indices]
            if not entries_to_write:
                return  # No new entries to write
            mode = 'a'
        else:
            # In write mode, write all entries
            entries_to_write = SESSION_LOGS
            mode = 'w'
            write_session_logs_csv._written_indices = set()
        
        logging.info(f"📝 Writing session logs CSV to: {session_csv_filepath} (mode: {mode}, records: {len(entries_to_write)})")
        with open(session_csv_filepath, mode, newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
            
            # Write header only if creating new file
            if not append_mode:
                writer.writeheader()
            
            # Write entries and track indices
            start_index = len(write_session_logs_csv._written_indices)
            for i, log_entry in enumerate(entries_to_write):
                entry_index = start_index + i
                write_session_logs_csv._written_indices.add(entry_index)
                # Prepare row with all fields, handling missing ones
                row = {
                    'session_id': log_entry.get('session_id', ''),
                    'username': log_entry.get('username', ''),
                    'event_type': log_entry.get('event_type', ''),
                    'message': log_entry.get('message', '')[:500],  # Limit message length
                    'error': log_entry.get('error', '')[:500],  # Limit error length
                    'traceback': log_entry.get('traceback', '')[:2000] if log_entry.get('traceback') else '',  # Limit traceback length
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
            logging.info(f"  Added {len(entries_to_write)} new log records (total: {len(SESSION_LOGS)})")
        else:
            logging.info(f"✓ Session logs CSV report written successfully: {session_csv_filepath}")
            logging.info(f"  Absolute path: {os.path.abspath(session_csv_filepath)}")
            logging.info(f"  Total session log records: {len(SESSION_LOGS)}")
            # Verify file exists
            if os.path.exists(session_csv_filepath):
                file_size = os.path.getsize(session_csv_filepath)
                logging.info(f"  File size: {file_size} bytes")
            else:
                logging.error(f"  ⚠️  WARNING: Session logs CSV file not found at {session_csv_filepath}")
        
        # Count by event type (only for full export)
        if not append_mode:
            event_counts = {}
            error_count = 0
            for log_entry in SESSION_LOGS:
                event_type = log_entry.get('event_type', 'UNKNOWN')
                event_counts[event_type] = event_counts.get(event_type, 0) + 1
                if event_type == 'ERROR':
                    error_count += 1
            
            logging.info(f"  Event type breakdown:")
            for event_type, count in event_counts.items():
                logging.info(f"    {event_type}: {count}")
            logging.info(f"  Total errors: {error_count}")
        
    except Exception as e:
        logging.error(f"✗ Error writing session logs CSV report: {e}")
        import traceback
        logging.error(traceback.format_exc())

def write_csv_report(append_mode=False):
    """Write collected metrics to CSV file.
    
    Args:
        append_mode: If True, append to existing file. If False, create new file.
    """
    global CSV_EXPORT_FILENAME, ERRORS_CSV_EXPORT_FILENAME
    
    # Get current working directory for absolute path
    cwd = os.getcwd()
    
    if not CSV_METRICS and not PAGE_ERRORS:
        if not append_mode:
            logging.warning("No metrics collected to write to CSV")
        return
    
    # Generate filename with timestamp (only on first write)
    if CSV_EXPORT_FILENAME is None or not append_mode:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        CSV_EXPORT_FILENAME = f"stress_test_results_{timestamp}.csv"
        ERRORS_CSV_EXPORT_FILENAME = f"stress_test_errors_{timestamp}.csv"
        logging.info(f"📊 CSV files will be written to: {cwd}")
        logging.info(f"   - Results: {CSV_EXPORT_FILENAME}")
        logging.info(f"   - Errors: {ERRORS_CSV_EXPORT_FILENAME}")
    
    csv_filename = CSV_EXPORT_FILENAME
    csv_filepath = os.path.join(cwd, csv_filename)
    
    # Define CSV columns
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
        # Determine which entries to write
        if not hasattr(write_csv_report, '_written_indices'):
            write_csv_report._written_indices = set()
        
        if append_mode:
            # In append mode, only write new entries
            metrics_to_write = [metric for i, metric in enumerate(CSV_METRICS) 
                               if i not in write_csv_report._written_indices]
            if not metrics_to_write:
                metrics_to_write = []  # No new metrics
            mode = 'a'
        else:
            # In write mode, write all entries
            metrics_to_write = CSV_METRICS
            mode = 'w'
            write_csv_report._written_indices = set()
        
        logging.info(f"📝 Writing CSV to: {csv_filepath} (mode: {mode}, records: {len(metrics_to_write)})")
        with open(csv_filepath, mode, newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            # Write header only if creating new file
            if not append_mode:
                writer.writeheader()
            
            # Write entries and track indices
            start_index = len(write_csv_report._written_indices)
            for i, metric in enumerate(metrics_to_write):
                entry_index = start_index + i
                write_csv_report._written_indices.add(entry_index)
                
                # Extract user from session_id for better readability
                # Extract user from session_id (format: User1_Session1_username@domain.com)
                session_id = metric.get('session_id', '')
                user = 'Unknown'
                if session_id:
                    parts = session_id.split('_')
                    if len(parts) >= 3:
                        user = '_'.join(parts[2:])  # Get username part
                
                # Prepare row data
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
            logging.info(f"  Added {len(metrics_to_write)} new records (total: {len(CSV_METRICS)})")
        else:
            logging.info(f"✓ CSV report written successfully: {csv_filepath}")
            logging.info(f"  Absolute path: {os.path.abspath(csv_filepath)}")
            logging.info(f"  Total records: {len(CSV_METRICS)}")
            # Verify file exists
            if os.path.exists(csv_filepath):
                file_size = os.path.getsize(csv_filepath)
                logging.info(f"  File size: {file_size} bytes")
            else:
                logging.error(f"  ⚠️  WARNING: CSV file not found at {csv_filepath}")
        
        # Write errors CSV if there are any errors
        if PAGE_ERRORS:
            errors_csv_filename = ERRORS_CSV_EXPORT_FILENAME
            errors_csv_filepath = os.path.join(cwd, errors_csv_filename)
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
                # Determine which errors to write
                if not hasattr(write_csv_report, '_error_written_indices'):
                    write_csv_report._error_written_indices = set()
                
                if append_mode:
                    errors_to_write = [error for i, error in enumerate(PAGE_ERRORS) 
                                     if i not in write_csv_report._error_written_indices]
                    if not errors_to_write:
                        errors_to_write = []  # No new errors
                    error_mode = 'a'
                else:
                    errors_to_write = PAGE_ERRORS
                    error_mode = 'w'
                    write_csv_report._error_written_indices = set()
                
                logging.info(f"📝 Writing errors CSV to: {errors_csv_filepath} (mode: {error_mode}, records: {len(errors_to_write)})")
                with open(errors_csv_filepath, error_mode, newline='', encoding='utf-8') as errors_csvfile:
                    writer = csv.DictWriter(errors_csvfile, fieldnames=error_fieldnames)
                    
                    # Write header only if creating new file
                    if not append_mode:
                        writer.writeheader()
                    
                    # Write entries and track indices
                    error_start_index = len(write_csv_report._error_written_indices)
                    for i, error in enumerate(errors_to_write):
                        error_entry_index = error_start_index + i
                        write_csv_report._error_written_indices.add(error_entry_index)
                        row = {
                            'type': error.get('type', ''),
                            'message': error.get('message', '')[:500],  # Limit length
                            'location': error.get('location', ''),
                            'url': error.get('url', ''),
                            'method': error.get('method', ''),
                            'error': error.get('error', ''),
                            'stack': error.get('stack', '')[:1000] if error.get('stack') else '',  # Limit length
                            'tab_name': error.get('tab_name', ''),
                            'session_id': error.get('session_id', ''),
                            'username': error.get('username', ''),
                            'timestamp': error.get('timestamp', '')
                        }
                        writer.writerow(row)
                
                if append_mode:
                    logging.info(f"✓ Errors CSV report updated (appended): {errors_csv_filepath}")
                    logging.info(f"  Added {len(errors_to_write)} new error records (total: {len(PAGE_ERRORS)})")
                else:
                    logging.info(f"✓ Errors CSV report written successfully: {errors_csv_filepath}")
                    logging.info(f"  Absolute path: {os.path.abspath(errors_csv_filepath)}")
                    logging.info(f"  Total error records: {len(PAGE_ERRORS)}")
                    # Verify file exists
                    if os.path.exists(errors_csv_filepath):
                        file_size = os.path.getsize(errors_csv_filepath)
                        logging.info(f"  File size: {file_size} bytes")
                    else:
                        logging.error(f"  ⚠️  WARNING: Errors CSV file not found at {errors_csv_filepath}")
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
    
    # Write categorized error CSVs
    try:
        from reporting.categorized_csv_reporter import write_all_categorized_csvs
        write_all_categorized_csvs(append_mode=append_mode)
    except ImportError:
        pass
    except Exception as e:
        logging.warning(f"Could not write categorized CSVs: {e}")

async def stress_test(browser, users):
    """Run stress test where all sessions ask questions concurrently across multiple browser windows."""
    # Resource calculation is disabled by default - use config values directly
    # If dynamic_resource_calculation is True, calculate optimal configuration based on resources
    if STRESS_TEST_CONFIG.get('dynamic_resource_calculation', False):
        # Use dynamic calculation - no hard limit
        # If max_concurrent_contexts is set in config, use that; otherwise calculate based on resources
        max_contexts_override = STRESS_TEST_CONFIG.get('max_concurrent_contexts')
        update_stress_test_config(
            dynamic_mode=True,
            override_max_contexts=max_contexts_override  # Use config value or None for unlimited
        )
    else:
        # Resource calculation disabled - use config values as-is
        logging.info("Resource calculation disabled - using config values directly")
    
    all_session_metrics = []
    stress_test_start = time.time()
    
    # Get configuration (values are now optimized and stored in STRESS_TEST_CONFIG)
    sessions_per_user = STRESS_TEST_CONFIG.get('sessions_per_user', 1)
    delay_between_questions = STRESS_TEST_CONFIG.get('delay_between_questions', 2)
    handle_both_courses = STRESS_TEST_CONFIG.get('handle_both_courses', True)
    session_setup_delay = STRESS_TEST_CONFIG.get('session_setup_delay', 0)
    session_batch_size = STRESS_TEST_CONFIG.get('session_batch_size', None)
    session_batch_delay = STRESS_TEST_CONFIG.get('session_batch_delay', 0)
    
    # Calculate total concurrent sessions needed
    total_concurrent_sessions = len(users) * sessions_per_user
    
    # Get max concurrent contexts from config (prevents overwhelming browser/system)
    max_contexts = STRESS_TEST_CONFIG.get('max_concurrent_contexts', 100)
    
    # Semaphore to limit concurrent context creation (prevent overwhelming browser)
    # Use the higher of max_contexts or total_concurrent_sessions to ensure all users can run
    # For heavy load testing, we want to allow all concurrent sessions
    semaphore_limit = max(max_contexts, total_concurrent_sessions)
    context_semaphore = asyncio.Semaphore(semaphore_limit)
    logging.info(f"Semaphore configuration: limit={semaphore_limit} (max_contexts={max_contexts}, total_sessions={total_concurrent_sessions})")
    
    # Calculate total questions
    total_questions = sum(len(user.get('questions', [])) for user in users)
    
    # Get continuous mode configuration
    continuous_mode = STRESS_TEST_CONFIG.get('continuous_mode', False)
    continuous_iterations = STRESS_TEST_CONFIG.get('continuous_iterations', None)
    continuous_cycle_delay = STRESS_TEST_CONFIG.get('continuous_cycle_delay', 5)
    
    logging.info("=" * 80)
    logging.info("STRESS TEST STARTED - CONCURRENT MULTI-WINDOW MODE")
    logging.info(f"Total Users Configured: {len(users)}")
    logging.info(f"User List:")
    for idx, user in enumerate(users, 1):
        username = user.get('username', 'Unknown')
        questions_count = len(user.get('questions', []))
        logging.info(f"  {idx}. {username} ({questions_count} questions)")
    logging.info(f"Sessions per User: {sessions_per_user} (each user gets {sessions_per_user} browser windows)")
    logging.info(f"Total Concurrent Browser Windows: {total_concurrent_sessions}")
    logging.info(f"Total Questions Across All Users: {total_questions}")
    logging.info(f"Handle Both Courses: {handle_both_courses}")
    logging.info(f"Continuous Mode: {continuous_mode}")
    if session_setup_delay > 0:
        logging.info(f"Session Setup Delay: {session_setup_delay}s between each session (staggered creation)")
    else:
        logging.info(f"Session Setup Delay: 0s (all sessions created immediately)")
    
    if session_batch_size and session_batch_size > 0:
        total_sessions = len(users) * sessions_per_user
        num_batches = (total_sessions + session_batch_size - 1) // session_batch_size
        logging.info(f"Session Batching: Enabled - {total_sessions} sessions in {num_batches} batches (batch size: {session_batch_size})")
        if session_batch_delay > 0:
            logging.info(f"Batch Delay: {session_batch_delay}s between batches")
    else:
        logging.info(f"Session Batching: Disabled (all sessions created at once)")
    
    # Network Monitoring Configuration
    enable_monitoring = STRESS_TEST_CONFIG.get('enable_network_monitoring', True)
    monitor_all = STRESS_TEST_CONFIG.get('monitor_all_users', True)
    logging.info(f"Network Monitoring: {'ENABLED' if enable_monitoring else 'DISABLED'}")
    if enable_monitoring:
        logging.info(f"  → Monitor All Users: {'YES' if monitor_all else 'NO (only first users)'}")
        if monitor_all:
            logging.info(f"  → ✓ All {len(users)} users will have network monitoring active")
        else:
            logging.warning(f"  → ⚠️  Only first users will be monitored (monitor_all_users=False)")
    else:
        logging.warning(f"  → ⚠️  Network monitoring is disabled (enable_network_monitoring=False)")
    if continuous_mode:
        if continuous_iterations:
            logging.info(f"  → Will run {continuous_iterations} question cycles per session")
        else:
            logging.info(f"  → Will run infinite question cycles (until stopped)")
        logging.info(f"  → Cycle delay: {continuous_cycle_delay}s between cycles")
        logging.info(f"  → All conversations maintained concurrently")
    if handle_both_courses:
        logging.info(f"Architecture: Each browser window opens BOTH Course 1 and Course 2")
        logging.info(f"           → Questions distributed between courses automatically")
        logging.info(f"           → Chatbot interactions run concurrently in both courses")
    logging.info(f"Architecture: Each user logs in from {sessions_per_user} separate browser windows")
    logging.info(f"           → All {total_concurrent_sessions} windows chat concurrently")
    logging.info(f"           → Each window asks questions independently")
    # Safely get semaphore value for logging
    semaphore_value = context_semaphore._value if hasattr(context_semaphore, '_value') else 'unknown'
    logging.info(f"Max concurrent contexts (semaphore limit): {semaphore_value}")
    logging.info("=" * 80)
    
    # Create all sessions concurrently - each session will ask ALL its questions
    # Each user gets multiple browser windows (sessions_per_user), all running concurrently
    tasks = []
    session_id_counter = 0
    task_creation_order = []
    user_task_counts = {}  # Track how many tasks per user
    
    # #region agent log
    debug_log("H2", f"stress_test:{2487}", "Starting task creation loop", {
        "total_users": len(users),
        "sessions_per_user": sessions_per_user,
        "expected_total_tasks": len(users) * sessions_per_user
    })
    # #endregion
    
    # Prepare all session configurations first
    session_configs = []
    for user_index, user in enumerate(users):
        user_questions = user.get('questions', [])
        username = user.get('username', 'Unknown')
        user_task_counts[user_index] = 0
        
        for session_idx in range(sessions_per_user):
            session_id_counter += 1
            session_id = f"User{user_index+1}_Session{session_idx+1}_{user['username']}"
            session_configs.append({
                'user_index': user_index,
                'user': user,
                'username': username,
                'user_questions': user_questions,
                'session_id': session_id,
                'session_idx': session_idx
            })
    
    # Create sessions in batches if batch_size is configured
    if session_batch_size and session_batch_size > 0:
        total_sessions = len(session_configs)
        num_batches = (total_sessions + session_batch_size - 1) // session_batch_size  # Ceiling division
        logging.info(f"Creating {total_sessions} sessions in {num_batches} batches (batch size: {session_batch_size})")
        
        for batch_num in range(num_batches):
            batch_start = batch_num * session_batch_size
            batch_end = min(batch_start + session_batch_size, total_sessions)
            batch_configs = session_configs[batch_start:batch_end]
            
            logging.info(f"Creating batch {batch_num + 1}/{num_batches} ({len(batch_configs)} sessions)...")
            
            # Create sessions in this batch
            for config in batch_configs:
                user_index = config['user_index']
                user = config['user']
                username = config['username']
                user_questions = config['user_questions']
                session_id = config['session_id']
                session_idx = config['session_idx']
                
                # #region agent log
                debug_log("H1", f"stress_test:{2969}", "Task creation start - H1: Browser context limit", {
                    "session_id": session_id,
                    "user_index": user_index,
                    "session_idx": session_idx,
                    "task_number": len(tasks),
                    "total_tasks_so_far": len(tasks),
                    "username": username,
                    "user_tasks_created": user_task_counts[user_index],
                    "total_users": len(users),
                    "current_user_number": user_index + 1,
                    "batch_number": batch_num + 1,
                    "batch_size": len(batch_configs)
                }, session_id=session_id)
                # #endregion
                
                logging.info(f"Creating session: {session_id} for user {username} "
                            f"(Session {session_idx+1} of {sessions_per_user} for this user) [Batch {batch_num + 1}/{num_batches}]")
                
                task = run_session_with_context(
                    browser, 
                    user, 
                    session_id, 
                    questions=user_questions,
                    handle_both_courses=handle_both_courses,
                    semaphore=context_semaphore
                )
                tasks.append(task)
                task_creation_order.append(session_id)
                user_task_counts[user_index] += 1
                
                # Add delay between session setups within batch
                if session_setup_delay > 0 and config != batch_configs[-1]:  # Don't delay after last in batch
                    await asyncio.sleep(session_setup_delay)
                    logging.debug(f"Session setup delay: waited {session_setup_delay}s before creating next session")
            
            # Wait between batches (except after the last batch)
            if batch_num < num_batches - 1 and session_batch_delay > 0:
                logging.info(f"Batch {batch_num + 1} completed. Waiting {session_batch_delay}s before next batch...")
                await asyncio.sleep(session_batch_delay)
    else:
        # No batching - create all sessions at once (original behavior)
        for config in session_configs:
            user_index = config['user_index']
            user = config['user']
            username = config['username']
            user_questions = config['user_questions']
            session_id = config['session_id']
            session_idx = config['session_idx']
            user_task_counts[user_index] = 0
            
            # #region agent log
            debug_log("H2", f"stress_test:{2493}", "Processing user in task creation", {
                "user_index": user_index,
                "username": username,
                "sessions_per_user": sessions_per_user,
                "tasks_created_so_far": len(tasks)
            })
            # #endregion
            
            # #region agent log
            debug_log("H1", f"stress_test:{2969}", "Task creation start - H1: Browser context limit", {
                "session_id": session_id,
                "user_index": user_index,
                "session_idx": session_idx,
                "task_number": len(tasks),
                "total_tasks_so_far": len(tasks),
                "username": username,
                "user_tasks_created": user_task_counts[user_index],
                "total_users": len(users),
                "current_user_number": user_index + 1
            }, session_id=session_id)
            # #endregion
            
            logging.info(f"Creating session: {session_id} for user {username} "
                        f"(Session {session_idx+1} of {sessions_per_user} for this user)")
            
            task = run_session_with_context(
                browser, 
                user, 
                session_id, 
                questions=user_questions,
                handle_both_courses=handle_both_courses,
                semaphore=context_semaphore
            )
            tasks.append(task)
            task_creation_order.append(session_id)
            user_task_counts[user_index] += 1
            
            # Add delay between session setups to stagger creation
            if session_setup_delay > 0:
                # Don't delay after the last session
                is_last_session = config == session_configs[-1]
                if not is_last_session:
                    await asyncio.sleep(session_setup_delay)
                    logging.debug(f"Session setup delay: waited {session_setup_delay}s before creating next session")
    
    # #region agent log
    debug_log("H1", f"stress_test:{3015}", "Task creation completed - H1: Browser context limit", {
        "total_tasks_created": len(tasks),
        "user_task_counts": user_task_counts,
        "expected_total": len(users) * sessions_per_user,
        "max_concurrent_contexts": max_contexts,
        "semaphore_limit": semaphore_limit,
        "total_concurrent_sessions": total_concurrent_sessions
    })
    # #endregion
    
    if not tasks:
        logging.info("No sessions to create, exiting...")
        return
    
    # Run all sessions concurrently (each opens its own browser window and asks all questions)
    logging.info(f"\nStarting {len(tasks)} concurrent sessions - all questions will be asked concurrently...")
    
    # #region agent log
    debug_log("H3", f"stress_test:{2298}", "About to start asyncio.gather", {
        "total_tasks": len(tasks),
        "task_order": task_creation_order.copy(),
        "semaphore_limit": semaphore_limit,
        "semaphore_available": context_semaphore._value if hasattr(context_semaphore, '_value') else 'unknown'
    })
    # #endregion
    
    if continuous_mode:
        if continuous_iterations:
            logging.info(f"Continuous mode: Each session will loop through questions {continuous_iterations} times")
        else:
            logging.info(f"Continuous mode: Each session will loop through questions indefinitely")
        logging.info(f"All conversations will be maintained concurrently across all {total_concurrent_sessions} windows")
    if handle_both_courses:
        logging.info(f"Each browser window will open BOTH Course 1 and Course 2 tabs")
        logging.info(f"Questions will be distributed between courses and asked concurrently")
    if not continuous_mode:
        logging.info(f"Each session will ask all its questions sequentially within its own browser window")
    
    gather_start_time = time.time()
    
    # #region agent log
    debug_log("H4", f"stress_test:{2559}", "asyncio.gather starting execution", {
        "total_tasks": len(tasks),
        "task_creation_order": task_creation_order.copy(),
        "user_task_counts": user_task_counts,
        "semaphore_limit": semaphore_limit,
        "semaphore_available": context_semaphore._value if hasattr(context_semaphore, '_value') else 'unknown'
    })
    # #endregion
    
    # Create tasks immediately to ensure true parallelism - all users start simultaneously
    # This ensures all users (including users 3-5) run in parallel without blocking
    task_objects = [asyncio.create_task(task) for task in tasks]
    results = await asyncio.gather(*task_objects, return_exceptions=True)
    gather_end_time = time.time()
    
    # Analyze which users actually executed
    user_execution_status = {}
    for i, result in enumerate(results):
        if i < len(task_creation_order):
            session_id = task_creation_order[i]
            try:
                user_part = session_id.split("_")[0]  # "User1", "User2", etc.
                user_idx = int(user_part.replace("User", "")) - 1
                if user_idx not in user_execution_status:
                    user_execution_status[user_idx] = {"success": 0, "failed": 0, "exceptions": 0}
                if isinstance(result, Exception):
                    user_execution_status[user_idx]["exceptions"] += 1
                elif isinstance(result, dict):
                    if result.get('success', False):
                        user_execution_status[user_idx]["success"] += 1
                    else:
                        user_execution_status[user_idx]["failed"] += 1
                else:
                    user_execution_status[user_idx]["success"] += 1
            except:
                pass
    
    # #region agent log
    debug_log("H3", f"stress_test:{2310}", "asyncio.gather completed", {
        "total_tasks": len(tasks),
        "gather_duration_ms": (gather_end_time - gather_start_time) * 1000,
        "results_count": len(results),
        "user_execution_status": user_execution_status
    })
    # #endregion
    
    # Track results
    successful_sessions = 0
    failed_sessions = 0
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            failed_sessions += 1
            logging.error(f"Session {i+1} failed with exception: {result}")
        elif isinstance(result, dict):
            if result.get('success', False):
                successful_sessions += 1
            else:
                failed_sessions += 1
                logging.error(f"Session {result.get('session_id', i+1)} failed: {result.get('error', 'Unknown error')}")
        else:
            # Assume success if no exception and not a dict
            successful_sessions += 1
    
    total_stress_test_time = (time.time() - stress_test_start) * 1000
    
    # Collect unique users from session results
    users_processed = set()
    for result in results:
        if isinstance(result, dict):
            session_id = result.get('session_id', '')
            # Extract username from session_id (format: User1_Session1_username@domain.com)
            if session_id:
                parts = session_id.split('_')
                if len(parts) >= 3:
                    username = '_'.join(parts[2:])
                    users_processed.add(username)
    
    # Print comprehensive stress test summary
    logging.info("\n" + "=" * 80)
    logging.info("STRESS TEST SUMMARY")
    logging.info("=" * 80)
    logging.info(f"Total Users Configured: {len(users)}")
    logging.info(f"Users Actually Processed: {len(users_processed)}")
    if users_processed:
        logging.info(f"Users List:")
        for username in sorted(users_processed):
            logging.info(f"  - {username}")
    if len(users_processed) < len(users):
        missing_users = set(u.get('username', 'Unknown') for u in users) - users_processed
        if missing_users:
            logging.warning(f"⚠️  Warning: {len(missing_users)} user(s) were not processed:")
            for username in sorted(missing_users):
                logging.warning(f"  - {username}")
    logging.info(f"Sessions per User: {sessions_per_user}")
    logging.info(f"Total Sessions Executed: {len(tasks)}")
    logging.info(f"Total Successful Sessions: {successful_sessions}")
    logging.info(f"Total Failed Sessions: {failed_sessions}")
    if successful_sessions + failed_sessions > 0:
        logging.info(f"Success Rate: {(successful_sessions / (successful_sessions + failed_sessions) * 100):.2f}%")
    logging.info(f"Total Stress Test Time: {total_stress_test_time:.2f}ms ({total_stress_test_time/1000:.2f}s)")
    logging.info("=" * 80)
    
    # Write CSV reports
    logging.info("\n" + "=" * 80)
    logging.info("WRITING CSV REPORTS")
    logging.info("=" * 80)
    logging.info(f"Current working directory: {os.getcwd()}")
    logging.info(f"Log file location: {os.path.abspath(LOG_FILENAME) if LOG_FILENAME else 'Not set'}")
    
    write_csv_report()
    write_session_logs_csv()
    
    logging.info("=" * 80)
    logging.info("CSV REPORT GENERATION COMPLETE")
    logging.info("=" * 80)
    
    # List all generated files
    cwd = os.getcwd()
    csv_files = [f for f in os.listdir(cwd) if f.endswith('.csv') and ('stress_test' in f or 'session_logs' in f)]
    log_files = [f for f in os.listdir(cwd) if f.endswith('.log') and 'stress_test' in f]
    
    if csv_files:
        logging.info(f"\n📁 Generated CSV files ({len(csv_files)}):")
        for csv_file in sorted(csv_files):
            file_path = os.path.join(cwd, csv_file)
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                logging.info(f"   ✓ {csv_file} ({file_size:,} bytes) - {os.path.abspath(file_path)}")
            else:
                logging.warning(f"   ✗ {csv_file} - FILE NOT FOUND")
    else:
        logging.warning("⚠️  No CSV files found in current directory!")
    
    if log_files:
        logging.info(f"\n📁 Generated log files ({len(log_files)}):")
        for log_file in sorted(log_files):
            file_path = os.path.join(cwd, log_file)
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                logging.info(f"   ✓ {log_file} ({file_size:,} bytes) - {os.path.abspath(file_path)}")
            else:
                logging.warning(f"   ✗ {log_file} - FILE NOT FOUND")

async def main():
    """Main function."""
    
    async with async_playwright() as p:
        # Create browser
        browser = await p.chromium.launch(
            headless=True,
            args=['--start-maximized']
        )
        
        logging.info("Browser started")
        
        if STRESS_TEST_CONFIG['enabled']:
            # Run stress test - each iteration asks one question from each user concurrently
            logging.info("=" * 80)
            logging.info("STRESS TEST MODE ENABLED")
            logging.info("=" * 80)
            await stress_test(browser=browser, users=USERS)
        else:
            # Run all users concurrently (normal mode) - each user asks all their questions
            logging.info("Running in normal mode (concurrent users)")
            logging.info(f"Processing {len(USERS)} users concurrently...")
            
            # Get handle_both_courses from config
            handle_both_courses = STRESS_TEST_CONFIG.get('handle_both_courses', True)
            
            # Create tasks for all users - each user asks all their questions
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
                # Run all user sessions concurrently
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Track results
                successful_users = 0
                failed_users = 0
                for j, result in enumerate(results):
                    if isinstance(result, Exception):
                        failed_users += 1
                        logging.error(f"User session failed with exception: {result}")
                    elif isinstance(result, dict):
                        if result.get('success', False):
                            successful_users += 1
                        else:
                            failed_users += 1
                            logging.error(f"User session failed: {result.get('error', 'Unknown error')}")
                    else:
                        successful_users += 1
                
                logging.info(f"All sessions completed: {successful_users} successful, {failed_users} failed")
            
            logging.info("All sessions completed")
        
        logging.info("Waiting before closing browser...")
        await asyncio.sleep(5)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
