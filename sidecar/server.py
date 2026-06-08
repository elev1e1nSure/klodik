"""FastAPI server with WebSocket endpoint and connection management."""

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

import agent
from config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Sidecar starting...")
    task = asyncio.create_task(agent.initiative_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
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
    """Manages active WebSocket connections."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket):
        try:
            self.active.remove(websocket)
        except ValueError:
            pass

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            if websocket.client_state == WebSocketState.DISCONNECTED:
                return
            await websocket.send_text(message)
        except (WebSocketDisconnect, RuntimeError, ConnectionResetError):
            pass
        except Exception:
            pass


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    agent.current_websocket = websocket
    print("[WS] Client connected")
    try:
        while True:
            data = await websocket.receive_text()
            print(f"[WS] Received: {data!r}")
            agent.last_activity = asyncio.get_event_loop().time()
            try:
                payload = json.loads(data)
                if payload.get("type") == "task":
                    task = payload.get("content", "")
                    print(f"[WS] Starting agent_loop with task: {task!r}")
                    asyncio.create_task(agent.agent_loop(task, websocket))
            except json.JSONDecodeError:
                await manager.send_personal_message(
                    json.dumps({"type": "error", "content": "Invalid JSON"}), websocket
                )
    except (WebSocketDisconnect, ConnectionResetError):
        print("[WS] Client disconnected")
    finally:
        manager.disconnect(websocket)
        if agent.current_websocket is websocket:
            agent.current_websocket = None
