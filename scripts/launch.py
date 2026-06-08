#!/usr/bin/env python3
"""Beautiful launcher for Klodik — Desktop AI Agent.

Supports multiple LLM providers:
  - Groq (cloud, fast)
  - OpenAI (gpt-4o, etc.)
  - Google Gemini
  - Ollama (local models)

Usage:
    python scripts/launch.py

Prerequisites:
    - Node.js + pnpm
    - Python 3.12+ with sidecar/.venv
    - Rust (for Tauri)
    - .env configured with API key for chosen provider
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Force UTF-8 on Windows console to prevent UnicodeEncodeError in rich
if sys.platform == "win32":
    import ctypes
    _kernel32 = ctypes.windll.kernel32
    _kernel32.SetConsoleOutputCP(65001)
    _kernel32.SetConsoleCP(65001)
    # Reopen stdout/stderr with UTF-8 if still on cp1252
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf_8"):
        import io
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

try:
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, Confirm
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.text import Text
    from rich.rule import Rule
    from rich import box
except ImportError:
    print("ERROR: 'rich' is not installed. Run: pip install rich")
    sys.exit(1)

console = Console()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
SIDECAR_DIR = PROJECT_ROOT / "sidecar"

# ---------------------------------------------------------------------------
# Provider presets
# ---------------------------------------------------------------------------
PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "groq": {
        "icon": "⚡",
        "color": "bold bright_magenta",
        "description": "Groq Cloud — blazing fast inference",
        "models": [
            "groq/llama-3.3-70b-versatile",
            "groq/llama-3.1-405b-reasoning",
            "groq/llama-3.1-8b-instant",
            "groq/mixtral-8x7b-32768",
            "groq/gemma2-9b-it",
        ],
        "key_env": "GROQ_API_KEY",
        "key_hint": "https://console.groq.com/keys",
        "needs_key": True,
        "auto_model": "groq/llama-3.3-70b-versatile",
    },
    "openai": {
        "icon": "🌐",
        "color": "bold bright_green",
        "description": "OpenAI — GPT-4o, o1, o3-mini",
        "models": [
            "gpt-4o",
            "gpt-4o-mini",
            "o1",
            "o1-mini",
            "o3-mini",
            "gpt-4-turbo",
        ],
        "key_env": "OPENAI_API_KEY",
        "key_hint": "https://platform.openai.com/api-keys",
        "needs_key": True,
        "auto_model": "gpt-4o",
    },
    "gemini": {
        "icon": "💎",
        "color": "bold bright_blue",
        "description": "Google Gemini — 2.0 Flash / Pro",
        "models": [
            "gemini/gemini-2.0-flash",
            "gemini/gemini-2.0-pro",
            "gemini/gemini-1.5-flash",
            "gemini/gemini-1.5-pro",
        ],
        "key_env": "GEMINI_API_KEY",
        "key_hint": "https://aistudio.google.com/app/apikey",
        "needs_key": True,
        "auto_model": "gemini/gemini-2.0-flash",
    },
    "openrouter": {
        "icon": "🔀",
        "color": "bold bright_white",
        "description": "OpenRouter — 100+ models via one key",
        "models": [],
        "key_env": "OPENROUTER_API_KEY",
        "key_hint": "https://openrouter.ai/keys",
        "needs_key": True,
        "auto_model": "openrouter/meta-llama/llama-3.3-70b-instruct",
    },
    "ollama": {
        "icon": "🦙",
        "color": "bold bright_yellow",
        "description": "Ollama — local models (llama3, mistral, etc.)",
        "models": [],  # fetched dynamically
        "key_env": None,
        "key_hint": "http://localhost:11434",
        "needs_key": False,
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str] | str, cwd: Path | None = None, capture: bool = True) -> tuple[int, str, str]:
    """Run a shell command and return (returncode, stdout, stderr)."""
    shell = isinstance(cmd, str)
    if not shell and sys.platform == "win32":
        # Windows subprocess without shell does not resolve .cmd/.bat
        resolved = shutil.which(cmd[0])
        if resolved:
            cmd = [resolved] + cmd[1:]
    result = subprocess.run(
        cmd,
        shell=shell,
        cwd=cwd,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stdout, result.stderr


def _detect_venv_python() -> Path | None:
    """Find the Python executable inside sidecar/.venv."""
    candidates = [
        SIDECAR_DIR / ".venv" / "Scripts" / "python.exe",
        SIDECAR_DIR / ".venv_new" / "Scripts" / "python.exe",
        SIDECAR_DIR / "venv" / "Scripts" / "python.exe",
        SIDECAR_DIR / ".venv" / "bin" / "python",
        SIDECAR_DIR / "venv" / "bin" / "python",
    ]
    for c in candidates:
        if c.exists():
            return c
    # Fallback: system python if it has required packages
    return Path(sys.executable) if sys.executable else None


def _detect_lang_by_ip() -> str:
    """Detect language by geo IP. Returns 'ru' for RU/BY/KZ/UA, else 'en'."""
    if requests is None:
        return "en"
    try:
        r = requests.get("https://ipapi.co/json/", timeout=5)
        r.raise_for_status()
        data = r.json()
        country = data.get("country_code", "").upper()
        if country in {"RU", "BY", "KZ", "UA"}:
            return "ru"
    except Exception:
        pass
    return "en"


def _load_env() -> dict[str, str]:
    """Parse current .env file into a dict."""
    env: dict[str, str] = {}
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip()
    return env


def _save_env(env: dict[str, str]) -> None:
    """Write dict back to .env file, preserving comments."""
    lines: list[str] = []
    seen: set[str] = set()

    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\n")
                stripped = line.strip()
                if stripped.startswith("#") or "=" not in stripped:
                    lines.append(line)
                    continue
                key, _, _ = stripped.partition("=")
                key = key.strip()
                if key in env:
                    lines.append(f"{key}={env[key]}")
                    seen.add(key)
                else:
                    lines.append(line)

    for k, v in env.items():
        if k not in seen:
            lines.append(f"{k}={v}")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _fetch_ollama_models(base_url: str = "http://localhost:11434") -> list[str]:
    """Fetch available models from local Ollama instance."""
    if requests is None:
        return []
    try:
        r = requests.get(f"{base_url}/api/tags", timeout=3)
        r.raise_for_status()
        data = r.json()
        models = [m.get("name", m.get("model", "")) for m in data.get("models", [])]
        return [f"ollama/{m}" for m in models if m]
    except Exception:
        return []


def _fetch_provider_models(provider: str, api_key: str) -> list[str]:
    """Fetch live model list from provider API."""
    if requests is None:
        return []
    try:
        if provider == "groq":
            r = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5,
            )
            r.raise_for_status()
            return [m["id"] for m in r.json().get("data", []) if m.get("id")]
        elif provider == "openai":
            r = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5,
            )
            r.raise_for_status()
            # Filter to chat models
            return sorted(
                [m["id"] for m in r.json().get("data", [])
                 if m.get("id", "").startswith("gpt-")],
                reverse=True,
            )
        elif provider == "openrouter":
            r = requests.get(
                "https://openrouter.ai/api/v1/models",
                timeout=5,
            )
            r.raise_for_status()
            raw = [m["id"] for m in r.json().get("data", []) if m.get("id")]
            return [f"openrouter/{m}" for m in raw]
    except Exception:
        return []
    return []


# ---------------------------------------------------------------------------
# UI screens
# ---------------------------------------------------------------------------

def _show_welcome() -> None:
    """Display the beautiful welcome banner."""
    banner = Text(
        r"""
