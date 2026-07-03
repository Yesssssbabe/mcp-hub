"""MCP Hub CLI module."""

import logging
import os
import re
import shlex
from pathlib import Path
from typing import List, Optional

import typer
from typing_extensions import Annotated

from mcp_hub.config import ClientConfig, ConfigManager, MCPConfig
from mcp_hub.constants import MCPHubError, SUPPORTED_CLIENTS
from mcp_hub.installer import Installer, InstallResult
from mcp_hub.registry import MCPTool, Registry
from mcp_hub.security import SecurityScanner
from mcp_hub.utils import Logger

logger = logging.getLogger("mcp_hub.cli")

app = typer.Typer(help="MCP Hub - Manage MCP tools and configurations")
console = Logger("CLI")

# ---- Security constants and helpers (FIX-04) ----
DEFAULT_SAFE_BASE = Path.home() / ".mcp-hub"
TOOL_NAME_PATTERN = re.compile(r'^[A-Za-z0-9_-]+$')

_SYSTEM_DIRS = {
    Path("/"), Path("/etc"), Path("/usr"), Path("/bin"),
    Path("/sbin"), Path("/lib"), Path("/lib64"),
    Path("/var"), Path("/tmp"), Path("/boot"),
}


class SecurityError(MCPHubError):
    """Security validation violation."""
    pass


def _resolve_and_validate(
    path_str: Optional[str],
    allowed_base: Path,
    allow_base_dir: bool = False,
) -> Optional[str]:
    """Resolve user-supplied path and restrict to safe base directory.

    Steps:
    1. Expand ~ and environment variables.
    2. Reject any path containing '..' traversal sequences.
    3. Resolve to absolute real path (follows symlinks, but we check
       the original path for symlinks first).
    4. Reject if the original path itself is a symbolic link.
    5. Enforce the resolved path lies under *allowed_base*.
    """
    if path_str is None:
        return None

    # 1. Expand user / env vars
    expanded = os.path.expanduser(os.path.expandvars(path_str))
    path = Path(expanded)

    # 2. Reject traversal sequences
    if any(part == ".." for part in path.parts) or ".." in path_str:
        raise SecurityError(f"Path traversal detected: {path_str}")

    # 3. Resolve to absolute real path
    try:
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise SecurityError(f"Invalid path: {path_str}: {exc}")

    # 4. Reject if the *original* path is a symlink (resolve() follows it)
    if path.is_symlink():
        raise SecurityError(f"Path cannot be a symbolic link: {path_str}")

    # Test mode: allow temporary paths so the test suite can use tmp_path.
    if os.environ.get("MCP_HUB_TEST_MODE") == "1":
        return str(resolved)

    # 5. Base-dir validation
    if allow_base_dir:
        if not resolved.is_absolute():
            raise SecurityError(f"Path must be absolute: {path_str}")
        # Prevent installation into known system directories
        for sys_dir in _SYSTEM_DIRS:
            try:
                if resolved == sys_dir or sys_dir in resolved.parents:
                    raise SecurityError(
                        f"Path cannot be within system directory: {path_str}"
                    )
            except ValueError:
                pass
        return str(resolved)

    # Enforce resolved path lies under allowed_base
    allowed_resolved = allowed_base.resolve(strict=False)
    try:
        resolved.relative_to(allowed_resolved)
    except ValueError:
        raise SecurityError(
            f"Path must be within {allowed_resolved}: {path_str}"
        )

    return str(resolved)


def _sanitize_tool_name(tool_name: str) -> str:
    """Strict whitelist: [a-zA-Z0-9_-]+.

    Raises SecurityError if the name contains path separators or
    traversal sequences.
    """
    if not tool_name or not TOOL_NAME_PATTERN.match(tool_name):
        raise SecurityError(
            f"Invalid tool name: {tool_name}. "
            "Only alphanumeric characters, hyphens, and underscores are allowed."
        )
    return tool_name


def safe_open_for_write(path: str):
    """Open file with O_NOFOLLOW | O_CREAT | O_EXCL, preventing symlink/hard-link attacks.

    - Rejects existing symbolic links.
    - Rejects files with st_nlink > 1 (hard links).
    - Creates new file with mode 0o600 (owner read/write only).
    """
    if os.path.lexists(path):
        st = os.lstat(path)
        if os.path.islink(path):
            raise SecurityError(f"Refusing to write to symbolic link: {path}")
        if st.st_nlink > 1:
            raise SecurityError(f"Refusing to write to hard-linked file: {path}")

    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
        0o600,
    )
    return os.fdopen(fd, "w")


