"""Session logging: records agent actions per session in markdown files."""

import os
from datetime import datetime
from pathlib import Path
from typing import Any

# Directory for session logs
_LOG_DIR = Path(__file__).resolve().parent / "sessions"

_current_session_path: Path | None = None


def _ensure_dir() -> None:
    os.makedirs(_LOG_DIR, exist_ok=True)


def _get_session_path() -> Path:
    global _current_session_path
    if _current_session_path is None:
        _ensure_dir()
        filename = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".md"
        _current_session_path = _LOG_DIR / filename
        with open(_current_session_path, "w", encoding="utf-8") as f:
            f.write(f"# Session {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    return _current_session_path


def append(tool_name: str, result: str) -> None:
    """Append a tool execution entry to the current session log."""
    path = _get_session_path()
    timestamp = datetime.now().strftime("%H:%M:%S")
    preview = result[:500].replace("\n", " ")
    if len(result) > 500:
        preview += "..."
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"### [{timestamp}] {tool_name}\n\n")
        f.write(f"```\n{preview}\n```\n\n")


def list_sessions() -> list[str]:
    """Return sorted list of session filenames."""
    _ensure_dir()
    files = sorted(_LOG_DIR.glob("*.md"), reverse=True)
    return [f.name for f in files]


def read_session(filename: str) -> str:
    """Read a session log file by name."""
    _ensure_dir()
    path = _LOG_DIR / filename
    if not path.exists():
        return f"Session not found: {filename}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading session: {e}"


class SessionLog:
    """Wrapper class so ``from session_log import session_log`` works."""

    def append(self, tool_name: str, result: str) -> None:
        append(tool_name, result)

    def list_sessions(self) -> list[str]:
        return list_sessions()

    def read_session(self, filename: str) -> str:
        return read_session(filename)


session_log = SessionLog()
