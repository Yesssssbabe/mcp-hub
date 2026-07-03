"""MCP Hub configuration management for multiple AI clients.

Supports Claude, Cursor, Cline, Copilot, VSCode, and Windsurf with
cross-platform configuration path detection and management.
"""

import os
import sys
import json
import re
import shutil
import tempfile
import logging
import random
import threading
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

from filelock import FileLock
from pydantic import BaseModel, Field, field_validator

from mcp_hub.constants import (
    ConfigError,
    SUPPORTED_CLIENTS,
    DEFAULT_CONFIG_PATH,
    DEFAULT_DATA_DIR,
)
from mcp_hub.registry import Registry, MCPTool


# ---------------------------------------------------------------------------
# Cross-platform configuration paths
# ---------------------------------------------------------------------------

CLIENT_CONFIG_PATHS = {
    "claude": {
        "macos": "~/Library/Application Support/Claude/claude_desktop_config.json",
        "windows": "%APPDATA%/Claude/claude_desktop_config.json",
        "linux": "~/.config/claude/claude_desktop_config.json",
    },
    "cursor": {
        "macos": "~/.cursor/mcp.json",
        "windows": "%APPDATA%/Cursor/mcp.json",
        "linux": "~/.config/Cursor/mcp.json",
    },
    "cline": {
        "macos": "~/.cline/mcp.json",
        "windows": "%APPDATA%/Cline/mcp.json",
        "linux": "~/.config/Cline/mcp.json",
    },
    "copilot": {
        "macos": "~/.github/copilot/mcp.json",
        "windows": "%APPDATA%/GitHub Copilot/mcp.json",
        "linux": "~/.config/GitHub Copilot/mcp.json",
    },
    "vscode": {
        "macos": "~/.vscode/mcp.json",
        "windows": "%APPDATA%/Code/User/mcp.json",
        "linux": "~/.config/Code/User/mcp.json",
    },
    "windsurf": {
        "macos": "~/.windsurf/mcp.json",
        "windows": "%APPDATA%/Windsurf/mcp.json",
        "linux": "~/.config/Windsurf/mcp.json",
    },
}

# Sensitive environment variable keys that should be handled with extra care
SENSITIVE_ENV_KEYS = {
    "api_key",
    "apikey",
    "api_secret",
    "apisecret",
    "secret",
    "token",
    "password",
    "auth",
    "credential",
    "key",
    "private_key",
    "access_key",
    "secret_key",
    "access_token",
    "refresh_token",
    "database_url",
    "db_url",
    "connection_string",
    "dsn",
    "jdbc_url",
    "redis_url",
    "mongo_uri",
    "jwt",
    "client_secret",
    "client_id",
    "session",
    "cookie",
    "csrf_token",
    "bearer",
    "passwd",
    "pwd",
    "pin",
    "passphrase",
    "ssh_key",
    "github_token",
    "ghp_",
    "credentials",
    "creds",
    "nonce",
    "salt",
}

_logger = logging.getLogger(__name__)


def _get_current_os() -> str:
    """Return the normalized OS identifier."""
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32" or os.name == "nt":
        return "windows"
    return "linux"


def _get_home_dir() -> Path:
    """Return the user's home directory, ignoring potential HOME tampering."""
    return Path.home()


def _is_safe_path(path: str, allowed_base: str) -> bool:
    """Verify that *path* is inside *allowed_base* after resolving symlinks.

    Returns True only if the resolved path is a descendant of the resolved
    allowed_base directory.
    """
    try:
        resolved = Path(path).resolve()
        base = Path(allowed_base).resolve()
        resolved.relative_to(base)
        return True
    except (ValueError, RuntimeError):
        return False


