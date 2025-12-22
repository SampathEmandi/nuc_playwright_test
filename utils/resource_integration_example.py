"""
Example code showing how to integrate resource calculator into main.py

Copy this code snippet into the stress_test() function in main.py
"""

# ============================================================================
# ADDITION: At the start of stress_test() function in main.py
# ============================================================================
"""
Add this import at the top of main.py (with other imports):
"""

from utils.config_optimizer import update_stress_test_config


# ============================================================================
# ADDITION: In stress_test() function - At the START (after stress_test_start)
# ============================================================================
"""
Add this code right after stress_test_start = time.time() in stress_test():
"""

async def stress_test(browser, users):
    """Run stress test where all sessions ask questions concurrently..."""
    all_session_metrics = []
    stress_test_start = time.time()
    
    # ADD THIS: Calculate optimal configuration based on system resources
    if STRESS_TEST_CONFIG.get('dynamic_resource_calculation', True):
        logging.info("\n" + "=" * 80)
        logging.info("CALCULATING OPTIMAL CONFIGURATION BASED ON SYSTEM RESOURCES")
        logging.info("=" * 80)
        update_stress_test_config(dynamic_mode=True)
        logging.info("=" * 80 + "\n")
    
    # Get configuration (now optimized if dynamic calculation is enabled)
    sessions_per_user = STRESS_TEST_CONFIG.get('sessions_per_user', 10)
    delay_between_questions = STRESS_TEST_CONFIG.get('delay_between_questions', 2)
    handle_both_courses = STRESS_TEST_CONFIG.get('handle_both_courses', True)
    max_contexts = STRESS_TEST_CONFIG.get('max_concurrent_contexts', 10000)
    
    # ... rest of existing code continues as normal ...


# ============================================================================
# ALTERNATIVE: If you want to disable dynamic calculation
# ============================================================================
"""
To disable dynamic calculation and use static values from config.py:
"""

# Option 1: Set in config.py
# STRESS_TEST_CONFIG['dynamic_resource_calculation'] = False

# Option 2: Call with dynamic_mode=False
# update_stress_test_config(dynamic_mode=False)


# ============================================================================
# ALTERNATIVE: If you want to override calculated values
# ============================================================================
"""
To override calculated values (e.g., force specific number of sessions):
"""

# Calculate optimal values, but override sessions_per_user
update_stress_test_config(
    dynamic_mode=True,
    override_sessions_per_user=5  # Force 5 sessions per user regardless of calculation
)

# Or override max_concurrent_contexts
update_stress_test_config(
    dynamic_mode=True,
    override_max_contexts=100  # Force max 100 concurrent contexts
)