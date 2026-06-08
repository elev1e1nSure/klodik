"""Structured colored logger for the sidecar."""

from datetime import datetime

_RESET = "\033[0m"
_GRAY = "\033[90m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_BLUE = "\033[34m"
_BOLD = "\033[1m"


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _out(level: str, color: str, msg: str) -> None:
    print(f"{color}[{_now()}] {_BOLD}[{level}]{_RESET} {color}{msg}{_RESET}", flush=True)


def info(msg: str) -> None:
    _out("INFO", _GREEN, msg)


def warn(msg: str) -> None:
    _out("WARN", _YELLOW, msg)


def error(msg: str) -> None:
    _out("ERROR", _RED, msg)


def debug(msg: str) -> None:
    _out("DEBUG", _GRAY, msg)


def agent(msg: str) -> None:
    _out("AGENT", _CYAN, msg)


def ws(msg: str) -> None:
    _out("WS", _BLUE, msg)