def _expand_path(path: str, allow_vars: bool = False) -> str:
    """Expand user home and optionally environment variables in a path.

    Uses Path.home() instead of os.path.expanduser() to avoid
    HOME environment variable tampering. Resolves symbolic links.
    For external inputs, environment variables are rejected to prevent injection.
    """
    path = os.fspath(path)
    if not allow_vars:
        if any(c in path for c in ("$", "%")):
            raise ConfigError(
                "Path contains environment variable references which are not allowed for security reasons"
            )
        expanded = path
    else:
        expanded = os.path.expandvars(path)
    home = _get_home_dir()
    if expanded.startswith("~"):
        # Replace ~ with the real home directory, ignoring HOME env var
        expanded = str(home / expanded[1:].lstrip("/\\"))
    return str(Path(expanded).resolve())


# Allowed directories for import operations
ALLOWED_IMPORT_DIRS = [
    _expand_path(DEFAULT_DATA_DIR),
    _expand_path("~/.config"),
]

# Allowed directory for export operations
ALLOWED_EXPORT_DIR = _expand_path(DEFAULT_DATA_DIR)


# Allowed commands for MCP servers (whitelist)
ALLOWED_COMMANDS = {
    "npx", "uvx", "node", "python", "python3", "docker", "uv"
}

# Dangerous shell metacharacters that should not appear in args
SHELL_METACHARS = re.compile(r'[;|&$(){}[\]<>]`')

# Maximum allowed nesting depth for global_settings
MAX_GLOBAL_SETTINGS_DEPTH = 3

# Maximum allowed size for global_settings (in bytes, roughly)
MAX_GLOBAL_SETTINGS_SIZE = 10 * 1024  # 10KB


def _validate_command(command: str) -> None:
    """Validate that a command is in the allowed whitelist and exists in PATH."""
    if not command or not command.strip():
        raise ConfigError("Command must not be empty")
    cmd_path = command.strip()
    cmd_name = os.path.basename(cmd_path)
    if cmd_name not in ALLOWED_COMMANDS:
        raise ConfigError(
            f"Command '{cmd_name}' is not in the allowed list: {ALLOWED_COMMANDS}"
        )
    if not os.path.isabs(cmd_path) and shutil.which(cmd_path) is None:
        raise ConfigError(f"Command '{cmd_path}' not found in PATH")
    if ".." in cmd_path or "~" in cmd_path:
        raise ConfigError(f"Command path contains invalid characters: {cmd_path}")


def _validate_args(args: List[Any]) -> None:
    """Validate that args do not contain shell metacharacters."""
    if not isinstance(args, list):
        raise ConfigError("Args must be a list of strings")
    for arg in args:
        if not isinstance(arg, str):
            raise ConfigError(f"Arg must be a string, got {type(arg).__name__}")
        if SHELL_METACHARS.search(arg):
            raise ConfigError(f"Argument contains illegal shell characters: {arg}")


def _validate_env(env: Dict[str, Any]) -> None:
    """Validate environment variable keys and values."""
    if not isinstance(env, dict):
        raise ConfigError("Env must be a dictionary")
    for key, value in env.items():
        if not isinstance(key, str):
            raise ConfigError(f"Env key must be a string, got {type(key).__name__}")
        if not isinstance(value, str):
            raise ConfigError(f"Env value must be a string, got {type(value).__name__}")
        lower_key = key.lower()
        if lower_key in {"ld_preload", "path", "ld_library_path", "dyld_insert_libraries"}:
            raise ConfigError(
                f"Environment variable '{key}' is not allowed for security reasons"
            )
        if "\n" in value or "\r" in value:
            raise ConfigError(f"Env value for '{key}' contains newlines")
        if len(value) > 4096:
            raise ConfigError(
                f"Env value for '{key}' exceeds maximum length of 4096 characters"
            )


