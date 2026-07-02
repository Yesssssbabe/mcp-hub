"""Shared fixtures for MCP Hub tests."""

import json
import os

import pytest

from mcp_hub.registry import MCPTool, Registry
from mcp_hub.config import ConfigManager, MCPConfig, ClientConfig


def make_minimal_tool(**kwargs):
    """Create a minimal MCPTool with required fields."""
    defaults = {
        "name": "test-tool",
        "display_name": "Test Tool",
        "description": "A test tool",
        "install_type": "npm",
        "install_command": "npx test-tool",
        "author": "Test Author",
        "repository": "https://github.com/test/test-tool",
    }
    defaults.update(kwargs)
    return MCPTool(**defaults)


@pytest.fixture
def sample_tool():
    """Return a sample MCPTool instance."""
    return make_minimal_tool()


@pytest.fixture
def sample_tool_dict():
    """Return a sample MCPTool as dictionary."""
    return {
        "name": "test-tool",
        "display_name": "Test Tool",
        "description": "A test tool for unit tests",
        "version": "1.0.0",
        "install_type": "npm",
        "install_command": "npx test-tool",
        "author": "Test Author",
        "repository": "https://github.com/test/test-tool",
        "homepage": "https://example.com",
        "license": "MIT",
        "tags": ["test", "example"],
        "categories": ["testing"],
        "stars": 100,
        "forks": 10,
        "downloads": 500,
        "security_score": 3,
        "permissions": ["filesystem:read"],
        "is_official": False,
        "is_installed": False,
    }


@pytest.fixture
def mock_registry_data():
    """Return sample registry data with multiple tools."""
    return {
        "tools": [
            {
                "name": "tool-a",
                "display_name": "Tool A",
                "description": "Tool A for data processing",
                "version": "1.0.0",
                "install_type": "npm",
                "install_command": "npx tool-a",
                "author": "Author A",
                "repository": "https://github.com/a/tool-a",
                "categories": ["data"],
                "tags": ["data", "processing"],
                "stars": 500,
                "forks": 50,
                "downloads": 1000,
                "security_score": 3,
                "is_installed": True,
                "install_path": "/tmp/mcp/tools/tool-a",
                "permissions": ["filesystem:read"],
            },
            {
                "name": "tool-b",
                "display_name": "Tool B",
                "description": "Tool B for web scraping",
                "version": "2.1.0",
                "install_type": "npm",
                "install_command": "npx tool-b",
                "author": "Author B",
                "repository": "https://github.com/b/tool-b",
                "categories": ["web"],
                "tags": ["web", "scraping", "http"],
                "stars": 1200,
                "forks": 120,
                "downloads": 5000,
                "security_score": 2,
                "is_installed": False,
                "permissions": ["network:all"],
            },
            {
                "name": "tool-c",
                "display_name": "Tool C",
                "description": "Tool C for general utilities",
                "version": "0.5.0",
                "install_type": "pip",
                "install_command": "pip install tool-c",
                "author": "Author C",
                "repository": "https://github.com/c/tool-c",
                "categories": ["utilities"],
                "tags": ["utils", "helpers"],
                "stars": 50,
                "forks": 5,
                "downloads": 200,
                "security_score": 4,
                "is_installed": True,
                "install_path": "/tmp/mcp/tools/tool-c",
                "permissions": ["filesystem:read"],
            },
        ]
    }


@pytest.fixture
def tmp_registry(tmp_path):
    """Create a temporary Registry."""
    registry_path = tmp_path / "registry.json"
    registry = Registry(registry_path=str(registry_path))
    return registry


@pytest.fixture
def tmp_registry_with_data(tmp_path, mock_registry_data):
    """Create a temporary Registry pre-loaded with mock data."""
    registry_path = tmp_path / "registry.json"
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(mock_registry_data, f)
    registry = Registry(registry_path=str(registry_path))
    return registry


@pytest.fixture
def tmp_config(tmp_path):
    """Create a temporary ConfigManager."""
    config_path = tmp_path / "config.json"
    return ConfigManager(config_path=str(config_path))


@pytest.fixture
def sample_mcp_config():
    """Return a sample MCPConfig instance."""
    return MCPConfig(
        name="sample-server",
        command="python",
        args=["-m", "mcp_server"],
        env={"API_KEY": "test-key"},
        description="A sample MCP server",
    )
