# -*- coding: utf-8 -*-
"""AgentApp base class for AgentScope Runtime."""
from abc import ABC, abstractmethod
from typing import AsyncIterator, Any

from ..message import Msg


class SessionContext:
    """Session context passed to AgentApp during request handling.

    Contains the session ID and optional metadata from the platform.
    """

    def __init__(
        self,
        session_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the session context.

        Args:
            session_id (`str`):
                The unique session identifier.
            metadata (`dict[str, Any] | None`, optional):
                Additional metadata from the platform (e.g., user_id,
                tenant_id).
        """
        self.session_id = session_id
        self.metadata = metadata or {}

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"SessionContext(session_id={self.session_id!r}, "
            f"metadata={self.metadata!r})"
        )


class AgentApp(ABC):
    """Base class for AgentScope Runtime applications.

    Users must subclass this and implement the `__call__` method to handle
    incoming requests. The class must be named `App` and defined in `app.py`
    in the project root.

    Example:
        .. code-block:: python

            from agentscope.runtime import runtime, AgentApp, SessionContext
            from agentscope.message import Msg
            from typing import AsyncIterator

            class App(AgentApp):
                async def __call__(
                    self,
                    msg: Msg,
                    ctx: SessionContext,
                ) -> AsyncIterator[Msg]:
                    model = runtime.models.main
                    async for chunk in model.stream([msg]):
                        yield Msg(
                            name="assistant",
                            content=chunk.text,
                            role="assistant",
                        )
    """

    @abstractmethod
    async def __call__(
        self,
        msg: Msg,
        ctx: SessionContext,
    ) -> AsyncIterator[Msg]:
        """Handle an incoming request and yield response messages.

        This method must be implemented by subclasses. It receives the user's
        input message and session context, and should yield response messages
        as an async iterator for streaming output.

        Args:
            msg (`Msg`):
                The user's input message.
            ctx (`SessionContext`):
                The session context containing session_id and metadata.

        Yields:
            `Msg`:
                Response messages to stream back to the user.
        """
        # This is an abstract method, but we need yield for type checking
        yield  # type: ignore[misc]

    async def on_startup(self) -> None:
        """Hook called when the application starts up.

        Override this method to perform initialization tasks such as:
        - Preloading models
        - Establishing database connections
        - Loading static resources

        At this point, the runtime is fully initialized and resources like
        `runtime.models` and `runtime.tools` are available.
        """

    async def on_shutdown(self) -> None:
        """Hook called when the application shuts down.

        Override this method to perform cleanup tasks such as:
        - Closing connections
        - Saving state
        - Releasing resources
        """
