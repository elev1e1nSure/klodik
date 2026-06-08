"""Window management tools."""

from .base import tool, ToolError
from .registry import registry

try:
    import pygetwindow as gw
except ImportError:
    gw = None  # type: ignore[assignment]


def _get_window(title: str):
    """Find a window by title substring."""
    if gw is None:
        raise ToolError("pygetwindow not installed")
    matches = gw.getWindowsWithTitle(title)
    if not matches:
        raise ToolError(f"Window not found: '{title}'")
    # Prefer exact match, otherwise first
    for w in matches:
        if w.title == title:
            return w
    return matches[0]


@tool(
    "list_windows",
    "List all visible windows with their titles",
    {
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def list_windows() -> str:
    if gw is None:
        raise ToolError("pygetwindow not installed")
    try:
        windows = gw.getAllWindows()
        lines: list[str] = []
        for w in windows:
            if not w.title or not w.visible:
                continue
            lines.append(f"- '{w.title}' ({w.left},{w.top} {w.width}x{w.height})")
        if not lines:
            return "No visible windows found"
        return f"Visible windows ({len(lines)}):\n" + "\n".join(lines[:30])
    except Exception as e:
        raise ToolError(f"Cannot list windows: {e}")


@tool(
    "focus_window",
    "Focus (activate) a window by title",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Window title (substring is enough)"},
        },
        "required": ["title"],
    },
)
def focus_window(*, title: str) -> str:
    try:
        w = _get_window(title)
        w.activate()
        return f"Focused window: '{w.title}'"
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Cannot focus window: {e}")


@tool(
    "minimize_window",
    "Minimize a window by title",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Window title (substring is enough)"},
        },
        "required": ["title"],
    },
)
def minimize_window(*, title: str) -> str:
    try:
        w = _get_window(title)
        w.minimize()
        return f"Minimized window: '{w.title}'"
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Cannot minimize window: {e}")


@tool(
    "move_window",
    "Move and resize a window by title",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Window title (substring is enough)"},
            "x": {"type": "integer", "description": "New X position"},
            "y": {"type": "integer", "description": "New Y position"},
            "width": {"type": "integer", "description": "New width"},
            "height": {"type": "integer", "description": "New height"},
        },
        "required": ["title", "x", "y", "width", "height"],
    },
)
def move_window(*, title: str, x: int, y: int, width: int, height: int) -> str:
    try:
        w = _get_window(title)
        w.moveTo(x, y)
        w.resizeTo(width, height)
        return f"Moved/resized window '{w.title}' to ({x},{y}) {width}x{height}"
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Cannot move window: {e}")


# Auto-register on import
registry.register(list_windows)
registry.register(focus_window)
registry.register(minimize_window)
registry.register(move_window)
