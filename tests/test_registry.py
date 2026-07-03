"""Tests for mcp_hub.registry module."""

import json
from datetime import datetime

import pytest

from mcp_hub.registry import MCPTool, Registry


def make_tool(**kwargs):
    defaults = {
        "name": "test",
        "display_name": "Test",
        "description": "desc",
        "install_type": "npm",
        "install_command": "npx test",
        "author": "a",
        "repository": "https://github.com/a/b",
    }
    defaults.update(kwargs)
    return MCPTool(**defaults)


class TestMCPToolModel:
    """Test MCPTool Pydantic model."""

    def test_create_minimal_tool(self):
        tool = make_tool()
        assert tool.name == "test"
        assert tool.display_name == "Test"
        assert tool.description == "desc"
        assert tool.version == "0.1.0"
        assert tool.license == "MIT"
        assert tool.tags == []
        assert tool.categories == []
        assert tool.stars == 0
        assert tool.forks == 0
        assert tool.downloads == 0
        assert tool.is_official is False
        assert tool.is_installed is False
        assert tool.install_path is None

    def test_create_full_tool(self):
        tool = make_tool(
            name="full-tool",
            display_name="Full Tool",
            description="A full tool",
            version="2.0.0",
            author="Full Author",
            repository="https://github.com/full/tool",
            homepage="https://full.example.com",
            license="Apache-2.0",
            tags=["tag1", "tag2"],
            categories=["cat1", "cat2"],
            language="Python",
            stars=100,
            forks=20,
            downloads=1000,
            security_score=4,
            permissions=["read"],
            is_official=True,
            is_installed=True,
            install_path="/path",
            mcp_server_name="full",
            env_vars=["KEY"],
        )
        assert tool.security_score == 4
        assert tool.is_official is True

    def test_tool_rating_validation(self):
        # security_score must be 0-4
        with pytest.raises(ValueError):
            make_tool(security_score=5)
        with pytest.raises(ValueError):
            make_tool(security_score=-1)

    def test_tool_to_json(self):
        tool = make_tool(name="json-tool")
        json_str = tool.model_dump_json()
        assert "json-tool" in json_str

    def test_tool_from_dict(self, sample_tool_dict):
        tool = MCPTool(**sample_tool_dict)
        assert tool.name == "test-tool"
        assert tool.display_name == "Test Tool"

    def test_required_fields(self):
        with pytest.raises(ValueError):
            MCPTool(name="missing")
        with pytest.raises(ValueError):
            MCPTool(display_name="missing")


class TestRegistryInit:
    """Test Registry initialization."""

    def test_registry_empty_init(self, tmp_path):
        registry_path = tmp_path / "registry.json"
        registry = Registry(registry_path=str(registry_path))
        assert len(registry) == 0

    def test_registry_load_from_file(self, tmp_path, mock_registry_data):
        registry_path = tmp_path / "registry.json"
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(mock_registry_data, f)
        registry = Registry(registry_path=str(registry_path))
        assert len(registry) == 3
        assert "tool-a" in registry
        assert "tool-b" in registry
        assert "tool-c" in registry

    def test_registry_load_invalid_json(self, tmp_path):
        registry_path = tmp_path / "registry.json"
        with open(registry_path, "w", encoding="utf-8") as f:
            f.write("not valid json")
        registry = Registry(registry_path=str(registry_path))
        assert len(registry) == 0

    def test_registry_creates_directory(self, tmp_path):
        nested = tmp_path / "nested" / "deep" / "registry.json"
        registry = Registry(registry_path=str(nested))
        registry._save()
        assert nested.parent.exists()


class TestRegistryAdd:
    """Test Registry add functionality."""

    def test_add_tool(self, tmp_registry):
        tool = make_tool(name="new-tool", display_name="New")
        tmp_registry.add(tool)
        assert "new-tool" in tmp_registry

    def test_add_duplicate_raises(self, tmp_registry):
        tool = make_tool(name="dup", display_name="Dup")
        tmp_registry.add(tool)
        with pytest.raises(ValueError):
            tmp_registry.add(tool)

    def test_add_saves_to_file(self, tmp_path):
        registry_path = tmp_path / "registry.json"
        registry = Registry(registry_path=str(registry_path))
        registry.add(make_tool(name="persist", display_name="Persist"))
        registry2 = Registry(registry_path=str(registry_path))
        assert "persist" in registry2

    def test_add_updates_timestamp(self, tmp_registry):
        before = datetime.now().isoformat()
        tool = make_tool(name="timestamp", display_name="Timestamp")
        tmp_registry.add(tool)
        assert tmp_registry.get("timestamp").updated_at >= before


