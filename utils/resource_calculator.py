"""
Resource calculator module for dynamically determining optimal configuration
based on available system resources.
"""
import psutil
import os
import logging
from typing import Dict, Tuple


class ResourceCalculator:
    """
    Calculates optimal configuration values based on system resources.
    """
    
    # Estimated resource usage per browser context/session
    MEMORY_PER_CONTEXT_MB = 150  # Average memory per browser context (MB)
    CPU_PER_CONTEXT_PERCENT = 1.5  # Average CPU usage per context (%)
    
    # Safety margins (percentage to reserve for system)
    MEMORY_RESERVE_PERCENT = 20  # Reserve 20% of memory for system
    CPU_RESERVE_PERCENT = 25  # Reserve 25% of CPU for system
    
    # Minimum/maximum constraints
    MIN_SESSIONS_PER_USER = 1
    MAX_SESSIONS_PER_USER = 50
    MIN_CONCURRENT_CONTEXTS = 1
    MAX_CONCURRENT_CONTEXTS = None  # No upper limit - use system resources as guide
    
    def __init__(self):
        """Initialize the resource calculator."""
        self.cpu_count = psutil.cpu_count(logical=True)
        self.total_memory_gb = psutil.virtual_memory().total / (1024 ** 3)
        self.available_memory_gb = psutil.virtual_memory().available / (1024 ** 3)
        
        logging.info(f"[RESOURCE_CALCULATOR] System Resources Detected:")
        logging.info(f"  CPU Cores (logical): {self.cpu_count}")
        logging.info(f"  Total Memory: {self.total_memory_gb:.2f} GB")
        logging.info(f"  Available Memory: {self.available_memory_gb:.2f} GB")
    
    def get_system_resources(self) -> Dict:
        """
        Get current system resource usage.
        
        Returns:
            Dictionary with system resource information
        """
        memory = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=1)
        
        return {
            'cpu_count': self.cpu_count,
            'cpu_percent_used': cpu_percent,
            'cpu_percent_available': 100 - cpu_percent,
            'total_memory_gb': self.total_memory_gb,
            'available_memory_gb': self.available_memory_gb,
            'memory_percent_used': memory.percent,
            'memory_percent_available': 100 - memory.percent,
            'memory_used_gb': memory.used / (1024 ** 3),
        }
    
    def calculate_max_contexts_by_memory(self) -> int:
        """
        Calculate maximum concurrent contexts based on available memory.
        
        Returns:
            Maximum number of contexts that can run based on memory
        """
        # Calculate usable memory (after reserving system memory)
        usable_memory_mb = (self.available_memory_gb * 1024) * (1 - self.MEMORY_RESERVE_PERCENT / 100)
        
        # Calculate max contexts based on memory
        max_contexts = int(usable_memory_mb / self.MEMORY_PER_CONTEXT_MB)
        
        logging.info(f"[RESOURCE_CALCULATOR] Memory-based calculation:")
        logging.info(f"  Usable memory (after {self.MEMORY_RESERVE_PERCENT}% reserve): {usable_memory_mb:.2f} MB")
        logging.info(f"  Memory per context: {self.MEMORY_PER_CONTEXT_MB} MB")
        logging.info(f"  Max contexts (memory): {max_contexts}")
        
        return max_contexts
    
    def calculate_max_contexts_by_cpu(self) -> int:
        """
        Calculate maximum concurrent contexts based on available CPU.
        
        Returns:
            Maximum number of contexts that can run based on CPU
        """
        # Get current CPU usage
        cpu_percent_used = psutil.cpu_percent(interval=1)
        cpu_percent_available = 100 - cpu_percent_used
        
        # Calculate usable CPU (after reserving system CPU)
        usable_cpu_percent = cpu_percent_available * (1 - self.CPU_RESERVE_PERCENT / 100)
        
        # Calculate max contexts based on CPU
        # Assuming each context uses CPU_PER_CONTEXT_PERCENT of one CPU
        max_contexts = int((self.cpu_count * usable_cpu_percent) / self.CPU_PER_CONTEXT_PERCENT)
        
        logging.info(f"[RESOURCE_CALCULATOR] CPU-based calculation:")
        logging.info(f"  CPU usage: {cpu_percent_used:.1f}%")
        logging.info(f"  Usable CPU (after {self.CPU_RESERVE_PERCENT}% reserve): {usable_cpu_percent:.1f}%")
        logging.info(f"  CPU per context: {self.CPU_PER_CONTEXT_PERCENT}%")
        logging.info(f"  Max contexts (CPU): {max_contexts}")
        
        return max_contexts
    
    def calculate_optimal_config(self, num_users: int) -> Tuple[int, int]:
        """
        Calculate optimal sessions_per_user and max_concurrent_contexts.
        
        Args:
            num_users: Number of users that will run concurrently
        
        Returns:
            Tuple of (sessions_per_user, max_concurrent_contexts)
        """
        # Calculate max contexts based on both memory and CPU
        max_contexts_memory = self.calculate_max_contexts_by_memory()
        max_contexts_cpu = self.calculate_max_contexts_by_cpu()
        
        # Use the more restrictive limit (conservative approach)
        max_contexts = min(max_contexts_memory, max_contexts_cpu)
        
        # Apply constraints
        max_contexts = max(self.MIN_CONCURRENT_CONTEXTS, max_contexts)
        # Apply upper limit only if MAX_CONCURRENT_CONTEXTS is set
        if self.MAX_CONCURRENT_CONTEXTS is not None:
            max_contexts = min(max_contexts, self.MAX_CONCURRENT_CONTEXTS)
        
        # Calculate sessions_per_user based on max contexts and number of users
        if num_users > 0:
            sessions_per_user = max_contexts // num_users
            sessions_per_user = max(self.MIN_SESSIONS_PER_USER,
                                  min(sessions_per_user, self.MAX_SESSIONS_PER_USER))
        else:
            sessions_per_user = self.MIN_SESSIONS_PER_USER
        
        # Ensure max_concurrent_contexts is at least sessions_per_user * num_users
        # to allow all users to run their sessions
        required_contexts = sessions_per_user * num_users
        if max_contexts < required_contexts:
            # If we can't support all sessions, reduce sessions_per_user
            sessions_per_user = max_contexts // num_users if num_users > 0 else 1
            sessions_per_user = max(self.MIN_SESSIONS_PER_USER, sessions_per_user)
            logging.warning(f"[RESOURCE_CALCULATOR] Resources limited: Reduced sessions_per_user to {sessions_per_user}")
        
        logging.info(f"[RESOURCE_CALCULATOR] Optimal Configuration:")
        logging.info(f"  Number of users: {num_users}")
        logging.info(f"  Sessions per user: {sessions_per_user}")
        logging.info(f"  Max concurrent contexts: {max_contexts}")
        logging.info(f"  Total sessions that can run: {sessions_per_user * num_users}")
        
        return sessions_per_user, max_contexts
    
    def get_resource_recommendations(self) -> Dict:
        """
        Get resource usage recommendations and warnings.
        
        Returns:
            Dictionary with recommendations
        """
        resources = self.get_system_resources()
        recommendations = {
            'warnings': [],
            'recommendations': [],
            'system_status': 'healthy'
        }
        
        # Check memory
        if resources['memory_percent_used'] > 80:
            recommendations['warnings'].append(
                f"High memory usage: {resources['memory_percent_used']:.1f}% used. "
                f"Consider reducing sessions_per_user."
            )
            recommendations['system_status'] = 'warning'
        elif resources['memory_percent_used'] > 90:
            recommendations['system_status'] = 'critical'
            recommendations['warnings'].append(
                f"Critical memory usage: {resources['memory_percent_used']:.1f}% used. "
                f"System may become unstable."
            )
        
        # Check CPU
        if resources['cpu_percent_used'] > 80:
            recommendations['warnings'].append(
                f"High CPU usage: {resources['cpu_percent_used']:.1f}% used. "
                f"Consider reducing sessions_per_user."
            )
            if recommendations['system_status'] == 'healthy':
                recommendations['system_status'] = 'warning'
        
        # Recommendations based on available resources
        if resources['available_memory_gb'] < 2:
            recommendations['recommendations'].append(
                "Low available memory. Consider closing other applications."
            )
        
        if resources['cpu_percent_available'] < 20:
            recommendations['recommendations'].append(
                "Low CPU availability. Consider reducing concurrent sessions."
            )
        
        return recommendations


