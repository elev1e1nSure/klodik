"""Mouse and keyboard input tools (via pyautogui)."""

from .base import tool, ToolError
from .registry import registry

try:
    import pyautogui
except ImportError:
    pyautogui = None  # type: ignore[assignment]


@tool(
    "move_mouse",
    "Move the mouse cursor to screen coordinates",
    {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "X coordinate"},
            "y": {"type": "integer", "description": "Y coordinate"},
        },
        "required": ["x", "y"],
    },
)
def move_mouse(*, x: int, y: int) -> str:
    if pyautogui is None:
        raise ToolError("pyautogui not installed")
    try:
        pyautogui.moveTo(x, y, duration=0.5)
        return f"Mouse moved to ({x}, {y})"
    except Exception as e:
        raise ToolError(f"Mouse error: {e}")


@tool(
    "click",
    "Click the mouse at screen coordinates",
    {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "X coordinate"},
            "y": {"type": "integer", "description": "Y coordinate"},
        },
        "required": ["x", "y"],
    },
)
def click(*, x: int, y: int) -> str:
    if pyautogui is None:
        raise ToolError("pyautogui not installed")
    try:
        pyautogui.click(x, y)
        return f"Clicked at ({x}, {y})"
    except Exception as e:
        raise ToolError(f"Click error: {e}")


@tool(
    "type_text",
    "Type text as if from keyboard",
    {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to type"},
        },
        "required": ["text"],
    },
)
def type_text(*, text: str) -> str:
    if pyautogui is None:
        raise ToolError("pyautogui not installed")
    try:
        pyautogui.typewrite(text, interval=0.01)
        return f"Typed: {text[:50]}..."
    except Exception as e:
        raise ToolError(f"Typing error: {e}")


@tool(
    "press_key",
    "Press a keyboard key (enter, ctrl, alt, tab, etc.)",
    {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Key name"},
        },
        "required": ["key"],
    },
)
def press_key(*, key: str) -> str:
    if pyautogui is None:
        raise ToolError("pyautogui not installed")
    try:
        pyautogui.press(key)
        return f"Pressed: {key}"
    except Exception as e:
        raise ToolError(f"Keypress error: {e}")


# Auto-register on import
registry.register(move_mouse)
registry.register(click)
registry.register(type_text)
registry.register(press_key)