⠀⠀⠀⠀⠀⠀⠀⠀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⢸⣿⡿⠿⣿⣿⣿⣿⣿⣿⣿⠿⢿⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⢸⣿⡁⠀⢸⣿⣿⣿⣿⣿⣇⠀⠀⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⣶⣶⣶⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣶⣶⣶⠀⠀⠀⠀⠀
⠀⠀⠀⠀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠙⠛⠛⢻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡟⠛⠛⠛⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⠿⣿⣿⡿⠿⠿⣿⣿⡿⢿⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⠀⣿⣿⡇⠀⠀⣿⣿⡇⢸⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠘⠛⠛⠀⠛⠛⠃⠀⠀⠛⠛⠃⠘⠛⠃⠀⠀⠀⠀⠀⠀⠀⠀
        """,
        style="bold bright_cyan",
    )
    subtitle = Text(
        "Desktop AI Agent  —  Pixel-art companion for your screen",
        style="dim italic",
    )
    console.print(Panel(
        Text.assemble(banner, "\n", subtitle),
        title="[bold bright_white]🤖  Klodik Launcher[/]",
        subtitle="[dim]v1.0.0[/]",
        border_style="bright_cyan",
        box=box.ROUNDED,
        padding=(1, 4),
    ))


def _check_prerequisites() -> dict[str, tuple[bool, str]]:
    """Check Node, pnpm, Python venv, Rust."""
    results: dict[str, tuple[bool, str]] = {}

    # Node.js
    rc, out, _ = _run(["node", "--version"])
    results["Node.js"] = (rc == 0, out.strip() if rc == 0 else "not found")

    # pnpm
    rc, out, _ = _run(["pnpm", "--version"])
    results["pnpm"] = (rc == 0, out.strip() if rc == 0 else "not found")

    # Python venv
    py = _detect_venv_python()
    if py:
        rc, out, _ = _run([str(py), "--version"])
        results["Python venv"] = (rc == 0, out.strip() if rc == 0 else "error")
    else:
        results["Python venv"] = (False, "venv not found — create with: python -m venv sidecar\\.venv")

    # Rust
    rc, out, _ = _run(["rustc", "--version"])
    results["Rust"] = (rc == 0, out.strip() if rc == 0 else "not found")

    return results


def _render_prerequisites() -> None:
    """Print prerequisite check results as a table."""
    env = _load_env()
    lang = env.get("LAUNCHER_LANG", "ru")
    results = _check_prerequisites()
    table = Table(
        title=f"[bold]{_t('system_check', lang)}[/]",
        box=box.SIMPLE_HEAD,
        show_header=False,
        padding=(0, 2),
    )
    table.add_column("Component", style="bold")
    table.add_column("Status", min_width=30)

    for name, (ok, detail) in results.items():
        icon = "[green]✓[/]" if ok else "[red]✗[/]"
        style = "green" if ok else "red"
        table.add_row(f"{icon} {name}", f"[{style}]{detail}[/]")

    console.print(table)
    console.print()

    if not all(ok for ok, _ in results.values()):
        console.print(Panel(
            "[yellow]Some prerequisites are missing.[/]\n"
            "Fix them before launching, or the app may fail to start.",
            border_style="yellow",
        ))
        console.print()


def _render_env_status(env: dict[str, str]) -> None:
    """Show current .env configuration."""
    lang = env.get("LAUNCHER_LANG", "ru")
    provider = env.get("PROVIDER", "groq")
    model = env.get("MODEL", "—")

    preset = PROVIDER_PRESETS.get(provider, {})
    icon = preset.get("icon", "🔧")
    key_env = preset.get("key_env")
    key_set = f"[green]{_t('set', lang)}[/]" if (key_env and env.get(key_env)) or not key_env else f"[red]{_t('missing', lang)}[/]"

    table = Table(title=f"[bold]{_t('current_config', lang)}[/]", box=box.SIMPLE, show_header=False)
    table.add_column("Setting", style="bold cyan")
    table.add_column("Value")
    table.add_row(_t("provider", lang), f"{icon} {provider}")
    table.add_row(_t("model", lang), model)
    table.add_row(_t("api_key", lang), key_set)
    console.print(table)
    console.print()


def _select_provider(env: dict[str, str]) -> dict[str, str] | None:
    """Interactive provider & model selection. Returns None if cancelled."""
    lang = env.get("LAUNCHER_LANG", "ru")
    console.print(Rule(f"[bold]{_t('provider_selection', lang)}[/]", style="cyan"))

    # Build provider table
    table = Table(box=box.ROUNDED, show_header=True, padding=(0, 1))
    table.add_column("#", style="bold", justify="center")
    table.add_column(_t("provider", lang), style="bold")
    table.add_column("Description", style="dim")
    table.add_column("Key Required", justify="center")

    names = list(PROVIDER_PRESETS.keys())
    for i, name in enumerate(names, 1):
        p = PROVIDER_PRESETS[name]
        icon = p["icon"]
        key_req = "[red]yes[/]" if p["needs_key"] else "[green]no[/]"
        table.add_row(f"[ {i} ]", f"{icon} {name}", p["description"], key_req)
    table.add_row("[ 0 ]", _t("back", lang), "", "")

    console.print(table)
    console.print()

    choice = Prompt.ask(
        _t("select_provider", lang),
        choices=[str(i) for i in range(0, len(names) + 1)],
        default="1",
    )
    if choice == "0":
        return None
    provider = names[int(choice) - 1]
    preset = PROVIDER_PRESETS[provider]
    console.print(f"\n[bold]{preset['icon']} Selected:[/] [{preset['color']}]{provider}[/]\n")

    # API key first
    api_key = ""
    if preset["needs_key"]:
        key_env = preset["key_env"]
        current_key = env.get(key_env, "")
        if current_key and not current_key.startswith("your_"):
            masked = current_key[:8] + "***" if len(current_key) > 10 else "***"
            console.print(f"[dim]Current {key_env}: {masked}[/]")
        else:
            console.print(f"[yellow]⚠ {key_env} not set.[/]")
            hint = preset.get("key_hint", "")
            if hint:
                console.print(f"[dim]Get it at: {hint}[/]")
        new_key = Prompt.ask(
            _t("api_key_paste", lang),
            password=True,
            default="",
        )
        if new_key:
            env[key_env] = new_key
            api_key = new_key
        else:
            api_key = current_key

    # Fetch models from API (if supported)
    models: list[str] = []
    auto_model = preset.get("auto_model", "")
    if provider in ("groq", "openai", "openrouter") and api_key:
        with console.status(f"[yellow]{_t('fetching_models', lang)}[/]"):
            models = _fetch_provider_models(provider, api_key)
    elif provider == "gemini":
        models = preset["models"].copy()
    elif provider == "ollama":
        with console.status("[yellow]Checking local Ollama...[/]"):
            models = _fetch_ollama_models(env.get("OLLAMA_BASE_URL", "http://localhost:11434"))
        if not models:
            console.print("[yellow]⚠ Ollama not detected on localhost:11434.[/]")

    # Show model picker: [0] Auto-select + numbered list
    if models:
        model_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        model_table.add_column("#", justify="right")
        model_table.add_column(_t("model", lang))
        model_table.add_row("[ 0 ]", f"[green]{_t('auto_select', lang)}[/] ({auto_model or models[0]})")
        for i, m in enumerate(models[:20], 1):  # cap at 20
            label = m
            if len(label) > 50:
                label = label[:47] + "..."
            model_table.add_row(f"[ {i} ]", label)
        console.print(model_table)
        console.print()
        model_choice = Prompt.ask(
            _t("select_model", lang),
            choices=[str(i) for i in range(0, min(len(models), 20) + 1)],
            default="0",
        )
        if model_choice == "0":
            # Auto-select
            model = auto_model if auto_model else models[0]
        else:
            model = models[int(model_choice) - 1]
    else:
        # Fallback: manual entry
        default_model = auto_model or preset.get("models", [""])[0] or "ollama/llama3"
        model = Prompt.ask("Model name", default=default_model)

    console.print(f"[green]{_t('model_picked', lang)}:[/] [bold]{model}[/]\n")

    # Temperature / max_tokens (optional quick config)
    if Confirm.ask(f"[dim]{_t('adjust_params', lang)}[/]", default=False):
        temp = Prompt.ask(_t("temp", lang), default=env.get("TEMPERATURE", "0.7"))
        max_tok = Prompt.ask(_t("max_tokens", lang), default=env.get("MAX_TOKENS", "512"))
        env["TEMPERATURE"] = temp
        env["MAX_TOKENS"] = max_tok

    env["PROVIDER"] = provider
    env["MODEL"] = model
    return env


def _launch_app(py: Path, env: dict[str, str]) -> bool:
    """Start sidecar + Tauri dev mode. Returns True if launched, False otherwise."""
    is_win = platform.system() == "Windows"
    lang = env.get("LAUNCHER_LANG", "ru")
    ws_port = int(env.get("WS_PORT", "8765"))

    # 1) Ensure port is free
    if _is_port_in_use(ws_port):
        if not _clear_port(ws_port, lang):
            console.print(f"[red]{_t('launch_failed', lang)}[/]")
            return False

    # 2) Start sidecar
    sidecar_env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        sidecar = subprocess.Popen(
            [str(py), str(SIDECAR_DIR / "main.py")],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=sidecar_env,
        )
    except Exception as e:
        console.print(f"[red]{_t('launch_failed', lang)}: {e}[/]")
        return False

    # 3) Start Tauri
    tauri_cmd = ["pnpm", "tauri", "dev"]
    if is_win:
        pnpm_path = shutil.which("pnpm")
        if pnpm_path:
            tauri_cmd = [pnpm_path, "tauri", "dev"]
    try:
        tauri = subprocess.Popen(
            tauri_cmd,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as e:
        console.print(f"[red]{_t('launch_failed', lang)}: {e}[/]")
        sidecar.terminate()
        return False

    console.print(Panel(
        f"[green]🚀 {_t('launching', lang)}[/]\n"
        f"[dim]{_t('sidecar_pid', lang)}: {sidecar.pid} | {_t('tauri_pid', lang)}: {tauri.pid}[/]\n"
        f"[dim]{_t('ctrl_c', lang)}.[/]",
        border_style="green",
    ))

    def _force_kill(proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        if is_win:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
            )
        else:
            proc.kill()

    import queue
    import threading
    import re

    log_queue: queue.Queue = queue.Queue()

    _ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

    def _strip_ansi(s: str) -> str:
        return _ANSI_RE.sub("", s)

    def _reader(proc: subprocess.Popen, tag: str) -> None:
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                log_queue.put((tag, line))
        except Exception:
            pass

    threading.Thread(target=_reader, args=(sidecar, "sidecar"), daemon=True).start()
    threading.Thread(target=_reader, args=(tauri, "tauri"), daemon=True).start()

    try:
        while True:
            try:
                tag, line = log_queue.get(timeout=0.1)
                stripped = _strip_ansi(line.rstrip())
                ts = datetime.now().strftime("[%H:%M:%S]")
                if tag == "sidecar":
                    console.print(f"[cyan]{ts} [sidecar][/] {stripped}")
                else:
                    # Tauri: show only errors / build finished / app running
                    lower = stripped.lower()
                    if "warning:" in lower:
                        console.print(f"[yellow]{ts} [tauri] [WARN] {stripped}[/]")
                    elif any(k in lower for k in ("error", "failed", "panic", "compile error")):
                        console.print(f"[red]{ts} [tauri] [ERROR] {stripped}[/]")
                    elif "finished" in lower and "dev" in lower:
                        console.print(f"[green]{ts} [tauri] Build finished — running[/]")
                    elif "running" in lower and "klodik.exe" in lower:
                        console.print(f"[green]{ts} [tauri] App started[/]")
                    # Suppress all other tauri noise (Vite, cargo progress, etc.)
            except queue.Empty:
                pass

            if sidecar.poll() is not None and tauri.poll() is not None and log_queue.empty():
                break
    except KeyboardInterrupt:
        console.print(f"\n[yellow]{_t('shutting_down', lang)}[/]")
        sidecar.terminate()
        tauri.terminate()
        try:
            sidecar.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _force_kill(sidecar)
        try:
            tauri.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _force_kill(tauri)
    return True


# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------

_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "menu_title": "Main Menu",
        "launch": "Launch Klodik",
        "configure": "Configure provider / model",
        "language": "Switch language",
        "exit": "Exit",
        "choose": "Choose option",
        "system_check": "System Check",
        "current_config": "Current Config",
        "provider": "Provider",
        "model": "Model",
        "api_key": "API Key",
        "set": "✓ set",
        "missing": "✗ missing",
        "launching": "Launching Klodik...",
        "sidecar_pid": "Sidecar PID",
        "tauri_pid": "Tauri PID",
        "ctrl_c": "Press Ctrl+C to stop",
        "shutting_down": "Shutting down...",
        "no_venv": "Could not find Python in sidecar/.venv",
        "create_venv": "Create it: python -m venv sidecar\\.venv",
        "config_saved": "✓ Configuration saved.",
        "bye": "Goodbye! Run again when ready.",
        "provider_selection": "Provider Selection",
        "select_provider": "Select provider",
        "select_model": "Select model",
        "api_key_prompt": "Paste your API key (Enter to keep current)",
        "adjust_params": "Adjust generation parameters?",
        "temp": "Temp",
        "max_tokens": "Max tokens",
        "lang_switch": "Select language",
        "lang_en": "English",
        "lang_ru": "Русский",
        "back": "←  Back",
        "port_in_use": "Port {port} is already in use",
        "kill_confirm": "Kill process {pid} using port {port}?",
        "killed": "Killed process {pid}",
        "skipped": "Skipped",
        "rate_limit": "API rate limit reached. Wait a minute and try again.",
        "api_error": "API error",
        "unexpected_error": "Unexpected error",
        "launch_failed": "Launch failed",
        "db_manage": "Memory database",
        "db_show": "Show recent conversations",
        "db_clear": "Clear all conversations",
        "db_cleared": "Memory cleared",
        "db_empty": "No conversations yet",
        "db_count": "{count} conversations",
        "api_key_menu": "API key",
        "api_key_current": "Current key",
        "api_key_paste": "Paste API key",
        "api_key_saved": "API key saved",
        "auto_select": "Auto-select best model",
        "fetching_models": "Fetching models from API...",
        "model_picked": "Selected model",
        "invalid_choice": "Invalid choice. Try again.",
    },
    "ru": {
        "menu_title": "Главное меню",
        "launch": "Запустить Клодика",
        "configure": "Настроить провайдер / модель",
        "language": "Сменить язык",
        "exit": "Выход",
        "choose": "Выбери пункт",
        "system_check": "Проверка системы",
        "current_config": "Текущая конфигурация",
        "provider": "Провайдер",
        "model": "Модель",
        "api_key": "API-ключ",
        "set": "✓ есть",
        "missing": "✗ нет",
        "launching": "Запуск Клодика...",
        "sidecar_pid": "Sidecar PID",
        "tauri_pid": "Tauri PID",
        "ctrl_c": "Ctrl+C — остановить",
        "shutting_down": "Завершаю работу...",
        "no_venv": "Не нашёл Python в sidecar/.venv",
        "create_venv": "Создай: python -m venv sidecar\\.venv",
        "config_saved": "✓ Настройки сохранены.",
        "bye": "Пока! Запускай снова, когда будешь готов.",
        "provider_selection": "Выбор провайдера",
        "select_provider": "Выбери провайдера",
        "select_model": "Выбери модель",
        "api_key_prompt": "Вставь API-ключ (Enter — оставить текущий)",
        "adjust_params": "Настроить параметры генерации?",
        "temp": "Температура",
        "max_tokens": "Макс. токенов",
        "lang_switch": "Выбери язык",
        "lang_en": "English",
        "lang_ru": "Русский",
        "back": "←  Назад",
        "port_in_use": "Порт {port} уже занят",
        "kill_confirm": "Убить процесс {pid}, использующий порт {port}?",
        "killed": "Процесс {pid} остановлен",
        "skipped": "Пропущено",
        "rate_limit": "Достигнут лимит API. Подожди минуту и попробуй снова.",
        "api_error": "Ошибка API",
        "unexpected_error": "Неожиданная ошибка",
        "launch_failed": "Запуск не удался",
        "db_manage": "База данных памяти",
        "db_show": "Показать последние диалоги",
        "db_clear": "Очистить все диалоги",
        "db_cleared": "Память очищена",
        "db_empty": "Пока нет диалогов",
        "db_count": "{count} диалогов",
        "api_key_menu": "API-ключ",
        "api_key_current": "Текущий ключ",
        "api_key_paste": "Вставь API-ключ",
        "api_key_saved": "Ключ сохранён",
        "auto_select": "Авто-выбор лучшей модели",
        "fetching_models": "Загружаю модели из API...",
        "model_picked": "Выбрана модель",
        "invalid_choice": "Неверный выбор. Попробуй ещё.",
    },
}


def _t(key: str, lang: str, **kwargs: Any) -> str:
    """Get translated string with optional formatting."""
    text = _TEXTS.get(lang, _TEXTS["en"]).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def _is_port_in_use(port: int) -> bool:
    """Check if a local TCP port is already bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return True
    return False


