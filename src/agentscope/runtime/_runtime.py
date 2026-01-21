# -*- coding: utf-8 -*-
"""Runtime singleton for AgentScope Runtime."""
import importlib.util
import os
import sys
from typing import TYPE_CHECKING, Any

from ._config import (
    load_config,
    RuntimeConfig,
    ModelConfig,
    MCPServerConfig,
)
from ._app_base import AgentApp
from .._logging import logger

if TYPE_CHECKING:
    from ..model import ChatModelBase
    from ..tool import Toolkit
    from ..session import SessionBase
    from ..mcp import StatefulClientBase


class ModelRegistry:
    """Registry for accessing models by slot name.

    Supports both attribute access (runtime.models.main) and
    dictionary access (runtime.models["main"]).
    """

    def __init__(self) -> None:
        """Initialize the model registry."""
        self._models: dict[str, "ChatModelBase"] = {}

    def _register(self, name: str, model: "ChatModelBase") -> None:
        """Register a model with the given slot name.

        Args:
            name (`str`):
                The slot name for the model.
            model (`ChatModelBase`):
                The model instance.
        """
        self._models[name] = model

    def __getattr__(self, name: str) -> "ChatModelBase":
        """Get a model by attribute access.

        Args:
            name (`str`):
                The model slot name.

        Returns:
            `ChatModelBase`:
                The model instance.

        Raises:
            AttributeError:
                If the model slot is not found.
        """
        if name.startswith("_"):
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'",
            )
        if name not in self._models:
            raise AttributeError(
                f"Model slot '{name}' not found. "
                f"Available slots: {list(self._models.keys())}",
            )
        return self._models[name]

    def __getitem__(self, name: str) -> "ChatModelBase":
        """Get a model by dictionary access.

        Args:
            name (`str`):
                The model slot name.

        Returns:
            `ChatModelBase`:
                The model instance.

        Raises:
            KeyError:
                If the model slot is not found.
        """
        if name not in self._models:
            raise KeyError(
                f"Model slot '{name}' not found. "
                f"Available slots: {list(self._models.keys())}",
            )
        return self._models[name]

    def keys(self) -> list[str]:
        """Return all model slot names.

        Returns:
            `list[str]`:
                List of model slot names.
        """
        return list(self._models.keys())

    def __contains__(self, name: str) -> bool:
        """Check if a model slot exists.

        Args:
            name (`str`):
                The model slot name.

        Returns:
            `bool`:
                True if the slot exists.
        """
        return name in self._models

    def __len__(self) -> int:
        """Return the number of registered models."""
        return len(self._models)


def _create_model(name: str, config: ModelConfig) -> "ChatModelBase":
    """Create a model instance from configuration.

    Args:
        name (`str`):
            The model slot name.
        config (`ModelConfig`):
            The model configuration.

    Returns:
        `ChatModelBase`:
            The created model instance.

    Raises:
        ValueError:
            If the provider is not supported.
    """
    from ..model import (
        OpenAIChatModel,
        AnthropicChatModel,
        DashScopeChatModel,
        GeminiChatModel,
        OllamaChatModel,
    )

    provider_map = {
        "openai": OpenAIChatModel,
        "anthropic": AnthropicChatModel,
        "dashscope": DashScopeChatModel,
        "gemini": GeminiChatModel,
        "ollama": OllamaChatModel,
    }

    model_cls = provider_map.get(config.provider)
    if model_cls is None:
        raise ValueError(
            f"Unsupported model provider '{config.provider}' "
            f"for slot '{name}'. "
            f"Supported providers: {list(provider_map.keys())}",
        )

    # Build constructor arguments
    kwargs: dict[str, Any] = {
        "model_name": config.model,
        "stream": config.stream,
    }

    if config.api_key is not None:
        kwargs["api_key"] = config.api_key

    if config.base_url is not None:
        # Different providers use different argument names
        if config.provider == "openai":
            kwargs.setdefault("client_kwargs", {})
            kwargs["client_kwargs"]["base_url"] = config.base_url
        elif config.provider == "ollama":
            kwargs["host"] = config.base_url
        # Other providers may have different handling

    if config.generate_kwargs:
        kwargs["generate_kwargs"] = config.generate_kwargs

    if config.client_kwargs:
        kwargs.setdefault("client_kwargs", {})
        kwargs["client_kwargs"].update(config.client_kwargs)

    logger.info(
        "Creating model '%s' with provider '%s'",
        name,
        config.provider,
    )
    return model_cls(**kwargs)


