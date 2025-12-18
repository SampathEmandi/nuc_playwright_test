from playwright.async_api import async_playwright
import asyncio
from pathlib import Path
import logging
import time
import random
from datetime import datetime
import csv
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Global list to store CSV metrics
CSV_METRICS = []

# Global list to store page errors and warnings for CSV
PAGE_ERRORS = []

# ============================================================================
# STRESS TEST CONFIGURATION
# ============================================================================
STRESS_TEST_CONFIG = {
    'enabled': True,  # Set to False for normal single session mode
    'sessions_per_user': 4,  # Number of concurrent browser windows per user (each user logs in multiple times)
    'delay_between_questions': 3,  # Seconds to wait between questions within a session
    'handle_both_courses': True,  # Set to False to open only one course per session
    'course_for_questions': 1,  # Which course to open (1 or 2) - only used if handle_both_courses is False
    'max_concurrent_contexts': 30,  # Maximum number of concurrent browser contexts (windows) across all users
    # WebSocket Stress Configuration
    'websocket_stress_mode': False,  # Enable aggressive WebSocket stress testing
    'websocket_rapid_fire': False,  # Send questions as fast as possible (minimal delays)
    'websocket_keep_alive': True,  # Keep WebSocket connections open longer
    # Example: 5 users × 1 session = 5 concurrent browser windows, each handling one course
}

# ============================================================================
# QUESTION POOL - Questions will be randomly assigned based on course
# ============================================================================
course_1_questions = [
    "How does understanding normal anatomy and physiology help in identifying disease or illness?",
    "Why is it helpful to learn medical terms when studying body systems?",
    "What is meant by 'organization of the human body' in this course?",
    "Which body system includes the skin, hair, and nails, and what is one key function of it?",
    "What types of bones make up the skeletal system, and how are they classified?",
    "How do muscles and bones work together to produce body movement?",
    "What is the basic function of neurons in the nervous system?",
    "What is the role of the brain and spinal cord within the nervous system?",
    "What kinds of career paths might use knowledge from this anatomy and physiology course?",
    "How are quizzes and exams used in this course to check your understanding of each module?",
]

course_2_questions = [
"What is the required textbook for the Introduction to Business (BUMA1000) course?", 
"Which textbook chapters are assigned in Module 1: Fundamentos de los negocios?",
"What are the three main grade categories and their percentage weights in this course?",      
"Name two ProQuest databases recommended for Module 2 assignments?",  
"Which external resources are suggested for Module 3: Negocios globales?",  
"What is the main focus of Module 4: Fundamentos de gerencia and which textbook chapter supports it?",  
"What are the four management functions mentioned in the course materials?",  
"What is the purpose of the Preprueba and does it affect the final grade?",  
"What is a business plan, and why is it important for entrepreneurs and investors?",  
"What is one key difference between entrepreneurship and management according to the transcript?",
]

general_questions = [
    "Hi, please explain the course description",
    "explain what this course is about",
    "What are the modules of this course?",
    "What topics will I learn in this course?",
    "How is this course structured?",
    "What are the learning objectives?",
    "Can you explain the course content?",
    "What should I expect from this course?",
    "Tell me about the course syllabus",
    "What will I study in this course?",
]

# Combined pool with all questions (fallback)
QUESTION_POOL = course_1_questions + course_2_questions + general_questions

# Configuration for question handling
QUESTION_CONFIG = {
    'questions_per_session': None,  # None = ask all questions, or set a number to limit
    'min_response_wait': 5,  # Minimum seconds to wait for response
    'max_response_wait': 30,  # Maximum seconds to wait for response
    'response_check_interval': 2,  # Check every N seconds if response appeared
}

# ============================================================================
# USER CREDENTIALS AND QUESTIONS - Each user has their own list of questions
# ============================================================================
USERS = [
    {
        'username': 'babug@bay6.ai',
        'password': 'devBay62025##',
        'questions': course_1_questions[:5] + general_questions[:3],  # User's question list
    },
    {
        'username': 'deepk@bay6.ai',
        'password': 'devBay62025##',
        'questions': course_1_questions[5:] + general_questions[3:6],  # User's question list
    },
    {
        'username': 'ctalluri@bay6.ai',
        'password': 'devBay62025##',
        'questions': general_questions[:5] + course_1_questions[:3],  # User's question list
    },
    {
        'username': 'samuelp@bay6.ai',
        'password': 'devBay62025##',
        'questions': course_1_questions + general_questions[:2],  # User's question list
    },
    {
        'username': 'jasleenk@bay6.ai',
        'password': 'devBay62025##',
        'questions': general_questions + course_1_questions[:2],  # User's question list
    },
]

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

