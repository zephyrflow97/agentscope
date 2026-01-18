# -*- coding: utf-8 -*-
"""HTTP+SSE server for AgentScope platform.

This module implements the HTTP server with Server-Sent Events (SSE)
for streaming chat responses from agents.
"""
import asyncio
import json
from typing import TYPE_CHECKING, Any, AsyncGenerator

from ..message import TextBlock
from ..tool import ToolResponse

if TYPE_CHECKING:
    from ..agent import AgentBase
    from .session_backend import PlatformSessionBackend


class ChatServer:
    """HTTP+SSE server for agent chat interactions.

    Provides endpoints:
    - POST /chat: Send a message and receive SSE response stream
    - GET /health: Health check endpoint
    """

    def __init__(
        self,
        agent: "AgentBase",
        session_backend: "PlatformSessionBackend | None" = None,
        host: str = "0.0.0.0",
        port: int = 8000,
    ) -> None:
        """Initialize the chat server.

        Args:
            agent: The agent instance to handle chat requests.
            session_backend: Session backend for state persistence.
            host: Host to bind the server to.
            port: Port to bind the server to.
        """
        self._agent = agent
        self._session_backend = session_backend
        self._host = host
        self._port = port
        self._app: Any = None

    async def _load_session(self, session_id: str) -> None:
        """Load session state if backend is configured."""
        if self._session_backend is None:
            return

        await self._session_backend.load(
            session_id=session_id,
            allow_not_exist=True,
            agent=self._agent,
        )

    async def _save_session(self, session_id: str) -> None:
        """Save session state if backend is configured."""
        if self._session_backend is None:
            return

        await self._session_backend.save(
            session_id=session_id,
            agent=self._agent,
        )

    async def _format_sse_event(
        self,
        event_type: str,
        data: dict[str, Any],
    ) -> str:
        """Format data as SSE event.

        Args:
            event_type: Type of the event.
            data: Event data.

        Returns:
            SSE-formatted string.
        """
        data_with_type = {"type": event_type, **data}
        return f"data: {json.dumps(data_with_type, ensure_ascii=False)}\n\n"

    async def _stream_response(
        self,
        message: str,
        session_id: str,
    ) -> AsyncGenerator[str, None]:
        """Stream agent response as SSE events.

        Args:
            message: User message.
            session_id: Session identifier.

        Yields:
            SSE-formatted event strings.
        """
        from ..message import TextBlock, ToolUseBlock

        try:
            # Load session state
            await self._load_session(session_id)

            # Get response from agent
            async for chunk in self._agent(message):
                # Handle different content block types
                if hasattr(chunk, "content") and chunk.content:
                    for block in chunk.content:
                        if block["type"] == "text":
                            yield await self._format_sse_event(
                                "text",
                                {"content": block.get("text", "")},
                            )
                        elif block["type"] == "tool_use":
                            yield await self._format_sse_event(
                                "tool_call",
                                {
                                    "id": block.get("id", ""),
                                    "name": block.get("name", ""),
                                    "input": block.get("input", {}),
                                },
                            )
                        elif block["type"] == "tool_result":
                            # Extract text from tool result content
                            result_content = block.get("content", [])
                            result_text = ""
                            if isinstance(result_content, list):
                                for item in result_content:
                                    if isinstance(item, dict):
                                        result_text += item.get("text", "")
                                    elif isinstance(item, str):
                                        result_text += item
                            elif isinstance(result_content, str):
                                result_text = result_content

                            yield await self._format_sse_event(
                                "tool_result",
                                {
                                    "tool_use_id": block.get("tool_use_id", ""),
                                    "result": result_text,
                                },
                            )

            # Save session state
            await self._save_session(session_id)

            # Send done event
            yield await self._format_sse_event("done", {})

        except Exception as e:
            yield await self._format_sse_event(
                "error",
                {"message": str(e)},
            )

    def _create_app(self) -> Any:
        """Create the ASGI application.

        Returns:
            Starlette application instance.
        """
        try:
            from starlette.applications import Starlette
            from starlette.requests import Request
            from starlette.responses import JSONResponse, StreamingResponse
            from starlette.routing import Route
        except ImportError:
            raise ImportError(
                "Server requires 'starlette' package. "
                "Install it with: pip install starlette uvicorn"
            )

        async def health(request: Request) -> JSONResponse:
            """Health check endpoint."""
            return JSONResponse({"status": "ok"})

        async def chat(request: Request) -> StreamingResponse:
            """Chat endpoint with SSE streaming."""
            try:
                body = await request.json()
            except json.JSONDecodeError:
                return JSONResponse(
                    {"error": "Invalid JSON"},
                    status_code=400,
                )

            message = body.get("message")
            session_id = body.get("session_id", "default")

            if not message:
                return JSONResponse(
                    {"error": "Missing 'message' field"},
                    status_code=400,
                )

            return StreamingResponse(
                self._stream_response(message, session_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        routes = [
            Route("/health", health, methods=["GET"]),
            Route("/chat", chat, methods=["POST"]),
        ]

        return Starlette(routes=routes)

    async def run(self) -> None:
        """Run the server."""
        try:
            import uvicorn
        except ImportError:
            raise ImportError(
                "Server requires 'uvicorn' package. "
                "Install it with: pip install uvicorn"
            )

        app = self._create_app()
        config = uvicorn.Config(
            app,
            host=self._host,
            port=self._port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()

    def run_sync(self) -> None:
        """Run the server synchronously."""
        asyncio.run(self.run())