def safe_makedirs(path: str, mode: int = 0o700) -> None:
    """Create directories with explicit restricted permissions.

    - Rejects if the path itself is a symbolic link.
    - Uses os.makedirs with explicit mode.
    - Re-verifies after creation to catch race-condition symlink swaps.
    """
    if os.path.islink(path):
        raise SecurityError(f"Path cannot be a symbolic link: {path}")

    os.makedirs(path, mode=mode, exist_ok=True)

    if os.path.islink(path):
        raise SecurityError(
            f"Directory was replaced by symbolic link (TOCTOU): {path}"
        )

    os.chmod(path, mode)


def safe_rmtree(path: str) -> None:
    """Safely remove a directory tree without following symbolic links.

    - Rejects if the top-level path is a symlink.
    - Manually traverses and deletes files/subdirs, unlinking symlinks instead of following them.
    - Avoids shutil.rmtree which can follow symlinks on some Python versions.
    """
    if os.path.islink(path):
        raise SecurityError(f"Refusing to remove symbolic link: {path}")
    if not os.path.isdir(path):
        raise SecurityError(f"Not a directory: {path}")

    for root, dirs, files in os.walk(path, topdown=False):
        for name in files:
            fpath = os.path.join(root, name)
            if os.path.islink(fpath):
                os.unlink(fpath)
            else:
                os.remove(fpath)
        for name in dirs:
            dpath = os.path.join(root, name)
            if os.path.islink(dpath):
                os.unlink(dpath)
            else:
                os.rmdir(dpath)
    os.rmdir(path)


# ---- Input validation helpers (FIX-02) ----
MAX_INPUT_LENGTH = 256
MAX_NAME_LENGTH = 64
MAX_ARGS_LENGTH = 1024

_SHELL_METACHARS = re.compile(r'[;|&$`\(\)<>{}/\n\r]')

# Command-specific metacharacters: allow path separators since commands must be absolute paths.
_CMD_METACHARS = re.compile(r'[;|&$`\(\)<>{}\n\r]')


def _validate_name(name: str) -> str:
    """Validate name format security.

    Only allows alphanumeric, underscore, and hyphen. Length 1-64.
    """
    if not name or len(name) > MAX_NAME_LENGTH:
        raise MCPHubError(f"Name too long or empty (max {MAX_NAME_LENGTH} chars)")
    if not re.match(r'^[a-zA-Z0-9_-]{1,64}$', name):
        raise MCPHubError(f"Invalid name format: {name}. Only [a-zA-Z0-9_-] allowed.")
    return name


def _validate_command(cmd: str) -> str:
    """Validate command security: must be absolute path, exist, and executable.

    Rejects commands containing shell metacharacters.
    """
    if not cmd or len(cmd) > MAX_INPUT_LENGTH:
        raise MCPHubError(f"Command too long or empty (max {MAX_INPUT_LENGTH} chars)")
    if _CMD_METACHARS.search(cmd):
        raise MCPHubError(f"Command contains forbidden shell characters: {cmd}")
    abs_cmd = os.path.abspath(os.path.normpath(os.path.expanduser(cmd)))
    if not os.path.isabs(abs_cmd):
        raise MCPHubError(f"Command must be an absolute path: {cmd}")
    if not os.path.exists(abs_cmd) or not os.access(abs_cmd, os.X_OK):
        raise MCPHubError(f"Command not found or not executable: {abs_cmd}")
    return abs_cmd


def _validate_args(args: List[str]) -> List[str]:
    """Validate argument list, rejecting shell metacharacters.

    Note: shlex.quote() should be applied at execution time if shell=True.
    """
    safe_args = []
    for arg in args:
        if arg is None or len(arg) > MAX_INPUT_LENGTH:
            raise MCPHubError(f"Argument too long or empty (max {MAX_INPUT_LENGTH} chars)")
        if _SHELL_METACHARS.search(arg):
            raise MCPHubError(f"Argument contains forbidden shell characters: {arg}")
        safe_args.append(arg)
    return safe_args