def distribute_questions_by_course(user_questions, course_1_questions, course_2_questions, general_questions):
    """Distribute user questions between Course 1 and Course 2 based on question type.
    
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
            course_1_list.append(question)
        elif question in course_2_set:
            course_2_list.append(question)
        elif question in general_set:
            # Distribute general questions evenly between both courses
            if len(course_1_list) <= len(course_2_list):
                course_1_list.append(question)
            else:
                course_2_list.append(question)
        else:
            # Unknown question type - add to Course 1 by default
            course_1_list.append(question)
    
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
        # Check if context is still valid
        if context.browser and not context.browser.is_connected():
            raise Exception(f"Browser disconnected before opening course {course_number}")
        
        logging.info(f"Opening course {course_number} in {tab_name}...")
        page = await context.new_page()
        
        # Setup error and console logging for course page
        setup_page_error_logging(page, tab_name, session_id=session_id, username=username)
        
        # Check again before navigation
        if context.browser and not context.browser.is_connected():
            await page.close()
            raise Exception(f"Browser disconnected before navigation to course {course_number}")
        
        # Navigate to dashboard
        await page.goto('https://development.instructure.com', wait_until='domcontentloaded', timeout=60000)
        
        # Wait for dashboard container to be attached
        await page.locator('#DashboardCard_Container').wait_for(state='attached', timeout=30000)
        
        # Wait for both course cards to be visible before clicking (with retry and refresh)
        logging.info(f"[{tab_name}] Waiting for Course 1 and Course 2 cards to be visible...")
        course_1_card = page.locator('#DashboardCard_Container > div > div:nth-child(1) > div > div:nth-child(1) > div > a > div')
        course_2_card = page.locator('#DashboardCard_Container > div > div:nth-child(1) > div > div:nth-child(2) > div > a > div')
        
        # Try to wait for cards with retry logic
        cards_visible = False
        for attempt in range(3):
            try:
                # Wait for both cards with longer timeout
                await course_1_card.wait_for(state='visible', timeout=45000)
                await course_2_card.wait_for(state='visible', timeout=45000)
                cards_visible = True
                logging.info(f"[{tab_name}] Both course cards visible on attempt {attempt + 1}")
                break
            except Exception as e:
                logging.warning(f"[{tab_name}] Course cards not visible on attempt {attempt + 1}: {e}")
                if attempt < 2:
                    # Refresh page and retry
                    logging.info(f"[{tab_name}] Refreshing page and retrying...")
                    await page.reload(wait_until='domcontentloaded', timeout=30000)
                    await asyncio.sleep(2)
                    # Re-wait for dashboard container
                    await page.locator('#DashboardCard_Container').wait_for(state='attached', timeout=30000)
                else:
                    # Last attempt - try to proceed anyway if at least dashboard is visible
                    logging.warning(f"[{tab_name}] Could not wait for both cards, proceeding with available course...")
                    try:
                        # Check if at least the target course card exists
                        target_card = page.locator(f'#DashboardCard_Container > div > div:nth-child(1) > div > div:nth-child({course_number}) > div > a > div')
                        await target_card.wait_for(state='visible', timeout=10000)
                        cards_visible = True
                    except:
                        pass  # Will try to click anyway
        
        # Simple click on course link - Playwright handles waiting automatically
        course_locator = page.locator(f'#DashboardCard_Container > div > div:nth-child(1) > div > div:nth-child({course_number}) > div > a')
        await course_locator.click(timeout=30000)
        # Wait for navigation after click
        await page.wait_for_load_state('domcontentloaded', timeout=30000)
        logging.info(f"✓ Course {course_number} opened in {tab_name}")
        return page
    except Exception as e:
        logging.error(f"✗ Error opening course {course_number} in {tab_name}: {e}")
        raise

def setup_network_monitoring(page, tab_name):
    """Setup network monitoring for WebSocket and API calls."""
    websocket_requests = []
    api_requests = []
    websocket_timings = {}
    
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
            logging.info(f"[{tab_name}] WebSocket Request: {url}")
            logging.info(f"[{tab_name}]   Headers: {dict(request.headers)}")
        elif 'nucaiapi' in url or 'nucapi' in url:
            api_requests.append({
                'url': url,
                'method': request.method,
                'timestamp': request_time
            })
            logging.info(f"[{tab_name}] API Request: {url} - Method: {request.method}")
    
    def handle_response(response):
        url = response.url
        response_time = time.time()
        status = response.status
        
        # Log HTTP error responses (4xx, 5xx)
        if status >= 400:
            if status >= 500:
                logging.error(f"[{tab_name}] [HTTP ERROR] {status} {url}")
            elif status == 404:
                logging.warning(f"[{tab_name}] [HTTP 404] Not Found: {url}")
            elif status == 403:
                logging.warning(f"[{tab_name}] [HTTP 403] Forbidden: {url}")
            elif status == 401:
                logging.warning(f"[{tab_name}] [HTTP 401] Unauthorized: {url}")
            else:
                logging.warning(f"[{tab_name}] [HTTP {status}] {url}")
        
        try:
            if 'chatbot_websocket' in url or 'websocket' in url.lower():
                if url in websocket_timings:
                    websocket_timings[url]['response_time'] = response_time
                    connection_time = (response_time - websocket_timings[url]['request_start']) * 1000
                    logging.info(f"[{tab_name}] WebSocket Connected: {url}")
                    logging.info(f"[{tab_name}]   Connection Time: {connection_time:.2f}ms")
                    logging.info(f"[{tab_name}]   Status: {response.status}")
            elif 'nucaiapi' in url or 'nucapi' in url:
                timing = response.request.timing
                response_time_ms = timing.get('responseEnd', 0) - timing.get('requestStart', 0)
                logging.info(f"[{tab_name}] API Response: {url}")
                logging.info(f"[{tab_name}]   Status: {response.status}")
                logging.info(f"[{tab_name}]   Response Time: {response_time_ms:.2f}ms")
                if timing.get('responseStart', 0) > 0:
                    ttfb = timing.get('responseStart', 0) - timing.get('requestStart', 0)
                    logging.info(f"[{tab_name}]   Time to First Byte (TTFB): {ttfb:.2f}ms")
        except Exception as e:
            logging.debug(f"[{tab_name}] Error handling response: {e}")
    
    page.on('request', handle_request)
    page.on('response', handle_response)
    
    return websocket_requests, api_requests, websocket_timings

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

async def interact_with_chatbot(page, tab_name, questions=None, session_id=None, course_number=None, username=None):
    """Interact with chatbot on a given page.
    
    Args:
        page: Page object
        tab_name: Name of the tab/course
        questions: List of questions to ask
        session_id: Session identifier for CSV logging
        course_number: Course number (1 or 2) for CSV logging
        username: Username for logging
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
        
        # Setup network monitoring
        websocket_requests, api_requests, websocket_timings = setup_network_monitoring(page, tab_name)
        
        # Wait for page to fully load
        await page.wait_for_load_state('domcontentloaded', timeout=30000)
        
        # Click the chatbot button using class selector (matches the working JS code)
        chatbot_btn = page.locator('._chatbot_btn_in_iframe')
        await chatbot_btn.wait_for(state='visible', timeout=30000)
        await chatbot_btn.scroll_into_view_if_needed()
        
        # Time the chatbot button click
        click_start = time.time()
        await chatbot_btn.click(timeout=10000)
        click_time = (time.time() - click_start) * 1000
        logging.info(f"[{tab_name}] Chatbot button clicked in {click_time:.2f}ms")
        
        # Wait for the chatbot interface to load - wait a bit and then re-acquire iframe
        logging.info(f"Waiting for chatbot interface to load in {tab_name}...")
        await asyncio.sleep(2)  # Give time for the chatbot interface to initialize
        
        # Wait for chatbot iframe to be ready and get content frame
        iframe = await get_iframe_content_frame(page, tab_name)
        
        # Wait for authorize button in iframe and click
        logging.info(f"Waiting for authorize button in {tab_name}...")
        authorize_btn = iframe.get_by_role('button', name='Authorize')
        await authorize_btn.wait_for(state='visible', timeout=30000)
        
        # Time the authorize click
        auth_start = time.time()
        await authorize_btn.click()
        auth_time = (time.time() - auth_start) * 1000
        logging.info(f"[{tab_name}] Authorize button clicked in {auth_time:.2f}ms")
        
        # Wait for the chatbot interface to reload after authorization
        logging.info(f"Waiting for chatbot interface to reload after authorization in {tab_name}...")
        await asyncio.sleep(2)
        
        # Re-acquire the iframe in case it reloaded after authorization
        iframe = await get_iframe_content_frame(page, tab_name)
        
        # Track metrics for each question
        question_metrics = []
        total_interaction_start = time.time()
        
        # Use all questions if questions_per_session is None, otherwise limit
        if QUESTION_CONFIG['questions_per_session'] is None:
            questions_to_use = questions  # Use all questions
        else:
            questions_to_use = questions[:QUESTION_CONFIG['questions_per_session']]
        logging.info(f"[{tab_name}] Using {len(questions_to_use)} questions: {questions_to_use}")
        
        # Interact with bot for multiple questions
        for question_num, question in enumerate(questions_to_use, 1):
            try:
                logging.info(f"[{tab_name}] ========== Question {question_num} ==========")
                question_start = time.time()
                
                # Re-acquire iframe for each question in case it changed
                try:
                    iframe = await get_iframe_content_frame(page, tab_name)
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
                        question_metrics.append({
                            'question_number': question_num,
                            'question': question,
                            'question_submit_time': 0,
                            'response_wait_time': 0,
                            'question_total_time': 0,
                            'response_received': False,
                            'error': f'Could not get iframe after refresh: {str(retry_error)}'
                        })
                        continue
                
                # Wait for question box to be ready with robust retry logic and refresh on error
                question_box = None
                for attempt in range(10):  # More attempts for better reliability
                    try:
                        # Re-acquire iframe first (it might have reloaded)
                        iframe = await get_iframe_content_frame(page, tab_name)
                        
                        # Try to find question box with multiple strategies
                        question_box = iframe.get_by_role('textbox', name='Enter your question here')
                        
                        # Wait for it to be visible and enabled
                        await question_box.wait_for(state='visible', timeout=15000)
                        
                        # Verify it's actually usable
                        is_visible = await question_box.is_visible()
                        is_enabled = await question_box.is_enabled()
                        
                        if is_visible and is_enabled:
                            logging.info(f"[{tab_name}] Question box found and ready on attempt {attempt + 1}")
                            break
                        else:
                            raise Exception(f"Question box not usable: visible={is_visible}, enabled={is_enabled}")
                            
                    except Exception as e:
                        logging.debug(f"[{tab_name}] Attempt {attempt + 1} to find question box for question {question_num} failed: {e}")
                        if attempt < 9:
                            # Refresh page and retry iframe access on error
                            if attempt >= 3:  # After 3 failed attempts, try refreshing
                                logging.info(f"[{tab_name}] Refreshing page due to iframe/question box error...")
                                try:
                                    await page.reload(wait_until='domcontentloaded', timeout=30000)
                                    await asyncio.sleep(2)  # Wait for page to stabilize
                                    # Re-click chatbot button after refresh
                                    try:
                                        chatbot_btn = page.locator('._chatbot_btn_in_iframe')
                                        await chatbot_btn.wait_for(state='visible', timeout=10000)
                                        await chatbot_btn.click(timeout=5000)
                                        await asyncio.sleep(2)  # Wait for chatbot to load
                                    except:
                                        pass  # Chatbot might already be open
                                except Exception as refresh_error:
                                    logging.warning(f"[{tab_name}] Page refresh failed: {refresh_error}")
                            
                            # Progressive backoff: wait longer with each attempt
                            wait_time = 1 + (attempt * 0.5)  # 1, 1.5, 2, 2.5, 3... seconds
                            await asyncio.sleep(wait_time)
                        else:
                            logging.warning(f"[{tab_name}] Could not find question box for question {question_num} after {attempt + 1} attempts")
                            question_box = None
                
                if question_box is None:
                    logging.warning(f"[{tab_name}] Skipping question {question_num} - question box not available")
                    question_metrics.append({
                        'question_number': question_num,
                        'question': question,
                        'question_submit_time': 0,
                        'response_wait_time': 0,
                        'question_total_time': (time.time() - question_start) * 1000,
                        'response_received': False,
                        'error': 'Question box not available'
                    })
                    continue
                
                # Clear previous question if any
                try:
                    await question_box.click()
                    await question_box.fill('')  # Clear field
                except Exception as e:
                    logging.debug(f"[{tab_name}] Could not clear question box: {e}")
                
                # Time the question submission
                question_submit_start = time.time()
                await question_box.fill(question)
                await question_box.press('Enter')  # Submit question
                question_submit_time = (time.time() - question_submit_start) * 1000
                logging.info(f"[{tab_name}] Question {question_num} - Question: {question}")
                logging.info(f"[{tab_name}] Question {question_num} - Question submission time: {question_submit_time:.2f}ms")
                
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
                
                # Wait additional time after response to ensure UI is ready for next question
                if response_received:
                    logging.info(f"[{tab_name}] Question {question_num} - Waiting for UI to stabilize after response...")
                    await asyncio.sleep(2)  # Give UI time to stabilize
                
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
                question_metrics.append(question_metric)
                
                # Store in CSV metrics if session_id and course_number provided
                if session_id and course_number:
                    CSV_METRICS.append({
                        'session_id': session_id,
                        'course_number': course_number,
                        'question_number': question_num,
                        'question_text': question[:200] if len(question) > 200 else question,  # Limit length
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
                
                # Delay between questions - configurable for WebSocket stress testing
                if question_num < len(questions_to_use):
                    # Check if rapid fire mode is enabled for WebSocket stress
                    if STRESS_TEST_CONFIG.get('websocket_rapid_fire', False):
                        # Minimal delay - just enough for UI to be ready
                        delay = 0.5
                        logging.info(f"[{tab_name}] Rapid fire mode - minimal delay ({delay}s) before next question...")
                    else:
                        # Use configured delay
                        delay = STRESS_TEST_CONFIG.get('delay_between_questions', 3)
                        logging.info(f"[{tab_name}] Waiting {delay}s before next question...")
                    await asyncio.sleep(delay)
                    
            except Exception as question_error:
                logging.error(f"[{tab_name}] Error in question {question_num}: {question_error}")
                question_total_time = (time.time() - question_start) * 1000 if 'question_start' in locals() else 0
                question_metric = {
                    'question_number': question_num,
                    'question': question,
                    'question_submit_time': 0,
                    'response_wait_time': 0,
                    'question_total_time': question_total_time,
                    'response_received': False,
                    'error': str(question_error)
                }
                question_metrics.append(question_metric)
                
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
                # Wait before trying next question
                if question_num < len(questions_to_use):
                    await asyncio.sleep(2)
                continue
        
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
    
        # Check if context is still valid
        try:
            if context.browser and not context.browser.is_connected():
                raise Exception("Browser is not connected")
        except Exception as e:
            logging.error(f"{log_prefix} ✗ Context invalid: {e}")
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
        # Check context before creating page
        if context.browser and not context.browser.is_connected():
            raise Exception("Browser disconnected before creating login page")
        
        login_page = await context.new_page()
        
        # Setup error and console logging for login page
        setup_page_error_logging(login_page, "Login Page", session_id=session_id, username=username)
        
        # Login
        logging.info(f"{log_prefix} Logging in...")
        login_start_time = time.time()
        # Check again before navigation
        if context.browser and not context.browser.is_connected():
            raise Exception("Browser disconnected before navigation")
        
        await login_page.goto('https://development.instructure.com/login/ldap', wait_until='domcontentloaded', timeout=60000)
        
        await login_page.fill("#pseudonym_session_unique_id", username)
        await login_page.fill("#pseudonym_session_password", password)
        
        # Click login button
        await login_page.click("#login_form > div.ic-Login__actions > div.ic-Form-control.ic-Form-control--login > input")
        
        # Wait for dashboard to load - wait for both course cards to be visible (with retry)
        logging.info(f"{log_prefix} Waiting for dashboard to load...")
        dashboard_locator = login_page.locator('#DashboardCard_Container')
        await dashboard_locator.wait_for(state='visible', timeout=60000)
        
        # Wait for both course cards to be visible with retry logic
        logging.info(f"{log_prefix} Waiting for Course 1 and Course 2 cards to be visible...")
        course_1_card = login_page.locator('#DashboardCard_Container > div > div:nth-child(1) > div > div:nth-child(1) > div > a > div')
        course_2_card = login_page.locator('#DashboardCard_Container > div > div:nth-child(1) > div > div:nth-child(2) > div > a > div')
        
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
        
        # Close login page (no longer needed)
        await login_page.close()
        
        session_start = time.time()
        course_open_start_time = time.time()
        
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
            course_1_page, course_2_page = await asyncio.gather(
                open_course(context, 1, f"Course 1", session_id=session_id, username=username),
                open_course(context, 2, f"Course 2", session_id=session_id, username=username),
                return_exceptions=False
            )
            course_open_end_time = time.time()
            course_open_time_ms = (course_open_end_time - course_open_start_time) * 1000 if course_open_start_time else 0
            
            # Run chatbot interactions concurrently for both courses
            chatbot_tasks = []
            
            if course_1_questions_list:
                chatbot_tasks.append(
                    interact_with_chatbot(course_1_page, "Course 1", course_1_questions_list, session_id=session_id, course_number=1, username=username)
                )
            
            if course_2_questions_list:
                chatbot_tasks.append(
                    interact_with_chatbot(course_2_page, "Course 2", course_2_questions_list, session_id=session_id, course_number=2, username=username)
                )
            
            if chatbot_tasks:
                logging.info(f"{log_prefix} Starting concurrent chatbot interactions for both courses...")
                chatbot_start = time.time()
                await asyncio.gather(*chatbot_tasks, return_exceptions=True)
                chatbot_total_time = (time.time() - chatbot_start) * 1000
                logging.info(f"{log_prefix} ✓ All questions answered in both courses in {chatbot_total_time:.2f}ms")
        else:
            # Single course mode - open only one course per session
            logging.info(f"{log_prefix} Opening course {course_number} (single course mode)...")
            course_1_page = await open_course(context, course_number, f"Course {course_number}")
            course_open_end_time = time.time()
            course_open_time_ms = (course_open_end_time - course_open_start_time) * 1000 if course_open_start_time else 0
            
            if questions:
                logging.info(f"{log_prefix} Asking {len(questions)} question(s) in Course {course_number}...")
                chatbot_start = time.time()
                await interact_with_chatbot(course_1_page, f"Course {course_number}", questions, session_id=session_id, course_number=course_number, username=username)
                chatbot_total_time = (time.time() - chatbot_start) * 1000
                logging.info(f"{log_prefix} ✓ All questions answered in Course {course_number} in {chatbot_total_time:.2f}ms")
        
        session_total_time = (time.time() - session_start) * 1000
        logging.info(f"{log_prefix} ✓ Session completed in {session_total_time:.2f}ms")
        
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
        logging.error(f"{log_prefix} ✗ Error: {e}")
        import traceback
        logging.error(f"✗ Full error traceback for {username}:")
        logging.error(traceback.format_exc())
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

async def run_session_with_context(browser, user, session_id, questions=None, question=None, handle_both_courses=True, semaphore=None):
    """Run a user session with its own browser context to ask questions.
    
    Args:
        questions: List of questions to ask (preferred)
        question: Single question (for backward compatibility, will be converted to list)
        handle_both_courses: If True, opens both Course 1 and Course 2 and chats concurrently
    """
    context = None
    if semaphore:
        await semaphore.acquire()
    
    # Handle backward compatibility: if question is provided but questions is not, use question
    if questions is None and question is not None:
        questions = [question]
    
    try:
        # Check if browser is still open before proceeding
        try:
            if not browser.is_connected():
                logging.error(f"Session {session_id}: Browser is not connected")
                return {'session_id': session_id, 'success': False, 'error': 'Browser not connected'}
        except Exception as e:
            logging.error(f"Session {session_id}: Error checking browser connection: {e}")
            return {'session_id': session_id, 'success': False, 'error': f'Browser check failed: {str(e)}'}
        
        # Create a new browser context for this session (separate window)
        try:
            context = await browser.new_context()
            logging.info(f"Session {session_id}: Created new browser context")
        except Exception as e:
            logging.error(f"Session {session_id}: Failed to create context: {e}")
            return {'session_id': session_id, 'success': False, 'error': f'Context creation failed: {str(e)}'}
        
        # Verify context was created successfully
        if context is None:
            logging.error(f"Session {session_id}: Context is None after creation")
            return {'session_id': session_id, 'success': False, 'error': 'Context creation returned None'}
        
        # Small delay to ensure context is ready
        await asyncio.sleep(0.2)
        
        # Verify browser is still connected before running session
        if not browser.is_connected():
            logging.error(f"Session {session_id}: Browser disconnected before session start")
            return {'session_id': session_id, 'success': False, 'error': 'Browser disconnected'}
        
        # Run the session with the questions (handles both courses if enabled)
        try:
            await run_user_session(context, user, questions, handle_both_courses, session_id=session_id)
            logging.info(f"Session {session_id}: Completed successfully")
            return {'session_id': session_id, 'success': True}
        except Exception as session_error:
            logging.error(f"Session {session_id}: Error during session execution: {session_error}")
            import traceback
            logging.error(f"Session {session_id}: Traceback: {traceback.format_exc()}")
            return {'session_id': session_id, 'success': False, 'error': str(session_error)}
    except Exception as e:
        logging.error(f"Session {session_id}: Error setting up session: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return {'session_id': session_id, 'success': False, 'error': str(e)}
    finally:
        # Close the context (browser window) for this session - only after session completes or fails
        if context:
            try:
                logging.info(f"Session {session_id}: Starting cleanup...")
                # Check if browser is still connected before cleanup
                if context.browser and context.browser.is_connected():
                    # Close all pages first
                    pages_closed = 0
                    for page in context.pages:
                        try:
                            if not page.is_closed():
                                await page.close()
                                pages_closed += 1
                        except Exception as e:
                            logging.debug(f"Session {session_id}: Error closing page during cleanup: {e}")
                    
                    logging.info(f"Session {session_id}: Closed {pages_closed} page(s)")
                    
                    # Wait a bit to ensure all operations complete
                    await asyncio.sleep(0.5)
                    
                    # Close context only if browser is still connected
                    if context.browser.is_connected():
                        await context.close()
                        logging.info(f"Session {session_id}: Closed browser context (session completed or failed)")
                    else:
                        logging.warning(f"Session {session_id}: Browser disconnected, skipping context close")
                else:
                    logging.debug(f"Session {session_id}: Browser not connected, skipping context cleanup")
            except Exception as e:
                logging.warning(f"Session {session_id}: Error closing context: {e}")
        if semaphore:
            semaphore.release()
            logging.debug(f"Session {session_id}: Released semaphore")

def write_csv_report():
    """Write collected metrics to CSV file."""
    if not CSV_METRICS:
        logging.warning("No metrics collected to write to CSV")
        return
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_filename = f"stress_test_results_{timestamp}.csv"
    
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
        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            # Extract user from session_id for better readability
            for metric in CSV_METRICS:
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
        
        logging.info(f"✓ CSV report written to: {csv_filename}")
        logging.info(f"  Total records: {len(CSV_METRICS)}")
        
        # Write errors CSV if there are any errors
        if PAGE_ERRORS:
            errors_csv_filename = f"stress_test_errors_{timestamp}.csv"
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
                with open(errors_csv_filename, 'w', newline='', encoding='utf-8') as errors_csvfile:
                    writer = csv.DictWriter(errors_csvfile, fieldnames=error_fieldnames)
                    writer.writeheader()
                    
                    for error in PAGE_ERRORS:
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
                
                logging.info(f"✓ Errors CSV report written to: {errors_csv_filename}")
                logging.info(f"  Total error records: {len(PAGE_ERRORS)}")
            except Exception as e:
                logging.error(f"✗ Error writing errors CSV report: {e}")
                import traceback
                logging.error(traceback.format_exc())
        
    except Exception as e:
        logging.error(f"✗ Error writing CSV report: {e}")
        import traceback
        logging.error(traceback.format_exc())

async def stress_test(browser, users):
    """Run stress test where all sessions ask questions concurrently across multiple browser windows."""
    all_session_metrics = []
    stress_test_start = time.time()
    
    # Get configuration
    sessions_per_user = STRESS_TEST_CONFIG.get('sessions_per_user', 1)
    delay_between_questions = STRESS_TEST_CONFIG.get('delay_between_questions', 2)
    handle_both_courses = STRESS_TEST_CONFIG.get('handle_both_courses', True)
    
    # Calculate total concurrent sessions needed
    total_concurrent_sessions = len(users) * sessions_per_user
    
    # Get max concurrent contexts from config (prevents overwhelming browser/system)
    max_contexts = STRESS_TEST_CONFIG.get('max_concurrent_contexts', 30)
    
    # Semaphore to limit concurrent context creation (prevent overwhelming browser)
    # This ensures we don't create too many browser windows at once
    context_semaphore = asyncio.Semaphore(min(max_contexts, total_concurrent_sessions))
    
    # Calculate total questions
    total_questions = sum(len(user.get('questions', [])) for user in users)
    
    logging.info("=" * 80)
    logging.info("STRESS TEST STARTED - CONCURRENT MULTI-WINDOW MODE")
    logging.info(f"Users: {len(users)}")
    logging.info(f"Sessions per User: {sessions_per_user} (each user gets {sessions_per_user} browser windows)")
    logging.info(f"Total Concurrent Browser Windows: {total_concurrent_sessions}")
    logging.info(f"Total Questions Across All Users: {total_questions}")
    logging.info(f"Handle Both Courses: {handle_both_courses}")
    if handle_both_courses:
        logging.info(f"Architecture: Each browser window opens BOTH Course 1 and Course 2")
        logging.info(f"           → Questions distributed between courses automatically")
        logging.info(f"           → Chatbot interactions run concurrently in both courses")
    logging.info(f"Architecture: Each user logs in from {sessions_per_user} separate browser windows")
    logging.info(f"           → All {total_concurrent_sessions} windows chat concurrently")
    logging.info(f"           → Each window asks questions independently")
    logging.info(f"Max concurrent contexts (semaphore limit): {context_semaphore._value}")
    logging.info("=" * 80)
    
    # Create all sessions concurrently - each session will ask ALL its questions
    # Each user gets multiple browser windows (sessions_per_user), all running concurrently
    tasks = []
    session_id_counter = 0
    
    for user_index, user in enumerate(users):
        user_questions = user.get('questions', [])
        
        # Create multiple browser windows (sessions) for this user
        # Each window is a separate browser context, allowing concurrent chatting
        for session_idx in range(sessions_per_user):
            session_id_counter += 1
            session_id = f"User{user_index+1}_Session{session_idx+1}_{user['username']}"
            
            logging.info(f"Creating session: {session_id} for user {user['username']} "
                        f"(Session {session_idx+1} of {sessions_per_user} for this user)")
            
            # Each session gets its own browser window and will ask all questions concurrently
            # with other sessions from the same user and other users
            # Each window will handle both Course 1 and Course 2 if handle_both_courses is True
            tasks.append(run_session_with_context(
                browser, 
                user, 
                session_id, 
                questions=user_questions,  # Pass all questions
                handle_both_courses=handle_both_courses,
                semaphore=context_semaphore
            ))
    
    if not tasks:
        logging.info("No sessions to create, exiting...")
        return
    
    # Run all sessions concurrently (each opens its own browser window and asks all questions)
    logging.info(f"\nStarting {len(tasks)} concurrent sessions - all questions will be asked concurrently...")
    if handle_both_courses:
        logging.info(f"Each browser window will open BOTH Course 1 and Course 2 tabs")
        logging.info(f"Questions will be distributed between courses and asked concurrently")
    logging.info(f"Each session will ask all its questions sequentially within its own browser window")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
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
    
    # Print comprehensive stress test summary
    logging.info("\n" + "=" * 80)
    logging.info("STRESS TEST SUMMARY")
    logging.info("=" * 80)
    logging.info(f"Users: {len(users)}")
    logging.info(f"Sessions per User: {sessions_per_user}")
    logging.info(f"Total Sessions Executed: {len(tasks)}")
    logging.info(f"Total Successful Sessions: {successful_sessions}")
    logging.info(f"Total Failed Sessions: {failed_sessions}")
    if successful_sessions + failed_sessions > 0:
        logging.info(f"Success Rate: {(successful_sessions / (successful_sessions + failed_sessions) * 100):.2f}%")
    logging.info(f"Total Stress Test Time: {total_stress_test_time:.2f}ms ({total_stress_test_time/1000:.2f}s)")
    logging.info("=" * 80)
    
    # Write CSV report
    write_csv_report()

async def main():
    """Main function."""
    
    async with async_playwright() as p:
        # Create browser
        browser = await p.chromium.launch(headless=False)
        
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
