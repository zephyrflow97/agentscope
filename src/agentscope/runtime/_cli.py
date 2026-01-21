# -*- coding: utf-8 -*-
"""CLI entrypoint for AgentScope Runtime."""
from __future__ import annotations

import argparse
import asyncio
import os

from .._logging import logger
from ._runtime import runtime
from ._platform import PlatformClient
from ._server import build_app


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="agentscope",
        description="AgentScope Runtime",
    )
    subparsers = parser.add_subparsers(dest="command")

    run_p = subparsers.add_parser("run", help="Run an AgentScope project")
    run_p.add_argument(
        "project_path",
        nargs="?",
        default=".",
        help="Project directory (default: .)",
    )
    run_p.add_argument(
        "--port",
        type=int,
        default=None,
        help="HTTP port (default from config or 8080)",
    )
    run_p.add_argument(
        "--config",
        default="agentapp.yaml",
        help="Config file path (default: agentapp.yaml)",
    )
    run_p.add_argument(
        "--no-platform",
        action="store_true",
        help="Disable platform communication",
    )
    run_p.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Log level",
    )

    return parser.parse_args(argv)


async def _run_async(args: argparse.Namespace) -> None:
    if args.command != "run":
        raise SystemExit("Specify a subcommand. Try 'agentscope run .'")

    # Initialize runtime
    project_path = os.path.abspath(args.project_path)
    await runtime.initialize(
        config_path=args.config,
        project_path=project_path,
    )

    # Platform client
    platform_client = None
    if not args.no_platform:
        platform_client = PlatformClient(runtime.config.platform, runtime)

    # Build FastAPI app and run with uvicorn
    app = build_app(runtime, platform_client)

    # Determine port
    port = args.port or (
        runtime.config.server.port if runtime.is_initialized else 8080
    )

    # Lazy import uvicorn
    import uvicorn  # type: ignore[import-not-found]

    logger.info("Starting HTTP server on 0.0.0.0:%s", port)

    # Use uvicorn's async server API to avoid nested asyncio.run()
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level=args.log_level,
    )
    server = uvicorn.Server(config)
    await server.serve()


def main(argv: list[str] | None = None) -> None:
    """Main entry point for the AgentScope CLI.

    Args:
        argv (`list[str] | None`):
            Optional command line arguments.
    """
    args = _parse_args(argv)
    try:
        asyncio.run(_run_async(args))
    except KeyboardInterrupt:  # pragma: no cover
        pass


if __name__ == "__main__":  # pragma: no cover
    main()