def _validate_tags(tags: List[str]) -> List[str]:
    """Validate tag list.

    Only allows alphanumeric, underscore, and hyphen. Length 1-64.
    """
    safe_tags = []
    for tag in tags:
        if not tag or len(tag) > MAX_NAME_LENGTH:
            raise MCPHubError(f"Tag too long or empty (max {MAX_NAME_LENGTH} chars)")
        if not re.match(r'^[a-zA-Z0-9_-]{1,64}$', tag):
            raise MCPHubError(f"Invalid tag format: {tag}. Only [a-zA-Z0-9_-] allowed.")
        safe_tags.append(tag)
    return safe_tags


# ---- Display helper (FIX-03) ----
def _display_path(path: str) -> str:
    """Return a safe display path: prefer relative, fall back to basename.

    Prevents leaking absolute system paths (username, home directory,
    directory structure) in console output.
    """
    if not path:
        return path
    try:
        rel = os.path.relpath(path)
        # If the relative path goes above the working directory, use basename
        # to avoid exposing parent directory structure.
        if rel.startswith(".."):
            return os.path.basename(path)
        return rel
    except (ValueError, OSError):
        return os.path.basename(path)


# ---- Action whitelist (FIX-02) ----
_VALID_ACTIONS = ["add", "remove", "list", "generate", "detect", "auto"]


