# -*- coding: utf-8 -*-
# pylint: disable=protected-access
"""Unittests for the runtime module."""
import os
import tempfile
from unittest import TestCase
from unittest.async_case import IsolatedAsyncioTestCase
from unittest.mock import MagicMock

from agentscope.runtime._config import (
    _expand_env_vars,
    load_config,
    ModelConfig,
    MCPServerConfig,
    SessionConfig,
    PlatformConfig,
    ServerConfig,
    RuntimeConfig,
)
from agentscope.runtime._app_base import SessionContext
from agentscope.runtime._runtime import ModelRegistry, Runtime
from agentscope.runtime._cli import _parse_args


class TestExpandEnvVars(TestCase):
    """Tests for _expand_env_vars function."""

    def test_expand_string_env_var(self) -> None:
        """Test expanding environment variable in a string."""
        os.environ["TEST_VAR"] = "test_value"
        result = _expand_env_vars("prefix_${TEST_VAR}_suffix")
        self.assertEqual(result, "prefix_test_value_suffix")
        del os.environ["TEST_VAR"]

    def test_expand_multiple_env_vars(self) -> None:
        """Test expanding multiple environment variables."""
        os.environ["VAR1"] = "value1"
        os.environ["VAR2"] = "value2"
        result = _expand_env_vars("${VAR1}_and_${VAR2}")
        self.assertEqual(result, "value1_and_value2")
        del os.environ["VAR1"]
        del os.environ["VAR2"]

    def test_expand_in_dict(self) -> None:
        """Test expanding environment variables in a dictionary."""
        os.environ["DICT_VAR"] = "dict_value"
        result = _expand_env_vars(
            {"key": "${DICT_VAR}", "nested": {"inner": "${DICT_VAR}"}},
        )
        self.assertEqual(
            result,
            {"key": "dict_value", "nested": {"inner": "dict_value"}},
        )
        del os.environ["DICT_VAR"]

    def test_expand_in_list(self) -> None:
        """Test expanding environment variables in a list."""
        os.environ["LIST_VAR"] = "list_value"
        result = _expand_env_vars(
            ["${LIST_VAR}", "static", {"key": "${LIST_VAR}"}],
        )
        self.assertEqual(
            result,
            ["list_value", "static", {"key": "list_value"}],
        )
        del os.environ["LIST_VAR"]

    def test_unset_env_var_raises(self) -> None:
        """Test that unset environment variable raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            _expand_env_vars("${UNSET_VARIABLE_12345}")
        self.assertIn("UNSET_VARIABLE_12345", str(ctx.exception))

    def test_no_expansion_needed(self) -> None:
        """Test that strings without env vars are unchanged."""
        result = _expand_env_vars("plain string")
        self.assertEqual(result, "plain string")

    def test_non_string_values(self) -> None:
        """Test that non-string values pass through."""
        self.assertEqual(_expand_env_vars(123), 123)
        self.assertEqual(_expand_env_vars(True), True)
        self.assertEqual(_expand_env_vars(None), None)


class TestLoadConfig(TestCase):
    """Tests for load_config function."""

    def test_load_minimal_config(self) -> None:
        """Test loading a minimal configuration file."""
        yaml_content = """
models: {}
mcp_servers: {}
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
        ) as f:
            f.write(yaml_content)
            f.flush()
            config = load_config(f.name)
        os.unlink(f.name)

        self.assertIsInstance(config, RuntimeConfig)
        self.assertEqual(config.models, {})
        self.assertEqual(config.mcp_servers, {})
        self.assertEqual(config.session.backend, "json")
        self.assertEqual(config.server.port, 8080)

    def test_load_config_with_models(self) -> None:
        """Test loading configuration with model definitions."""
        yaml_content = """
models:
  main:
    provider: openai
    model: gpt-4
    api_key: test_key
    stream: true
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
        ) as f:
            f.write(yaml_content)
            f.flush()
            config = load_config(f.name)
        os.unlink(f.name)

        self.assertIn("main", config.models)
        model = config.models["main"]
        self.assertEqual(model.provider, "openai")
        self.assertEqual(model.model, "gpt-4")
        self.assertEqual(model.api_key, "test_key")
        self.assertTrue(model.stream)

    def test_load_config_with_env_vars(self) -> None:
        """Test loading configuration with environment variables."""
        os.environ["TEST_API_KEY"] = "secret_api_key"
        yaml_content = """
