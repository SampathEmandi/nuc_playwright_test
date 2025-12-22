"""
Browser and iframe utilities for the Playwright stress test application.
"""
import asyncio
import logging
from utils.logging_utils import debug_log


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