def _find_process_on_port(port: int) -> int | None:
    """Find the PID listening on the given port (Windows-only for now)."""
    if sys.platform != "win32":
        return None
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            shell=False, timeout=5,
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                if parts:
                    try:
                        return int(parts[-1])
                    except ValueError:
                        continue
    except Exception:
        pass
    return None


def _clear_port(port: int, lang: str) -> bool:
    """Ask user before killing a process that occupies the port."""
    if not _is_port_in_use(port):
        return True
    pid = _find_process_on_port(port)
    if pid is None:
        console.print(f"[yellow]{_t('port_in_use', lang, port=port)}[/]")
        return False
    console.print(f"[yellow]{_t('port_in_use', lang, port=port)} (PID {pid})[/]")
    if Confirm.ask(_t("kill_confirm", lang, pid=pid, port=port), default=True):
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True, timeout=5,
            )
            time.sleep(0.5)
            console.print(f"[green]{_t('killed', lang, pid=pid)}[/]")
            return True
        except Exception as e:
            console.print(f"[red]{_t('killed', lang, pid=pid)}: {e}[/]")
            return False
    else:
        console.print(f"[dim]{_t('skipped', lang)}[/]")
        return False


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def _show_menu(env: dict[str, str]) -> str | None:
    """Display main menu and return user choice."""
    lang = env.get("LAUNCHER_LANG", "ru")
    provider = env.get("PROVIDER", "groq")
    model = env.get("MODEL", "—")
    preset = PROVIDER_PRESETS.get(provider, {})

    sprite = Text(
        r"""⠀⠀⠀⠀⠀⠀⠀⠀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⢸⣿⡿⠿⣿⣿⣿⣿⣿⣿⣿⠿⢿⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⢸⣿⡁⠀⢸⣿⣿⣿⣿⣿⣇⠀⠀⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⣶⣶⣶⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣶⣶⣶⠀⠀⠀⠀⠀
⠀⠀⠀⠀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠙⠛⠛⢻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡟⠛⠛⠛⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⠿⣿⣿⡿⠿⠿⣿⣿⡿⢿⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⠀⣿⣿⡇⠀⠀⣿⣿⡇⢸⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠘⠛⠛⠀⠛⠛⠃⠀⠀⠛⠛⠃⠘⠛⠃⠀⠀⠀⠀⠀⠀⠀⠀""",
        style="bold bright_cyan",
    )

    lines: list[Text] = [
        Text.assemble(("[ 1 ]", "bold cyan"), "  🚀  ", _t("launch", lang)),
        Text.assemble(("[ 2 ]", "bold cyan"), "  ⚙️  ", _t("configure", lang)),
        Text.assemble(("[ 3 ]", "bold cyan"), "  🌐  ", _t("language", lang)),
        Text.assemble(("[ 4 ]", "bold cyan"), "  🧠  ", _t("db_manage", lang)),
        Text.assemble(("[ 5 ]", "bold cyan"), "  *   ", _t("api_key_menu", lang)),
        Text.assemble(("[ 6 ]", "bold cyan"), "  <-  ", _t("exit", lang)),
    ]

    config_line = (
        f"[dim]{_t('provider', lang)}:[/] {preset.get('icon', '🔧')} {provider}  |  "
        f"[dim]{_t('model', lang)}:[/] {model}"
    )
    console.print(Panel(
        Group(sprite, *lines),
        title=f"[bold]🤖 {_t('menu_title', lang)}[/]  ·  {config_line}",
        border_style="bright_cyan",
        padding=(0, 2),
    ))

    choice = Prompt.ask(
        f"{_t('choose', lang)}",
        choices=["1", "2", "3", "4", "5", "6"],
        default="1",
    )
    return choice