models:
  main:
    provider: openai
    model: gpt-4
    api_key: ${TEST_API_KEY}
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
        ) as f:
            f.write(yaml_content)
            f.flush()
            config = load_config(f.name)
        os.unlink(f.name)
        del os.environ["TEST_API_KEY"]

        self.assertEqual(config.models["main"].api_key, "secret_api_key")

    def test_load_config_missing_file(self) -> None:
        """Test that missing config file raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_load_config_missing_model_provider(self) -> None:
        """Test that missing model provider raises ValueError."""
        yaml_content = """
models:
  main:
    model: gpt-4
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
        ) as f:
            f.write(yaml_content)
            f.flush()
            with self.assertRaises(ValueError) as ctx:
                load_config(f.name)
        os.unlink(f.name)
        self.assertIn("provider", str(ctx.exception))

    def test_load_config_with_mcp_servers(self) -> None:
        """Test loading configuration with MCP server definitions."""
        yaml_content = """
mcp_servers:
  tools:
    url: http://localhost:8000
    transport: sse
    headers:
      Authorization: Bearer token
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
        ) as f:
            f.write(yaml_content)
            f.flush()
            config = load_config(f.name)
        os.unlink(f.name)

        self.assertIn("tools", config.mcp_servers)
        mcp = config.mcp_servers["tools"]
        self.assertEqual(mcp.url, "http://localhost:8000")
        self.assertEqual(mcp.transport, "sse")
        self.assertEqual(mcp.headers, {"Authorization": "Bearer token"})


class TestDataclasses(TestCase):
    """Tests for configuration dataclasses."""

    def test_model_config_defaults(self) -> None:
        """Test ModelConfig default values."""
        config = ModelConfig(provider="openai", model="gpt-4")
        self.assertIsNone(config.api_key)
        self.assertIsNone(config.base_url)
        self.assertTrue(config.stream)
        self.assertEqual(config.generate_kwargs, {})
        self.assertEqual(config.client_kwargs, {})

    def test_mcp_server_config_defaults(self) -> None:
        """Test MCPServerConfig default values."""
        config = MCPServerConfig(url="http://localhost:8000", transport="sse")
        self.assertEqual(config.headers, {})
        self.assertEqual(config.timeout, 30.0)
        self.assertEqual(config.sse_read_timeout, 300.0)

    def test_session_config_defaults(self) -> None:
        """Test SessionConfig default values."""
        config = SessionConfig()
        self.assertEqual(config.backend, "json")
        self.assertEqual(config.save_dir, "./sessions")

    def test_platform_config_defaults(self) -> None:
        """Test PlatformConfig default values."""
        config = PlatformConfig()
        self.assertIsNone(config.endpoint)
        self.assertIsNone(config.instance_id)
        self.assertEqual(config.heartbeat_interval, 30)

    def test_server_config_defaults(self) -> None:
        """Test ServerConfig default values."""
        config = ServerConfig()
        self.assertEqual(config.port, 8080)


class TestSessionContext(TestCase):
    """Tests for SessionContext."""

    def test_session_context_basic(self) -> None:
        """Test basic SessionContext creation."""
        ctx = SessionContext(session_id="test_session")
        self.assertEqual(ctx.session_id, "test_session")
        self.assertEqual(ctx.metadata, {})

    def test_session_context_with_metadata(self) -> None:
        """Test SessionContext with metadata."""
        ctx = SessionContext(
            session_id="test_session",
            metadata={"user_id": "user123", "tenant_id": "tenant456"},
        )
        self.assertEqual(ctx.session_id, "test_session")
        self.assertEqual(ctx.metadata["user_id"], "user123")
        self.assertEqual(ctx.metadata["tenant_id"], "tenant456")

    def test_session_context_repr(self) -> None:
        """Test SessionContext string representation."""
        ctx = SessionContext(session_id="test", metadata={"key": "value"})
        repr_str = repr(ctx)
        self.assertIn("test", repr_str)
        self.assertIn("key", repr_str)


class TestModelRegistry(TestCase):
    """Tests for ModelRegistry."""

    def test_register_and_retrieve_by_attr(self) -> None:
        """Test registering and retrieving model by attribute."""
        registry = ModelRegistry()
        mock_model = MagicMock()
        registry._register("main", mock_model)
        self.assertEqual(registry.main, mock_model)

    def test_register_and_retrieve_by_index(self) -> None:
        """Test registering and retrieving model by index."""
        registry = ModelRegistry()
        mock_model = MagicMock()
        registry._register("main", mock_model)
        self.assertEqual(registry["main"], mock_model)

    def test_attribute_error_for_missing_model(self) -> None:
        """Test AttributeError for missing model slot."""
        registry = ModelRegistry()
        with self.assertRaises(AttributeError) as ctx:
            _ = registry.nonexistent
        self.assertIn("nonexistent", str(ctx.exception))

    def test_key_error_for_missing_model(self) -> None:
        """Test KeyError for missing model slot."""
        registry = ModelRegistry()
        with self.assertRaises(KeyError) as ctx:
            _ = registry["nonexistent"]
        self.assertIn("nonexistent", str(ctx.exception))

    def test_keys_method(self) -> None:
        """Test keys() method returns all slot names."""
        registry = ModelRegistry()
        registry._register("main", MagicMock())
        registry._register("secondary", MagicMock())
        keys = registry.keys()
        self.assertIn("main", keys)
        self.assertIn("secondary", keys)

    def test_contains_method(self) -> None:
        """Test __contains__ method."""
        registry = ModelRegistry()
        registry._register("main", MagicMock())
        self.assertIn("main", registry)
        self.assertNotIn("nonexistent", registry)

    def test_len_method(self) -> None:
        """Test __len__ method."""
        registry = ModelRegistry()
        self.assertEqual(len(registry), 0)
        registry._register("main", MagicMock())
        self.assertEqual(len(registry), 1)
        registry._register("secondary", MagicMock())
        self.assertEqual(len(registry), 2)

    def test_private_attribute_raises(self) -> None:
        """Test that accessing private attributes raises AttributeError."""
        registry = ModelRegistry()
        with self.assertRaises(AttributeError):
            _ = registry._private


class TestRuntime(TestCase):
    """Tests for Runtime class."""

    def test_runtime_initial_state(self) -> None:
        """Test Runtime initial state before initialization."""
        rt = Runtime()
        self.assertFalse(rt.is_initialized)
        self.assertIsInstance(rt.models, ModelRegistry)

    def test_runtime_app_not_initialized(self) -> None:
        """Test accessing app before initialization raises RuntimeError."""
        rt = Runtime()
        with self.assertRaises(RuntimeError) as ctx:
            _ = rt.app
        self.assertIn("not initialized", str(ctx.exception))

    def test_runtime_config_not_initialized(self) -> None:
        """Test accessing config before initialization raises RuntimeError."""
        rt = Runtime()
        with self.assertRaises(RuntimeError) as ctx:
            _ = rt.config
        self.assertIn("not initialized", str(ctx.exception))


class TestRuntimeAsync(IsolatedAsyncioTestCase):
    """Async tests for Runtime class."""

    async def test_runtime_double_init_raises(self) -> None:
        """Test that double initialization raises RuntimeError."""
        rt = Runtime()
        rt._initialized = True  # Simulate initialized state
        with self.assertRaises(RuntimeError) as ctx:
            await rt.initialize()
        self.assertIn("already initialized", str(ctx.exception))

    async def test_runtime_shutdown_when_not_initialized(self) -> None:
        """Test that shutdown is safe when not initialized."""
        rt = Runtime()
        await rt.shutdown()  # Should not raise


class TestCliArgumentParsing(TestCase):
    """Tests for CLI argument parsing."""

    def test_parse_run_command(self) -> None:
        """Test parsing 'run' command."""
        args = _parse_args(["run", "."])
        self.assertEqual(args.command, "run")
        self.assertEqual(args.project_path, ".")

    def test_parse_run_default_path(self) -> None:
        """Test parsing 'run' with default path."""
        args = _parse_args(["run"])
        self.assertEqual(args.command, "run")
        self.assertEqual(args.project_path, ".")

    def test_parse_run_with_port(self) -> None:
        """Test parsing 'run' with --port option."""
        args = _parse_args(["run", ".", "--port", "9000"])
        self.assertEqual(args.port, 9000)

    def test_parse_run_with_config(self) -> None:
        """Test parsing 'run' with --config option."""
        args = _parse_args(["run", ".", "--config", "custom.yaml"])
        self.assertEqual(args.config, "custom.yaml")

    def test_parse_run_with_no_platform(self) -> None:
        """Test parsing 'run' with --no-platform flag."""
        args = _parse_args(["run", ".", "--no-platform"])
        self.assertTrue(args.no_platform)

    def test_parse_run_with_log_level(self) -> None:
        """Test parsing 'run' with --log-level option."""
        args = _parse_args(["run", ".", "--log-level", "debug"])
        self.assertEqual(args.log_level, "debug")

    def test_parse_run_default_values(self) -> None:
        """Test default values for 'run' command."""
        args = _parse_args(["run"])
        self.assertIsNone(args.port)
        self.assertEqual(args.config, "agentapp.yaml")
        self.assertFalse(args.no_platform)
        self.assertEqual(args.log_level, "info")
