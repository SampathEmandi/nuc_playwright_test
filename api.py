"""
FastAPI application for running stress tests as background tasks.
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from playwright.async_api import async_playwright

from config import STRESS_TEST_CONFIG, USERS
from main import stress_test

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# FastAPI app
app = FastAPI(
    title="Playwright Stress Test API",
    description="API for running chatbot stress tests as background tasks",
    version="1.0.0"
)

# In-memory task storage (use Redis or database in production)
task_status: Dict[str, Dict] = {}
task_cancellation: Dict[str, bool] = {}  # Track cancellation requests


# ============================================================================
# Request/Response Models
# ============================================================================

class StressTestConfig(BaseModel):
    """Configuration for stress test."""
    sessions_per_user: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of concurrent browser windows per user (required)"
    )
    handle_both_courses: bool = Field(
        default=True,
        description="If True, opens both Course 1 and Course 2. If False, opens only one course specified by course_for_questions"
    )
    course_for_questions: Optional[int] = Field(
        default=None,
        ge=1,
        le=2,
        description="Which course to open (1 or 2) - only used if handle_both_courses is False. Required if handle_both_courses is False"
    )
    delay_between_questions: Optional[float] = Field(
        default=None,
        ge=0,
        description="Seconds to wait between questions (0 for maximum performance)"
    )
    max_concurrent_contexts: Optional[int] = Field(
        default=None,
        ge=1,
        description="Maximum number of concurrent browser contexts (no upper limit)"
    )
    continuous_mode: Optional[bool] = Field(
        default=None,
        description="Keep conversations active continuously"
    )
    continuous_iterations: Optional[int] = Field(
        default=None,
        ge=1,
        description="Number of question cycles to run. Set to null/None to run until stopped (infinite). Set to a number to run that many cycles."
    )
    concurrent_questions: Optional[bool] = Field(
        default=None,
        description="Ask all questions concurrently within each session"
    )
    websocket_rapid_fire: Optional[bool] = Field(
        default=None,
        description="Send questions as fast as possible (NO delays)"
    )
    session_setup_delay: Optional[float] = Field(
        default=None,
        ge=0,
        description="Seconds to wait between setting up each session (0 = no delay, helps stagger session creation)"
    )
    session_batch_size: Optional[int] = Field(
        default=None,
        ge=1,
        description="Number of sessions to create per batch (None = create all at once, no batching)"
    )
    session_batch_delay: Optional[float] = Field(
        default=None,
        ge=0,
        description="Seconds to wait between batches (0 = no delay between batches)"
    )
    enable_csv_export: Optional[bool] = Field(
        default=None,
        description="Enable/disable CSV file writing (False = no CSV files, useful for local testing)"
    )
    
    @model_validator(mode='after')
    def validate_course_selection(self):
        """Validate that course_for_questions is provided when handle_both_courses is False."""
        if not self.handle_both_courses and self.course_for_questions is None:
            raise ValueError('course_for_questions is required when handle_both_courses is False. Set to 1 or 2.')
        return self


class UserConfig(BaseModel):
    """User configuration."""
    username: str = Field(..., description="User email/username")
    password: str = Field(..., description="User password")
    questions: Optional[List[str]] = Field(
        default=None,
        description="Custom questions for this user (uses default if not provided)"
    )


class StressTestRequest(BaseModel):
    """Request model for starting a stress test."""
    users: Optional[List[UserConfig]] = Field(
        default=None,
        description="Custom user list (uses config.py users if not provided)"
    )
    config: Optional[StressTestConfig] = Field(
        default=None,
        description="Stress test configuration overrides"
    )


class TaskStatusResponse(BaseModel):
    """Response model for task status."""
    task_id: str
    status: str  # "pending", "running", "completed", "failed"
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None


# ============================================================================
# Background Task Functions
# ============================================================================

async def run_stress_test_task(
    task_id: str,
    users: List[Dict],
    config_overrides: Optional[Dict] = None
):
    """Run stress test as a background task."""
    try:
        # Update task status
        task_status[task_id]["status"] = "running"
        task_status[task_id]["started_at"] = datetime.now().isoformat()
        task_status[task_id]["message"] = "Stress test started"
        
        # Check if task was cancelled before starting
        if task_cancellation.get(task_id, False):
            task_status[task_id]["status"] = "cancelled"
            task_status[task_id]["completed_at"] = datetime.now().isoformat()
            task_status[task_id]["message"] = "Task cancelled before starting"
            logging.info(f"[Task {task_id}] Task cancelled before starting")
            return
        
        # Apply configuration overrides
        if config_overrides:
            for key, value in config_overrides.items():
                if value is not None:
                    STRESS_TEST_CONFIG[key] = value
                    logging.info(f"[Task {task_id}] Applied config override: {key} = {value}")
        
        # Log continuous_iterations behavior
        continuous_iterations = STRESS_TEST_CONFIG.get('continuous_iterations')
        if continuous_iterations is None:
            logging.info(f"[Task {task_id}] Continuous mode: Will run until stopped (infinite iterations)")
        else:
            logging.info(f"[Task {task_id}] Continuous mode: Will run {continuous_iterations} cycles")
        
        # Launch browser and run stress test
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--start-maximized']
            )
            
            logging.info(f"[Task {task_id}] Browser started")
            
            try:
                # Check for cancellation before starting
                if task_cancellation.get(task_id, False):
                    task_status[task_id]["status"] = "cancelled"
                    task_status[task_id]["completed_at"] = datetime.now().isoformat()
                    task_status[task_id]["message"] = "Task cancelled"
                    logging.info(f"[Task {task_id}] Task cancelled")
                    return
                
                # Run stress test
                await stress_test(browser=browser, users=users)
                
                # Check if cancelled during execution
                if task_cancellation.get(task_id, False):
                    task_status[task_id]["status"] = "cancelled"
                    task_status[task_id]["completed_at"] = datetime.now().isoformat()
                    task_status[task_id]["message"] = "Task cancelled during execution"
                    logging.info(f"[Task {task_id}] Task cancelled during execution")
                else:
                    # Update task status
                    task_status[task_id]["status"] = "completed"
                    task_status[task_id]["completed_at"] = datetime.now().isoformat()
                    task_status[task_id]["message"] = "Stress test completed successfully"
                    logging.info(f"[Task {task_id}] Stress test completed")
                
            finally:
                # Clean up browser
                logging.info(f"[Task {task_id}] Closing browser...")
                await asyncio.sleep(2)
                await browser.close()
                
    except Exception as e:
        # Update task status with error
        error_msg = str(e)
        task_status[task_id]["status"] = "failed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["error"] = error_msg
        task_status[task_id]["message"] = f"Stress test failed: {error_msg}"
        logging.error(f"[Task {task_id}] Stress test failed: {e}", exc_info=True)


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Playwright Stress Test API",
        "version": "1.0.0",
        "endpoints": {
            "POST /api/v1/stress-test": "Start a stress test as background task",
            "GET /api/v1/tasks/{task_id}": "Get task status",
            "GET /api/v1/tasks": "List all tasks",
            "POST /api/v1/tasks/{task_id}/stop": "Stop a running task",
            "DELETE /api/v1/tasks/{task_id}": "Delete a task from the list"
        }
    }


@app.post("/api/v1/stress-test", response_model=TaskStatusResponse)
async def start_stress_test(
    request: StressTestRequest,
    background_tasks: BackgroundTasks
):
    """
    Start a stress test as a background task.
    
    Args:
        request: Stress test configuration and user list
        background_tasks: FastAPI background tasks handler
    
    Returns:
        Task status with task_id for tracking
    """
    # Generate unique task ID
    task_id = str(uuid.uuid4())
    
    # Prepare users list
    if request.users:
        users = [
            {
                "username": user.username,
                "password": user.password,
                "questions": user.questions or (USERS[0]["questions"] if USERS and "questions" in USERS[0] else [])
            }
            for user in request.users
        ]
    else:
        # Use default users from config
        users = USERS
    
    # Prepare config overrides
    config_overrides = {}
    if request.config:
        config_dict = request.config.model_dump(exclude_none=True)
        config_overrides = config_dict
        
        # Log important configuration
        logging.info(f"[Task {task_id}] Configuration:")
        logging.info(f"  sessions_per_user: {config_overrides.get('sessions_per_user', 'default')}")
        logging.info(f"  handle_both_courses: {config_overrides.get('handle_both_courses', 'default')}")
        if not config_overrides.get('handle_both_courses', True):
            logging.info(f"  course_for_questions: {config_overrides.get('course_for_questions', 'not set')}")
    
    # Initialize task status
    task_status[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "completed_at": None,
        "error": None,
        "message": "Task created, waiting to start"
    }
    
    # Add background task
    background_tasks.add_task(
        run_stress_test_task,
        task_id=task_id,
        users=users,
        config_overrides=config_overrides if config_overrides else None
    )
    
    logging.info(f"Created stress test task: {task_id}")
    
    return TaskStatusResponse(**task_status[task_id])


# @app.get("/api/v1/tasks/{task_id}", response_model=TaskStatusResponse)
# async def get_task_status(task_id: str):
#     """
#     Get the status of a stress test task.
    
