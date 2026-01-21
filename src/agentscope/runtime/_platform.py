# -*- coding: utf-8 -*-
"""Platform communication for AgentScope Runtime."""
import asyncio
import time
from datetime import datetime, timezone
from typing import Literal, TYPE_CHECKING

from ._config import PlatformConfig
from .._logging import logger

if TYPE_CHECKING:
    from ._runtime import Runtime


class PlatformClient:
    """Client for communicating with the AgentScope platform.

    Handles heartbeat reporting and configuration update checking.
    """

    def __init__(
        self,
        config: PlatformConfig,
        runtime: "Runtime",
    ) -> None:
        """Initialize the platform client.

        Args:
            config (`PlatformConfig`):
                Platform configuration.
            runtime (`Runtime`):
                The runtime instance for collecting metrics.
        """
        self.config = config
        self.runtime = runtime
        self._heartbeat_task: asyncio.Task | None = None
        self._start_time = time.time()
        self._request_count = 0
        self._active_sessions: set[str] = set()

    @property
    def enabled(self) -> bool:
        """Check if platform communication is enabled.

        Returns:
            `bool`:
                True if platform endpoint and instance_id are configured.
        """
        return (
            self.config.endpoint is not None
            and self.config.instance_id is not None
        )

    def record_request(self, session_id: str) -> None:
        """Record a request for metrics.

        Args:
            session_id (`str`):
                The session ID of the request.
        """
        self._request_count += 1
        self._active_sessions.add(session_id)

    def _get_metrics(self) -> dict:
        """Get current metrics for heartbeat.

        Returns:
            `dict`:
                Metrics dictionary.
        """
        import resource

        # Get memory usage (Linux/macOS)
        try:
            usage = resource.getrusage(resource.RUSAGE_SELF)
            memory_mb = usage.ru_maxrss / 1024  # Convert to MB (Linux is KB)
        except Exception:
            memory_mb = 0

        return {
            "active_sessions": len(self._active_sessions),
            "total_requests": self._request_count,
            "memory_usage_mb": int(memory_mb),
        }

    async def _send_heartbeat(self) -> None:
        """Send a heartbeat to the platform."""
        import aiohttp

        if not self.enabled:
            return

        url = (
            f"{self.config.endpoint}/instances/"
            f"{self.config.instance_id}/heartbeat"
        )
        payload = {
            "status": "running",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": self._get_metrics(),
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            "Heartbeat failed with status %d",
                            response.status,
                        )
        except Exception as e:
            logger.warning("Failed to send heartbeat: %s", e)

    async def _check_config_update(
        self,
    ) -> Literal["restart", "reload", "none"]:
        """Check if configuration has been updated.

        Returns:
            `Literal["restart", "reload", "none"]`:
                The action to take.
        """
        import aiohttp

        if not self.enabled:
            return "none"

        url = (
            f"{self.config.endpoint}/instances/"
            f"{self.config.instance_id}/config"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("updated", False):
                            return data.get("action", "none")
        except Exception as e:
            logger.warning("Failed to check config update: %s", e)

        return "none"

    async def _heartbeat_loop(self) -> None:
        """Background task that sends periodic heartbeats."""
        while True:
            try:
                await self._send_heartbeat()

                # Check for config updates
                action = await self._check_config_update()
                if action == "restart":
                    logger.info(
                        "Configuration updated, restart required. "
                        "Shutting down for restart...",
                    )
                    # Signal the application to restart
                    # This will be handled by the orchestrator/container
                    import sys

                    sys.exit(0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Error in heartbeat loop: %s", e)

            await asyncio.sleep(self.config.heartbeat_interval)

    async def start(self) -> None:
        """Start the heartbeat background task."""
        if not self.enabled:
            logger.info(
                "Platform communication disabled (no endpoint configured)",
            )
            return

        logger.info(
            "Starting platform heartbeat (interval: %ds)",
            self.config.heartbeat_interval,
        )
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        """Stop the heartbeat background task."""
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
            logger.info("Platform heartbeat stopped")
