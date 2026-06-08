"""Entry point for the sidecar FastAPI server."""

import uvicorn

from config import settings
from log import info
from server import app

if __name__ == "__main__":
    info("Sidecar starting...")
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=settings.ws_port,
        log_level="warning",
        access_log=False,
    )
