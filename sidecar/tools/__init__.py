"""Agent tools package.

Importing this package auto-discovers all decorated tools into ``registry``.
"""

from .registry import registry
from . import file_tools, system_tools, web_tools, input_tools

# Ensure all modules are loaded so decorators fire
__all__ = ["registry"]
