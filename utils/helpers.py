"""
Helper utility functions for the Playwright stress test application.
"""
import asyncio
import random
import logging
from config import course_1_questions, course_2_questions, general_questions


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