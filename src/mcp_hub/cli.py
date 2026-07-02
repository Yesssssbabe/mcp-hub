"""MCP Hub CLI module."""

from typing import Optional

import typer
from typing_extensions import Annotated

from mcp_hub.config import ConfigManager, MCPConfig
from mcp_hub.constants import MCPHubError, SUPPORTED_CLIENTS
from mcp_hub.installer import Installer, InstallResult
from mcp_hub.registry import MCPTool, Registry
from mcp_hub.security import SecurityScanner
from mcp_hub.utils import Logger

app = typer.Typer(help="MCP Hub - Manage MCP tools and configurations")
console = Logger("CLI")


@app.command()
def init(
    registry_path: Annotated[Optional[str], typer.Option("--registry", "-r", help="Registry path")] = None,
    config_path: Annotated[Optional[str], typer.Option("--config", "-c", help="Config path")] = None,
) -> None:
    """Initialize MCP Hub."""
    try:
        registry = Registry(registry_path)
        config = ConfigManager(config_path)
        console.info("MCP Hub initialized successfully")
        console.info(f"Registry: {registry.registry_path}")
        console.info(f"Config: {config.config_path}")
    except MCPHubError as e:
        console.error(f"Initialization failed: {e}")
        raise typer.Exit(1)


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query")] = "",
    category: Annotated[Optional[str], typer.Option("--category", "-c", help="Filter by category")] = None,
    tags: Annotated[Optional[str], typer.Option("--tags", "-t", help="Filter by tags (comma-separated)")] = None,
    registry_path: Annotated[Optional[str], typer.Option("--registry", "-r")] = None,
) -> None:
    """Search for tools in the registry."""
    try:
        registry = Registry(registry_path)
        tag_list = tags.split(",") if tags else None
        results = registry.search(query, category=category, tags=tag_list)

        if not results:
            console.info("No tools found")
            return

        console.info(f"Found {len(results)} tool(s):")
        for tool in results:
            status = "✓" if tool.installed else " "
            console.info(f"  [{status}] {tool.name} - {tool.description}")
    except MCPHubError as e:
        console.error(f"Search failed: {e}")
        raise typer.Exit(1)


@app.command()
def install(
    tool_name: Annotated[str, typer.Argument(help="Tool name to install")],
    registry_path: Annotated[Optional[str], typer.Option("--registry", "-r")] = None,
    base_dir: Annotated[Optional[str], typer.Option("--base-dir", "-b")] = None,
) -> None:
    """Install a tool."""
    try:
        registry = Registry(registry_path)
        tool = registry.get(tool_name)
        if not tool:
            console.error(f"Tool '{tool_name}' not found in registry")
            raise typer.Exit(1)

        installer = Installer(registry=registry, base_dir=base_dir)
        result = installer.install(tool)

        if result.success:
            console.info(result.message)
        else:
            console.error(result.message)
            if result.errors:
                for error in result.errors:
                    console.error(f"  - {error}")
            raise typer.Exit(1)
    except MCPHubError as e:
        console.error(f"Installation failed: {e}")
        raise typer.Exit(1)


@app.command()
def uninstall(
    tool_name: Annotated[str, typer.Argument(help="Tool name to uninstall")],
    base_dir: Annotated[Optional[str], typer.Option("--base-dir", "-b")] = None,
) -> None:
    """Uninstall a tool."""
    try:
        installer = Installer(base_dir=base_dir)
        result = installer.uninstall(tool_name)

        if result.success:
            console.info(result.message)
        else:
            console.error(result.message)
            raise typer.Exit(1)
    except MCPHubError as e:
        console.error(f"Uninstall failed: {e}")
        raise typer.Exit(1)


@app.command(name="list")
def list_tools(
    installed_only: Annotated[bool, typer.Option("--installed", "-i", help="Show only installed tools")] = False,
    registry_path: Annotated[Optional[str], typer.Option("--registry", "-r")] = None,
) -> None:
    """List tools in the registry."""
    try:
        registry = Registry(registry_path)
        if installed_only:
            tools = registry.get_installed()
        else:
            tools = list(registry._tools.values())

        if not tools:
            console.info("No tools found")
            return

        console.info(f"{'Installed ' if installed_only else ''}Tools ({len(tools)}):")
        for tool in tools:
            status = "✓" if tool.installed else " "
            console.info(f"  [{status}] {tool.name} ({tool.version}) - {tool.category}")
    except MCPHubError as e:
        console.error(f"List failed: {e}")
        raise typer.Exit(1)


@app.command()
def config(
    action: Annotated[str, typer.Argument(help="Action: add, remove, list, generate")],
    client: Annotated[Optional[str], typer.Option("--client", "-c")] = None,
    config_path: Annotated[Optional[str], typer.Option("--config", "-p")] = None,
    name: Annotated[Optional[str], typer.Option("--name", "-n")] = None,
    command: Annotated[Optional[str], typer.Option("--command", "-cmd")] = None,
    args: Annotated[Optional[str], typer.Option("--args", "-a")] = None,
) -> None:
    """Manage MCP configurations."""
    try:
        cm = ConfigManager(config_path)

        if action == "add":
            if not name or not command:
                console.error("--name and --command are required for add")
                raise typer.Exit(1)
            arg_list = args.split(",") if args else []
            cfg = MCPConfig(name=name, command=command, args=arg_list)
            cm.add_server(cfg)
            console.info(f"Added server configuration: {name}")

        elif action == "remove":
            if not name:
                console.error("--name is required for remove")
                raise typer.Exit(1)
            if cm.remove_server(name):
                console.info(f"Removed server configuration: {name}")
            else:
                console.error(f"Server not found: {name}")
                raise typer.Exit(1)

        elif action == "list":
            servers = cm.list_servers()
            console.info(f"Servers ({len(servers)}):")
            for s in servers:
                status = "enabled" if s.enabled else "disabled"
                console.info(f"  [{status}] {s.name}: {s.command} {', '.join(s.args)}")

        elif action == "generate":
            mcp_json = cm.generate_mcp_json()
            import json
            console.info(json.dumps(mcp_json, indent=2))

        elif action == "detect":
            detected = cm.detect_client_configs()
            console.info(f"Detected clients ({len(detected)}):")
            for c, path in detected.items():
                console.info(f"  {c}: {path}")

        elif action == "auto":
            if not client:
                console.error("--client is required for auto")
                raise typer.Exit(1)
            cfg = cm.auto_configure(client)
            console.info(f"Auto-configured {client} at {cfg.config_path}")

        else:
            console.error(f"Unknown action: {action}")
            raise typer.Exit(1)
    except MCPHubError as e:
        console.error(f"Config operation failed: {e}")
        raise typer.Exit(1)


@app.command()
def scan(
    tool_name: Annotated[str, typer.Argument(help="Tool name to scan")],
    registry_path: Annotated[Optional[str], typer.Option("--registry", "-r")] = None,
    quick: Annotated[bool, typer.Option("--quick", "-q", help="Quick scan")] = False,
) -> None:
    """Scan a tool for security issues."""
    try:
        registry = Registry(registry_path)
        tool = registry.get(tool_name)
        if not tool:
            console.error(f"Tool '{tool_name}' not found in registry")
            raise typer.Exit(1)

        scanner = SecurityScanner()
        if quick:
            report = scanner.quick_scan(tool)
        else:
            report = scanner.scan(tool)

        console.info(f"Security Report for {tool_name}:")
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
    except MCPHubError as e:
        console.error(f"Scan failed: {e}")
        raise typer.Exit(1)


def main() -> None:
    """Entry point for CLI."""
    app()
