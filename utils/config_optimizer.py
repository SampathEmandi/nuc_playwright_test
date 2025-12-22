"""
Configuration optimizer that dynamically calculates optimal settings
based on available system resources.
"""
import logging
from typing import Dict, Optional
from utils.resource_calculator import calculate_optimal_config, apply_optimal_config
from config import STRESS_TEST_CONFIG, USERS


def optimize_config(dynamic_mode: bool = True, 
                   override_sessions_per_user: Optional[int] = None,
                   override_max_contexts: Optional[int] = None) -> Dict:
    """
    Optimize stress test configuration based on system resources.
    
    Args:
        dynamic_mode: If True, calculate values dynamically based on resources.
                     If False, use values from config.
        override_sessions_per_user: Override sessions_per_user (if provided)
        override_max_contexts: Override max_concurrent_contexts (if provided)
    
    Returns:
        Dictionary with optimized configuration values
    """
    if not dynamic_mode:
        logging.info("[CONFIG_OPTIMIZER] Using static configuration from config.py")
        return {
            'sessions_per_user': STRESS_TEST_CONFIG.get('sessions_per_user', 10),
            'max_concurrent_contexts': STRESS_TEST_CONFIG.get('max_concurrent_contexts', 10000),
            'calculation_method': 'static'
        }
    
    logging.info("=" * 80)
    logging.info("DYNAMIC CONFIGURATION OPTIMIZATION")
    logging.info("=" * 80)
    
    try:
        # Calculate optimal configuration
        num_users = len(USERS)
        optimal = calculate_optimal_config(num_users=num_users)
        
        # Apply overrides if provided
        if override_sessions_per_user is not None:
            optimal['sessions_per_user'] = override_sessions_per_user
            logging.info(f"[CONFIG_OPTIMIZER] Override: sessions_per_user = {override_sessions_per_user}")
        
        if override_max_contexts is not None:
            optimal['max_concurrent_contexts'] = override_max_contexts
            logging.info(f"[CONFIG_OPTIMIZER] Override: max_concurrent_contexts = {override_max_contexts}")
        
        logging.info("=" * 80)
        logging.info("OPTIMAL CONFIGURATION CALCULATED:")
        logging.info(f"  sessions_per_user: {optimal['sessions_per_user']}")
        logging.info(f"  max_concurrent_contexts: {optimal['max_concurrent_contexts']}")
        logging.info(f"  Total concurrent sessions: {optimal['sessions_per_user'] * num_users}")
        logging.info("=" * 80)
        
        return optimal
        
    except Exception as e:
        logging.error(f"[CONFIG_OPTIMIZER] Error calculating optimal config: {e}")
        logging.warning("[CONFIG_OPTIMIZER] Falling back to static configuration")
        return {
            'sessions_per_user': STRESS_TEST_CONFIG.get('sessions_per_user', 10),
            'max_concurrent_contexts': STRESS_TEST_CONFIG.get('max_concurrent_contexts', 10000),
            'calculation_method': 'static_fallback',
            'error': str(e)
        }


def update_stress_test_config(dynamic_mode: bool = True,
                             override_sessions_per_user: Optional[int] = None,
                             override_max_contexts: Optional[int] = None):
    """
    Update STRESS_TEST_CONFIG with optimized values.
    
    Args:
        dynamic_mode: If True, calculate values dynamically
        override_sessions_per_user: Override sessions_per_user
        override_max_contexts: Override max_concurrent_contexts
    """
    optimal = optimize_config(
        dynamic_mode=dynamic_mode,
        override_sessions_per_user=override_sessions_per_user,
        override_max_contexts=override_max_contexts
    )
    
    # Update global config
    STRESS_TEST_CONFIG['sessions_per_user'] = optimal['sessions_per_user']
    STRESS_TEST_CONFIG['max_concurrent_contexts'] = optimal['max_concurrent_contexts']
    
    # Store calculation method for reference
    STRESS_TEST_CONFIG['_calculation_method'] = optimal.get('calculation_method', 'unknown')
    
    return optimal


def get_optimized_config_values() -> tuple:
    """
    Get optimized configuration values.
    
    Returns:
        Tuple of (sessions_per_user, max_concurrent_contexts)
    """
    return (
        STRESS_TEST_CONFIG.get('sessions_per_user', 10),
        STRESS_TEST_CONFIG.get('max_concurrent_contexts', 10000)
    )