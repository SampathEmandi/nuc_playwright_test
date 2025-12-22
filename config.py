"""
Configuration constants for the Playwright stress test application.
"""

# ============================================================================
# STRESS TEST CONFIGURATION
# ============================================================================
STRESS_TEST_CONFIG = {
    'enabled': True,  # Set to False for normal single session mode
    'sessions_per_user': 10,  # Number of concurrent browser windows per user (each user logs in multiple times) - Can be calculated dynamically
    'delay_between_questions': 3,  # Seconds to wait between questions within a session
    'handle_both_courses': True,  # Set to False to open only one course per session
    # 'course_for_questions': 1,  # Which course to open (1 or 2) - only used if handle_both_courses is False
    'max_concurrent_contexts': 10000,  # Maximum number of concurrent browser contexts (windows) across all users - Can be calculated dynamically
    'dynamic_resource_calculation': True,  # If True, calculate sessions_per_user and max_concurrent_contexts based on available resources
    # WebSocket Stress Configuration
    'websocket_stress_mode': False,  # Enable aggressive WebSocket stress testing
    'websocket_rapid_fire': False,  # Send questions as fast as possible (minimal delays)
    'websocket_keep_alive': True,  # Keep WebSocket connections open longer
    # Continuous Conversation Configuration
    'continuous_mode': True,  # Keep conversations active continuously (loop through questions)
    'continuous_iterations': None,  # Number of question cycles to run (None = infinite until stopped)
    'continuous_cycle_delay': 5,  # Seconds to wait between question cycles (after all questions in cycle are asked)
    'maintain_concurrent': True,  # Maintain all conversations concurrently (don't wait for one to finish)
    'concurrent_questions': True,  # Ask all questions concurrently (rapid-fire mode) for maximum stress
    # CSV Export Configuration
    'incremental_csv_export': True,  # Write CSV logs periodically during execution (not just at end)
    'csv_export_interval': 300,  # Seconds between incremental CSV exports (default: 5 minutes)
    # Network Monitoring Configuration
    'enable_network_monitoring': True,  # Enable network monitoring for all users (WebSocket and API tracking)
    'monitor_all_users': True,  # Monitor network traffic for all users (not just first 1-2)
    # Session Tracking Configuration
    'enable_session_tracking': True,  # Enable concurrent session tracking with periodic reports
    'tracking_report_interval': 300,  # Seconds between periodic tracking reports (default: 5 minutes = 300s)
    # Example: 5 users × 10 sessions = 50 concurrent browser windows, each handling one course
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
        'username': 'ctalluri@bay6.ai',
        'password': 'devBay62025##',
        # All course 1 questions go to course 1, all course 2 to course 2, general to both
        'questions': course_1_questions + course_2_questions + general_questions,
    },
    {
        'username': 'babug@bay6.ai',
        'password': 'devBay62025##',
        # All course 1 questions go to course 1, all course 2 to course 2, general to both
        'questions': course_1_questions + course_2_questions + general_questions,
    },
    {
        'username': 'deepk@bay6.ai',
        'password': 'devBay62025##',
        # All course 1 questions go to course 1, all course 2 to course 2, general to both
        'questions': course_1_questions + course_2_questions + general_questions,
    },
    {
        'username': 'samuelp@bay6.ai',
        'password': 'devBay62025##',
        # All course 1 questions go to course 1, all course 2 to course 2, general to both
        'questions': course_1_questions + course_2_questions + general_questions,
    },
    {
        'username': 'jasleenk@bay6.ai',
        'password': 'devBay62025##',
        # All course 1 questions go to course 1, all course 2 to course 2, general to both
        'questions': course_1_questions + course_2_questions + general_questions,
    },
]