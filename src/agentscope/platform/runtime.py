# -*- coding: utf-8 -*-
"""Container runtime entry point for AgentScope platform.

This module is the entry point when running an AgentScope application
inside a platform-managed container. It:
1. Reads platform configuration from environment variables
2. Initializes the model client
3. Connects to MCP servers and registers tools
4. Loads the developer's module and creates the agent
5. Starts the HTTP+SSE server
"""
import asyncio
import importlib.util
import os
import sys
from typing import TYPE_CHECKING, Any

from .config import PlatformConfig
from .manifest import MANIFEST_FILENAME, parse_manifest
from .server import ChatServer
from .session_backend import (
    PlatformSessionBackend,
    create_session_backend,
)

if TYPE_CHECKING:
    from ..agent import AgentBase
    from ..formatter import FormatterBase
    from ..model import ChatModelBase
    from ..tool import Toolkit


# Environment variable names
ENV_INSTANCE_ID = "AS_INSTANCE_ID"
ENV_TENANT_ID = "AS_TENANT_ID"
ENV_MODEL_TYPE = "AS_MODEL_TYPE"
ENV_MODEL_NAME = "AS_MODEL_NAME"
ENV_MODEL_API_KEY = "AS_MODEL_API_KEY"
ENV_MODEL_BASE_URL = "AS_MODEL_BASE_URL"
ENV_MCP_SERVERS = "AS_MCP_SERVERS"
ENV_SESSION_BACKEND = "AS_SESSION_BACKEND"
ENV_SESSION_URL = "AS_SESSION_URL"
ENV_SERVER_HOST = "AS_SERVER_HOST"
ENV_SERVER_PORT = "AS_SERVER_PORT"

# Model type to class mapping
MODEL_CLASSES = {
    "openai": "OpenAIChatModel",
    "anthropic": "AnthropicChatModel",
    "dashscope": "DashScopeChatModel",
    "ollama": "OllamaChatModel",
    "gemini": "GeminiChatModel",
}

# Model type to formatter mapping
FORMATTER_CLASSES = {
    "openai": "OpenAIChatFormatter",
    "anthropic": "AnthropicChatFormatter",
    "dashscope": "DashScopeChatFormatter",
    "ollama": "OllamaChatFormatter",
    "gemini": "GeminiChatFormatter",
}


def _get_env(name: str, default: str | None = None) -> str:
    """Get environment variable or raise error if required."""
    value = os.environ.get(name, default)
    if value is None:
        raise ValueError(f"Required environment variable '{name}' is not set")
    return value


def _get_env_optional(name: str, default: str | None = None) -> str | None:
    """Get optional environment variable."""
    return os.environ.get(name, default)


def _create_model(
    model_type: str,
    model_name: str,
    api_key: str,
    base_url: str | None = None,
) -> "ChatModelBase":
    """Create a model instance based on type.

    Args:
        model_type: Type of model (openai, anthropic, etc.).
        model_name: Model name/identifier.
        api_key: API key for authentication.
        base_url: Optional custom base URL.

    Returns:
        ChatModelBase instance.

    Raises:
        ValueError: If model type is unknown.
    """
    from .. import model

    if model_type not in MODEL_CLASSES:
        raise ValueError(
            f"Unknown model type: {model_type}. "
            f"Supported types: {', '.join(MODEL_CLASSES.keys())}"
        )

    model_class_name = MODEL_CLASSES[model_type]
    model_class = getattr(model, model_class_name)

    kwargs: dict[str, Any] = {
        "model": model_name,
        "api_key": api_key,
    }

    if base_url:
        kwargs["base_url"] = base_url

    return model_class(**kwargs)


def _create_formatter(model_type: str) -> "FormatterBase":
    """Create a formatter instance matching the model type.

    Args:
        model_type: Type of model.

    Returns:
        FormatterBase instance.
    """
    from .. import formatter

    if model_type not in FORMATTER_CLASSES:
        # Default to OpenAI formatter
        model_type = "openai"

    formatter_class_name = FORMATTER_CLASSES[model_type]
    formatter_class = getattr(formatter, formatter_class_name)
    return formatter_class()


async def _create_toolkit(mcp_servers: str | None) -> "Toolkit":
    """Create a toolkit and register MCP clients.

    Args:
        mcp_servers: Comma-separated list of MCP server URLs.

    Returns:
        Toolkit instance with registered MCP tools.
    """
    from ..mcp import HttpStatefulClient
    from ..tool import Toolkit

    toolkit = Toolkit()

    if not mcp_servers:
        return toolkit

    # Parse MCP server URLs
    server_urls = [
        url.strip() for url in mcp_servers.split(",")
        if url.strip()
    ]

    for i, url in enumerate(server_urls):
        try:
            # Determine transport type from URL
            if url.endswith("/sse"):
                transport = "sse"
            elif url.endswith("/mcp"):
                transport = "streamable_http"
            else:
                # Default to SSE
                transport = "sse"

            client = HttpStatefulClient(
                name=f"mcp_server_{i}",
                transport=transport,
                url=url,
            )

            await client.connect()
            await toolkit.register_mcp_client(
                mcp_client=client,
                namesake_strategy="rename",
            )

        except Exception as e:
            print(f"Warning: Failed to connect to MCP server {url}: {e}")

    return toolkit