def _switch_language(env: dict[str, str]) -> dict[str, str]:
    """Toggle language ru ↔ en instantly."""
    lang = env.get("LAUNCHER_LANG", "ru")
    new_lang = "en" if lang == "ru" else "ru"
    env["LAUNCHER_LANG"] = new_lang
    _save_env(env)
    console.print(f"[green]✓ {_t('lang_en' if new_lang == 'en' else 'lang_ru', new_lang)}[/]\n")
    return env


def _enter_api_key(env: dict[str, str]) -> None:
    """Quickly enter API key for the current provider."""
    lang = env.get("LAUNCHER_LANG", "ru")
    provider = env.get("PROVIDER", "groq")
    preset = PROVIDER_PRESETS.get(provider, {})
    key_env = preset.get("key_env")

    if not key_env:
        console.print(f"[yellow]{provider} does not need an API key.[/]\n")
        return

    current_key = env.get(key_env, "")
    if current_key and not current_key.startswith("your_"):
        masked = current_key[:8] + "***" if len(current_key) > 10 else "***"
        console.print(f"[dim]{_t('api_key_current', lang)} ({key_env}): {masked}[/]")
    else:
        console.print(f"[yellow]⚠ {key_env} not set.[/]")
        hint = preset.get("key_hint", "")
        if hint:
            console.print(f"[dim]Get it at: {hint}[/]")

    new_key = Prompt.ask(
        _t("api_key_paste", lang),
        password=True,
        default="",
    )
    if new_key:
        env[key_env] = new_key
        _save_env(env)
        console.print(f"[green]✓ {_t('api_key_saved', lang)} ({key_env})[/]\n")
    else:
        console.print("[dim]No changes.[/]\n")


