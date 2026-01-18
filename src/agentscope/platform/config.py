# -*- coding: utf-8 -*-
"""The platform configuration module for AgentScope.

This module defines the PlatformConfig dataclass that is used to inject
runtime configuration into developer applications running on the platform.
"""
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..model import ChatModelBase
    from ..formatter import FormatterBase
    from ..tool import Toolkit


@dataclass
class PlatformConfig:
    """Platform-injected runtime configuration.

    This configuration is provided by the platform when instantiating
    developer applications in containers. Developers must use these
    components instead of creating their own model connections or tools.

    Attributes:
        model: The chat model instance provided by the platform.
        formatter: The message formatter matching the model type.
        toolkit: The toolkit containing MCP tools from the platform pool.
        instance_id: Unique identifier for this application instance.
        tenant_id: The tenant (user) who owns this instance.
        app_name: The name of the application from the manifest.
        app_version: The version of the application from the manifest.
    """

    # Core components (injected by platform)
    model: "ChatModelBase"
    formatter: "FormatterBase"
    toolkit: "Toolkit"

    # Platform metadata
    instance_id: str
    tenant_id: str
    app_name: str
    app_version: str
