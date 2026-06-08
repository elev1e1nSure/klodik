"""Tool registry that collects and executes agent tools."""

import json
from typing import Any

from .base import ToolError


class ToolRegistry:
    """Central registry for all agent tools.

    Tools are discovered by importing the individual tool modules.
    Each decorated function is automatically added to the registry.
    """

    def __init__(self):
        self._tools: dict[str, Any] = {}
        self._schemas: list[dict[str, Any]] = []

    def register(self, func: Any):
        """Register a decorated tool function."""
        name = getattr(func, "_tool_name", func.__name__)
        self._tools[name] = func
        self._schemas.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": getattr(func, "_tool_description", ""),
                    "parameters": getattr(func, "_tool_parameters", {"type": "object", "properties": {}}),
                },
            }
        )

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool by name with the given arguments.

        Returns a string result on success or a formatted error message.
        """
        if name not in self._tools:
            return f"Unknown tool: {name}"

        try:
            return self._tools[name](**arguments)
        except ToolError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error: {e}"

    @property
    def schemas(self) -> list[dict[str, Any]]:
        """Return the OpenAI-compatible tool schemas for the LLM."""
        return self._schemas.copy()


# Global singleton
registry = ToolRegistry()
