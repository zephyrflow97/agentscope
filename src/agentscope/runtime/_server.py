# -*- coding: utf-8 -*-
"""HTTP server for AgentScope Runtime using FastAPI."""
from contextlib import asynccontextmanager
from typing import AsyncIterator, Any

from .._logging import logger


# pylint: disable=too-many-statements
def build_app(runtime: Any, platform_client: Any | None = None) -> Any:
    """Build and return a FastAPI app exposing Runtime APIs.

    Args:
        runtime (`Any`):
            The runtime instance.
        platform_client (`Any | None`):
            Optional platform client for heartbeat.

    Returns:
        `Any`:
            A FastAPI application instance.

    Endpoints:
    - POST /invoke  (SSE streaming of Msg JSON)
    - GET  /health
    """
    # Lazy imports for third-party libraries
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse, StreamingResponse
    import json

    from ..message import Msg
    from ._app_base import SessionContext

    @asynccontextmanager
    async def lifespan(fastapi_app: Any) -> AsyncIterator[None]:
        """Lifespan context manager for startup/shutdown events."""
        # Startup
        if (
            fastapi_app.state.platform_client is not None
            and fastapi_app.state.platform_client.enabled
        ):
            await fastapi_app.state.platform_client.start()

        yield

        # Shutdown
        if fastapi_app.state.platform_client is not None:
            try:
                await fastapi_app.state.platform_client.stop()
            except Exception as e:  # noqa: BLE001
                logger.warning("Error stopping platform client: %s", e)
        try:
            await fastapi_app.state.runtime.shutdown()
        except Exception as e:  # noqa: BLE001
            logger.warning("Error during runtime shutdown: %s", e)

    app = FastAPI(lifespan=lifespan)

    # Attach runtime and platform client to app state
    app.state.runtime = runtime
    app.state.platform_client = platform_client

    @app.get("/health")
    async def health() -> Any:
        """Health check endpoint."""
        cfg = runtime.config if runtime.is_initialized else None
        instance_id = None
        if cfg and cfg.platform and cfg.platform.instance_id:
            instance_id = cfg.platform.instance_id

        import time

        return JSONResponse(
            {
                "status": "healthy",
                "instance_id": instance_id,
                "uptime": int(
                    getattr(runtime, "_start_time", time.time())
                    and time.time()
                    - getattr(runtime, "_start_time", time.time()),
                ),
            },
        )

    @app.post("/invoke")
    async def invoke(request: Request) -> Any:
        """Invoke the user's App and stream responses via SSE.

        Request body:
        {
          "session_id": "...",
          "message": { name, content, role },
          "metadata": { ... }
        }
        """
        try:
            payload = await request.json()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON: {e}",
            ) from e

        session_id = payload.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise HTTPException(
                status_code=400,
                detail="session_id is required",
            )

        message = payload.get("message")
        if not isinstance(message, dict):
            raise HTTPException(
                status_code=400,
                detail="message must be an object",
            )

        # Build Msg from dict (validates keys)
        try:
            msg = Msg.from_dict(message)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(
                status_code=400,
                detail=f"invalid message: {e}",
            ) from e

        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise HTTPException(
                status_code=400,
                detail="metadata must be an object",
            )

        ctx = SessionContext(session_id=session_id, metadata=metadata)

        # Record metrics for platform heartbeat
        if app.state.platform_client is not None:
            try:
                app.state.platform_client.record_request(session_id)
            except Exception:  # noqa: BLE001
                pass

        async def event_iter() -> AsyncIterator[bytes]:
            """Iterate over App streaming responses and yield SSE bytes."""
            # Call user's App (async iterator of Msg)
            try:
                async for out_msg in app.state.runtime.app(msg, ctx):
                    try:
                        line = json.dumps(
                            out_msg.to_dict(),
                            ensure_ascii=False,
                        )
                    except Exception:  # noqa: BLE001
                        # Fallback: text-only error info
                        line = json.dumps(
                            {
                                "name": "system",
                                "role": "assistant",
                                "content": "<serialization-error>",
                            },
                            ensure_ascii=False,
                        )
                    yield ("data: " + line + "\n\n").encode("utf-8")
            except Exception as e:  # noqa: BLE001
                err = json.dumps(
                    {
                        "error": {"code": "APP_ERROR", "message": str(e)},
                    },
                    ensure_ascii=False,
                )
                yield ("data: " + err + "\n\n").encode("utf-8")

            # End signal
            done = json.dumps(
                {
                    "name": "assistant",
                    "role": "assistant",
                    "content": "",
                    "metadata": {"done": True},
                },
                ensure_ascii=False,
            )
            yield ("data: " + done + "\n\n").encode("utf-8")

        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
        return StreamingResponse(
            event_iter(),
            media_type="text/event-stream",
            headers=headers,
        )

    return app
