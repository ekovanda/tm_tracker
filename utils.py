"""
Contains various utility functions
"""
import math

# TODO: Add unit test for this
def prettify_time(time: int) -> str:
    """
    Prettifies a time for nicer display.

    e.g: 61102 -> 01:01.102
    """
    if time == math.inf:
        return "∞"
    
    minutes: int = math.floor(time / 60_000)
    if minutes < 10:
        minutes_component = "0"+str(minutes)
    else:
        minutes_component = str(minutes)
    
    seconds: int = math.floor((time - (minutes * 60_000)) / 1_000)
    if seconds < 10:
        seconds_component = "0"+str(seconds)
    else:
        seconds_component = str(seconds)
    
    thousands_component = str(time)[-3:].ljust(3, "0")

    return f"{minutes_component}:{seconds_component}.{thousands_component}"