def _validate_global_settings(settings: Dict[str, Any], depth: int = 0) -> None:
    """Validate global_settings depth, size, and types."""
    if not isinstance(settings, dict):
        raise ConfigError("global_settings must be a dictionary")
    if depth > MAX_GLOBAL_SETTINGS_DEPTH:
        raise ConfigError(
            f"global_settings exceeds maximum nesting depth of {MAX_GLOBAL_SETTINGS_DEPTH}"
        )
    try:
        size = len(json.dumps(settings))
    except (TypeError, ValueError):
        raise ConfigError("global_settings contains non-serializable values")
    if size > MAX_GLOBAL_SETTINGS_SIZE:
        raise ConfigError(
            f"global_settings exceeds maximum size of {MAX_GLOBAL_SETTINGS_SIZE} bytes"
        )
    for key, value in settings.items():
        if not isinstance(key, str):
            raise ConfigError(
                f"global_settings key must be a string, got {type(key).__name__}"
            )
        if key.startswith("__") or key in {"prototype", "constructor"}:
            raise ConfigError(f"global_settings key '{key}' is not allowed")
        if isinstance(value, dict):
            _validate_global_settings(value, depth + 1)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, (dict, list)):
                    _validate_global_settings({"_": item}, depth + 1)
                elif not isinstance(item, (str, int, float, bool, type(None))):
                    raise ConfigError(
                        f"global_settings value type {type(item).__name__} is not allowed"
                    )
        elif not isinstance(value, (str, int, float, bool, type(None))):
            raise ConfigError(
                f"global_settings value type {type(value).__name__} is not allowed"
            )


def _validate_import_path(file_path: str) -> Path:
    """Validate that an import path is within allowed directories and is a .json file."""
    # Disable environment variable expansion for import paths to prevent injection
    expanded = _expand_path(file_path, allow_vars=False)
    path = Path(expanded).resolve()
    if ".." in file_path:
        raise ConfigError("Import path contains '..' which is not allowed")
    if path.suffix.lower() != ".json":
        raise ConfigError("Import file must be a .json file")
    allowed = False
    for allowed_dir in ALLOWED_IMPORT_DIRS:
        allowed_path = Path(allowed_dir).resolve()
        try:
            path.relative_to(allowed_path)
            allowed = True
            break
        except ValueError:
            continue
    if not allowed:
        raise ConfigError(
            f"Import path {path} must be within allowed directories: {ALLOWED_IMPORT_DIRS}"
        )
    return path


def _validate_export_path(output_path: str) -> Path:
    """Validate that an export path is within the allowed export directory."""
    expanded = _expand_path(output_path, allow_vars=False)
    path = Path(expanded).resolve()
    if ".." in output_path:
        raise ConfigError("Export path contains '..' which is not allowed")
    allowed_dir = Path(ALLOWED_EXPORT_DIR).resolve()
    try:
        path.relative_to(allowed_dir)
    except ValueError:
        raise ConfigError(
            f"Export path {path} must be within the allowed export directory: {allowed_dir}"
        )
    return path


def _backup_file(file_path: str) -> Optional[str]:
    """Create a timestamped backup of *file_path* if it exists.

    Returns the backup path or None if the file did not exist.
    Resolves symbolic links and does not follow them during copy.
    """
    real_path = os.path.realpath(file_path)
    if not os.path.exists(real_path):
        return None
    # Ensure the resolved path is within the home directory for safety
    home = _get_home_dir()
    try:
        Path(real_path).resolve().relative_to(home.resolve())
    except ValueError:
        raise ConfigError(
            f"Backup target is outside the home directory: {file_path}"
        )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    pid = os.getpid()
    rand = random.randint(0, 9999)
    backup_path = f"{real_path}.backup.{timestamp}.{pid}.{rand:04d}"
    shutil.copy2(real_path, backup_path, follow_symlinks=False)
    os.chmod(backup_path, 0o600)
    _logger.info("Backed up %s -> %s", file_path, backup_path)
    return backup_path


