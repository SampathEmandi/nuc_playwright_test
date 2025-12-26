"""
Modular entry point for the Playwright stress test application.

This file imports from the refactored modules and provides the main() function.
"""
from playwright.async_api import async_playwright
import asyncio
import logging

# Import configuration
from config import STRESS_TEST_CONFIG, USERS

# Import utilities
from utils.logging_utils import setup_logging, LOG_FILENAME

# Import session management
from session.session_manager import run_session_with_context

# Import stress test
from stress_test import stress_test


async def main():
    """Main function."""
    
    async with async_playwright() as p:
        # Create browser - NOT headless to ensure all windows are visible for monitoring
        browser = await p.chromium.launch(
            headless=False,  # Always visible for monitoring and debugging
            args=['--start-maximized']  # Start maximized for better visibility
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