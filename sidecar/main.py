import asyncio
import fnmatch
import json
import os
import re
import shutil
import subprocess
from contextlib import asynccontextmanager
from typing import Any

try:
    import pyautogui
except ImportError:
    pyautogui = None

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from litellm import completion


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Sidecar starting...")
    yield
    print("Sidecar shutting down...")


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except (RuntimeError, Exception):
            pass


manager = ConnectionManager()


SYSTEM_PROMPT = """Ты — компаньон на рабочем столе. Живёшь прямо на экране пользователя.

Правила:
- Отвечай ТОЛЬКО по-русски. Без исключений.
- Говори как живой человек в мессенджере. Коротко, простыми словами.
- Никаких официальных вступлений, списков возможностей, корпоративной болтовни.
- Без мотивационной фигни, без "я рад помочь", без перечислений функций.
- Можешь быть немного саркастичным, если контекст позволяет. Не робот.
- Если не понял — спроси кратко. Если что-то глупо — скажи прямо.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "terminal",
            "description": "Run a shell command in the terminal",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute"},
                    "cwd": {"type": "string", "description": "Working directory (optional)", "default": "."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read contents of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative file path"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write contents to a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative file path"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search files by name or content in a directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search pattern"},
                    "path": {"type": "string", "description": "Directory to search in", "default": "."},
                    "by_content": {"type": "boolean", "description": "Search in file contents", "default": False},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mkdir",
            "description": "Create a directory (including intermediate directories)",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to create"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List contents of a directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to list", "default": "."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "Move or rename a file or directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source path"},
                    "destination": {"type": "string", "description": "Destination path"},
                },
                "required": ["source", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_mouse",
            "description": "Move the mouse cursor to screen coordinates",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click the mouse at screen coordinates",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_script",
            "description": "Run a script file (python, bash, etc.)",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the script file"},
                    "args": {"type": "array", "items": {"type": "string"}, "description": "Arguments to pass", "default": []},
                },
                "required": ["path"],
            },
        },
    },
]


def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool and return the result."""
    try:
        if name == "terminal":
            cmd = arguments["command"]
            cwd = arguments.get("cwd", ".")
            result = subprocess.run(
                cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=30
            )
            out = result.stdout.strip()
            err = result.stderr.strip()
            if result.returncode != 0:
                return f"Exit code {result.returncode}\n{out}\n{err}".strip()
            return out or "(no output)"

        elif name == "read_file":
            path = arguments["path"]
            with open(path, "r", encoding="utf-8") as f:
                return f.read()

        elif name == "write_file":
            path = arguments["path"]
            content = arguments["content"]
            dir_name = os.path.dirname(path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"File written: {path}"

        elif name == "search":
            query = arguments["query"]
            path = arguments.get("path", ".")
            by_content = arguments.get("by_content", False)
            matches = []
            for root, dirs, files in os.walk(path):
                for filename in files:
                    full = os.path.join(root, filename)
                    rel = os.path.relpath(full, path)
                    if fnmatch.fnmatch(filename.lower(), f"*{query.lower()}*"):
                        matches.append(rel)
                    elif by_content:
                        try:
                            with open(full, "r", encoding="utf-8", errors="ignore") as f:
                                if query in f.read():
                                    matches.append(rel)
                        except Exception:
                            pass
            return "\n".join(matches) if matches else "No matches found"

        elif name == "mkdir":
            path = arguments["path"]
            os.makedirs(path, exist_ok=True)
            return f"Directory created: {path}"

        elif name == "list_dir":
            path = arguments.get("path", ".")
            items = os.listdir(path)
            return "\n".join(items) if items else "(empty)"

        elif name == "move_file":
            source = arguments["source"]
            destination = arguments["destination"]
            shutil.move(source, destination)
            return f"Moved {source} -> {destination}"

        elif name == "move_mouse":
            if pyautogui is None:
                return "Error: pyautogui not installed"
            x = arguments["x"]
            y = arguments["y"]
            pyautogui.moveTo(x, y, duration=0.5)
            return f"Mouse moved to ({x}, {y})"

        elif name == "click":
            if pyautogui is None:
                return "Error: pyautogui not installed"
            x = arguments["x"]
            y = arguments["y"]
            pyautogui.click(x, y)
            return f"Clicked at ({x}, {y})"

        elif name == "run_script":
            script_path = arguments["path"]
            args = arguments.get("args", [])
            result = subprocess.run(
                ["python", script_path, *args],
                capture_output=True, text=True, timeout=30,
            )
            out = result.stdout.strip()
            err = result.stderr.strip()
            if result.returncode != 0:
                return f"Exit code {result.returncode}\n{out}\n{err}".strip()
            return out or "(no output)"

        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        return f"Error: {e}"


MODEL = "ollama/dolphin-llama3"
MAX_TOOL_ITERATIONS = 5


async def agent_loop(task: str, websocket: WebSocket):
    """Agent loop with tool calling via litellm + ollama."""
    print(f"[Agent] Loop started for task: {task!r}")
    await manager.send_personal_message(
        json.dumps({"type": "status", "content": "thinking"}), websocket
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            print(f"[Agent] Calling LLM...")
            response = await asyncio.to_thread(
                completion,
                model=MODEL,
                messages=messages,
                api_base="http://localhost:11434",
            )
            print(f"[Agent] LLM responded")

            msg = response.choices[0].message
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)

            if not tool_calls:
                # Final answer
                content = msg.content or "Done."
                print(f"[LLM raw] {content!r}")
                content = re.sub(r"^(?i:echo)\s*[:\-]?\s*", "", content).strip()
                print(f"[LLM clean] {content!r}")
                await manager.send_personal_message(
                    json.dumps({"type": "message", "content": content}),
                    websocket,
                )
                break

            # Execute tools
            await manager.send_personal_message(
                json.dumps({"type": "status", "content": "working"}), websocket
            )

            for tool_call in tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)
                print(f"[Agent] Executing tool: {fn_name}")
                result = await asyncio.to_thread(execute_tool, fn_name, fn_args)
                print(f"[Agent] Tool result: {result[:200]!r}...")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": fn_name,
                    "content": result,
                })

        else:
            await manager.send_personal_message(
                json.dumps({"type": "message", "content": "Reached max tool iterations."}),
                websocket,
            )

    except Exception as e:
        print(f"[Agent] ERROR: {e}")
        await manager.send_personal_message(
            json.dumps({"type": "error", "content": str(e)}), websocket
        )

    await manager.send_personal_message(
        json.dumps({"type": "status", "content": "idle"}), websocket
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    print("[WS] Client connected")
    try:
        while True:
            data = await websocket.receive_text()
            print(f"[WS] Received: {data!r}")
            try:
                payload = json.loads(data)
                if payload.get("type") == "task":
                    task = payload.get("content", "")
                    print(f"[WS] Starting agent_loop with task: {task!r}")
                    asyncio.create_task(agent_loop(task, websocket))
            except json.JSONDecodeError:
                await manager.send_personal_message(
                    json.dumps({"type": "error", "content": "Invalid JSON"}), websocket
                )
    except WebSocketDisconnect:
        print("[WS] Client disconnected")
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765)
