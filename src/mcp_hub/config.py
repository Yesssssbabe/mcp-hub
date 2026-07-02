"""MCP Hub configuration management for multiple AI clients.

Supports Claude, Cursor, Cline, Copilot, VSCode, and Windsurf with
cross-platform configuration path detection and management.
"""

import os
import sys
import json
import shutil
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

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
}


def _get_current_os() -> str:
    """Return the normalized OS identifier."""
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32" or os.name == "nt":
        return "windows"
    return "linux"


def _expand_path(path: str) -> str:
    """Expand user home and environment variables in a path."""
    expanded = os.path.expanduser(os.path.expandvars(path))
    return os.path.abspath(expanded)


def _backup_file(file_path: str) -> Optional[str]:
    """Create a timestamped backup of *file_path* if it exists.

    Returns the backup path or None if the file did not exist.
    """
    if not os.path.exists(file_path):
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.backup.{timestamp}"
    shutil.copy2(file_path, backup_path)
    return backup_path


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

    def to_mcp_dict(self) -> Dict[str, Any]:
        """Serialize to the standard MCP JSON format."""
        result: Dict[str, Any] = {"command": self.command}
        if self.args:
            result["args"] = self.args
        if self.env:
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

    def to_mcp_json(self) -> Dict[str, Any]:
        """Generate the standard MCP JSON configuration."""
        mcp_servers: Dict[str, Any] = {}
        for name, server in self.servers.items():
            if server.enabled:
                mcp_servers[name] = server.to_mcp_dict()
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
        self.config_path = config_path or _expand_path(DEFAULT_CONFIG_PATH)
        self.configs: Dict[str, ClientConfig] = {}
        self._registry = Registry()
        self._load()

    # -- Internal persistence ------------------------------------------------

    def _load(self) -> None:
        """Load configurations from the hub's internal config file."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError as exc:
                raise ConfigError(
                    f"Invalid JSON in config file {self.config_path}: {exc}"
                ) from exc

            for client_name, client_data in data.items():
                if client_name not in SUPPORTED_CLIENTS:
                    continue
                self.configs[client_name] = ClientConfig(**client_data)

    def _save(self) -> None:
        """Save the hub's internal configuration state to disk."""
        config_dir = os.path.dirname(self.config_path)
        if config_dir:
            os.makedirs(config_dir, exist_ok=True)
        data: Dict[str, Any] = {}
        for name, config in self.configs.items():
            data[name] = config.model_dump()
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")

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
        if client_name not in SUPPORTED_CLIENTS:
            raise ConfigError(f"Unsupported client: {client_name}")

        # 1. Build the MCP server configuration from the tool.
        tool_config = tool.mcp_config_template or {}
        server_name = tool_config.get("name", tool.mcp_server_name or tool.name)
        command = tool_config.get("command", "")
        args = tool_config.get("args", [])
        env = tool_config.get("env", {})
        description = tool_config.get("description", tool.description)

        if not command:
            raise ConfigError(f"Tool '{tool.name}' has no command defined")

        mcp_server = MCPConfig(
            name=server_name,
            command=command,
            args=args,
            env=env,
            description=description,
            enabled=True,
        )

        # 2. Ensure the client exists in internal state.
        if client_name not in self.configs:
            self.configs[client_name] = ClientConfig(client_name=client_name)
        self.configs[client_name].add_server(mcp_server)

        # 3. Write the standard MCP JSON to the client's config file.
        client_file_path = self.get_client_config_path(client_name)
        if not client_file_path:
            raise ConfigError(f"Could not determine config path for {client_name}")

        # Backup existing config before modifying.
        if os.path.exists(client_file_path):
            _backup_file(client_file_path)

        # Read existing client config (if any) to merge global settings.
        existing_data: Dict[str, Any] = {}
        if os.path.exists(client_file_path):
            try:
                with open(client_file_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except json.JSONDecodeError:
                existing_data = {}

        # Merge: our internal state is authoritative for mcpServers.
        merged = existing_data.copy()
        merged["mcpServers"] = self.configs[client_name].to_mcp_json().get(
            "mcpServers", {}
        )

        os.makedirs(os.path.dirname(client_file_path), exist_ok=True)
        with open(client_file_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
            f.write("\n")

        # 4. Save internal hub state.
        self._save()
        return True

    def remove_server(self, client_name: str, server_name: str) -> bool:
        """Remove an MCP server from a client's configuration."""
        if client_name not in SUPPORTED_CLIENTS:
            raise ConfigError(f"Unsupported client: {client_name}")

        if client_name not in self.configs:
            return False

        removed = self.configs[client_name].remove_server(server_name)
        if not removed:
            return False

        # Update the client config file.
        client_file_path = self.get_client_config_path(client_name)
        if client_file_path and os.path.exists(client_file_path):
            _backup_file(client_file_path)
            try:
                with open(client_file_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing_data = {}

            merged = existing_data.copy()
            mcp_servers = merged.get("mcpServers", {})
            if server_name in mcp_servers:
                del mcp_servers[server_name]
            merged["mcpServers"] = mcp_servers

            with open(client_file_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2, ensure_ascii=False)
                f.write("\n")

        self._save()
        return True

    def list_servers(self, client_name: str) -> List[MCPConfig]:
        """List all MCP servers configured for a client."""
        if client_name not in SUPPORTED_CLIENTS:
            raise ConfigError(f"Unsupported client: {client_name}")
        config = self.configs.get(client_name)
        if not config:
            return []
        return list(config.servers.values())

    # -- Client config retrieval ---------------------------------------------

    def get_client_config(self, client_name: str) -> Optional[ClientConfig]:
        """Get a client's configuration from the hub's internal state."""
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
        if client_name not in SUPPORTED_CLIENTS:
            raise ConfigError(f"Unsupported client: {client_name}")

        path = _expand_path(file_path)
        if not os.path.exists(path):
            raise ConfigError(f"Config file not found: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc

        self.configs[client_name] = ClientConfig.from_mcp_json(client_name, data)
        self._save()
        return True

    def export_client_config(
        self, client_name: str, output_path: Optional[str] = None
    ) -> str:
        """Export a client's configuration to a file.

        Returns the path of the written file.
        """
        if client_name not in SUPPORTED_CLIENTS:
            raise ConfigError(f"Unsupported client: {client_name}")

        config = self.configs.get(client_name)
        if not config:
            raise ConfigError(f"No configuration found for client: {client_name}")

        if output_path:
            out_path = _expand_path(output_path)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = _expand_path(
                f"{DEFAULT_DATA_DIR}/exports/{client_name}_mcp_{timestamp}.json"
            )

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        data = config.to_mcp_json()
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")

        return out_path

    # -- MCP JSON generation -------------------------------------------------

    def generate_mcp_json(self, client_name: str) -> Dict[str, Any]:
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
        return config.to_mcp_json()

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
            # Check for potential security issues in env keys.
            for env_key in server.env.keys():
                lower_key = env_key.lower()
                if any(s in lower_key for s in SENSITIVE_ENV_KEYS):
                    # Not an error, but a warning.
                    issues.append(
                        f"Server '{name}' uses sensitive env key '{env_key}'; "
                        f"ensure it is stored securely"
                    )

        # Validate the generated JSON is serializable.
        try:
            json.dumps(config.to_mcp_json())
        except (TypeError, ValueError) as exc:
            issues.append(f"Generated MCP JSON is not valid: {exc}")

        return issues

    # -- Supported clients & paths ---------------------------------------------

    def get_supported_clients(self) -> List[str]:
        """Return the list of supported clients."""
        return SUPPORTED_CLIENTS.copy()

    def get_client_config_path(self, client_name: str) -> Optional[str]:
        """Get the config path for a specific client on the current OS."""
        if client_name not in CLIENT_CONFIG_PATHS:
            return None
        os_key = _get_current_os()
        raw_path = CLIENT_CONFIG_PATHS[client_name].get(os_key)
        if not raw_path:
            return None
        return _expand_path(raw_path)

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
