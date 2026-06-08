"""Clipboard read/write tools."""

from .base import tool, ToolError
from .registry import registry

try:
    import pyperclip
except ImportError:
    pyperclip = None  # type: ignore[assignment]


def _get_clipboard_text() -> str:
    """Read clipboard text, trying multiple backends."""
    if pyperclip is not None:
        try:
            return pyperclip.paste() or ""
        except Exception:
            pass
    # Fallback: tkinter
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        text = root.clipboard_get()
        root.destroy()
        return text or ""
    except Exception:
        pass
    raise ToolError("Clipboard access failed — pyperclip or tkinter required")


def _set_clipboard_text(text: str) -> None:
    """Write text to clipboard, trying multiple backends."""
    if pyperclip is not None:
        try:
            pyperclip.copy(text)
            return
        except Exception:
            pass
    # Fallback: tkinter
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.destroy()
        return
    except Exception:
        pass
    raise ToolError("Clipboard write failed — pyperclip or tkinter required")


@tool(
    "read_clipboard",
    "Read text from the system clipboard",
    {
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def read_clipboard() -> str:
    try:
        text = _get_clipboard_text()
        preview = text[:200].replace("\n", " ")
        if len(text) > 200:
            preview += "..."
        return f"Clipboard: {preview}"
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Clipboard read error: {e}")


@tool(
    "write_clipboard",
    "Write text to the system clipboard",
    {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to copy to clipboard"},
        },
        "required": ["text"],
    },
)
def write_clipboard(*, text: str) -> str:
    try:
        _set_clipboard_text(text)
        preview = text[:100].replace("\n", " ")
        if len(text) > 100:
            preview += "..."
        return f"Copied to clipboard: {preview}"
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Clipboard write error: {e}")


# Auto-register on import
registry.register(read_clipboard)
registry.register(write_clipboard)
