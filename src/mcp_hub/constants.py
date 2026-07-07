"""MCP Hub constants and exceptions."""

import os
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
# FIX-08: unify to ~/.config/mcp-hub/ with ~/.mcp-hub/ backward compat
# FIX-07: read MCP_HUB_CONFIG_DIR env var
_env_dir = os.environ.get("MCP_HUB_CONFIG_DIR")
if _env_dir:
    _default_data_dir = Path(_env_dir).expanduser().resolve()
else:
    try:
        _home = Path.home()
    except (RuntimeError, OSError):
        _home = Path.cwd() if Path.cwd().exists() else Path("/tmp")
    _default_data_dir = _home / ".config" / "mcp-hub"
    if (_home / ".mcp-hub").exists() and not _default_data_dir.exists():
        _default_data_dir = _home / ".mcp-hub"

DEFAULT_DATA_DIR: Final[Path] = _default_data_dir
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
    5: "critical",
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
    if isinstance(level, str):
        return level.lower() in _REVERSE_SECURITY
    return False


def get_security_level_name(level: int) -> Optional[str]:
    """Get the name of a security level by its numeric value."""
    return SECURITY_LEVELS.get(level)


def get_security_level_value(name: str) -> Optional[int]:
    """Get the numeric value of a security level by its name."""
    return _REVERSE_SECURITY.get(name)
