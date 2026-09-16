"""Spatial light modulators and DMDs as displays on Linux, X11 and Wayland."""

from . import patterns
from .displays import WINDOW_APP_ID, Display, Output, find_output, list_outputs, session_is_wayland
from .sim import SimDisplay

__all__ = ['SimDisplay', "Display", "Output", "WINDOW_APP_ID", "find_output", "list_outputs", "patterns", "session_is_wayland"]
__version__ = "0.1.0"
