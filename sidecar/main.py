"""Entry point for the sidecar FastAPI server."""

import uvicorn

from config import settings
from server import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=settings.ws_port)
