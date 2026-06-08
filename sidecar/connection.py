"""WebSocket connection management — extracted to break server↔agent circular import."""

import json

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState


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
