"""Global exception handling so unexpected errors return clean JSON, not stack traces."""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("opscore.errors")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Log the real error server-side; return a generic message to the client.
        log.exception(f"Unhandled error on {request.method} {request.url.path}: {exc}")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
