"""
Timezone utilities for CaptureCare
Handles conversion between UTC storage and Australian Eastern Time display
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Australian Eastern timezone (handles AEST/AEDT automatically)
AUSTRALIA_TZ = ZoneInfo('Australia/Sydney')

def now_utc():
    """Get current time in UTC with timezone awareness"""
    return datetime.now(timezone.utc)

def now_local():
    """Get current time in Australian Eastern time"""
    return datetime.now(AUSTRALIA_TZ)

def to_local(dt):
    """
    Convert a datetime to Australian Eastern time
    
    Args:
        dt: datetime object (naive or aware)
    
    Returns:
        datetime in Australia/Sydney timezone
    """
    if dt is None:
        return None
    
    # If naive, assume it's UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to Australian Eastern time
    return dt.astimezone(AUSTRALIA_TZ)

def to_utc(dt):
    """
    Convert a datetime to UTC
    
    Args:
        dt: datetime object (naive or aware, assumed to be in Australia/Sydney if naive)
    
    Returns:
        datetime in UTC timezone
    """
    if dt is None:
        return None
    
    # If naive, assume it's in Australian Eastern time
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=AUSTRALIA_TZ)
    
    # Convert to UTC
    return dt.astimezone(timezone.utc)

def format_local(dt, format_str='%Y-%m-%d %H:%M:%S %Z'):
    """
    Format a datetime in Australian Eastern time
    
    Args:
        dt: datetime object
        format_str: strftime format string
    
    Returns:
        Formatted string in Australia/Sydney timezone
    """
    if dt is None:
        return None
    
    local_dt = to_local(dt)
    return local_dt.strftime(format_str)

def normalize_weekday_to_python(js_weekday):
    """
    Convert JavaScript weekday (0=Sunday) to Python weekday (0=Monday)
    
    Args:
        js_weekday: int (0-6 where 0=Sunday)
    
    Returns:
        int (0-6 where 0=Monday)
    """
    return (js_weekday + 6) % 7

def normalize_weekday_to_js(python_weekday):
    """
    Convert Python weekday (0=Monday) to JavaScript weekday (0=Sunday)
    
    Args:
        python_weekday: int (0-6 where 0=Monday)
    
    Returns:
        int (0-6 where 0=Sunday)
    """
    return (python_weekday + 1) % 7
