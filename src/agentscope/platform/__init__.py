# -*- coding: utf-8 -*-
"""The platform module for AgentScope.

This module provides functionality for building and deploying AgentScope
applications on a multi-tenant platform, including:

- PlatformConfig: Runtime configuration injected by the platform
- Manifest parsing: Parse and validate agentscope.yaml manifest files
- Pack command: Package applications for deployment
- Runtime: Container runtime entry point
- Server: HTTP+SSE service for chat interactions
"""

from .config import PlatformConfig
from .manifest import (
    Manifest,
    EntrypointConfig,
    RuntimeConfig,
    parse_manifest,
    validate_entrypoint,
    MANIFEST_FILENAME,
)
from .pack import pack
from .server import ChatServer
from .session_backend import (
    PlatformSessionBackend,
    RedisSessionBackend,
    DatabaseSessionBackend,
    FileSessionBackend,
    create_session_backend,
)

__all__ = [
    # Config
    "PlatformConfig",
    # Manifest
    "Manifest",
    "EntrypointConfig",
    "RuntimeConfig",
    "parse_manifest",
    "validate_entrypoint",
    "MANIFEST_FILENAME",
    # Pack
    "pack",
    # Server
    "ChatServer",
    # Session backends
    "PlatformSessionBackend",
    "RedisSessionBackend",
    "DatabaseSessionBackend",
    "FileSessionBackend",
    "create_session_backend",
]