async def _create_mcp_client(
    name: str,
    config: MCPServerConfig,
) -> "StatefulClientBase":
    """Create and connect an MCP client from configuration.

    Args:
        name (`str`):
            The MCP server name.
        config (`MCPServerConfig`):
            The MCP server configuration.

    Returns:
        `StatefulClientBase`:
            The connected MCP client.
    """
    from ..mcp import HttpStatefulClient

    client = HttpStatefulClient(
        name=name,
        transport=config.transport,
        url=config.url,
        headers=config.headers,
        timeout=config.timeout,
        sse_read_timeout=config.sse_read_timeout,
    )

    logger.info(
        "Connecting to MCP server '%s' at %s (%s)",
        name,
        config.url,
        config.transport,
    )
    await client.connect()
    return client


class Runtime:
    """Global runtime singleton for AgentScope applications.

    Manages all resources including models, tools, and sessions. Access
    resources through the global `runtime` instance.

    Attributes:
        models (`ModelRegistry`):
            Registry of configured models, accessed by slot name.
        tools (`Toolkit`):
            Toolkit containing all registered tools from MCP servers.
        session (`SessionBase`):
            Session manager for persisting state.

    Example:
        .. code-block:: python

            from agentscope.runtime import runtime

            # Access models
            model = runtime.models.main

            # Access tools
            tools = runtime.tools.get_json_schemas()

            # Access session
            await runtime.session.save_session_state(
                session_id="user_123",
                memory=agent.memory,
            )
    """

    def __init__(self) -> None:
        """Initialize the runtime (not yet configured)."""
        self._initialized = False
        self._config: RuntimeConfig | None = None
        self._app: AgentApp | None = None
        self._mcp_clients: list["StatefulClientBase"] = []

        self.models = ModelRegistry()
        self.tools: "Toolkit" = None  # type: ignore[assignment]
        self.session: "SessionBase" = None  # type: ignore[assignment]

    @property
    def app(self) -> AgentApp:
        """Get the loaded AgentApp instance.

        Returns:
            `AgentApp`:
                The user's application instance.

        Raises:
            RuntimeError:
                If the runtime is not initialized.
        """
        if self._app is None:
            raise RuntimeError(
                "Runtime is not initialized. "
                "Call `await runtime.initialize()` first.",
            )
        return self._app

    @property
    def config(self) -> RuntimeConfig:
        """Get the loaded configuration.

        Returns:
            `RuntimeConfig`:
                The runtime configuration.

        Raises:
            RuntimeError:
                If the runtime is not initialized.
        """
        if self._config is None:
            raise RuntimeError(
                "Runtime is not initialized. "
                "Call `await runtime.initialize()` first.",
            )
        return self._config

    @property
    def is_initialized(self) -> bool:
        """Check if the runtime is initialized.

        Returns:
            `bool`:
                True if initialized.
        """
        return self._initialized

    async def initialize(
        self,
        config_path: str = "agentapp.yaml",
        project_path: str | None = None,
    ) -> None:
        """Initialize the runtime from configuration.

        Args:
            config_path (`str`):
                Path to the configuration file, relative to project_path.
            project_path (`str | None`):
                Path to the project directory. Defaults to current directory.

        Raises:
            RuntimeError:
                If the runtime is already initialized.
            FileNotFoundError:
                If configuration or app.py is not found.
            ValueError:
                If configuration is invalid.
        """
        if self._initialized:
            raise RuntimeError(
                "Runtime is already initialized. "
                "Call `await runtime.shutdown()` first to reinitialize.",
            )

        project_path = project_path or os.getcwd()
        full_config_path = os.path.join(project_path, config_path)

        logger.info("Initializing runtime from %s", full_config_path)

        # 1. Load configuration
        self._config = load_config(full_config_path)

        # 2. Initialize models
        for name, model_config in self._config.models.items():
            model = _create_model(name, model_config)
            # pylint: disable-next=protected-access
            self.models._register(
                name,
                model,
            )

        # 3. Initialize Toolkit and MCP clients
        from ..tool import Toolkit

        self.tools = Toolkit()

        for name, mcp_config in self._config.mcp_servers.items():
            client = await _create_mcp_client(name, mcp_config)
            self._mcp_clients.append(client)
            await self.tools.register_mcp_client(
                mcp_client=client,
                namesake_strategy="rename",
            )

        # 4. Initialize Session
        from ..session import JSONSession

        self.session = JSONSession(
            save_dir=self._config.session.save_dir,
        )

        # 5. Load user App
        self._app = self._load_app(project_path)

        # 6. Call App.on_startup()
        logger.info("Calling App.on_startup()")
        await self._app.on_startup()

        self._initialized = True
        logger.info("Runtime initialized successfully")

    def _load_app(self, project_path: str) -> AgentApp:
        """Load the user's App class from app.py.

        Args:
            project_path (`str`):
                Path to the project directory.

        Returns:
            `AgentApp`:
                An instance of the user's App class.

        Raises:
            FileNotFoundError:
                If app.py is not found.
            ValueError:
                If App class is not found or invalid.
        """
        app_file = os.path.join(project_path, "app.py")
        if not os.path.exists(app_file):
            raise FileNotFoundError(
                f"App file not found: {app_file}. "
                "Create an app.py file with an App class that inherits "
                "from AgentApp.",
            )

        # Add project path to sys.path for imports
        if project_path not in sys.path:
            sys.path.insert(0, project_path)

        # Load the module
        spec = importlib.util.spec_from_file_location("app", app_file)
        if spec is None or spec.loader is None:
            raise ValueError(f"Failed to load module from {app_file}")

        module = importlib.util.module_from_spec(spec)
        sys.modules["app"] = module
        spec.loader.exec_module(module)

        # Get the App class
        if not hasattr(module, "App"):
            raise ValueError(
                f"App class not found in {app_file}. "
                "Define a class named 'App' that inherits from AgentApp.",
            )

        app_cls = getattr(module, "App")
        if not isinstance(app_cls, type) or not issubclass(app_cls, AgentApp):
            raise ValueError(
                f"App class in {app_file} must inherit from AgentApp.",
            )

        logger.info("Loaded App class from %s", app_file)
        return app_cls()

    async def shutdown(self) -> None:
        """Shutdown the runtime and release all resources.

        Calls App.on_shutdown() and closes all MCP client connections.
        """
        if not self._initialized:
            return

        logger.info("Shutting down runtime")

        # 1. Call App.on_shutdown()
        if self._app is not None:
            try:
                await self._app.on_shutdown()
            except Exception as e:
                logger.warning("Error in App.on_shutdown(): %s", e)

        # 2. Close MCP clients (LIFO order as per documentation)
        for client in reversed(self._mcp_clients):
            try:
                await client.close()
            except Exception as e:
                logger.warning("Error closing MCP client: %s", e)

        self._mcp_clients.clear()
        self._app = None
        self._config = None
        self._initialized = False
        self.models = ModelRegistry()
        self.tools = None  # type: ignore[assignment]
        self.session = None  # type: ignore[assignment]

        logger.info("Runtime shutdown complete")


# Global singleton instance
runtime = Runtime()
