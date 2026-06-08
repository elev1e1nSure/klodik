"""Base types and helpers for the tool registry."""

from typing import Any, Callable


class ToolError(Exception):
    """Raised when a tool cannot execute successfully.

    The message is returned to the LLM as the tool result.
    """

    pass


ToolFunction = Callable[..., str]


def tool(name: str, description: str, parameters: dict[str, Any]):
    """Decorator that registers a function as an agent tool.

    The decorated function must accept keyword arguments matching the
    parameter schema and return a ``str`` result (even on error).
    """

    def decorator(func: ToolFunction) -> ToolFunction:
        func._tool_name = name  # type: ignore[attr-defined]
        func._tool_description = description  # type: ignore[attr-defined]
        func._tool_parameters = parameters  # type: ignore[attr-defined]
        return func

    return decorator
