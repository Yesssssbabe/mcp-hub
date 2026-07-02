"""Tests for mcp_hub.config module."""

    import json
    import os
    import platform

    import pytest

    from mcp_hub.config import ConfigManager, MCPConfig, ClientConfig, _expand_path, _get_current_os
    from mcp_hub.constants import ConfigError, SUPPORTED_CLIENTS
    from mcp_hub.registry import MCPTool


    def make_tool(**kwargs):
        defaults = {
            "name": "test-tool",
            "display_name": "Test Tool",
            "description": "desc",
            "install_type": "npm",
            "install_command": "npx test-tool",
            "author": "a",
            "repository": "https://github.com/a/b",
        }
        defaults.update(kwargs)
        return MCPTool(**defaults)


    class TestMCPConfig:
        """Test MCPConfig model."""

        def test_create_minimal(self):
            cfg = MCPConfig(name="test", command="python")
            assert cfg.name == "test"
            assert cfg.command == "python"
            assert cfg.args == []
            assert cfg.env == {}
            assert cfg.enabled is True

        def test_create_full(self):
            cfg = MCPConfig(
                name="server1",
                command="python",
                args=["-m", "server"],
                env={"KEY": "value"},
                description="A server",
                enabled=False,
            )
            assert cfg.name == "server1"
            assert cfg.command == "python"
            assert cfg.args == ["-m", "server"]
            assert cfg.env == {"KEY": "value"}
            assert cfg.enabled is False

        def test_name_validation_empty(self):
            with pytest.raises(ValueError):
                MCPConfig(name="", command="python")

        def test_command_validation_empty(self):
            with pytest.raises(ValueError):
                MCPConfig(name="test", command="")

        def test_to_mcp_dict(self):
            cfg = MCPConfig(name="test", command="python", args=["-m", "srv"], env={"K": "V"})
            d = cfg.to_mcp_dict()
            assert d == {"command": "python", "args": ["-m", "srv"], "env": {"K": "V"}}

        def test_to_mcp_dict_no_env(self):
            cfg = MCPConfig(name="test", command="python")
            d = cfg.to_mcp_dict()
            assert "env" not in d

        def test_from_mcp_dict(self):
            data = {"command": "node", "args": ["srv.js"], "env": {"X": "Y"}}
            cfg = MCPConfig.from_mcp_dict("srv", data)
            assert cfg.name == "srv"
            assert cfg.command == "node"
            assert cfg.args == ["srv.js"]
            assert cfg.env == {"X": "Y"}


    class TestClientConfig:
        """Test ClientConfig model."""

        def test_create(self):
            cfg = ClientConfig(client_name="claude")
            assert cfg.client_name == "claude"
            assert cfg.servers == {}

        def test_add_server(self):
            cfg = ClientConfig(client_name="claude")
            srv = MCPConfig(name="s1", command="python")
            cfg.add_server(srv)
            assert "s1" in cfg.servers

        def test_remove_server(self):
            cfg = ClientConfig(client_name="claude")
            cfg.add_server(MCPConfig(name="s1", command="python"))
            assert cfg.remove_server("s1") is True
            assert cfg.remove_server("s1") is False

        def test_to_mcp_json(self):
            cfg = ClientConfig(client_name="claude")
            cfg.add_server(MCPConfig(name="s1", command="python"))
            cfg.add_server(MCPConfig(name="s2", command="node", enabled=False))
            d = cfg.to_mcp_json()
            assert "mcpServers" in d
            assert "s1" in d["mcpServers"]
            assert "s2" not in d["mcpServers"]

        def test_from_mcp_json(self):
            data = {"mcpServers": {"srv": {"command": "python", "args": ["-m", "srv"]}}}
            cfg = ClientConfig.from_mcp_json("claude", data)
            assert "srv" in cfg.servers
            assert cfg.servers["srv"].command == "python"


    class TestConfigManagerInit:
        """Test ConfigManager initialization."""

        def test_init_custom_path(self, tmp_path):
            config_path = tmp_path / "config.json"
            cm = ConfigManager(config_path=str(config_path))
            assert cm.config_path == str(config_path)

        def test_init_creates_directory(self, tmp_path):
            nested = tmp_path / "nested" / "config.json"
            cm = ConfigManager(config_path=str(nested))
            assert nested.parent.exists()

        def test_init_loads_existing(self, tmp_path):
            config_path = tmp_path / "config.json"
            data = {
                "claude": {
                    "client_name": "claude",
                    "servers": {
                        "srv1": {"name": "srv1", "command": "python"}
                    }
                }
            }
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            cm = ConfigManager(config_path=str(config_path))
            assert "claude" in cm.configs

        def test_init_load_invalid_json(self, tmp_path):
            config_path = tmp_path / "config.json"
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("bad json")
            with pytest.raises(ConfigError):
                ConfigManager(config_path=str(config_path))


    class TestConfigManagerAddServer:
        """Test add_server functionality."""

        def test_add_server(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            tool = make_tool(
                name="test-srv",
                mcp_server_name="test-srv",
                mcp_config_template={"command": "npx", "args": ["-y", "test-srv"]},
            )
            result = cm.add_server("claude", tool)
            assert result is True
            assert "test-srv" in [s.name for s in cm.list_servers("claude")]

        def test_add_unsupported_client(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            tool = make_tool(name="x", mcp_config_template={"command": "npx"})
            with pytest.raises(ConfigError):
                cm.add_server("unsupported", tool)

        def test_add_no_command(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            tool = make_tool(name="x", mcp_config_template={})
            with pytest.raises(ConfigError):
                cm.add_server("claude", tool)

        def test_add_persists(self, tmp_path):
            config_path = tmp_path / "config.json"
            cm = ConfigManager(config_path=str(config_path))
            tool = make_tool(
                name="persist",
                mcp_server_name="persist",
                mcp_config_template={"command": "npx", "args": ["-y", "persist"]},
            )
            cm.add_server("claude", tool)
            cm2 = ConfigManager(config_path=str(config_path))
            assert "persist" in [s.name for s in cm2.list_servers("claude")]


    class TestConfigManagerRemoveServer:
        """Test remove_server functionality."""

        def test_remove_existing(self, tmp_path):
            config_path = tmp_path / "config.json"
            cm = ConfigManager(config_path=str(config_path))
            tool = make_tool(name="old", mcp_server_name="old", mcp_config_template={"command": "npx"})
            cm.add_server("claude", tool)
            assert cm.remove_server("claude", "old") is True
            assert "old" not in [s.name for s in cm.list_servers("claude")]

        def test_remove_nonexistent(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            assert cm.remove_server("claude", "missing") is False

        def test_remove_unsupported_client(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            with pytest.raises(ConfigError):
                cm.remove_server("unsupported", "x")

        def test_remove_no_config(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            assert cm.remove_server("claude", "x") is False


    class TestConfigManagerListServers:
        """Test list_servers functionality."""

        def test_list_empty(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            assert cm.list_servers("claude") == []

        def test_list_servers(self, tmp_path):
            config_path = tmp_path / "config.json"
            cm = ConfigManager(config_path=str(config_path))
            tool = make_tool(name="s1", mcp_server_name="s1", mcp_config_template={"command": "npx"})
            cm.add_server("claude", tool)
            servers = cm.list_servers("claude")
            assert len(servers) == 1
            assert servers[0].name == "s1"

        def test_list_unsupported_client(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            with pytest.raises(ConfigError):
                cm.list_servers("unsupported")


    class TestConfigManagerGetClientConfig:
        """Test get_client_config functionality."""

        def test_get_nonexistent(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            assert cm.get_client_config("claude") is None

        def test_get_existing(self, tmp_path):
            config_path = tmp_path / "config.json"
            cm = ConfigManager(config_path=str(config_path))
            tool = make_tool(name="s1", mcp_server_name="s1", mcp_config_template={"command": "npx"})
            cm.add_server("claude", tool)
            cfg = cm.get_client_config("claude")
            assert cfg is not None
            assert cfg.client_name == "claude"

        def test_get_unsupported(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            with pytest.raises(ConfigError):
                cm.get_client_config("unsupported")


    class TestConfigManagerGenerateMCPJson:
        """Test generate_mcp_json functionality."""

        def test_generate_empty(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            result = cm.generate_mcp_json("claude")
            assert result == {"mcpServers": {}}

        def test_generate_with_servers(self, tmp_path):
            config_path = tmp_path / "config.json"
            cm = ConfigManager(config_path=str(config_path))
            tool = make_tool(name="gen", mcp_server_name="gen", mcp_config_template={"command": "npx"})
            cm.add_server("claude", tool)
            result = cm.generate_mcp_json("claude")
            assert "mcpServers" in result
            assert "gen" in result["mcpServers"]

        def test_generate_unsupported(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            with pytest.raises(ConfigError):
                cm.generate_mcp_json("unsupported")


    class TestConfigManagerDetectClientConfigs:
        """Test detect_client_configs functionality."""

        def test_detect_no_clients(self, tmp_path, monkeypatch):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            monkeypatch.setattr(os.path, "exists", lambda x: False)
            detected = cm.detect_client_configs()
            assert detected == {}

        def test_detect_claude_mac(self, tmp_path, monkeypatch):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            fake_path = tmp_path / "claude" / "claude_desktop_config.json"
            fake_path.parent.mkdir(parents=True)
            fake_path.write_text("{}")
            monkeypatch.setattr("mcp_hub.config._get_current_os", lambda: "macos")
            monkeypatch.setattr(os.path, "expanduser", lambda x: str(tmp_path))
            monkeypatch.setattr(os.path, "expandvars", lambda x: str(x))
            detected = cm.detect_client_configs()
            assert "claude" in detected


    class TestConfigManagerValidateClientConfig:
        """Test validate_client_config functionality."""

        def test_validate_unsupported(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            errors = cm.validate_client_config("unsupported")
            assert len(errors) == 1
            assert "Unsupported" in errors[0]

        def test_validate_no_config(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            errors = cm.validate_client_config("claude")
            assert len(errors) == 1
            assert "No configuration" in errors[0]

        def test_validate_empty_servers(self, tmp_path):
            config_path = tmp_path / "config.json"
            cm = ConfigManager(config_path=str(config_path))
            cm.configs["claude"] = ClientConfig(client_name="claude")
            errors = cm.validate_client_config("claude")
            assert any("No MCP servers" in e for e in errors)

        def test_validate_sensitive_env(self, tmp_path):
            config_path = tmp_path / "config.json"
            cm = ConfigManager(config_path=str(config_path))
            cfg = ClientConfig(client_name="claude")
            cfg.add_server(MCPConfig(name="s", command="python", env={"API_KEY": "secret"}))
            cm.configs["claude"] = cfg
            errors = cm.validate_client_config("claude")
            assert any("sensitive" in e.lower() for e in errors)


    class TestConfigManagerImportExport:
        """Test import/export functionality."""

        def test_import_client_config(self, tmp_path):
            config_path = tmp_path / "config.json"
            cm = ConfigManager(config_path=str(config_path))
            import_path = tmp_path / "import.json"
            import_path.write_text(json.dumps({"mcpServers": {"srv": {"command": "python"}}}))
            cm.import_client_config("claude", str(import_path))
            assert "srv" in [s.name for s in cm.list_servers("claude")]

        def test_import_not_found(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            with pytest.raises(ConfigError):
                cm.import_client_config("claude", "/nonexistent.json")

        def test_export_client_config(self, tmp_path):
            config_path = tmp_path / "config.json"
            cm = ConfigManager(config_path=str(config_path))
            tool = make_tool(name="exp", mcp_server_name="exp", mcp_config_template={"command": "npx"})
            cm.add_server("claude", tool)
            out = cm.export_client_config("claude", output_path=str(tmp_path / "out.json"))
            assert os.path.exists(out)
            data = json.load(open(out))
            assert "mcpServers" in data

        def test_export_no_config(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            with pytest.raises(ConfigError):
                cm.export_client_config("claude")


    class TestConfigManagerAutoConfigure:
        """Test auto_configure functionality."""

        def test_auto_configure(self, tmp_path, monkeypatch):
            config_path = tmp_path / "config.json"
            cm = ConfigManager(config_path=str(config_path))
            registry = Registry(registry_path=str(tmp_path / "reg.json"))
            registry.add(make_tool(name="auto-tool", mcp_server_name="auto", mcp_config_template={"command": "npx"}))
            cm.set_registry(registry)
            result = cm.auto_configure("auto-tool")
            assert isinstance(result, dict)

        def test_auto_configure_tool_not_found(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            with pytest.raises(ConfigError):
                cm.auto_configure("nonexistent")

        def test_auto_configure_specific_clients(self, tmp_path, monkeypatch):
            config_path = tmp_path / "config.json"
            cm = ConfigManager(config_path=str(config_path))
            registry = Registry(registry_path=str(tmp_path / "reg.json"))
            registry.add(make_tool(name="auto2", mcp_server_name="auto2", mcp_config_template={"command": "npx"}))
            cm.set_registry(registry)
            result = cm.auto_configure("auto2", clients=["claude"])
            assert result["claude"] is True or result["claude"] is False


    class TestConfigManagerEdgeCases:
        """Test edge cases."""

        def test_get_supported_clients(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            clients = cm.get_supported_clients()
            assert set(clients) == set(SUPPORTED_CLIENTS)

        def test_get_client_config_path(self, tmp_path, monkeypatch):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            monkeypatch.setattr("mcp_hub.config._get_current_os", lambda: "macos")
            path = cm.get_client_config_path("claude")
            assert path is not None
            assert "claude_desktop_config" in path

        def test_set_registry(self, tmp_path):
            cm = ConfigManager(config_path=str(tmp_path / "config.json"))
            reg = Registry(registry_path=str(tmp_path / "reg.json"))
            cm.set_registry(reg)
            assert cm.get_registry() is reg

        def test_unicode_in_config(self, tmp_path):
            config_path = tmp_path / "unicode.json"
            cm = ConfigManager(config_path=str(config_path))
            tool = make_tool(
                name="中文",
                display_name="中文",
                mcp_server_name="中文",
                mcp_config_template={"command": "npx"},
            )
            cm.add_server("claude", tool)
            cm2 = ConfigManager(config_path=str(config_path))
            assert "中文" in [s.name for s in cm2.list_servers("claude")]

        def test_cross_platform_path(self, tmp_path):
            unix = str(tmp_path / "unix" / "config.json")
            cm = ConfigManager(config_path=unix)
            assert cm.config_path == unix
    