"""Tests for mcp_hub.constants module."""

import pytest

from mcp_hub.constants import (
    ConfigError,
    DEFAULT_CONFIG_PATH,
    DEFAULT_DATA_DIR,
    DEFAULT_REGISTRY_PATH,
    INSTALL_TYPES,
    InstallationError,
    MCPHubError,
    RegistryError,
    SecurityError,
    SecurityLevel,
    SUPPORTED_CLIENTS,
)


class TestExceptionHierarchy:
    """Test exception class hierarchy."""

    def test_mcp_hub_error_is_base_exception(self):
        assert issubclass(MCPHubError, Exception)

    @pytest.mark.parametrize(
        "exception_class",
        [InstallationError, RegistryError, SecurityError, ConfigError],
    )
    def test_all_exceptions_inherit_from_mcp_hub_error(self, exception_class):
        assert issubclass(exception_class, MCPHubError)

    def test_can_raise_and_catch_mcp_hub_error(self):
        with pytest.raises(MCPHubError):
            raise MCPHubError("test error")

    def test_can_raise_and_catch_specific_errors(self):
        errors = [
            InstallationError("install failed"),
            RegistryError("registry corrupt"),
            SecurityError("security breach"),
            ConfigError("bad config"),
        ]
        for error in errors:
            with pytest.raises(MCPHubError):
                raise error

    def test_error_message_preservation(self):
        msg = "custom error message 123"
        err = RegistryError(msg)
        assert str(err) == msg


class TestConstants:
    """Test constant values."""

    def test_default_registry_path(self):
        assert isinstance(DEFAULT_REGISTRY_PATH, str)
        assert DEFAULT_REGISTRY_PATH == "~/.mcp-hub/registry.json"

    def test_default_config_path(self):
        assert isinstance(DEFAULT_CONFIG_PATH, str)
        assert DEFAULT_CONFIG_PATH == "~/.mcp-hub/config.json"

    def test_default_data_dir(self):
        assert isinstance(DEFAULT_DATA_DIR, str)
        assert DEFAULT_DATA_DIR == "~/.mcp-hub"

    def test_supported_clients_is_list(self):
        assert isinstance(SUPPORTED_CLIENTS, list)
        assert all(isinstance(c, str) for c in SUPPORTED_CLIENTS)

    def test_supported_clients_contents(self):
        expected = {"claude", "cursor", "cline", "copilot", "vscode", "windsurf"}
        assert set(SUPPORTED_CLIENTS) == expected

    def test_install_types_is_list(self):
        assert isinstance(INSTALL_TYPES, list)
        assert all(isinstance(t, str) for t in INSTALL_TYPES)

    def test_install_types_contents(self):
        expected = {"pip", "npm", "uv", "source", "docker"}
        assert set(INSTALL_TYPES) == expected


class TestSecurityLevel:
    """Test SecurityLevel IntEnum."""

    def test_security_level_values(self):
        assert SecurityLevel.CRITICAL == 1
        assert SecurityLevel.HIGH == 2
        assert SecurityLevel.MEDIUM == 3
        assert SecurityLevel.LOW == 4
        assert SecurityLevel.SAFE == 5

    @pytest.mark.parametrize(
        "level,name",
        [
            (SecurityLevel.CRITICAL, "CRITICAL"),
            (SecurityLevel.HIGH, "HIGH"),
            (SecurityLevel.MEDIUM, "MEDIUM"),
            (SecurityLevel.LOW, "LOW"),
            (SecurityLevel.SAFE, "SAFE"),
        ],
    )
    def test_security_level_names(self, level, name):
        assert level.name == name

    def test_security_level_comparison(self):
        assert SecurityLevel.CRITICAL < SecurityLevel.HIGH
        assert SecurityLevel.LOW < SecurityLevel.SAFE

    def test_security_level_from_int(self):
        assert SecurityLevel(1) == SecurityLevel.CRITICAL
        assert SecurityLevel(5) == SecurityLevel.SAFE