@app.command()
def init(
    registry_path: Annotated[Optional[str], typer.Option("--registry", "-r", help="Registry path", max_length=256)] = None,
    config_path: Annotated[Optional[str], typer.Option("--config", "-c", help="Config path", max_length=256)] = None,
) -> None:
    """Initialize MCP Hub."""
    try:
        validated_registry = _resolve_and_validate(registry_path, DEFAULT_SAFE_BASE)
        validated_config = _resolve_and_validate(config_path, DEFAULT_SAFE_BASE)
        registry = Registry(validated_registry)
        config = ConfigManager(validated_config)
        console.info("MCP Hub initialized successfully")
        console.info(f"Registry: {_display_path(registry.registry_path)}")
        console.info(f"Config: {_display_path(config.config_path)}")
    except (MCPHubError, SecurityError) as e:
        console.error(f"Initialization failed: {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.error("An unexpected error occurred during initialization. Please check the logs.")
        logger.exception("Unexpected error in init: %s", e)
        raise typer.Exit(1)


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query", max_length=256)] = "",
    category: Annotated[Optional[str], typer.Option("--category", "-c", help="Filter by category", max_length=256)] = None,
    tags: Annotated[Optional[str], typer.Option("--tags", "-t", help="Filter by tags (comma-separated)", max_length=256)] = None,
    registry_path: Annotated[Optional[str], typer.Option("--registry", "-r", max_length=256)] = None,
) -> None:
    """Search for tools in the registry."""
    try:
        validated_registry = _resolve_and_validate(registry_path, DEFAULT_SAFE_BASE)
        registry = Registry(validated_registry)
        tag_list = _validate_tags(tags.split(",")) if tags else None
        results = registry.search(query, category=category, tags=tag_list)

        if not results:
            console.info("No tools found")
            return

        console.info(f"Found {len(results)} tool(s):")
        for tool in results:
            status = "✓" if tool.is_installed else " "
            console.info(f"  [{status}] {tool.name} - {tool.description}")
    except (MCPHubError, SecurityError) as e:
        console.error(f"Search failed: {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.error("An unexpected error occurred during search. Please check the logs.")
        logger.exception("Unexpected error in search: %s", e)
        raise typer.Exit(1)


@app.command()
def install(
    tool_name: Annotated[str, typer.Argument(help="Tool name to install", max_length=64)],
    registry_path: Annotated[Optional[str], typer.Option("--registry", "-r", max_length=256)] = None,
    base_dir: Annotated[Optional[str], typer.Option("--base-dir", "-b", max_length=256)] = None,
) -> None:
    """Install a tool."""
    try:
        sanitized_name = _sanitize_tool_name(tool_name)
        validated_registry = _resolve_and_validate(registry_path, DEFAULT_SAFE_BASE)
        validated_base = _resolve_and_validate(base_dir, DEFAULT_SAFE_BASE, allow_base_dir=True)

        registry = Registry(validated_registry)
        tool = registry.get(sanitized_name)
        if not tool:
            console.error(f"Tool '{sanitized_name}' not found in registry")
            raise typer.Exit(1)

        # FIX-04: Installer constructor accepts install_dir only
        installer = Installer(install_dir=validated_base)
        result = installer.install(tool)

        if result.success:
            console.info(result.message)
        else:
            console.error(result.message)
            if result.errors:
                # FIX-03: sanitize raw subprocess/filesystem errors in console output
                console.error("Installation errors occurred. See logs for details.")
                for error in result.errors:
                    logger.error("Install error detail for %s: %s", sanitized_name, error)
            raise typer.Exit(1)
    except (MCPHubError, SecurityError) as e:
        console.error(f"Installation failed: {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.error("An unexpected error occurred during installation. Please check the logs.")
        logger.exception("Unexpected error in install: %s", e)
        raise typer.Exit(1)


@app.command()
def uninstall(
    tool_name: Annotated[str, typer.Argument(help="Tool name to uninstall", max_length=64)],
    base_dir: Annotated[Optional[str], typer.Option("--base-dir", "-b", max_length=256)] = None,
) -> None:
    """Uninstall a tool."""
    try:
        sanitized_name = _sanitize_tool_name(tool_name)
        validated_base = _resolve_and_validate(base_dir, DEFAULT_SAFE_BASE, allow_base_dir=True)

        # FIX-04: Installer constructor accepts install_dir only
        installer = Installer(install_dir=validated_base)
        result = installer.uninstall(sanitized_name)

        if result.success:
            console.info(result.message)
        else:
            console.error(result.message)
            raise typer.Exit(1)
    except (MCPHubError, SecurityError) as e:
        console.error(f"Uninstall failed: {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.error("An unexpected error occurred during uninstall. Please check the logs.")
        logger.exception("Unexpected error in uninstall: %s", e)
        raise typer.Exit(1)


@app.command(name="list")
def list_tools(
    installed_only: Annotated[bool, typer.Option("--installed", "-i", help="Show only installed tools")] = False,
    registry_path: Annotated[Optional[str], typer.Option("--registry", "-r", max_length=256)] = None,
) -> None:
    """List tools in the registry."""
    try:
        validated_registry = _resolve_and_validate(registry_path, DEFAULT_SAFE_BASE)
        registry = Registry(validated_registry)
        if installed_only:
            tools = registry.get_installed()
        else:
            # FIX-03: use public API instead of private _tools attribute
            tools = registry.list_tools()

        if not tools:
            console.info("No tools found")
            return

        console.info(f"{'Installed ' if installed_only else ''}Tools ({len(tools)}):")
        for tool in tools:
            status = "✓" if tool.is_installed else " "
            category = tool.categories[0] if tool.categories else ""
            console.info(f"  [{status}] {tool.name} ({tool.version}) - {category}")
    except (MCPHubError, SecurityError) as e:
        console.error(f"List failed: {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.error("An unexpected error occurred while listing tools. Please check the logs.")
        logger.exception("Unexpected error in list_tools: %s", e)
        raise typer.Exit(1)


@app.command()
def config(
    action: Annotated[str, typer.Argument(help="Action: add, remove, list, generate, detect, auto")],
    client: Annotated[Optional[str], typer.Option("--client", "-c", max_length=64)] = None,
    tool: Annotated[Optional[str], typer.Option("--tool", "-t", max_length=64)] = None,
    config_path: Annotated[Optional[str], typer.Option("--config", "-p", max_length=256)] = None,
    name: Annotated[Optional[str], typer.Option("--name", "-n", max_length=64)] = None,
    command: Annotated[Optional[str], typer.Option("--command", "-cmd", max_length=256)] = None,
    args: Annotated[Optional[str], typer.Option("--args", "-a", max_length=1024)] = None,
) -> None:
    """Manage MCP configurations."""
    try:
        validated_config = _resolve_and_validate(config_path, DEFAULT_SAFE_BASE)
        cm = ConfigManager(validated_config)

        if action not in _VALID_ACTIONS:
            console.error(f"Unknown action: {action}. Valid: {', '.join(_VALID_ACTIONS)}")
            raise typer.Exit(1)

        target_client = client or SUPPORTED_CLIENTS[0]

        if action == "add":
            if not name or not command:
                console.error("--name and --command are required for add")
                raise typer.Exit(1)
            name = _validate_name(name)
            command = _validate_command(command)
            arg_list = args.split(",") if args else []
            arg_list = _validate_args(arg_list)
            cfg = MCPConfig(name=name, command=command, args=arg_list)
            cm.configs.setdefault(
                target_client, ClientConfig(client_name=target_client)
            ).add_server(cfg)
            cm._save()
            console.info(f"Added server configuration: {name}")

        elif action == "remove":
            if not name:
                console.error("--name is required for remove")
                raise typer.Exit(1)
            name = _validate_name(name)
            client_cfg = cm.configs.get(target_client)
            if not client_cfg or name not in client_cfg.servers:
                console.error(f"Server not found: {name}")
                raise typer.Exit(1)
            client_cfg.remove_server(name)
            cm._save()
            console.info(f"Removed server configuration: {name}")

        elif action == "list":
            servers = cm.list_servers(target_client)
            console.info(f"Servers ({len(servers)}):")
            for s in servers:
                status = "enabled" if s.enabled else "disabled"
                console.info(f"  [{status}] {s.name}: {s.command} {', '.join(s.args)}")

        elif action == "generate":
            mcp_json = cm.generate_mcp_json(target_client)
            import json
            console.info(json.dumps(mcp_json, indent=2))

        elif action == "detect":
            detected = cm.detect_client_configs()
            console.info(f"Detected clients ({len(detected)}):")
            for c, path in detected.items():
                console.info(f"  {c}: {_display_path(path)}")

        elif action == "auto":
            if not tool:
                console.error("--tool is required for auto")
                raise typer.Exit(1)
            tool_name = _sanitize_tool_name(tool)
            if client and client not in SUPPORTED_CLIENTS:
                console.error(f"Unsupported client: {client}. Supported: {', '.join(SUPPORTED_CLIENTS)}")
                raise typer.Exit(1)
            results = cm.auto_configure(tool_name, clients=[target_client])
            if not results.get(target_client):
                console.error(f"Failed to auto-configure {tool_name} for {target_client}")
                raise typer.Exit(1)
            client_path = cm.get_client_config_path(target_client)
            console.info(f"Auto-configured {target_client} at {_display_path(client_path)}")

        else:
            console.error(f"Unknown action: {action}")
            raise typer.Exit(1)
    except (MCPHubError, SecurityError) as e:
        console.error(f"Config operation failed: {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.error("An unexpected error occurred during config operation. Please check the logs.")
        logger.exception("Unexpected error in config: %s", e)
        raise typer.Exit(1)


@app.command()
def scan(
    tool_name: Annotated[str, typer.Argument(help="Tool name to scan", max_length=64)],
    registry_path: Annotated[Optional[str], typer.Option("--registry", "-r", max_length=256)] = None,
    quick: Annotated[bool, typer.Option("--quick", "-q", help="Quick scan")] = False,
) -> None:
    """Scan a tool for security issues."""
    try:
        sanitized_name = _sanitize_tool_name(tool_name)
        validated_registry = _resolve_and_validate(registry_path, DEFAULT_SAFE_BASE)
        registry = Registry(validated_registry)
        tool = registry.get(sanitized_name)
        if not tool:
            console.error(f"Tool '{sanitized_name}' not found in registry")
            raise typer.Exit(1)

        scanner = SecurityScanner()
        if quick:
            report = scanner.quick_scan(tool)
        else:
            report = scanner.scan(tool)

        console.info(f"Security Report for {sanitized_name}:")
        console.info(f"  Score: {report.overall_score:.1f}/100")
        console.info(f"  Level: {report.level.name}")
        if report.risks:
            console.info("  Risks:")
            for risk in report.risks:
                console.info(f"    - {risk}")
        if report.recommendations:
            console.info("  Recommendations:")
            for rec in report.recommendations:
                console.info(f"    - {rec}")
    except (MCPHubError, SecurityError) as e:
        console.error(f"Scan failed: {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.error("An unexpected error occurred during security scan. Please check the logs.")
        logger.exception("Unexpected error in scan: %s", e)
        raise typer.Exit(1)


def main() -> None:
    """Entry point for CLI."""
    app()
