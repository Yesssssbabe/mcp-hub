"""Tests for mcp_hub.constants module."""

from pathlib import Path

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
    SUPPORTED_CLIENTS,
)
from mcp_hub.security import SecurityLevel


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
        assert isinstance(DEFAULT_REGISTRY_PATH, Path)
        expected_base = Path.home() / ".config" / "mcp-hub"
        legacy_base = Path.home() / ".mcp-hub"
        if legacy_base.exists() and not expected_base.exists():
            expected_base = legacy_base
        assert str(DEFAULT_REGISTRY_PATH) == str(expected_base / "registry.json")

    def test_default_config_path(self):
        assert isinstance(DEFAULT_CONFIG_PATH, Path)
        expected_base = Path.home() / ".config" / "mcp-hub"
        legacy_base = Path.home() / ".mcp-hub"
        if legacy_base.exists() and not expected_base.exists():
            expected_base = legacy_base
        assert str(DEFAULT_CONFIG_PATH) == str(expected_base / "config.json")

    def test_default_data_dir(self):
        assert isinstance(DEFAULT_DATA_DIR, Path)
        expected_base = Path.home() / ".config" / "mcp-hub"
        legacy_base = Path.home() / ".mcp-hub"
        if legacy_base.exists() and not expected_base.exists():
            expected_base = legacy_base
        assert str(DEFAULT_DATA_DIR) == str(expected_base)

    def test_supported_clients_is_tuple(self):
        assert isinstance(SUPPORTED_CLIENTS, tuple)
        assert all(isinstance(c, str) for c in SUPPORTED_CLIENTS)

    def test_supported_clients_contents(self):
        expected = {"claude", "cursor", "cline", "copilot", "vscode", "windsurf"}
        assert set(SUPPORTED_CLIENTS) == expected

    def test_install_types_is_list(self):
        assert isinstance(INSTALL_TYPES, (list, tuple))
        assert all(isinstance(t, str) for t in INSTALL_TYPES)

    def test_install_types_contents(self):
        expected = {"npm", "pip", "docker", "git", "binary"}
        assert set(INSTALL_TYPES) == expected

    def test_security_levels_dict(self):
        from mcp_hub.constants import SECURITY_LEVELS
        assert SECURITY_LEVELS[0] == "unknown"
        assert SECURITY_LEVELS[1] == "low"
        assert SECURITY_LEVELS[2] == "medium"
        assert SECURITY_LEVELS[3] == "high"
        assert SECURITY_LEVELS[4] == "verified"

    def test_log_levels(self):
        from mcp_hub.constants import LOG_LEVELS
        assert isinstance(LOG_LEVELS, (list, tuple))
        assert "DEBUG" in LOG_LEVELS
        assert "INFO" in LOG_LEVELS
        assert "WARNING" in LOG_LEVELS
        assert "ERROR" in LOG_LEVELS


class TestSecurityLevel:
    """Test SecurityLevel IntEnum."""

    def test_security_level_values(self):
        assert SecurityLevel.UNKNOWN == 0
        assert SecurityLevel.LOW == 1
        assert SecurityLevel.MEDIUM == 2
        assert SecurityLevel.HIGH == 3
        assert SecurityLevel.VERIFIED == 4

    @pytest.mark.parametrize(
        "level,name",
        [
            (SecurityLevel.UNKNOWN, "UNKNOWN"),
            (SecurityLevel.LOW, "LOW"),
            (SecurityLevel.MEDIUM, "MEDIUM"),
            (SecurityLevel.HIGH, "HIGH"),
            (SecurityLevel.VERIFIED, "VERIFIED"),
        ],
    )
    def test_security_level_names(self, level, name):
        assert level.name == name

    def test_security_level_comparison(self):
        assert SecurityLevel.UNKNOWN < SecurityLevel.LOW
        assert SecurityLevel.LOW < SecurityLevel.VERIFIED

    def test_security_level_from_int(self):
        assert SecurityLevel(0) == SecurityLevel.UNKNOWN
        assert SecurityLevel(4) == SecurityLevel.VERIFIED