def _mask_env_values(env: Dict[str, str]) -> Dict[str, str]:
    """Return a copy of env dict with sensitive values masked."""
    masked = {}
    for key, value in env.items():
        lower_key = key.lower()
        if any(s in lower_key for s in SENSITIVE_ENV_KEYS):
            masked[key] = "***"
        else:
            # Heuristic: mask if value looks like a secret
            val_lower = value.lower()
            if (val_lower.startswith("sk-") or
                val_lower.startswith("ghp_") or
                val_lower.startswith("github_pat_") or
                val_lower.startswith("akia") or
                val_lower.startswith("asia") or
                val_lower.startswith("sg.") or
                val_lower.startswith("rk-") or
                val_lower.startswith("pk-") or
                # JWT heuristic: three segments separated by dots
                (value.count(".") == 2 and len(value) > 20) or
                # URL with embedded credentials
                ("://" in value and "@" in value)):
                masked[key] = "***"
            else:
                masked[key] = value
    return masked


def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    """Atomically write JSON data to *path* using a temp file + os.replace.

    If the write fails, the temporary file is cleaned up and the original
    *path* is left untouched.
    """
    dir_name = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class MCPConfig(BaseModel):
    """Represents an MCP server configuration for a client."""

    name: str
    command: str
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    description: Optional[str] = None
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Server name must not be empty")
        return v.strip()

    @field_validator("command")
    @classmethod
    def _command_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Command must not be empty")
        return v.strip()

    def to_mcp_dict(self, mask_sensitive: bool = False) -> Dict[str, Any]:
        """Serialize to the standard MCP JSON format."""
        result: Dict[str, Any] = {"command": self.command}
        if self.args:
            result["args"] = self.args
        if self.env:
            if mask_sensitive:
                result["env"] = _mask_env_values(self.env)
            else:
                result["env"] = self.env
        return result

    @classmethod
    def from_mcp_dict(cls, name: str, data: Dict[str, Any]) -> "MCPConfig":
        """Create an MCPConfig from standard MCP JSON data."""
        return cls(
            name=name,
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env", {}),
            enabled=data.get("enabled", True),
            description=data.get("description"),
        )


class ClientConfig(BaseModel):
    """Represents a client's full MCP configuration."""

    client_name: str
    servers: Dict[str, MCPConfig] = Field(default_factory=dict)
    global_settings: Dict[str, Any] = Field(default_factory=dict)
    version: str = "1.0"

    def add_server(self, config: MCPConfig) -> None:
        """Add or replace a server in this client configuration."""
        self.servers[config.name] = config

    def remove_server(self, server_name: str) -> bool:
        """Remove a server by name. Returns True if it existed."""
        if server_name in self.servers:
            del self.servers[server_name]
            return True
        return False

    def to_mcp_json(self, mask_sensitive: bool = False) -> Dict[str, Any]:
        """Generate the standard MCP JSON configuration."""
        mcp_servers: Dict[str, Any] = {}
        for name, server in self.servers.items():
            if server.enabled:
                mcp_servers[name] = server.to_mcp_dict(mask_sensitive=mask_sensitive)
        return {"mcpServers": mcp_servers, **self.global_settings}

    @classmethod
    def from_mcp_json(cls, client_name: str, data: Dict[str, Any]) -> "ClientConfig":
        """Parse standard MCP JSON into a ClientConfig."""
        servers: Dict[str, MCPConfig] = {}
        mcp_servers = data.get("mcpServers", {})
        for name, server_data in mcp_servers.items():
            servers[name] = MCPConfig.from_mcp_dict(name, server_data)
        global_settings = {k: v for k, v in data.items() if k != "mcpServers"}
        return cls(
            client_name=client_name,
            servers=servers,
            global_settings=global_settings,
        )


# ---------------------------------------------------------------------------
# ConfigManager
# ---------------------------------------------------------------------------

