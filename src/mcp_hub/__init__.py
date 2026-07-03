"""MCP Hub - Discover, install, and manage MCP tools."""
from __future__ import annotations

from typing import Final

__version__: Final = "0.1.0"
__author__: Final = "MCP Hub Team"

from mcp_hub.constants import (
    MCPHubError,
    InstallationError,
    RegistryError,
    SecurityError,
    ConfigError,
    DEFAULT_REGISTRY_PATH,
    DEFAULT_CONFIG_PATH,
    SUPPORTED_CLIENTS,
    INSTALL_TYPES,
)

__all__: list[str] = [
    "__version__",
    "MCPHubError",
    "InstallationError",
    "RegistryError",
    "SecurityError",
    "ConfigError",
    "DEFAULT_REGISTRY_PATH",
    "DEFAULT_CONFIG_PATH",
    "SUPPORTED_CLIENTS",
    "INSTALL_TYPES",
]