#     Args:
#         task_id: Unique task identifier
    
#     Returns:
#         Current task status
#     """
#     if task_id not in task_status:
#         raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
#     return TaskStatusResponse(**task_status[task_id])


# @app.get("/api/v1/tasks")
# async def list_tasks():
#     """
#     List all stress test tasks.
    
#     Returns:
#         List of all tasks with their status
#     """
#     return {
#         "tasks": [
#             TaskStatusResponse(**status).model_dump()
#             for status in task_status.values()
#         ],
#         "total": len(task_status)
#     }


# @app.post("/api/v1/tasks/{task_id}/stop")
# async def stop_task(task_id: str):
#     """
#     Stop a running stress test task.
    
#     Args:
#         task_id: Unique task identifier
    
#     Returns:
#         Success message
#     """
#     if task_id not in task_status:
#         raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
#     current_status = task_status[task_id]["status"]
#     if current_status in ["completed", "failed", "cancelled"]:
#         raise HTTPException(
#             status_code=400, 
#             detail=f"Task {task_id} is already {current_status} and cannot be stopped"
#         )
    
#     # Mark task for cancellation
#     task_cancellation[task_id] = True
#     task_status[task_id]["message"] = "Stop request received, task will be cancelled"
#     logging.info(f"[Task {task_id}] Stop request received")
    
#     return {
#         "message": f"Stop request sent for task {task_id}",
#         "task_id": task_id,
#         "status": task_status[task_id]["status"]
#     }


# @app.delete("/api/v1/tasks/{task_id}")
# async def delete_task(task_id: str):
#     """
#     Delete a task from the task list.
    
#     Args:
#         task_id: Unique task identifier
    
#     Returns:
#         Success message
#     """
#     if task_id not in task_status:
#         raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
#     del task_status[task_id]
#     if task_id in task_cancellation:
#         del task_cancellation[task_id]
#     return {"message": f"Task {task_id} deleted successfully"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_tasks": sum(
            1 for task in task_status.values()
            if task["status"] in ["pending", "running"]
        )
    }


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