class ConfigManager:
    """Manages MCP configurations for multiple AI clients."""

    def __init__(self, config_path: Optional[str] = None):
        if config_path:
            expanded = _expand_path(config_path, allow_vars=False)
            # Test mode: allow temporary paths so the test suite can use tmp_path.
            if os.environ.get("MCP_HUB_TEST_MODE") != "1":
                allowed_base = _expand_path(DEFAULT_DATA_DIR, allow_vars=True)
                if not _is_safe_path(expanded, allowed_base):
                    raise ConfigError(
                        f"Config path must be inside {allowed_base}: {config_path}"
                    )
            self.config_path = expanded
            config_dir = os.path.dirname(self.config_path)
            if config_dir:
                os.makedirs(config_dir, exist_ok=True)
        else:
            self.config_path = _expand_path(DEFAULT_CONFIG_PATH, allow_vars=True)
        self.configs: Dict[str, ClientConfig] = {}
        self._registry = Registry()
        self._lock = threading.RLock()
        self._hub_lock = FileLock(self.config_path + ".lock")
        self._load()

    # -- Internal persistence ------------------------------------------------

    def _load(self) -> None:
        """Load configurations from the hub's internal config file."""
        with self._lock:
            if not os.path.exists(self.config_path):
                return
            try:
                with self._hub_lock:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
            except json.JSONDecodeError as exc:
                _logger.error(
                    "Invalid JSON in hub config %s: %s", self.config_path, exc
                )
                raise ConfigError(
                    f"Invalid JSON in config file {self.config_path}: {exc}"
                ) from exc

            for client_name, client_data in data.items():
                if client_name not in SUPPORTED_CLIENTS:
                    continue
                self.configs[client_name] = ClientConfig(**client_data)

    def _save(self) -> None:
        """Save the hub's internal configuration state to disk."""
        with self._lock:
            config_dir = os.path.dirname(self.config_path)
            if config_dir:
                os.makedirs(config_dir, exist_ok=True)
            data: Dict[str, Any] = {}
            for name, config in self.configs.items():
                data[name] = config.model_dump()
            with self._hub_lock:
                _atomic_write_json(self.config_path, data)
            os.chmod(self.config_path, 0o600)

    # -- Server management ---------------------------------------------------

    def add_server(self, client_name: str, tool: MCPTool) -> bool:
        """Add an MCP server to a client's configuration.

        Steps:
        1. Get the tool's MCP config template from the registry.
        2. Generate the MCP server config JSON.
        3. Read the existing client config (if it exists).
        4. Merge the new server config.
        5. Write the updated client config.
        6. Save the internal hub config state.
        """
        with self._lock:
            if client_name not in SUPPORTED_CLIENTS:
                raise ConfigError(f"Unsupported client: {client_name}")

            # 1. Build the MCP server configuration from the tool.
            tool_config = tool.mcp_config_template
            server_name = tool.mcp_server_name or tool.name
            command = tool_config.command if tool_config else ""
            args = list(tool_config.args) if tool_config else []
            env = dict(tool_config.env) if tool_config and tool_config.env else {}
            description = tool.description

            if not command:
                raise ConfigError(
                    f"Tool '{tool.name}' has no command defined"
                )

            # Security validation: command whitelist, args filtering, env restrictions
            _validate_command(command)
            _validate_args(args)
            _validate_env(env)

            mcp_server = MCPConfig(
                name=server_name,
                command=command,
                args=args,
                env=env,
                description=description,
                enabled=True,
            )

            # 2. Resolve client config path before any mutation.
            client_file_path = self.get_client_config_path(client_name)
            if not client_file_path:
                raise ConfigError(
                    f"Could not determine config path for {client_name}"
                )

            # 3. Read existing client config under file lock to preserve
            #    global settings.
            existing_data: Dict[str, Any] = {}
            if os.path.exists(client_file_path):
                client_lock = FileLock(client_file_path + ".lock")
                with client_lock:
                    _backup_file(client_file_path)
                    try:
                        with open(
                            client_file_path, "r", encoding="utf-8"
                        ) as f:
                            existing_data = json.load(f)
                    except json.JSONDecodeError as exc:
                        _logger.warning(
                            "Client config %s contains invalid JSON (%s). "
                            "Existing non-mcpServers settings may be lost.",
                            client_file_path,
                            exc,
                        )
                        corrupted_path = (
                            f"{client_file_path}.corrupted."
                            f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
                        )
                        try:
                            shutil.copy2(
                                client_file_path, corrupted_path
                            )
                            _logger.info(
                                "Preserved corrupted config at %s",
                                corrupted_path,
                            )
                        except OSError:
                            pass
                        existing_data = {}

            # 4. Update in-memory state.
            if client_name not in self.configs:
                self.configs[client_name] = ClientConfig(
                    client_name=client_name
                )
            self.configs[client_name].add_server(mcp_server)

            # 5. Merge: internal state is authoritative for mcpServers.
            merged = existing_data.copy()
            merged["mcpServers"] = self.configs[
                client_name
            ].to_mcp_json().get("mcpServers", {})

            # 6. Persist hub config first (source of truth), then client.
            self._save()

        # Write client file outside self._lock to avoid nested FileLock
        # contention with other processes.
        os.makedirs(
            os.path.dirname(client_file_path), exist_ok=True
        )
        client_lock = FileLock(client_file_path + ".lock")
        with client_lock:
            _atomic_write_json(client_file_path, merged)
        os.chmod(client_file_path, 0o600)

        return True

    def remove_server(self, client_name: str, server_name: str) -> bool:
        """Remove an MCP server from a client's configuration."""
        with self._lock:
            if client_name not in SUPPORTED_CLIENTS:
                raise ConfigError(f"Unsupported client: {client_name}")

            if client_name not in self.configs:
                return False

            removed = self.configs[client_name].remove_server(server_name)
            if not removed:
                return False

            client_file_path = self.get_client_config_path(client_name)

            # Read existing client config under lock if available.
            existing_data: Dict[str, Any] = {}
            if client_file_path and os.path.exists(client_file_path):
                client_lock = FileLock(client_file_path + ".lock")
                with client_lock:
                    _backup_file(client_file_path)
                    try:
                        with open(
                            client_file_path, "r", encoding="utf-8"
                        ) as f:
                            existing_data = json.load(f)
                    except json.JSONDecodeError as exc:
                        _logger.warning(
                            "Client config %s contains invalid JSON (%s). "
                            "Existing non-mcpServers settings may be lost.",
                            client_file_path,
                            exc,
                        )
                        corrupted_path = (
                            f"{client_file_path}.corrupted."
                            f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
                        )
                        try:
                            shutil.copy2(
                                client_file_path, corrupted_path
                            )
                            _logger.info(
                                "Preserved corrupted config at %s",
                                corrupted_path,
                            )
                        except OSError:
                            pass
                        existing_data = {}
                    except OSError:
                        existing_data = {}

                merged = existing_data.copy()
                mcp_servers = merged.get("mcpServers", {})
                if server_name in mcp_servers:
                    del mcp_servers[server_name]
                merged["mcpServers"] = mcp_servers
            else:
                merged = self.configs[client_name].to_mcp_json()

            # Save hub first (source of truth).
            self._save()

        # Write client file outside self._lock.
        if client_file_path:
            os.makedirs(
                os.path.dirname(client_file_path), exist_ok=True
            )
            client_lock = FileLock(client_file_path + ".lock")
            with client_lock:
                _atomic_write_json(client_file_path, merged)
            os.chmod(client_file_path, 0o600)

        return True

    def list_servers(self, client_name: str) -> List[MCPConfig]:
        """List all MCP servers configured for a client."""
        with self._lock:
            if client_name not in SUPPORTED_CLIENTS:
                raise ConfigError(f"Unsupported client: {client_name}")
            config = self.configs.get(client_name)
            if not config:
                return []
            return list(config.servers.values())

    # -- Client config retrieval ---------------------------------------------

    def get_client_config(self, client_name: str) -> Optional[ClientConfig]:
        """Get a client's configuration from the hub's internal state."""
        with self._lock:
            if client_name not in SUPPORTED_CLIENTS:
                raise ConfigError(f"Unsupported client: {client_name}")
            return self.configs.get(client_name)

    # -- Detection & import / export -----------------------------------------

    def detect_client_configs(self) -> Dict[str, str]:
        """Detect existing MCP configurations on the system.

        Returns a mapping of client_name -> config_file_path for each
        supported client whose configuration file already exists.
        """
        detected: Dict[str, str] = {}
        for client in SUPPORTED_CLIENTS:
            path = self.get_client_config_path(client)
            if path and os.path.exists(path):
                detected[client] = path
        return detected

    def import_client_config(self, client_name: str, file_path: str) -> bool:
        """Import an existing client configuration file into the hub."""
        with self._lock:
            if client_name not in SUPPORTED_CLIENTS:
                raise ConfigError(f"Unsupported client: {client_name}")

            path = _validate_import_path(file_path)
            if not path.exists():
                raise ConfigError(f"Config file not found: {path}")

            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError as exc:
                raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc

            # Validate MCP structure
            if "mcpServers" not in data:
                raise ConfigError("Invalid MCP config: missing 'mcpServers' key")

            self.configs[client_name] = ClientConfig.from_mcp_json(
                client_name, data
            )
            self._save()
            return True

    def export_client_config(
        self, client_name: str, output_path: Optional[str] = None
    ) -> str:
        """Export a client's configuration to a file.

        Returns the path of the written file.
        """
        with self._lock:
            if client_name not in SUPPORTED_CLIENTS:
                raise ConfigError(f"Unsupported client: {client_name}")

            config = self.configs.get(client_name)
            if not config:
                raise ConfigError(
                    f"No configuration found for client: {client_name}"
                )

            if output_path:
                # Reject user-provided absolute paths or paths with parent traversal
                if os.path.isabs(output_path):
                    raise ConfigError("Absolute paths are not allowed for export")
                if ".." in output_path:
                    raise ConfigError("Path traversal sequences are not allowed")
                out_path = _validate_export_path(output_path)
                out_path_str = str(out_path)
                # Also verify it's under the default data directory exports subdir
                allowed_base = _expand_path(
                    f"{DEFAULT_DATA_DIR}/exports", allow_vars=True
                )
                if not _is_safe_path(out_path_str, allowed_base):
                    raise ConfigError(
                        f"Export path must be inside {allowed_base}: {output_path}"
                    )
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                out_path_str = _expand_path(
                    f"{DEFAULT_DATA_DIR}/exports/{client_name}_mcp_{timestamp}.json",
                    allow_vars=True
                )

            os.makedirs(os.path.dirname(out_path_str), exist_ok=True)
            data = config.to_mcp_json()
            _atomic_write_json(out_path_str, data)
            os.chmod(out_path_str, 0o600)

            return out_path_str

    # -- MCP JSON generation -------------------------------------------------

    def generate_mcp_json(self, client_name: str, mask_sensitive: bool = False) -> Dict[str, Any]:
        """Generate the standard MCP JSON config for a client.

        Format:
        {
            "mcpServers": {
                "server-name": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
                    "env": {"API_KEY": "xxx"}
                }
            }
        }
        """
        if client_name not in SUPPORTED_CLIENTS:
            raise ConfigError(f"Unsupported client: {client_name}")
        config = self.configs.get(client_name)
        if not config:
            return {"mcpServers": {}}
        return config.to_mcp_json(mask_sensitive=mask_sensitive)

    # -- Validation ----------------------------------------------------------

    def validate_client_config(self, client_name: str) -> List[str]:
        """Validate a client's configuration and return any issues.

        Each issue is returned as a human-readable string. An empty list
        means the configuration is valid.
        """
        issues: List[str] = []
        if client_name not in SUPPORTED_CLIENTS:
            issues.append(f"Unsupported client: {client_name}")
            return issues

        config = self.configs.get(client_name)
        if not config:
            issues.append(f"No configuration found for client: {client_name}")
            return issues

        if not config.servers:
            issues.append("No MCP servers configured for this client")

        for name, server in config.servers.items():
            if not server.name:
                issues.append(f"Server at index has empty name")
            if not server.command:
                issues.append(f"Server '{name}' has empty command")
            # Check for potential security issues in env keys and values.
            for env_key, env_value in server.env.items():
                lower_key = env_key.lower()
                is_sensitive_key = any(s in lower_key for s in SENSITIVE_ENV_KEYS)
                
                is_sensitive_value = False
                val_lower = str(env_value).lower()
                if (val_lower.startswith("sk-") or
                    val_lower.startswith("ghp_") or
                    val_lower.startswith("github_pat_") or
                    val_lower.startswith("akia") or
                    val_lower.startswith("asia") or
                    val_lower.startswith("sg.") or
                    val_lower.startswith("rk-") or
                    val_lower.startswith("pk-") or
                    # JWT heuristic: three segments separated by dots
                    (env_value.count(".") == 2 and len(env_value) > 20) or
                    # URL with embedded credentials
                    ("://" in env_value and "@" in env_value)):
                    is_sensitive_value = True
                
                if is_sensitive_key or is_sensitive_value:
                    # Not an error, but a warning. Mask key name to avoid reconnaissance.
                    issues.append(
                        f"Server '{name}' uses a sensitive credential; "
                        f"ensure it is stored securely"
                    )

        # Validate global_settings depth and content
        if config.global_settings:
            try:
                _validate_global_settings(config.global_settings)
            except ConfigError as exc:
                issues.append(f"global_settings validation failed: {exc}")

        # Validate the generated JSON is serializable.
        try:
            json.dumps(config.to_mcp_json())
        except (TypeError, ValueError) as exc:
            issues.append(f"Generated MCP JSON is not valid: {exc}")

        return issues

    # -- Supported clients & paths ---------------------------------------------

    def get_supported_clients(self) -> List[str]:
        """Return the list of supported clients."""
        return list(SUPPORTED_CLIENTS)

    def get_client_config_path(self, client_name: str) -> Optional[str]:
        """Get the config path for a specific client on the current OS."""
        if client_name not in CLIENT_CONFIG_PATHS:
            return None
        os_key = _get_current_os()
        raw_path = CLIENT_CONFIG_PATHS[client_name].get(os_key)
        if not raw_path:
            return None
        return _expand_path(raw_path, allow_vars=True)

    # -- Auto configure ------------------------------------------------------

    def auto_configure(
        self, tool_name: str, clients: Optional[List[str]] = None
    ) -> Dict[str, bool]:
        """Auto-configure a tool for all supported clients (or specified ones).

        Looks the tool up in the registry and adds it to each target client.
        Returns a mapping of client_name -> success_boolean.
        """
        tool = self._registry.get(tool_name)
        if not tool:
            raise ConfigError(f"Tool not found in registry: {tool_name}")

        target_clients = clients or SUPPORTED_CLIENTS
        results: Dict[str, bool] = {}
        for client in target_clients:
            if client not in SUPPORTED_CLIENTS:
                results[client] = False
                continue
            try:
                results[client] = self.add_server(client, tool)
            except ConfigError:
                results[client] = False
        return results

    # -- Utilities -----------------------------------------------------------

    def set_registry(self, registry: Registry) -> None:
        """Replace the internal registry (useful for testing or custom setups)."""
        self._registry = registry

    def get_registry(self) -> Registry:
        """Return the internal registry instance."""
        return self._registry
