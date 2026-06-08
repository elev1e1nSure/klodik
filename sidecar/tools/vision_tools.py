"""Vision tools: screenshot and screen-aware interaction."""

import os
import tempfile
from pathlib import Path

from .base import tool, ToolError
from .registry import registry

try:
    import pyautogui
except ImportError:
    pyautogui = None  # type: ignore[assignment]


# Directory for temporary screenshots
_TEMP_DIR = Path(__file__).resolve().parent.parent / "temp"


def _ensure_temp_dir() -> None:
    os.makedirs(_TEMP_DIR, exist_ok=True)


@tool(
    "screenshot",
    "Take a screenshot of the entire screen and save it to a file. Returns the file path.",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Optional path to save the screenshot. If omitted, saves to a temp file.",
            },
        },
        "required": [],
    },
)
def screenshot(*, path: str | None = None) -> str:
    if pyautogui is None:
        raise ToolError("pyautogui not installed")
    try:
        _ensure_temp_dir()
        if path:
            save_path = Path(path).resolve()
            os.makedirs(save_path.parent, exist_ok=True)
        else:
            save_path = _TEMP_DIR / "screenshot.png"
        img = pyautogui.screenshot()
        img.save(str(save_path))
        return f"Screenshot saved: {save_path}"
    except Exception as e:
        raise ToolError(f"Screenshot failed: {e}")


@tool(
    "get_active_window",
    "Get information about the currently focused window (title, position, size).",
    {
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def get_active_window() -> str:
    if pyautogui is None:
        raise ToolError("pyautogui not installed")
    try:
        win = pyautogui.getActiveWindow()
        if win is None:
            return "No active window detected"
        title = getattr(win, "title", "unknown")
        left = getattr(win, "left", 0)
        top = getattr(win, "top", 0)
        width = getattr(win, "width", 0)
        height = getattr(win, "height", 0)
        return (
            f"Active window: '{title}'\n"
            f"Position: ({left}, {top})\n"
            f"Size: {width}x{height}"
        )
    except Exception as e:
        raise ToolError(f"Cannot get active window: {e}")


@tool(
    "click_element",
    "Take a screenshot to see the current screen state before clicking. Returns the screenshot path so you can decide coordinates.",
    {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Description of the element you want to click (for reference)",
            },
        },
        "required": ["description"],
    },
)
def click_element(*, description: str) -> str:
    if pyautogui is None:
        raise ToolError("pyautogui not installed")
    try:
        _ensure_temp_dir()
        save_path = _TEMP_DIR / "click_element_screenshot.png"
        img = pyautogui.screenshot()
        img.save(str(save_path))
        return (
            f"Screenshot saved: {save_path}\n"
            f"Target: '{description}'\n"
            f"Hint: use get_active_window to know window position, then use move_mouse + click with coordinates."
        )
    except Exception as e:
        raise ToolError(f"click_element failed: {e}")


# Auto-register on import
registry.register(screenshot)
registry.register(get_active_window)
registry.register(click_element)
