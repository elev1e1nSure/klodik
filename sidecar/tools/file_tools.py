"""File and directory tools for the agent."""

import fnmatch
import os
import shutil
from pathlib import Path

from .base import tool, ToolError
from .registry import registry


# Safety limits
_MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
_MAX_SEARCH_DEPTH = 10
_MAX_SEARCH_RESULTS = 100


def _sanitize_path(path: str) -> Path:
    """Resolve and validate a user-supplied path.

    Rejects empty paths and obvious system directories.
    """
    if not path or not str(path).strip():
        raise ToolError("Path cannot be empty")

    resolved = Path(path).resolve()

    # Prevent writing into Windows system directories
    system_roots = [Path("C:/Windows"), Path("C:/Program Files"), Path("C:/Program Files (x86)")]
    for root in system_roots:
        try:
            resolved.relative_to(root)
            raise ToolError(f"Access denied to system directory: {root}")
        except ValueError:
            pass

    return resolved


@tool(
    "read_file",
    "Read contents of a file",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute or relative file path"},
        },
        "required": ["path"],
    },
)
def read_file(*, path: str) -> str:
    try:
        target = _sanitize_path(path)
        if not target.exists():
            raise ToolError(f"File not found: {path}")
        if not target.is_file():
            raise ToolError(f"Not a file: {path}")
        size = target.stat().st_size
        if size > _MAX_FILE_SIZE:
            raise ToolError(f"File too large ({size} bytes, max {_MAX_FILE_SIZE})")
        with open(target, "r", encoding="utf-8") as f:
            return f.read()
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Cannot read file: {e}")


@tool(
    "write_file",
    "Write contents to a file",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute or relative file path"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    },
)
def write_file(*, path: str, content: str) -> str:
    try:
        target = _sanitize_path(path)
        dir_name = target.parent
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return f"File written: {target}"
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Cannot write file: {e}")


@tool(
    "search",
    "Search files by name or content in a directory",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search pattern"},
            "path": {"type": "string", "description": "Directory to search in", "default": "."},
            "by_content": {"type": "boolean", "description": "Search in file contents", "default": False},
        },
        "required": ["query"],
    },
)
def search(*, query: str, path: str = ".", by_content: bool = False) -> str:
    try:
        root = Path(path).resolve()
        if not root.is_dir():
            raise ToolError(f"Not a directory: {path}")

        matches: list[str] = []
        for root_dir, dirs, files in os.walk(root):
            depth = root_dir.count(os.sep) - str(root).count(os.sep)
            if depth > _MAX_SEARCH_DEPTH:
                del dirs[:]
                continue
            for filename in files:
                if len(matches) >= _MAX_SEARCH_RESULTS:
                    break
                full = Path(root_dir) / filename
                rel = full.relative_to(root)
                if fnmatch.fnmatch(filename.lower(), f"*{query.lower()}*"):
                    matches.append(str(rel))
                elif by_content:
                    try:
                        with open(full, "r", encoding="utf-8", errors="ignore") as f:
                            if query in f.read():
                                matches.append(str(rel))
                    except Exception:
                        pass
            if len(matches) >= _MAX_SEARCH_RESULTS:
                break

        return "\n".join(matches) if matches else "No matches found"
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Search failed: {e}")


@tool(
    "mkdir",
    "Create a directory (including intermediate directories)",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path to create"},
        },
        "required": ["path"],
    },
)
def mkdir(*, path: str) -> str:
    try:
        target = _sanitize_path(path)
        os.makedirs(target, exist_ok=True)
        return f"Directory created: {target}"
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Cannot create directory: {e}")


@tool(
    "list_dir",
    "List contents of a directory",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path to list", "default": "."},
        },
        "required": ["path"],
    },
)
def list_dir(*, path: str = ".") -> str:
    try:
        target = _sanitize_path(path)
        if not target.is_dir():
            raise ToolError(f"Not a directory: {path}")
        items = os.listdir(target)
        return "\n".join(items) if items else "(empty)"
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Cannot list directory: {e}")


@tool(
    "move_file",
    "Move or rename a file or directory",
    {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "Source path"},
            "destination": {"type": "string", "description": "Destination path"},
        },
        "required": ["source", "destination"],
    },
)
def move_file(*, source: str, destination: str) -> str:
    try:
        src = _sanitize_path(source)
        dst = _sanitize_path(destination)
        if not src.exists():
            raise ToolError(f"Source does not exist: {source}")
        shutil.move(str(src), str(dst))
        return f"Moved {src} -> {dst}"
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Cannot move file: {e}")


# Auto-register on import
registry.register(read_file)
registry.register(write_file)
registry.register(search)
registry.register(mkdir)
registry.register(list_dir)
registry.register(move_file)