class TestRegistryGetRemove:
    """Test Registry get and remove."""

    def test_get_existing(self, tmp_registry_with_data):
        tool = tmp_registry_with_data.get("tool-a")
        assert tool is not None
        assert tool.name == "tool-a"

    def test_get_nonexistent(self, tmp_registry_with_data):
        assert tmp_registry_with_data.get("nonexistent") is None

    def test_get_tool_alias(self, tmp_registry_with_data):
        assert tmp_registry_with_data.get_tool("tool-a") is not None

    def test_remove_existing(self, tmp_registry_with_data):
        tmp_registry_with_data.remove("tool-a")
        assert "tool-a" not in tmp_registry_with_data

    def test_remove_nonexistent_raises(self, tmp_registry_with_data):
        with pytest.raises(KeyError):
            tmp_registry_with_data.remove("nonexistent")

    def test_remove_persists(self, tmp_registry_with_data):
        tmp_registry_with_data.remove("tool-a")
        registry2 = Registry(registry_path=tmp_registry_with_data.registry_path)
        assert "tool-a" not in registry2


class TestRegistrySearch:
    """Test Registry search functionality."""

    def test_search_by_name(self, tmp_registry_with_data):
        results = tmp_registry_with_data.search("tool-a")
        assert len(results) == 1
        assert results[0].name == "tool-a"

    def test_search_by_description(self, tmp_registry_with_data):
        results = tmp_registry_with_data.search("web scraping")
        assert len(results) == 1
        assert results[0].name == "tool-b"

    def test_search_case_insensitive(self, tmp_registry_with_data):
        results_lower = tmp_registry_with_data.search("tool-a")
        results_upper = tmp_registry_with_data.search("TOOL-A")
        assert len(results_lower) == len(results_upper)

    def test_search_empty_returns_all(self, tmp_registry_with_data):
        results = tmp_registry_with_data.search("")
        assert len(results) == 3

    def test_search_no_match(self, tmp_registry_with_data):
        results = tmp_registry_with_data.search("nonexistent xyz")
        assert len(results) == 0

    def test_search_by_category(self, tmp_registry_with_data):
        results = tmp_registry_with_data.search("", category="data")
        assert len(results) == 1
        assert results[0].name == "tool-a"

    def test_search_by_tags(self, tmp_registry_with_data):
        results = tmp_registry_with_data.search("", tags=["web"])
        assert len(results) == 1
        assert results[0].name == "tool-b"

    def test_search_by_multiple_tags(self, tmp_registry_with_data):
        results = tmp_registry_with_data.search("", tags=["web", "scraping"])
        assert len(results) == 1
        assert results[0].name == "tool-b"

    def test_search_limit(self, tmp_registry_with_data):
        results = tmp_registry_with_data.search("", limit=2)
        assert len(results) == 2

    def test_search_sort_by_name(self, tmp_registry_with_data):
        results = tmp_registry_with_data.search("", sort_by="name")
        assert results[0].name == "tool-a"

    def test_search_sort_by_stars(self, tmp_registry_with_data):
        results = tmp_registry_with_data.search("", sort_by="stars")
        assert results[0].name == "tool-b"  # 1200 stars

    def test_search_on_empty_registry(self, tmp_registry):
        results = tmp_registry.search("anything")
        assert len(results) == 0


class TestRegistryCategories:
    """Test Registry category listing."""

    def test_list_categories(self, tmp_registry_with_data):
        categories = tmp_registry_with_data.list_categories()
        assert sorted(categories) == ["data", "utilities", "web"]

    def test_list_categories_empty(self, tmp_registry):
        assert tmp_registry.list_categories() == []

    def test_list_tags(self, tmp_registry_with_data):
        tags = tmp_registry_with_data.list_tags()
        assert "data" in tags
        assert "web" in tags