def calculate_optimal_config(num_users: int = None, config_dict: Dict = None) -> Dict:
    """
    Calculate optimal configuration values based on system resources.
    
    Args:
        num_users: Number of users (if None, will use len(config_dict['USERS']) if provided)
        config_dict: Optional dictionary with USERS list to auto-detect num_users
    
    Returns:
        Dictionary with calculated optimal values:
        {
            'sessions_per_user': int,
            'max_concurrent_contexts': int,
            'system_resources': dict,
            'recommendations': dict
        }
    """
    calculator = ResourceCalculator()
    
    # Determine number of users
    if num_users is None:
        if config_dict and 'USERS' in config_dict:
            num_users = len(config_dict['USERS'])
        else:
            # Default to a safe value if we can't determine
            num_users = 1
            logging.warning("[RESOURCE_CALCULATOR] Could not determine number of users, using default: 1")
    
    # Calculate optimal configuration
    sessions_per_user, max_concurrent_contexts = calculator.calculate_optimal_config(num_users)
    
    # Get system resources and recommendations
    system_resources = calculator.get_system_resources()
    recommendations = calculator.get_resource_recommendations()
    
    return {
        'sessions_per_user': sessions_per_user,
        'max_concurrent_contexts': max_concurrent_contexts,
        'system_resources': system_resources,
        'recommendations': recommendations,
        'calculation_method': 'dynamic'
    }


def apply_optimal_config(config_dict: Dict, num_users: int = None) -> Dict:
    """
    Calculate and apply optimal configuration to a config dictionary.
    
    Args:
        config_dict: Configuration dictionary to update
        num_users: Number of users (auto-detected if None)
    
    Returns:
        Updated configuration dictionary
    """
    optimal = calculate_optimal_config(num_users, config_dict)
    
    # Apply calculated values
    if 'STRESS_TEST_CONFIG' in config_dict:
        config_dict['STRESS_TEST_CONFIG']['sessions_per_user'] = optimal['sessions_per_user']
        config_dict['STRESS_TEST_CONFIG']['max_concurrent_contexts'] = optimal['max_concurrent_contexts']
    
    # Log recommendations
    if optimal['recommendations']['warnings']:
        logging.warning("[RESOURCE_CALCULATOR] Resource Warnings:")
        for warning in optimal['recommendations']['warnings']:
            logging.warning(f"  ⚠️  {warning}")
    
    if optimal['recommendations']['recommendations']:
        logging.info("[RESOURCE_CALCULATOR] Recommendations:")
        for rec in optimal['recommendations']['recommendations']:
            logging.info(f"  💡 {rec}")
    
    return config_dict
