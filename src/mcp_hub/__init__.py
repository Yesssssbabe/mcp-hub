"""MCP Hub - Discover, install, and manage MCP tools."""
__version__ = "0.1.0"
__author__ = "MCP Hub Team"

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

__all__ = [
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
