
"""FastAPI server with WebSocket endpoint."""

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import agent
from config import settings
from connection import manager
from log import info, ws, error


@asynccontextmanager
async def lifespan(app: FastAPI):
    info("Sidecar starting...")
    task = asyncio.create_task(agent.initiative_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    info("Sidecar shutting down...")


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


_current_task: asyncio.Task | None = None


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global _current_task
    try:
        await manager.connect(websocket)
        agent.current_websocket = websocket
        ws("Client connected")
        try:
            while True:
                try:
                    data = await websocket.receive_text()
                except (RuntimeError, AssertionError):
                    break
                ws(f"Received: {data!r}")
                agent.last_activity = asyncio.get_event_loop().time()
                try:
                    payload = json.loads(data)
                    if payload.get("type") == "task":
                        task = payload.get("content", "")
                        ws(f"Starting agent_loop with task: {task!r}")
                        if _current_task and not _current_task.done():
                            _current_task.cancel()
                            try:
                                await _current_task
                            except asyncio.CancelledError:
                                pass
                        _current_task = asyncio.create_task(agent.agent_loop(task, websocket))
                except json.JSONDecodeError:
                    await manager.send_personal_message(
                        json.dumps({"type": "error", "content": "Invalid JSON"}), websocket
                    )
        except (WebSocketDisconnect, ConnectionResetError):
            ws("Client disconnected")
        finally:
            manager.disconnect(websocket)
            if agent.current_websocket is websocket:
                agent.current_websocket = None
    except Exception as e:
        error(f"Unhandled WS error: {type(e).__name__}: {e}")
        try:
            manager.disconnect(websocket)
        except Exception:
            pass
        if agent.current_websocket is websocket:
            agent.current_websocket = None