class TestRegistryInstalled:
    """Test installed tools."""

    def test_get_installed(self, tmp_registry_with_data):
        installed = tmp_registry_with_data.get_installed()
        assert len(installed) == 2
        names = {t.name for t in installed}
        assert names == {"tool-a", "tool-c"}

    def test_list_installed(self, tmp_registry_with_data):
        names = tmp_registry_with_data.list_installed()
        assert sorted(names) == ["tool-a", "tool-c"]

    def test_is_installed(self, tmp_registry_with_data):
        assert tmp_registry_with_data.is_installed("tool-a") is True
        assert tmp_registry_with_data.is_installed("tool-b") is False
        assert tmp_registry_with_data.is_installed("nonexistent") is False

    def test_get_install_path(self, tmp_registry_with_data):
        assert tmp_registry_with_data.get_install_path("tool-a") == "/fake/tmp/path/tool-a"
        assert tmp_registry_with_data.get_install_path("tool-b") is None

    def test_mark_installed(self, tmp_registry_with_data):
        tmp_registry_with_data.mark_installed("tool-b", "/path/to/b", "npm")
        assert tmp_registry_with_data.is_installed("tool-b") is True
        assert tmp_registry_with_data.get_install_path("tool-b") == "/path/to/b"

    def test_mark_uninstalled(self, tmp_registry_with_data):
        tmp_registry_with_data.mark_uninstalled("tool-a")
        assert tmp_registry_with_data.is_installed("tool-a") is False
        assert tmp_registry_with_data.get_install_path("tool-a") is None


class TestRegistryMetrics:
    """Test metrics and security score updates."""

    def test_update_metrics(self, tmp_registry_with_data):
        tmp_registry_with_data.update_metrics("tool-a", stars=1000, downloads=5000)
        tool = tmp_registry_with_data.get("tool-a")
        assert tool.stars == 1000
        assert tool.downloads == 5000

    def test_update_metrics_nonexistent(self, tmp_registry_with_data):
        with pytest.raises(KeyError):
            tmp_registry_with_data.update_metrics("nonexistent", stars=100)

    def test_update_security_score(self, tmp_registry_with_data):
        tmp_registry_with_data.update_security_score("tool-a", 4)
        tool = tmp_registry_with_data.get("tool-a")
        assert tool.security_score == 4

    def test_update_security_score_out_of_range(self, tmp_registry_with_data):
        with pytest.raises(ValueError):
            tmp_registry_with_data.update_security_score("tool-a", 5)
        with pytest.raises(ValueError):
            tmp_registry_with_data.update_security_score("tool-a", -1)

    def test_update_existing_tool(self, tmp_registry_with_data):
        tool = tmp_registry_with_data.get("tool-a")
        tool.stars = 9999
        tmp_registry_with_data.update(tool)
        assert tmp_registry_with_data.get("tool-a").stars == 9999

    def test_update_nonexistent_tool(self, tmp_registry_with_data):
        tool = make_tool(name="nonexistent", display_name="Nonexistent")
        with pytest.raises(KeyError):
            tmp_registry_with_data.update(tool)


class TestRegistryEdgeCases:
    """Test edge cases."""

    def test_contains(self, tmp_registry_with_data):
        assert "tool-a" in tmp_registry_with_data
        assert "not-there" not in tmp_registry_with_data

    def test_len(self, tmp_registry_with_data):
        assert len(tmp_registry_with_data) == 3

    def test_very_long_name(self, tmp_registry):
        long_name = "a" * 1000
        with pytest.raises(ValueError):
            make_tool(name=long_name, display_name="Long")

    def test_unicode(self, tmp_registry):
        with pytest.raises(ValueError):
            make_tool(name="中文工具", display_name="中文")


class TestRegistryConcurrency:
    """Test concurrent registry operations."""

    def test_concurrent_add_and_save(self, tmp_path):
        from concurrent.futures import ThreadPoolExecutor
        registry_path = tmp_path / "registry.json"
        registry = Registry(registry_path=str(registry_path))

        def worker(i):
            try:
                registry.add(make_tool(name=f"tool-{i}", display_name=f"Tool {i}"))
                registry._save()
                return True
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(worker, range(20)))

        assert all(results)
        # File should be valid JSON after all concurrent writes
        with open(registry_path, "r") as f:
            data = json.load(f)
        assert len(data.get("tools", [])) == 20
