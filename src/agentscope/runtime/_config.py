# -*- coding: utf-8 -*-
"""Configuration parsing for AgentScope Runtime."""
import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ModelConfig:
    """Model configuration."""

    provider: Literal[
        "openai",
        "anthropic",
        "dashscope",
        "gemini",
        "ollama",
    ]
    model: str
    api_key: str | None = None
    base_url: str | None = None
    stream: bool = True
    generate_kwargs: dict[str, Any] = field(default_factory=dict)
    client_kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPServerConfig:
    """MCP Server configuration."""

    url: str
    transport: Literal["sse", "streamable_http"]
    headers: dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0
    sse_read_timeout: float = 300.0


@dataclass
class SessionConfig:
    """Session configuration."""

    backend: Literal["json"] = "json"
    save_dir: str = "./sessions"


@dataclass
class PlatformConfig:
    """Platform communication configuration."""

    endpoint: str | None = None
    instance_id: str | None = None
    heartbeat_interval: int = 30


@dataclass
class TracingConfig:
    """Tracing configuration."""

    endpoint: str | None = None


@dataclass
class ServerConfig:
    """HTTP Server configuration."""

    port: int = 8080


@dataclass
class RuntimeConfig:
    """Complete runtime configuration."""

    models: dict[str, ModelConfig] = field(default_factory=dict)
    mcp_servers: dict[str, MCPServerConfig] = field(default_factory=dict)
    session: SessionConfig = field(default_factory=SessionConfig)
    platform: PlatformConfig = field(default_factory=PlatformConfig)
    tracing: TracingConfig = field(default_factory=TracingConfig)
    server: ServerConfig = field(default_factory=ServerConfig)


def _expand_env_vars(value: Any) -> Any:
    """Recursively expand environment variables in values.

    Args:
        value (`Any`):
            The value to process.

    Returns:
        `Any`:
            The value with environment variables expanded.

    Raises:
        ValueError:
            If an environment variable is not set.
    """
    if isinstance(value, str):
        # Find all ${VAR} patterns
        pattern = re.compile(r"\$\{([^}]+)\}")
        matches = pattern.findall(value)
        for var_name in matches:
            env_value = os.environ.get(var_name)
            if env_value is None:
                raise ValueError(
                    f"Environment variable '{var_name}' is not set.",
                )
            value = value.replace(f"${{{var_name}}}", env_value)
        return value
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value


def _parse_model_config(name: str, config: dict[str, Any]) -> ModelConfig:
    """Parse model configuration.

    Args:
        name (`str`):
            The model slot name.
        config (`dict[str, Any]`):
            The raw model configuration.

    Returns:
        `ModelConfig`:
            The parsed model configuration.
    """
    provider = config.get("provider")
    if provider is None:
        raise ValueError(
            f"Model '{name}' is missing required field 'provider'.",
        )

    model = config.get("model")
    if model is None:
        raise ValueError(f"Model '{name}' is missing required field 'model'.")

    return ModelConfig(
        provider=provider,
        model=model,
        api_key=config.get("api_key"),
        base_url=config.get("base_url"),
        stream=config.get("stream", True),
        generate_kwargs=config.get("generate_kwargs", {}),
        client_kwargs=config.get("client_kwargs", {}),
    )


def _parse_mcp_server_config(
    name: str,
    config: dict[str, Any],
) -> MCPServerConfig:
    """Parse MCP server configuration.

    Args:
        name (`str`):
            The MCP server name.
        config (`dict[str, Any]`):
            The raw MCP server configuration.

    Returns:
        `MCPServerConfig`:
            The parsed MCP server configuration.
    """
    url = config.get("url")
    if url is None:
        raise ValueError(
            f"MCP server '{name}' is missing required field 'url'.",
        )

    transport = config.get("transport")
    if transport is None:
        raise ValueError(
            f"MCP server '{name}' is missing required field 'transport'.",
        )

    if transport not in ("sse", "streamable_http"):
        raise ValueError(
            f"MCP server '{name}' has invalid transport '{transport}'. "
            "Valid options are 'sse' and 'streamable_http'.",
        )

    return MCPServerConfig(
        url=url,
        transport=transport,
        headers=config.get("headers", {}),
        timeout=config.get("timeout", 30.0),
        sse_read_timeout=config.get("sse_read_timeout", 300.0),
    )


def load_config(config_path: str) -> RuntimeConfig:
    """Load and parse the runtime configuration from a YAML file.

    Args:
        config_path (`str`):
            Path to the agentapp.yaml configuration file.

    Returns:
        `RuntimeConfig`:
            The parsed runtime configuration.

    Raises:
        FileNotFoundError:
            If the configuration file does not exist.
        ValueError:
            If the configuration is invalid or missing required fields.
    """
    import yaml

    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}",
        )

    with open(config_path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f) or {}

    # Expand environment variables
    raw_config = _expand_env_vars(raw_config)

    # Parse models
    models: dict[str, ModelConfig] = {}
    for name, model_config in raw_config.get("models", {}).items():
        models[name] = _parse_model_config(name, model_config)

    # Parse MCP servers
    mcp_servers: dict[str, MCPServerConfig] = {}
    for name, mcp_config in raw_config.get("mcp_servers", {}).items():
        mcp_servers[name] = _parse_mcp_server_config(name, mcp_config)

    # Parse session config
    session_raw = raw_config.get("session", {})
    session = SessionConfig(
        backend=session_raw.get("backend", "json"),
        save_dir=session_raw.get("save_dir", "./sessions"),
    )

    # Parse platform config
    platform_raw = raw_config.get("platform", {})
    platform = PlatformConfig(
        endpoint=platform_raw.get("endpoint"),
        instance_id=platform_raw.get("instance_id"),
        heartbeat_interval=platform_raw.get("heartbeat_interval", 30),
    )

    # Parse tracing config
    tracing_raw = raw_config.get("tracing", {})
    tracing = TracingConfig(
        endpoint=tracing_raw.get("endpoint"),
    )

    # Parse server config
    server_raw = raw_config.get("server", {})
    server = ServerConfig(
        port=server_raw.get("port", 8080),
    )

    return RuntimeConfig(
        models=models,
        mcp_servers=mcp_servers,
        session=session,
        platform=platform,
        tracing=tracing,
        server=server,
    )