def _manage_memory(env: dict[str, str]) -> None:
    """Show or clear the agent's memory database."""
    import sqlite3

    lang = env.get("LAUNCHER_LANG", "ru")
    db_path = PROJECT_ROOT / "sidecar" / "memory.db"

    if not db_path.exists():
        console.print(f"[yellow]{_t('db_empty', lang)}[/]\n")
        return

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("#", justify="center", style="bold cyan")
    table.add_column("Option")
    table.add_row("1", _t("db_show", lang))
    table.add_row("2", _t("db_clear", lang))
    table.add_row("0", _t("back", lang))
    console.print(table)
    console.print()

    choice = Prompt.ask(
        _t("choose", lang),
        choices=["0", "1", "2"],
        default="0",
    )
    if choice == "0":
        return

    if choice == "1":
        try:
            with sqlite3.connect(str(db_path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT timestamp, task, response FROM interactions ORDER BY id DESC LIMIT 10"
                ).fetchall()
            if not rows:
                console.print(f"[yellow]{_t('db_empty', lang)}[/]\n")
                return
            console.print(f"[dim]{_t('db_count', lang, count=len(rows))}[/]\n")
            for row in rows:
                ts = row["timestamp"][:19].replace("T", " ")
                task = row["task"][:60]
                resp = row["response"][:80].replace("\n", " ")
                console.print(Panel(
                    f"[bold cyan]{ts}[/]\n"
                    f"[dim]📝[/] {task}…\n"
                    f"[dim]💬[/] {resp}…",
                    border_style="bright_cyan",
                    padding=(0, 1),
                ))
            console.print()
        except Exception as e:
            console.print(f"[red]Error reading DB: {e}[/]\n")
        return

    if choice == "2":
        confirm = Prompt.ask(
            "[red]Удалить ВСЕ диалоги?[/]" if lang == "ru" else "[red]Delete ALL conversations?[/]",
            choices=["y", "n"],
            default="n",
        )
        if confirm == "y":
            try:
                with sqlite3.connect(str(db_path)) as conn:
                    conn.execute("DELETE FROM interactions")
                console.print(f"[green]✓ {_t('db_cleared', lang)}[/]\n")
            except Exception as e:
                console.print(f"[red]Error: {e}[/]\n")
        return


def main() -> None:
    _render_prerequisites()

    env = _load_env()

    # Auto-detect language on first run
    if "LAUNCHER_LANG" not in env:
        detected = _detect_lang_by_ip()
        env["LAUNCHER_LANG"] = detected
        _save_env(env)
        console.print(f"[dim]Detected language: {_t('lang_en' if detected == 'en' else 'lang_ru', detected)}[/]")

    has_key = any(
        env.get(p["key_env"], "") and not env[p["key_env"]].startswith("your_")
        for p in PROVIDER_PRESETS.values()
        if p["needs_key"]
    )

    # If first run (no config), force config first
    if not env or not has_key:
        lang = env.get("LAUNCHER_LANG", "ru")
        console.print(Panel(
            "[yellow]No valid .env found or API keys missing.[/]\n"
            "Let's configure your provider and model."
            if lang == "en" else
            "[yellow]Не найден .env или API-ключи отсутствуют.[/]\n"
            "Настроим провайдера и модель.",
            border_style="yellow",
        ))
        console.print()
        new_env = _select_provider(env)
        if new_env is None:
            # User cancelled — keep defaults and go to menu
            new_env = env
        env = new_env
        _save_env(env)
        console.print(f"[green]{_t('config_saved', env.get('LAUNCHER_LANG', 'ru'))}[/]\n")

    # Main loop
    while True:
        choice = _show_menu(env)
        if choice == "1":
            break  # Launch
        elif choice == "2":
            new_env = _select_provider(env)
            if new_env is not None:
                env = new_env
                _save_env(env)
                console.print(f"[green]{_t('config_saved', env.get('LAUNCHER_LANG', 'ru'))}[/]\n")
            else:
                console.print()
        elif choice == "3":
            env = _switch_language(env)
        elif choice == "4":
            _manage_memory(env)
        elif choice == "5":
            _enter_api_key(env)
        elif choice == "6":
            console.print(f"[dim]{_t('bye', env.get('LAUNCHER_LANG', 'ru'))}[/]")
            sys.exit(0)
        else:
            console.print(f"[red]{_t('invalid_choice', env.get('LAUNCHER_LANG', 'ru'))}[/]\n")

    # Launch
    py = _detect_venv_python()
    if not py:
        lang = env.get("LAUNCHER_LANG", "ru")
        console.print(f"[red]{_t('no_venv', lang)}[/]")
        console.print(f"[dim]{_t('create_venv', lang)}[/]")
        sys.exit(1)

    ok = _launch_app(py, env)
    if not ok:
        console.print(f"[red]{_t('launch_failed', env.get('LAUNCHER_LANG', 'ru'))}[/]")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/]")
        sys.exit(0)
    except Exception as e:
        console.print(Panel(
            f"[red bold]{_t('unexpected_error', 'en')}[/]\n"
            f"[dim]{type(e).__name__}: {e}[/]",
            border_style="red",
        ))
        sys.exit(1)
