# -*- coding: utf-8 -*-
"""Simple Runtime example with a single chat agent."""
from typing import AsyncIterator

from agentscope.agent import ReActAgent
from agentscope.formatter import DashScopeChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.runtime import runtime, AgentApp, SessionContext


class App(AgentApp):
    """A simple chat agent application."""

    def __init__(self) -> None:
        """Initialize the App."""
        self._agents: dict[str, ReActAgent] = {}

    async def on_startup(self) -> None:
        """Called when the application starts."""
        # Pre-warm: nothing needed for this simple example

    async def on_shutdown(self) -> None:
        """Called when the application shuts down."""
        # Cleanup: nothing needed for this simple example

    def _get_or_create_agent(self, session_id: str) -> ReActAgent:
        """Get or create an agent for the given session.

        Args:
            session_id: The session identifier.

        Returns:
            A ReActAgent instance for the session.
        """
        if session_id not in self._agents:
            self._agents[session_id] = ReActAgent(
                name="Assistant",
                sys_prompt=(
                    "You are a helpful AI assistant. "
                    "Answer the user's questions concisely and accurately."
                ),
                model=runtime.models.main,
                formatter=DashScopeChatFormatter(),
                memory=InMemoryMemory(),
            )
        return self._agents[session_id]

    async def __call__(
        self,
        msg: Msg,
        ctx: SessionContext,
    ) -> AsyncIterator[Msg]:
        """Handle incoming messages and yield responses.

        Args:
            msg: The incoming user message.
            ctx: The session context.

        Yields:
            Response messages from the agent.
        """
        agent = self._get_or_create_agent(ctx.session_id)

        # Process the message through the agent
        response = await agent(msg)

        # Yield the response
        yield response
