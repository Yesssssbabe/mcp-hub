"""Tests for mcp_hub.cli module."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from mcp_hub.cli import app
from mcp_hub.registry import MCPTool, Registry

runner = CliRunner()


class TestInitCommand:
    """Test `init` CLI command."""

    def test_init_default(self, tmp_path):
        """Should initialize with default paths."""
        with patch("mcp_hub.cli.Registry") as mock_reg, \
             patch("mcp_hub.cli.ConfigManager") as mock_cfg:
            mock_reg.return_value.registry_path = str(tmp_path / "registry.json")
            mock_cfg.return_value.config_path = str(tmp_path / "config.json")
            result = runner.invoke(app, ["init"])
            assert result.exit_code == 0
            assert "initialized" in result.output.lower()

    def test_init_with_paths(self, tmp_path):
        """Should initialize with custom paths."""
        reg_path = tmp_path / "custom_registry.json"
        cfg_path = tmp_path / "custom_config.json"
        with patch("mcp_hub.cli.Registry") as mock_reg, \
             patch("mcp_hub.cli.ConfigManager") as mock_cfg:
            mock_reg.return_value.registry_path = str(reg_path)
            mock_cfg.return_value.config_path = str(cfg_path)
            result = runner.invoke(app, ["init", "--registry", str(reg_path), "--config", str(cfg_path)])
            assert result.exit_code == 0

    def test_init_error(self):
        """Should handle initialization error."""
        with patch("mcp_hub.cli.Registry", side_effect=Exception("fail")):
            result = runner.invoke(app, ["init"])
            assert result.exit_code == 1


class TestSearchCommand:
    """Test `search` CLI command."""

    def test_search_empty(self, tmp_path):
        """Should handle empty search."""
        reg_path = tmp_path / "registry.json"
        Registry(registry_path=str(reg_path)).save()
        result = runner.invoke(app, ["search", "", "--registry", str(reg_path)])
        assert result.exit_code == 0

    def test_search_with_results(self, tmp_path, monkeypatch):
        """Should display search results."""
        reg_path = tmp_path / "registry.json"
        registry = Registry(registry_path=str(reg_path))
        registry.add(MCPTool(
            name="found-tool",
            description="A tool that matches",
            install_type="pip",
            install_spec="found",
        ))
        result = runner.invoke(app, ["search", "found", "--registry", str(reg_path)])
        assert result.exit_code == 0
        assert "found-tool" in result.output

    def test_search_no_results(self, tmp_path):
        """Should handle no results."""
        reg_path = tmp_path / "registry.json"
        registry = Registry(registry_path=str(reg_path))
        registry.save()
        result = runner.invoke(app, ["search", "nonexistent", "--registry", str(reg_path)])
        assert result.exit_code == 0
        assert "No tools found" in result.output

    def test_search_by_category(self, tmp_path, monkeypatch):
        """Should search by category."""
        reg_path = tmp_path / "registry.json"
        registry = Registry(registry_path=str(reg_path))
        registry.add(MCPTool(
            name="cat-tool",
            description="test",
            install_type="pip",
            install_spec="cat",
            category="special",
        ))
        result = runner.invoke(app, ["search", "", "--category", "special", "--registry", str(reg_path)])
        assert result.exit_code == 0
        assert "cat-tool" in result.output

    def test_search_by_tags(self, tmp_path):
        """Should search by tags."""
        reg_path = tmp_path / "registry.json"
        registry = Registry(registry_path=str(reg_path))
        registry.add(MCPTool(
            name="tag-tool",
            description="test",
            install_type="pip",
            install_spec="tag",
            tags=["special", "tag"],
        ))
        result = runner.invoke(app, ["search", "", "--tags", "special", "--registry", str(reg_path)])
        assert result.exit_code == 0
        assert "tag-tool" in result.output

    def test_search_error(self):
        """Should handle search error."""
        with patch("mcp_hub.cli.Registry", side_effect=Exception("fail")):
            result = runner.invoke(app, ["search", "test"])
            assert result.exit_code == 1


class TestInstallCommand:
    """Test `install` CLI command."""

    def test_install_tool(self, tmp_path, monkeypatch):
        """Should install a tool."""
        reg_path = tmp_path / "registry.json"
        registry = Registry(registry_path=str(reg_path))
        registry.add(MCPTool(
            name="cli-tool",
            description="test",
            install_type="pip",
            install_spec="cli-tool",
        ))
        with patch("mcp_hub.cli.Installer") as mock_inst:
            mock_inst.return_value.install.return_value = MagicMock(
                success=True,
                tool_name="cli-tool",
                message="Installed cli-tool",
            )
            result = runner.invoke(app, ["install", "cli-tool", "--registry", str(reg_path)])
            assert result.exit_code == 0
            assert "Installed" in result.output

    def test_install_not_found(self, tmp_path):
        """Should handle tool not found."""
        reg_path = tmp_path / "registry.json"
        registry = Registry(registry_path=str(reg_path))
        registry.save()
        result = runner.invoke(app, ["install", "missing", "--registry", str(reg_path)])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_install_failure(self, tmp_path, monkeypatch):
        """Should handle install failure."""
        reg_path = tmp_path / "registry.json"
        registry = Registry(registry_path=str(reg_path))
        registry.add(MCPTool(
            name="fail-tool",
            description="test",
            install_type="pip",
            install_spec="fail",
        ))
        with patch("mcp_hub.cli.Installer") as mock_inst:
            mock_inst.return_value.install.return_value = MagicMock(
                success=False,
                tool_name="fail-tool",
                message="Installation failed",
                errors=["Permission denied"],
            )
            result = runner.invoke(app, ["install", "fail-tool", "--registry", str(reg_path)])
            assert result.exit_code == 1


class TestUninstallCommand:
    """Test `uninstall` CLI command."""

    def test_uninstall_success(self, tmp_path, monkeypatch):
        """Should uninstall successfully."""
        with patch("mcp_hub.cli.Installer") as mock_inst:
            mock_inst.return_value.uninstall.return_value = MagicMock(
                success=True,
                tool_name="gone",
                message="Uninstalled gone",
            )
            result = runner.invoke(app, ["uninstall", "gone"])
            assert result.exit_code == 0
            assert "Uninstalled" in result.output

    def test_uninstall_failure(self):
        """Should handle uninstall failure."""
        with patch("mcp_hub.cli.Installer") as mock_inst:
            mock_inst.return_value.uninstall.return_value = MagicMock(
                success=False,
                tool_name="bad",
                message="Not installed",
            )
            result = runner.invoke(app, ["uninstall", "bad"])
            assert result.exit_code == 1


class TestListCommand:
    """Test `list` CLI command."""

    def test_list_all(self, tmp_path):
        """Should list all tools."""
        reg_path = tmp_path / "registry.json"
        registry = Registry(registry_path=str(reg_path))
        registry.add(MCPTool(
            name="list-tool",
            description="test",
            install_type="pip",
            install_spec="list",
        ))
        result = runner.invoke(app, ["list", "--registry", str(reg_path)])
        assert result.exit_code == 0
        assert "list-tool" in result.output

    def test_list_installed_only(self, tmp_path):
        """Should list only installed tools."""
        reg_path = tmp_path / "registry.json"
        registry = Registry(registry_path=str(reg_path))
        registry.add(MCPTool(
            name="installed",
            description="test",
            install_type="pip",
            install_spec="installed",
            installed=True,
        ))
        registry.add(MCPTool(
            name="not-installed",
            description="test",
            install_type="pip",
            install_spec="ni",
            installed=False,
        ))
        result = runner.invoke(app, ["list", "--installed", "--registry", str(reg_path)])
        assert result.exit_code == 0
        assert "installed" in result.output
        assert "not-installed" not in result.output

    def test_list_empty(self, tmp_path):
        """Should handle empty list."""
        reg_path = tmp_path / "registry.json"
        Registry(registry_path=str(reg_path)).save()
        result = runner.invoke(app, ["list", "--registry", str(reg_path)])
        assert result.exit_code == 0
        assert "No tools found" in result.output

    def test_list_error(self):
        """Should handle list error."""
        with patch("mcp_hub.cli.Registry", side_effect=Exception("fail")):
            result = runner.invoke(app, ["list"])
            assert result.exit_code == 1


class TestConfigCommand:
    """Test `config` CLI command."""

    def test_config_add(self, tmp_path):
        """Should add server config."""
        config_path = tmp_path / "config.json"
        result = runner.invoke(app, [
            "config", "add",
            "--config", str(config_path),
            "--name", "new-server",
            "--command", "python",
            "--args", "-m,server",
        ])
        assert result.exit_code == 0
        assert "Added" in result.output

    def test_config_add_missing_args(self, tmp_path):
        """Should error on missing args."""
        config_path = tmp_path / "config.json"
        result = runner.invoke(app, [
            "config", "add",
            "--config", str(config_path),
        ])
        assert result.exit_code == 1

    def test_config_remove(self, tmp_path):
        """Should remove server config."""
        config_path = tmp_path / "config.json"
        from mcp_hub.config import ConfigManager, MCPConfig
        cm = ConfigManager(config_path=str(config_path))
        cm.add_server(MCPConfig(name="old", command="python"))
        result = runner.invoke(app, [
            "config", "remove",
            "--config", str(config_path),
            "--name", "old",
        ])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_config_remove_not_found(self, tmp_path):
        """Should handle remove not found."""
        config_path = tmp_path / "config.json"
        result = runner.invoke(app, [
            "config", "remove",
            "--config", str(config_path),
            "--name", "missing",
        ])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_config_list(self, tmp_path):
        """Should list servers."""
        config_path = tmp_path / "config.json"
        from mcp_hub.config import ConfigManager, MCPConfig
        cm = ConfigManager(config_path=str(config_path))
        cm.add_server(MCPConfig(name="s1", command="python"))
        result = runner.invoke(app, [
            "config", "list",
            "--config", str(config_path),
        ])
        assert result.exit_code == 0
        assert "s1" in result.output

    def test_config_generate(self, tmp_path):
        """Should generate MCP JSON."""
        config_path = tmp_path / "config.json"
        from mcp_hub.config import ConfigManager, MCPConfig
        cm = ConfigManager(config_path=str(config_path))
        cm.add_server(MCPConfig(name="gen", command="python"))
        result = runner.invoke(app, [
            "config", "generate",
            "--config", str(config_path),
        ])
        assert result.exit_code == 0
        assert "mcpServers" in result.output

    def test_config_detect(self, tmp_path, monkeypatch):
        """Should detect client configs."""
        config_path = tmp_path / "config.json"
        with patch("mcp_hub.cli.ConfigManager.detect_client_configs") as mock_detect:
            mock_detect.return_value = {"claude": "/path/to/claude.json"}
            result = runner.invoke(app, [
                "config", "detect",
                "--config", str(config_path),
            ])
            assert result.exit_code == 0
            assert "claude" in result.output

    def test_config_auto(self, tmp_path, monkeypatch):
        """Should auto-configure client."""
        config_path = tmp_path / "config.json"
        with patch("mcp_hub.cli.ConfigManager.auto_configure") as mock_auto:
            mock_auto.return_value = MagicMock(
                client="claude",
                config_path="/path",
            )
            result = runner.invoke(app, [
                "config", "auto",
                "--config", str(config_path),
                "--client", "claude",
            ])
            assert result.exit_code == 0
            assert "Auto-configured" in result.output

    def test_config_auto_no_client(self, tmp_path):
        """Should error without client."""
        config_path = tmp_path / "config.json"
        result = runner.invoke(app, [
            "config", "auto",
            "--config", str(config_path),
        ])
        assert result.exit_code == 1

    def test_config_unknown_action(self, tmp_path):
        """Should handle unknown action."""
        config_path = tmp_path / "config.json"
        result = runner.invoke(app, [
            "config", "unknown",
            "--config", str(config_path),
        ])
        assert result.exit_code == 1

    def test_config_error(self, tmp_path):
        """Should handle config error."""
        with patch("mcp_hub.cli.ConfigManager", side_effect=Exception("fail")):
            result = runner.invoke(app, ["config", "list"])
            assert result.exit_code == 1


class TestScanCommand:
    """Test `scan` CLI command."""

    def test_scan_tool(self, tmp_path, monkeypatch):
        """Should scan a tool."""
        reg_path = tmp_path / "registry.json"
        registry = Registry(registry_path=str(reg_path))
        registry.add(MCPTool(
            name="scan-me",
            description="test",
            install_type="pip",
            install_spec="scan",
            permissions=["filesystem:read"],
        ))
        with patch("mcp_hub.cli.SecurityScanner") as mock_scanner:
            mock_scanner.return_value.scan.return_value = MagicMock(
                overall_score=85.0,
                level=MagicMock(name="SAFE"),
                risks=[],
                recommendations=["No issues"],
            )
            result = runner.invoke(app, ["scan", "scan-me", "--registry", str(reg_path)])
            assert result.exit_code == 0
            assert "Security Report" in result.output

    def test_scan_quick(self, tmp_path, monkeypatch):
        """Should do quick scan."""
        reg_path = tmp_path / "registry.json"
        registry = Registry(registry_path=str(reg_path))
        registry.add(MCPTool(
            name="quick-scan",
            description="test",
            install_type="pip",
            install_spec="quick",
        ))
        with patch("mcp_hub.cli.SecurityScanner") as mock_scanner:
            mock_scanner.return_value.quick_scan.return_value = MagicMock(
                overall_score=90.0,
                level=MagicMock(name="SAFE"),
                risks=[],
                recommendations=[],
            )
            result = runner.invoke(app, [
                "scan", "quick-scan",
                "--registry", str(reg_path),
                "--quick",
            ])
            assert result.exit_code == 0

    def test_scan_not_found(self, tmp_path):
        """Should handle tool not found."""
        reg_path = tmp_path / "registry.json"
        Registry(registry_path=str(reg_path)).save()
        result = runner.invoke(app, ["scan", "missing", "--registry", str(reg_path)])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_scan_error(self):
        """Should handle scan error."""
        with patch("mcp_hub.cli.Registry", side_effect=Exception("fail")):
            result = runner.invoke(app, ["scan", "test"])
            assert result.exit_code == 1


class TestCLIErrorHandling:
    """Test general CLI error handling."""

    def test_no_command(self):
        """Should show help with no command."""
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "MCP Hub" in result.output

    def test_help_flag(self):
        """Should show help with --help."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "MCP Hub" in result.output

    def test_command_help(self):
        """Should show subcommand help."""
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        assert "search" in result.output.lower()

    def test_invalid_command(self):
        """Should error on invalid command."""
        result = runner.invoke(app, ["notacommand"])
        assert result.exit_code != 0
