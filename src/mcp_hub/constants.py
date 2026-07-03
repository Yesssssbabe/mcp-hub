"""MCP Hub constants and exceptions."""

from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Final, List, Optional, Tuple, Union


# ──────────────────────────────────────────
# Exception Hierarchy
# ──────────────────────────────────────────
class MCPHubError(Exception):
    """Base exception for all MCP Hub errors."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


class InstallationError(MCPHubError):
    """Raised when a tool installation fails."""


class RegistryError(MCPHubError):
    """Raised when a registry operation fails."""


class SecurityError(MCPHubError):
    """Raised when a security check fails."""


class ConfigError(MCPHubError):
    """Raised when configuration is invalid or missing."""


# ──────────────────────────────────────────
# Path Constants
# ──────────────────────────────────────────
DEFAULT_DATA_DIR: Final[Path] = Path.home() / ".mcp-hub"
DEFAULT_REGISTRY_PATH: Final[Path] = DEFAULT_DATA_DIR / "registry.json"
DEFAULT_CONFIG_PATH: Final[Path] = DEFAULT_DATA_DIR / "config.json"


def _validate_data_dir(path: Path) -> Path:
    """Validate data directory for symlink attacks and overly permissive modes."""
    if path.exists() and path.is_symlink():
        raise SecurityError(
            f"Data directory is a symlink: {path}",
            error_code="SEC_PATH_SYMLINK",
            details={"path": str(path)},
        )
    path.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode
    if mode & 0o022:
        raise SecurityError(
            f"Data directory has overly permissive mode: {oct(mode)}",
            error_code="SEC_PATH_PERMS",
            details={"path": str(path), "mode": oct(mode)},
        )
    return path


# ──────────────────────────────────────────
# Supported Clients & Install Types
# ──────────────────────────────────────────
SUPPORTED_CLIENTS: Final[Tuple[str, ...]] = (
    "claude",
    "cursor",
    "cline",
    "copilot",
    "vscode",
    "windsurf",
)

INSTALL_TYPES: Final[Tuple[str, ...]] = (
    "npm",
    "pip",
    "docker",
    "git",
    "binary",
)


# ──────────────────────────────────────────
# Security & Logging Levels
# ──────────────────────────────────────────
_SECURITY_LEVELS_PRIVATE: Dict[int, str] = {
    0: "unknown",
    1: "low",
    2: "medium",
    3: "high",
    4: "verified",
}

SECURITY_LEVELS: Final[MappingProxyType[int, str]] = MappingProxyType(
    _SECURITY_LEVELS_PRIVATE
)

_REVERSE_SECURITY: Final[Dict[str, int]] = {
    v: k for k, v in _SECURITY_LEVELS_PRIVATE.items()
}

LOG_LEVELS: Final[Tuple[str, ...]] = (
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
)


def is_valid_security_level(level: Union[int, str]) -> bool:
    """Check if a security level is valid (by numeric value or name)."""
    if isinstance(level, int):
        return level in SECURITY_LEVELS
    return level in _REVERSE_SECURITY


def get_security_level_name(level: int) -> Optional[str]:
    """Get the name of a security level by its numeric value."""
    return SECURITY_LEVELS.get(level)


def get_security_level_value(name: str) -> Optional[int]:
    """Get the numeric value of a security level by its name."""
    return _REVERSE_SECURITY.get(name)
