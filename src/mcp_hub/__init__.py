"""MCP Hub - Discover, install, and manage MCP tools."""
from __future__ import annotations

from typing import Final

__version__: Final = "0.2.0"
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

# v0.2.0 OSV security scanning exports
from mcp_hub.vulnerability_models import (
    VulnerabilityEntry,
    ScanResult,
    SeverityLevel,
    VulnerabilitySource,
)
from mcp_hub.osv_client import OSVClient
from mcp_hub.scan_cache import ScanCache

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
    # v0.2.0 security exports
    "VulnerabilityEntry",
    "ScanResult",
    "SeverityLevel",
    "VulnerabilitySource",
    "OSVClient",
    "ScanCache",
]
