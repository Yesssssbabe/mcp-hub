"""Tests for mcp_hub.scan_cache module."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from mcp_hub.scan_cache import ScanCache, DEFAULT_TTL_SECONDS


class TestScanCacheInit:
    def test_default_init(self):
        cache = ScanCache()
        assert cache.ttl_seconds == DEFAULT_TTL_SECONDS
        assert cache.cache_path is None

    def test_custom_ttl(self):
        cache = ScanCache(ttl_seconds=3600)
        assert cache.ttl_seconds == 3600

    def test_with_cache_path(self, tmp_path):
        path = str(tmp_path / "cache.json")
        cache = ScanCache(cache_path=path)
        assert cache.cache_path == path


class TestScanCacheGetSet:
    def test_set_and_get(self):
        cache = ScanCache()
        cache.set("tool-a", {"score": 80})
        result = cache.get("tool-a")
        assert result == {"score": 80}

    def test_get_missing(self):
        cache = ScanCache()
        assert cache.get("missing") is None

    def test_get_expired(self):
        cache = ScanCache(ttl_seconds=0.01)
        cache.set("tool-a", {"score": 80})
        time.sleep(0.05)
        assert cache.get("tool-a") is None

    def test_set_overwrite(self):
        cache = ScanCache()
        cache.set("tool-a", {"score": 80})
        cache.set("tool-a", {"score": 90})
        assert cache.get("tool-a") == {"score": 90}


class TestScanCacheInvalidate:
    def test_invalidate_single_tool(self):
        cache = ScanCache()
        cache.set("tool-a", {"score": 80})
        cache.set("tool-b", {"score": 70})
        cache.invalidate("tool-a")
        assert cache.get("tool-a") is None
        assert cache.get("tool-b") is not None

    def test_invalidate_all_scan_types(self):
        cache = ScanCache()
        cache.set("tool-a", {"score": 80}, scan_type="full")
        cache.set("tool-a", {"score": 75}, scan_type="quick")
        cache.invalidate("tool-a")
        assert cache.get("tool-a", scan_type="full") is None
        assert cache.get("tool-a", scan_type="quick") is None

    def test_invalidate_by_scan_type(self):
        cache = ScanCache()
        cache.set("tool-a", {"score": 80}, scan_type="full")
        cache.set("tool-a", {"score": 75}, scan_type="quick")
        cache.invalidate("tool-a", scan_type="full")
        assert cache.get("tool-a", scan_type="full") is None
        assert cache.get("tool-a", scan_type="quick") is not None

    def test_invalidate_all(self):
        cache = ScanCache()
        cache.set("tool-a", {"score": 80})
        cache.set("tool-b", {"score": 70})
        cache.invalidate_all()
        assert cache.get("tool-a") is None
        assert cache.get("tool-b") is None

    def test_invalidate_returns_true(self):
        cache = ScanCache()
        cache.set("tool-a", {"score": 80})
        assert cache.invalidate("tool-a") is True

    def test_invalidate_returns_false(self):
        cache = ScanCache()
        assert cache.invalidate("missing") is False


class TestScanCacheDependencyChange:
    def test_invalidate_on_new_file(self, tmp_path):
        cache = ScanCache()
        cache.set("tool-a", {"score": 80})
        dep_file = tmp_path / "package.json"
        dep_file.write_text("{}")
        invalidated = cache.invalidate_by_dependency_change(
            "tool-a", [str(dep_file)]
        )
        assert invalidated is True
        assert cache.get("tool-a") is None

    def test_no_invalidate_on_same_file(self, tmp_path):
        cache = ScanCache()
        cache.set("tool-a", {"score": 80})
        dep_file = tmp_path / "package.json"
        dep_file.write_text("{}")
        cache.invalidate_by_dependency_change("tool-a", [str(dep_file)])
        cache.set("tool-a", {"score": 80})
        invalidated = cache.invalidate_by_dependency_change(
            "tool-a", [str(dep_file)]
        )
        assert invalidated is False
        assert cache.get("tool-a") is not None

    def test_invalidate_on_file_change(self, tmp_path):
        cache = ScanCache()
        dep_file = tmp_path / "package.json"
        dep_file.write_text("{}")
        cache.invalidate_by_dependency_change("tool-a", [str(dep_file)])
        cache.set("tool-a", {"score": 80})
        time.sleep(0.1)
        dep_file.write_text('{"name": "test"}')
        invalidated = cache.invalidate_by_dependency_change(
            "tool-a", [str(dep_file)]
        )
        assert invalidated is True


class TestScanCacheFreshness:
    def test_is_fresh(self):
        cache = ScanCache()
        cache.set("tool-a", {"score": 80})
        assert cache.is_fresh("tool-a") is True

    def test_is_fresh_expired(self):
        cache = ScanCache(ttl_seconds=0.01)
        cache.set("tool-a", {"score": 80})
        time.sleep(0.05)
        assert cache.is_fresh("tool-a") is False

    def test_ttl_remaining(self):
        cache = ScanCache(ttl_seconds=3600)
        cache.set("tool-a", {"score": 80})
        remaining = cache.ttl_remaining("tool-a")
        assert remaining > 3500

    def test_ttl_remaining_not_cached(self):
        cache = ScanCache()
        assert cache.ttl_remaining("missing") == -1.0

    def test_ttl_remaining_expired(self):
        cache = ScanCache(ttl_seconds=0.01)
        cache.set("tool-a", {"score": 80})
        time.sleep(0.05)
        assert cache.ttl_remaining("tool-a") == -1.0


class TestScanCacheStats:
    def test_stats_empty(self):
        cache = ScanCache()
        stats = cache.stats()
        assert stats["total_entries"] == 0
        assert stats["valid_entries"] == 0

    def test_stats_with_entries(self):
        cache = ScanCache()
        cache.set("tool-a", {"score": 80})
        stats = cache.stats()
        assert stats["total_entries"] == 1
        assert stats["valid_entries"] == 1

    def test_stats_with_expired(self):
        cache = ScanCache(ttl_seconds=0.01)
        cache.set("tool-a", {"score": 80})
        time.sleep(0.05)
        stats = cache.stats()
        assert stats["total_entries"] == 1
        assert stats["expired_entries"] == 1
        assert stats["valid_entries"] == 0


class TestScanCachePersistence:
    def test_save_and_load(self, tmp_path):
        path = str(tmp_path / "cache.json")
        cache1 = ScanCache(cache_path=path)
        cache1.set("tool-a", {"score": 80})

        cache2 = ScanCache(cache_path=path)
        result = cache2.get("tool-a")
        assert result == {"score": 80}

    def test_load_corrupted_file(self, tmp_path):
        path = str(tmp_path / "cache.json")
        Path(path).write_text("not json")
        cache = ScanCache(cache_path=path)
        assert cache.get("anything") is None

    def test_hash_files_missing(self):
        cache = ScanCache()
        h = cache._hash_files(["/nonexistent/path"])
        assert len(h) == 32

    def test_hash_files_content(self, tmp_path):
        cache = ScanCache()
        f = tmp_path / "test.txt"
        f.write_text("hello")
        h1 = cache._hash_files([str(f)])
        f.write_text("world")
        h2 = cache._hash_files([str(f)])
        assert h1 != h2
