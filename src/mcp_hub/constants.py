"""MCP Hub constants and exceptions."""

from typing import Dict, List


# ──────────────────────────────────────────
# Exception Hierarchy
# ──────────────────────────────────────────
class MCPHubError(Exception):
    """Base exception for all MCP Hub errors."""
    pass


class InstallationError(MCPHubError):
    """Raised when a tool installation fails."""
    pass


class RegistryError(MCPHubError):
    """Raised when a registry operation fails."""
    pass


class SecurityError(MCPHubError):
    """Raised when a security check fails."""
    pass


class ConfigError(MCPHubError):
    """Raised when configuration is invalid or missing."""
    pass


# ──────────────────────────────────────────
# Path Constants
# ──────────────────────────────────────────
DEFAULT_DATA_DIR: str = "~/.mcp-hub"
DEFAULT_REGISTRY_PATH: str = "~/.mcp-hub/registry.json"
DEFAULT_CONFIG_PATH: str = "~/.mcp-hub/config.json"


# ──────────────────────────────────────────
# Supported Clients & Install Types
# ──────────────────────────────────────────
SUPPORTED_CLIENTS: List[str] = [
    "claude",
    "cursor",
    "cline",
    "copilot",
    "vscode",
    "windsurf",
]

INSTALL_TYPES: List[str] = [
    "npm",
    "pip",
    "docker",
    "git",
    "binary",
]


# ──────────────────────────────────────────
# Security & Logging Levels
# ──────────────────────────────────────────
SECURITY_LEVELS: Dict[int, str] = {
    0: "unknown",
    1: "low",
    2: "medium",
    3: "high",
    4: "verified",
}

LOG_LEVELS: List[str] = [
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
]
