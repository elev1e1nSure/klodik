"""System-level tools: terminal, open apps, open URLs, run scripts."""

import os
import platform
import subprocess
import sys

from .base import tool, ToolError
from .registry import registry


# Default shell command timeout (seconds)
_DEFAULT_TIMEOUT = 30


def _open_command() -> str:
    """Return the platform-specific open command."""
    system = platform.system()
    if system == "Windows":
        return "start"
    if system == "Darwin":
        return "open"
    return "xdg-open"


@tool(
    "terminal",
    "Run a shell command in the terminal",
    {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute"},
            "cwd": {"type": "string", "description": "Working directory (optional)", "default": "."},
        },
        "required": ["command"],
    },
)
def terminal(*, command: str, cwd: str = ".") -> str:
    try:
        # Auto-silent for winget install to prevent interactive hangs
        if "winget install" in command and "--silent" not in command:
            command += " --silent --accept-package-agreements --accept-source-agreements"

        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_DEFAULT_TIMEOUT,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if result.returncode != 0:
            return f"Exit code {result.returncode}\n{out}\n{err}".strip()
        return out or "(no output)"
    except subprocess.TimeoutExpired:
        raise ToolError(f"Command timed out after {_DEFAULT_TIMEOUT} seconds")
    except Exception as e:
        raise ToolError(f"Terminal error: {e}")


@tool(
    "open_app",
    "Open an application by name (notepad, chrome, wt, calc, etc.)",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Application name or command"},
        },
        "required": ["name"],
    },
)
def open_app(*, name: str) -> str:
    try:
        system = platform.system()
        if system == "Windows":
            subprocess.Popen(f"start /b {name}", shell=True)
        elif system == "Darwin":
            subprocess.Popen(["open", "-a", name])
        else:
            # Linux / other Unix
            subprocess.Popen([name])
        return f"Opened: {name}"
    except Exception as e:
        raise ToolError(f"Cannot open app: {e}")


@tool(
    "open_url",
    "Open a URL in the default browser",
    {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to open"},
        },
        "required": ["url"],
    },
)
def open_url(*, url: str) -> str:
    try:
        system = platform.system()
        if system == "Windows":
            subprocess.Popen(f"start {url}", shell=True)
        elif system == "Darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
        return f"Opened URL: {url}"
    except Exception as e:
        raise ToolError(f"Cannot open URL: {e}")


@tool(
    "run_script",
    "Run a script file (python, bash, etc.)",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the script file"},
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Arguments to pass",
                "default": [],
            },
        },
        "required": ["path"],
    },
)
def run_script(*, path: str, args: list[str] | None = None) -> str:
    try:
        script_args = args or []
        interpreter = sys.executable
        result = subprocess.run(
            [interpreter, path, *script_args],
            capture_output=True,
            text=True,
            timeout=_DEFAULT_TIMEOUT,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if result.returncode != 0:
            return f"Exit code {result.returncode}\n{out}\n{err}".strip()
        return out or "(no output)"
    except subprocess.TimeoutExpired:
        raise ToolError(f"Script timed out after {_DEFAULT_TIMEOUT} seconds")
    except Exception as e:
        raise ToolError(f"Script error: {e}")


# Auto-register on import
registry.register(terminal)
registry.register(open_app)
registry.register(open_url)
registry.register(run_script)
