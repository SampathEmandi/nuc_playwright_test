"""
Calculate maximum stress test configuration values for your system.
This script helps you determine the maximum sessions_per_user and 
max_concurrent_contexts you can safely run.
"""
import psutil
import sys

# Resource estimates (from resource_calculator.py)
MEMORY_PER_CONTEXT_MB = 150  # Average memory per browser context (MB)
CPU_PER_CONTEXT_PERCENT = 1.5  # Average CPU usage per context (%)

# Safety margins
MEMORY_RESERVE_PERCENT = 20  # Reserve 20% of memory for system
CPU_RESERVE_PERCENT = 25  # Reserve 25% of CPU for system

# Current limits
MAX_SESSIONS_PER_USER = 50
MAX_CONCURRENT_CONTEXTS = 10000

def calculate_max_stress():
    """Calculate maximum stress test values."""
    print("=" * 80)
    print("MAXIMUM STRESS TEST CONFIGURATION CALCULATOR")
    print("=" * 80)
    print()
    
    # Get system resources
    cpu_count = psutil.cpu_count(logical=True)
    total_memory_gb = psutil.virtual_memory().total / (1024 ** 3)
    available_memory_gb = psutil.virtual_memory().available / (1024 ** 3)
    memory_percent_used = psutil.virtual_memory().percent
    cpu_percent_used = psutil.cpu_percent(interval=1)
    
    print("SYSTEM RESOURCES:")
    print(f"  CPU Cores (logical): {cpu_count}")
    print(f"  Total Memory: {total_memory_gb:.2f} GB")
    print(f"  Available Memory: {available_memory_gb:.2f} GB ({100 - memory_percent_used:.1f}% free)")
    print(f"  Current CPU Usage: {cpu_percent_used:.1f}%")
    print()
    
    # Calculate max contexts by memory
    usable_memory_mb = (available_memory_gb * 1024) * (1 - MEMORY_RESERVE_PERCENT / 100)
    max_contexts_memory = int(usable_memory_mb / MEMORY_PER_CONTEXT_MB)
    
    print("MEMORY-BASED CALCULATION:")
    print(f"  Usable memory (after {MEMORY_RESERVE_PERCENT}% reserve): {usable_memory_mb:.2f} MB")
    print(f"  Memory per context: {MEMORY_PER_CONTEXT_MB} MB")
    print(f"  Max contexts (memory): {max_contexts_memory}")
    print()
    
    # Calculate max contexts by CPU
    cpu_percent_available = 100 - cpu_percent_used
    usable_cpu_percent = cpu_percent_available * (1 - CPU_RESERVE_PERCENT / 100)
    max_contexts_cpu = int((cpu_count * usable_cpu_percent) / CPU_PER_CONTEXT_PERCENT)
    
    print("CPU-BASED CALCULATION:")
    print(f"  CPU usage: {cpu_percent_used:.1f}%")
    print(f"  Usable CPU (after {CPU_RESERVE_PERCENT}% reserve): {usable_cpu_percent:.1f}%")
    print(f"  CPU per context: {CPU_PER_CONTEXT_PERCENT}%")
    print(f"  Max contexts (CPU): {max_contexts_cpu}")
    print()
    
    # Use the more restrictive limit
    max_contexts = min(max_contexts_memory, max_contexts_cpu)
    max_contexts = min(max_contexts, MAX_CONCURRENT_CONTEXTS)  # Apply hard limit
    
    print("=" * 80)
    print("RECOMMENDED MAXIMUM VALUES:")
    print("=" * 80)
    
    # Get number of users
    try:
        from config import USERS
        num_users = len(USERS)
        print(f"  Number of users: {num_users}")
    except:
        num_users = int(input("Enter number of users: "))
    
    if num_users > 0:
        sessions_per_user = max_contexts // num_users
        sessions_per_user = min(sessions_per_user, MAX_SESSIONS_PER_USER)
    else:
        sessions_per_user = MAX_SESSIONS_PER_USER
    
    total_sessions = sessions_per_user * num_users
    
    print(f"  sessions_per_user: {sessions_per_user} (max: {MAX_SESSIONS_PER_USER})")
    print(f"  max_concurrent_contexts: {max_contexts} (max: {MAX_CONCURRENT_CONTEXTS})")
    print(f"  Total concurrent sessions: {total_sessions}")
    print()
    
    # Calculate resource usage
    estimated_memory_gb = (total_sessions * MEMORY_PER_CONTEXT_MB) / 1024
    estimated_cpu_percent = (total_sessions * CPU_PER_CONTEXT_PERCENT) / cpu_count
    
    print("ESTIMATED RESOURCE USAGE:")
    print(f"  Memory: {estimated_memory_gb:.2f} GB ({estimated_memory_gb / total_memory_gb * 100:.1f}% of total)")
    print(f"  CPU: {estimated_cpu_percent:.1f}% average ({estimated_cpu_percent / cpu_count:.1f}% per core)")
    print()
    
    # Warnings
    print("WARNINGS:")
    if estimated_memory_gb > available_memory_gb * 0.8:
        print(f"  ⚠️  High memory usage: {estimated_memory_gb:.2f} GB may exceed available memory")
    if estimated_cpu_percent > 70:
        print(f"  ⚠️  High CPU usage: {estimated_cpu_percent:.1f}% may cause system slowdown")
    if max_contexts_memory < max_contexts_cpu:
        print(f"  ⚠️  Memory is the limiting factor (CPU could handle {max_contexts_cpu} contexts)")
    else:
        print(f"  ⚠️  CPU is the limiting factor (Memory could handle {max_contexts_memory} contexts)")
    print()
    
    print("=" * 80)
    print("CONFIG.PY SETTINGS FOR MAXIMUM STRESS:")
    print("=" * 80)
    print()
    print("Option 1: Use dynamic calculation (RECOMMENDED)")
    print("  'dynamic_resource_calculation': True,")
    print("  # Will automatically calculate optimal values")
    print()
    print("Option 2: Manual override for maximum stress")
    print(f"  'dynamic_resource_calculation': False,")
    print(f"  'sessions_per_user': {sessions_per_user},")
    print(f"  'max_concurrent_contexts': {max_contexts},")
    print()
    print("Option 3: Override limits in utils/resource_calculator.py for even higher values")
    print(f"  MAX_SESSIONS_PER_USER = {sessions_per_user * 2}  # Double the limit")
    print(f"  MAX_CONCURRENT_CONTEXTS = {max_contexts * 2}  # Double the limit")
    print("  # Then use dynamic calculation")
    print()
    print("=" * 80)

if __name__ == '__main__':
    try:
        calculate_max_stress()
    except KeyboardInterrupt:
        print("\n\nCalculation cancelled.")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