def _load_agent_factory(
    module_path: str,
    factory_name: str,
    app_dir: str,
) -> Any:
    """Load the agent factory function from developer's module.

    Args:
        module_path: Python module path (e.g., "app.main").
        factory_name: Factory function name.
        app_dir: Application directory.

    Returns:
        The factory function.

    Raises:
        ValueError: If module or function not found.
    """
    # Add app directory to path
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)

    # Import the module
    try:
        spec = importlib.util.find_spec(module_path)
        if spec is None:
            raise ValueError(f"Cannot find module: {module_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_path] = module
        if spec.loader is not None:
            spec.loader.exec_module(module)

    except ImportError as e:
        raise ValueError(f"Failed to import module {module_path}: {e}") from e

    # Get the factory function
    if not hasattr(module, factory_name):
        raise ValueError(
            f"Factory function '{factory_name}' not found in module "
            f"'{module_path}'"
        )

    factory = getattr(module, factory_name)
    if not callable(factory):
        raise ValueError(
            f"'{factory_name}' in module '{module_path}' is not callable"
        )

    return factory


async def initialize() -> tuple[
    "AgentBase",
    "PlatformSessionBackend | None",
    str,
    int,
]:
    """Initialize the runtime environment.

    Returns:
        Tuple of (agent, session_backend, host, port).
    """
    # Get configuration from environment
    instance_id = _get_env(ENV_INSTANCE_ID, "local-instance")
    tenant_id = _get_env(ENV_TENANT_ID, "local-tenant")
    model_type = _get_env(ENV_MODEL_TYPE, "openai")
    model_name = _get_env(ENV_MODEL_NAME, "gpt-4")
    api_key = _get_env(ENV_MODEL_API_KEY, "")
    base_url = _get_env_optional(ENV_MODEL_BASE_URL)
    mcp_servers = _get_env_optional(ENV_MCP_SERVERS)
    session_backend_type = _get_env_optional(ENV_SESSION_BACKEND, "file")
    session_url = _get_env_optional(ENV_SESSION_URL)
    host = _get_env_optional(ENV_SERVER_HOST, "0.0.0.0")
    port = int(_get_env_optional(ENV_SERVER_PORT, "8000") or "8000")

    # Parse manifest
    app_dir = os.getcwd()
    manifest = parse_manifest(app_dir)

    print(f"Initializing application: {manifest.name} v{manifest.version}")

    # Create model
    print(f"Creating model: {model_type}/{model_name}")
    chat_model = _create_model(
        model_type=model_type,
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
    )

    # Create formatter
    formatter = _create_formatter(model_type)

    # Create toolkit with MCP clients
    print("Creating toolkit...")
    toolkit = await _create_toolkit(mcp_servers)
    print(f"Registered {len(toolkit.tools)} tools")

    # Create platform config
    config = PlatformConfig(
        model=chat_model,
        formatter=formatter,
        toolkit=toolkit,
        instance_id=instance_id,
        tenant_id=tenant_id,
        app_name=manifest.name,
        app_version=manifest.version,
    )

    # Load and call the factory function
    print(
        f"Loading entrypoint: {manifest.entrypoint.module}:"
        f"{manifest.entrypoint.factory}"
    )
    factory = _load_agent_factory(
        module_path=manifest.entrypoint.module,
        factory_name=manifest.entrypoint.factory,
        app_dir=app_dir,
    )

    agent = factory(config)
    print(f"Created agent: {agent.name}")

    # Create session backend
    session_backend: PlatformSessionBackend | None = None
    if session_backend_type:
        try:
            session_backend = create_session_backend(
                backend_type=session_backend_type,
                url=session_url,
            )
            print(f"Using session backend: {session_backend_type}")
        except Exception as e:
            print(f"Warning: Failed to create session backend: {e}")

    return agent, session_backend, host, port


async def main() -> None:
    """Main entry point for the runtime."""
    try:
        agent, session_backend, host, port = await initialize()

        # Create and run the server
        print(f"Starting server on {host}:{port}")
        server = ChatServer(
            agent=agent,
            session_backend=session_backend,
            host=host,
            port=port,
        )
        await server.run()

    except Exception as e:
        print(f"Runtime error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
