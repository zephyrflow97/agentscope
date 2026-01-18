# -*- coding: utf-8 -*-
"""The manifest parsing module for AgentScope platform.

This module handles parsing and validation of agentscope.yaml manifest files
that define application metadata and entry points.
"""
import os
from dataclasses import dataclass, field
from typing import Any

import yaml


MANIFEST_FILENAME = "agentscope.yaml"


@dataclass
class EntrypointConfig:
    """Entrypoint configuration for the application.

    Attributes:
        module: Python module path (e.g., "app.main").
        factory: Factory function name that creates the Agent.
    """

    module: str
    factory: str


@dataclass
class RuntimeConfig:
    """Runtime requirements configuration.

    Attributes:
        python: Python version requirement (e.g., ">=3.10").
    """

    python: str = ">=3.10"


@dataclass
class Manifest:
    """Application manifest parsed from agentscope.yaml.

    Attributes:
        name: Application name.
        version: Application version.
        description: Application description.
        author: Application author email or name.
        entrypoint: Entrypoint configuration.
        runtime: Runtime requirements.
    """

    name: str
    version: str
    entrypoint: EntrypointConfig
    description: str = ""
    author: str = ""
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Manifest":
        """Create a Manifest from a dictionary.

        Args:
            data: Dictionary parsed from YAML.

        Returns:
            Manifest instance.

        Raises:
            ValueError: If required fields are missing or invalid.
        """
        # Validate required fields
        required_fields = ["name", "version", "entrypoint"]
        missing = [f for f in required_fields if f not in data]
        if missing:
            raise ValueError(
                f"Missing required fields in manifest: {', '.join(missing)}"
            )

        # Parse entrypoint
        ep_data = data["entrypoint"]
        if not isinstance(ep_data, dict):
            raise ValueError("Entrypoint must be a dictionary")

        ep_required = ["module", "factory"]
        ep_missing = [f for f in ep_required if f not in ep_data]
        if ep_missing:
            raise ValueError(
                f"Missing required entrypoint fields: {', '.join(ep_missing)}"
            )

        entrypoint = EntrypointConfig(
            module=ep_data["module"],
            factory=ep_data["factory"],
        )

        # Parse runtime (optional)
        runtime_data = data.get("runtime", {})
        runtime = RuntimeConfig(
            python=runtime_data.get("python", ">=3.10"),
        )

        return cls(
            name=data["name"],
            version=data["version"],
            description=data.get("description", ""),
            author=data.get("author", ""),
            entrypoint=entrypoint,
            runtime=runtime,
        )


def parse_manifest(manifest_path: str) -> Manifest:
    """Parse an agentscope.yaml manifest file.

    Args:
        manifest_path: Path to the manifest file or directory containing it.

    Returns:
        Parsed Manifest instance.

    Raises:
        FileNotFoundError: If manifest file doesn't exist.
        ValueError: If manifest is invalid.
    """
    # If path is a directory, look for the manifest file inside
    if os.path.isdir(manifest_path):
        manifest_path = os.path.join(manifest_path, MANIFEST_FILENAME)

    if not os.path.exists(manifest_path):
        raise FileNotFoundError(
            f"Manifest file not found: {manifest_path}"
        )

    with open(manifest_path, "r", encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in manifest: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("Manifest must be a YAML dictionary")

    return Manifest.from_dict(data)


def validate_entrypoint(manifest: Manifest, app_dir: str) -> bool:
    """Validate that the entrypoint module and factory function exist.

    Args:
        manifest: The parsed manifest.
        app_dir: Directory containing the application code.

    Returns:
        True if validation passes.

    Raises:
        ValueError: If entrypoint is invalid.
    """
    import importlib.util
    import sys

    # Add app directory to path temporarily
    original_path = sys.path.copy()
    sys.path.insert(0, app_dir)

    try:
        # Try to import the module
        module_name = manifest.entrypoint.module
        spec = importlib.util.find_spec(module_name)

        if spec is None:
            raise ValueError(
                f"Cannot find entrypoint module: {module_name}"
            )

        # Load the module to check for factory function
        module = importlib.util.module_from_spec(spec)
        if spec.loader is not None:
            spec.loader.exec_module(module)

        factory_name = manifest.entrypoint.factory
        if not hasattr(module, factory_name):
            raise ValueError(
                f"Factory function '{factory_name}' not found in "
                f"module '{module_name}'"
            )

        factory = getattr(module, factory_name)
        if not callable(factory):
            raise ValueError(
                f"'{factory_name}' in module '{module_name}' is not callable"
            )

        return True

    finally:
        # Restore original path
        sys.path = original_path
