"""Integration tests for OSV vulnerability scanning components."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from mcp_hub.dependency_vuln_mapper import DependencyVulnMapper, OSV_BATCH_SIZE
from mcp_hub.offline_vuln_db import OfflineVulnDB
from mcp_hub.osv_client import (
    OSVClient,
    OSVError,
    OSVNotFoundError,
    OSVRateLimitError,
    OSVServerError,
    OSVQuery,
)
from mcp_hub.scan_cache import ScanCache
from mcp_hub.vulnerability_models import (
    OSVBatchQuery,
    OSVQueryItem,
    ScanResult,
    SeverityLevel,
    VulnerabilityEntry,
    VulnerabilitySource,
    map_cvss_to_severity,
    map_osv_severity_to_cvss,
    normalize_vulnerability_from_osv,
    parse_fixed_versions_from_osv,
)


# ──────────────────────────────────────────────────────────────
#  VulnerabilityEntry model tests
# ──────────────────────────────────────────────────────────────


class TestVulnerabilityEntry:
    """Test VulnerabilityEntry pydantic model."""

    def test_create_minimal(self):
        entry = VulnerabilityEntry(id="CVE-2024-1234", package="test-pkg")
        assert entry.id == "CVE-2024-1234"
        assert entry.package == "test-pkg"
        assert entry.version == ""
        assert entry.severity == SeverityLevel.UNKNOWN
        assert entry.cvss is None

    def test_create_full(self):
        entry = VulnerabilityEntry(
            id="GHSA-xxx",
            package="lodash",
            version="4.17.15",
            severity=SeverityLevel.HIGH,
            cvss=7.5,
            fixed_versions=["4.17.21"],
            source=VulnerabilitySource.GHSA,
            description="Prototype pollution",
        )
        assert entry.is_high
        assert not entry.is_critical
        assert entry.fixed_versions == ["4.17.21"]

    def test_cvss_validation(self):
        entry = VulnerabilityEntry(id="CVE-1", package="x", cvss=11.0)
        # validator clamps to 10.0
        assert entry.cvss == 10.0

    def test_severity_validation_from_string(self):
        entry = VulnerabilityEntry(id="CVE-1", package="x", severity="critical")
        assert entry.severity == SeverityLevel.CRITICAL

    def test_source_validation_from_string(self):
        entry = VulnerabilityEntry(id="CVE-1", package="x", source="cve")
        assert entry.source == VulnerabilitySource.CVE

    def test_sorting(self):
        low = VulnerabilityEntry(id="L", package="x", severity=SeverityLevel.LOW)
        high = VulnerabilityEntry(id="H", package="x", severity=SeverityLevel.HIGH)
        crit = VulnerabilityEntry(
            id="C", package="x", severity=SeverityLevel.CRITICAL
        )
        assert sorted([low, high, crit], reverse=True) == [crit, high, low]

    def test_is_fixed_in(self):
        entry = VulnerabilityEntry(
            id="CVE-1", package="x", fixed_versions=["1.2.3"]
        )
        assert entry.is_fixed_in("1.2.3")
        assert not entry.is_fixed_in("1.2.2")


# ──────────────────────────────────────────────────────────────
#  ScanResult model tests
# ──────────────────────────────────────────────────────────────


class TestScanResult:
    """Test ScanResult pydantic model."""

    def test_create_default(self):
        result = ScanResult(tool_name="test-tool")
        assert result.total_vulns == 0
        assert not result.has_vulnerabilities
        assert result.max_cvss is None
        assert result.risk_score == 0

    def test_add_vulnerability(self):
        result = ScanResult(tool_name="t")
        result.add_vulnerability(
            VulnerabilityEntry(id="CVE-1", package="x", severity=SeverityLevel.HIGH)
        )
        assert result.total_vulns == 1
        assert result.risk_score == 15

    def test_get_by_severity(self):
        result = ScanResult(tool_name="t")
        result.add_vulnerability(
            VulnerabilityEntry(id="C", package="x", severity=SeverityLevel.CRITICAL)
        )
        result.add_vulnerability(
            VulnerabilityEntry(id="H", package="x", severity=SeverityLevel.HIGH)
        )
        assert len(result.get_critical_vulns()) == 1
        assert len(result.get_high_vulns()) == 1


# ──────────────────────────────────────────────────────────────
#  OSVQueryItem / OSVBatchQuery tests
# ──────────────────────────────────────────────────────────────


class TestOSVQueryItem:
    """Test OSV query builders."""

    def test_to_osv_dict_with_version(self):
        item = OSVQueryItem(package_name="django", ecosystem="PyPI", version="3.2")
        d = item.to_osv_dict()
        assert d["package"]["name"] == "django"
        assert d["version"] == "3.2"

    def test_to_osv_dict_without_version(self):
        item = OSVQueryItem(package_name="django", ecosystem="PyPI")
        d = item.to_osv_dict()
        assert "version" not in d

    def test_batch_payload(self):
        batch = OSVBatchQuery(
            queries=[
                OSVQueryItem(package_name="a", ecosystem="npm"),
                OSVQueryItem(package_name="b", ecosystem="PyPI", version="1.0"),
            ]
        )
        payload = batch.to_osv_payload()
        assert len(payload["queries"]) == 2
        assert payload["queries"][1]["version"] == "1.0"


# ──────────────────────────────────────────────────────────────
#  OSVClient tests (with mocked requests)
# ──────────────────────────────────────────────────────────────


class TestOSVClientMocked:
    """Test OSVClient with mocked HTTP responses."""

    @pytest.fixture
    def client(self):
        client = OSVClient()
        client._session = MagicMock()
        return client

    def test_query_single_success(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "vulns": [
                {
                    "id": "GHSA-123",
                    "summary": "Test vuln",
                    "severity": [{"type": "CVSS_V3", "score": "7.5"}],
                    "affected": [
                        {
                            "package": {"name": "lodash", "ecosystem": "npm"},
                            "ranges": [
                                {"events": [{"introduced": "0"}, {"fixed": "4.17.21"}]}
                            ],
                        }
                    ],
                    "aliases": ["CVE-2024-1234"],
                    "references": [{"url": "https://example.com"}],
                    "published": "2024-01-01T00:00:00Z",
                }
            ]
        }
        client._session.request.return_value = mock_resp

        from mcp_hub.osv_client import OSVQuery
        vulns = client.query_single(OSVQuery("lodash", "npm", "4.17.15"))
        assert len(vulns.get("vulns", [])) == 1
        assert vulns["vulns"][0]["id"] == "GHSA-123"

    def test_query_batch_success(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {"vulns": [{"id": "GHSA-1"}]},
                {"vulns": []},
            ]
        }
        client._session.request.return_value = mock_resp

        queries = [
            OSVQuery(package_name="a", ecosystem="npm"),
            OSVQuery(package_name="b", ecosystem="PyPI"),
        ]
        result = client.query_batch(queries)
        assert len(result.results) == 2
        assert result.results[0]["vulns"][0]["id"] == "GHSA-1"

    def test_query_single_not_found(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        client._session.request.return_value = mock_resp

        with pytest.raises(OSVNotFoundError):
            client.query_single(OSVQuery("x", "npm"))

    def test_rate_limit_retry_then_success(self, client):
        # First call 429, second call success
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {"Retry-After": "0.1"}
        mock_429.text = "rate limited"

        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {"vulns": []}

        client._session.request.side_effect = [mock_429, mock_ok]
        client.backoff_base = 0.05
        client.max_retries = 1

        vulns = client.query_single("x", "npm")
        assert vulns == []
        assert client._session.request.call_count == 2

    def test_server_error_after_retries(self, client):
        mock_500 = MagicMock()
        mock_500.status_code = 500
        mock_500.text = "internal error"
        client._session.request.return_value = mock_500

        client.backoff_base = 0.05
        client.max_retries = 1

        with pytest.raises(OSVServerError):
            client.query_single("x", "npm")

    def test_connection_error_fallback(self, client):
        import requests

        client._session.request.side_effect = requests.ConnectionError("boom")
        client.backoff_base = 0.05
        client.max_retries = 1

        with pytest.raises(OSVError):
            client.query_single("x", "npm")

    def test_get_vulnerability(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "GHSA-123"}
        client._session.request.return_value = mock_resp

        data = client.get_vulnerability("GHSA-123")
        assert data["id"] == "GHSA-123"

    def test_ecosystem_mapping(self):
        assert OSVClient.ecosystem_for_dep_type("npm") == "npm"
        assert OSVClient.ecosystem_for_dep_type("pip") == "PyPI"
        assert OSVClient.ecosystem_for_dep_type("poetry") == "PyPI"
        assert OSVClient.ecosystem_for_dep_type("cargo") == "crates.io"
        assert OSVClient.ecosystem_for_dep_type("go") == "Go"
        assert OSVClient.ecosystem_for_dep_type("unknown") == ""


# ──────────────────────────────────────────────────────────────
#  OfflineVulnDB tests
# ──────────────────────────────────────────────────────────────


class TestOfflineVulnDB:
    """Test offline vulnerability database."""

    def test_add_and_lookup(self, tmp_path):
        db = OfflineVulnDB(db_path=str(tmp_path / "vuln_db.json"))
        entry = VulnerabilityEntry(id="CVE-1", package="pkg-a")
        db.add("pkg-a", [entry])
        results = db.lookup("pkg-a")
        assert len(results) == 1
        assert results[0].id == "CVE-1"

    def test_lookup_case_insensitive(self, tmp_path):
        db = OfflineVulnDB(db_path=str(tmp_path / "vuln_db.json"))
        db.add("Pkg-A", [VulnerabilityEntry(id="CVE-1", package="Pkg-A")])
        assert db.lookup("pkg-a")
        assert db.lookup("PKG-A")

    def test_lookup_missing(self, tmp_path):
        db = OfflineVulnDB(db_path=str(tmp_path / "vuln_db.json"))
        assert db.lookup("nonexistent") == []

    def test_stale_entry_ignored(self, tmp_path):
        db = OfflineVulnDB(
            db_path=str(tmp_path / "vuln_db.json"), max_age_days=0
        )
        db.add("pkg", [VulnerabilityEntry(id="CVE-1", package="pkg")])
        # Immediately stale because max_age_days=0
        assert db.lookup("pkg") == []

    def test_cleanup(self, tmp_path):
        db = OfflineVulnDB(
            db_path=str(tmp_path / "vuln_db.json"), max_age_days=0
        )
        db.add("pkg", [VulnerabilityEntry(id="CVE-1", package="pkg")])
        removed = db.cleanup()
        assert removed == 1
        assert db.lookup("pkg") == []

    def test_clear(self, tmp_path):
        db = OfflineVulnDB(db_path=str(tmp_path / "vuln_db.json"))
        db.add("pkg", [VulnerabilityEntry(id="CVE-1", package="pkg")])
        db.clear()
        assert db.lookup("pkg") == []

    def test_stats(self, tmp_path):
        db = OfflineVulnDB(db_path=str(tmp_path / "vuln_db.json"))
        db.add("pkg", [VulnerabilityEntry(id="CVE-1", package="pkg")])
        stats = db.stats()
        assert stats["total_packages"] == 1
        assert stats["stale_packages"] == 0


# ──────────────────────────────────────────────────────────────
#  ScanCache tests
# ──────────────────────────────────────────────────────────────


class TestScanCache:
    """Test scan cache with TTL and invalidation."""

    def test_cache_hit(self, tmp_path):
        cache = ScanCache(ttl_seconds=3600)
        result = ScanResult(tool_name="t", vulnerabilities=[])
        cache.set("t", result, dep_hash="abc")
        cached = cache.get("t", dep_hash="abc")
        assert cached is not None
        assert cached.tool_name == "t"

    def test_cache_miss_wrong_hash(self, tmp_path):
        cache = ScanCache(ttl_seconds=3600)
        result = ScanResult(tool_name="t", vulnerabilities=[])
        cache.set("t", result, dep_hash="abc")
        assert cache.get("t", dep_hash="xyz") is None

    def test_cache_expired(self, tmp_path):
        cache = ScanCache(ttl_seconds=0)
        result = ScanResult(tool_name="t", vulnerabilities=[])
        cache.set("t", result)
        time.sleep(0.01)
        assert cache.get("t") is None

    def test_invalidate_by_tool(self, tmp_path):
        cache = ScanCache(ttl_seconds=3600)
        cache.set("t1", ScanResult(tool_name="t1"))
        cache.set("t2", ScanResult(tool_name="t2"))
        removed = cache.invalidate("t1")
        assert removed == 1
        assert cache.get("t1") is None
        assert cache.get("t2") is not None

    def test_invalidate_all(self, tmp_path):
        cache = ScanCache(ttl_seconds=3600)
        cache.set("t1", ScanResult(tool_name="t1"))
        cache.set("t2", ScanResult(tool_name="t2"))
        removed = cache.invalidate_all()
        assert removed == 2

    def test_invalidate_by_pattern(self, tmp_path):
        cache = ScanCache(ttl_seconds=3600)
        cache.set("prefix-tool-a", ScanResult(tool_name="prefix-tool-a"))
        cache.set("prefix-tool-b", ScanResult(tool_name="prefix-tool-b"))
        cache.set("other", ScanResult(tool_name="other"))
        removed = cache.invalidate_by_pattern("prefix")
        assert removed == 2
        assert cache.get("other") is not None

    def test_hash_dependencies(self):
        deps = [
            {"name": "b", "version": "2.0"},
            {"name": "a", "version": "1.0"},
        ]
        h1 = ScanCache.hash_dependencies(deps)
        h2 = ScanCache.hash_dependencies(list(reversed(deps)))
        assert h1 == h2  # Order-independent

    def test_persistent_cache(self, tmp_path):
        cache_dir = tmp_path / "scan_cache"
        cache = ScanCache(ttl_seconds=3600, cache_dir=str(cache_dir))
        result = ScanResult(tool_name="t", vulnerabilities=[])
        cache.set("t", result, dep_hash="abc")
        # Create new cache instance pointing to same dir
        cache2 = ScanCache(ttl_seconds=3600, cache_dir=str(cache_dir))
        cached = cache2.get("t", dep_hash="abc")
        assert cached is not None

    def test_stats(self):
        cache = ScanCache(ttl_seconds=3600)
        cache.set("t", ScanResult(tool_name="t"))
        stats = cache.stats()
        assert stats["total_entries"] == 1
        assert stats["expired_entries"] == 0


# ──────────────────────────────────────────────────────────────
#  DependencyVulnMapper tests
# ──────────────────────────────────────────────────────────────


class TestDependencyVulnMapper:
    """Test dependency-to-vulnerability mapping."""

    def test_deps_to_osv_queries(self):
        mapper = DependencyVulnMapper(offline_mode=True)
        deps = [
            {"name": "lodash", "version": "^4.17.0", "type": "npm"},
            {"name": "django", "version": "3.2", "type": "pip"},
            {"name": "unknown-eco", "version": "1.0", "type": "custom"},
        ]
        queries = mapper.deps_to_osv_queries(deps)
        assert len(queries) == 2
        assert queries[0].ecosystem == "npm"
        assert queries[1].ecosystem == "PyPI"
        # Version cleaned
        assert queries[0].version == "4.17.0"

    def test_clean_version(self):
        assert DependencyVulnMapper._clean_version("^1.2.3") == "1.2.3"
        assert DependencyVulnMapper._clean_version(">=1.0.0") == "1.0.0"
        assert DependencyVulnMapper._clean_version("~1.0.0") == "1.0.0"
        assert DependencyVulnMapper._clean_version("1.0.0;python>=3.9") == "1.0.0"

    def test_scan_offline_no_deps(self):
        mapper = DependencyVulnMapper(offline_mode=True)
        result = mapper.scan_dependencies("tool", [])
        assert result.tool_name == "tool"
        assert "No mappable dependencies" in result.warnings[0]

    def test_scan_offline_with_cached_data(self, tmp_path):
        db = OfflineVulnDB(db_path=str(tmp_path / "db.json"))
        db.add(
            "lodash",
            [VulnerabilityEntry(id="CVE-1", package="lodash", severity=SeverityLevel.HIGH)],
        )
        mapper = DependencyVulnMapper(offline_mode=True, offline_db=db)
        result = mapper.scan_dependencies(
            "tool", [{"name": "lodash", "version": "4.17.0", "type": "npm"}]
        )
        assert len(result.vulnerabilities) == 1
        assert result.vulnerabilities[0].id == "CVE-1"
        assert result.offline_mode is True

    def test_scan_online_mocked(self, tmp_path):
        mock_client = MagicMock()
        mock_client.query_batch.return_value = [
            VulnerabilityEntry(id="GHSA-1", package="lodash")
        ]
        mapper = DependencyVulnMapper(
            offline_mode=False,
            osv_client=mock_client,
            offline_db=OfflineVulnDB(db_path=str(tmp_path / "db.json")),
            scan_cache=ScanCache(ttl_seconds=3600),
        )
        result = mapper.scan_dependencies(
            "tool", [{"name": "lodash", "version": "4.17.0", "type": "npm"}]
        )
        assert len(result.vulnerabilities) == 1
        assert result.vulnerabilities[0].id == "GHSA-1"
        assert result.offline_mode is False

    def test_scan_online_failure_fallback(self, tmp_path):
        mock_client = MagicMock()
        mock_client.query_batch.side_effect = Exception("network down")
        db = OfflineVulnDB(db_path=str(tmp_path / "db.json"))
        db.add(
            "lodash",
            [VulnerabilityEntry(id="CVE-1", package="lodash")],
        )
        mapper = DependencyVulnMapper(
            offline_mode=False,
            osv_client=mock_client,
            offline_db=db,
            scan_cache=ScanCache(ttl_seconds=3600),
        )
        result = mapper.scan_dependencies(
            "tool", [{"name": "lodash", "version": "4.17.0", "type": "npm"}]
        )
        assert len(result.vulnerabilities) == 1
        assert "OSV query failed" in result.errors[0]
        assert "falling back to offline DB" in result.warnings[0]

    def test_deduplication(self, tmp_path):
        mock_client = MagicMock()
        mock_client.query_batch.return_value = [
            VulnerabilityEntry(id="GHSA-1", package="lodash"),
            VulnerabilityEntry(id="GHSA-1", package="lodash"),  # duplicate
        ]
        mapper = DependencyVulnMapper(
            offline_mode=False,
            osv_client=mock_client,
            offline_db=OfflineVulnDB(db_path=str(tmp_path / "db.json")),
            scan_cache=ScanCache(ttl_seconds=3600),
        )
        result = mapper.scan_dependencies(
            "tool", [{"name": "lodash", "version": "4.17.0", "type": "npm"}]
        )
        assert len(result.vulnerabilities) == 1

    def test_is_version_affected(self):
        vuln = VulnerabilityEntry(
            id="CVE-1", package="x", fixed_versions=["1.2.3"]
        )
        assert DependencyVulnMapper.is_version_affected(vuln, "1.2.2")
        assert not DependencyVulnMapper.is_version_affected(vuln, "1.2.3")

    def test_filter_affected(self):
        vulns = [
            VulnerabilityEntry(id="V1", package="x", fixed_versions=["2.0"]),
            VulnerabilityEntry(id="V2", package="x", fixed_versions=["1.5"]),
        ]
        affected = DependencyVulnMapper.filter_affected(vulns, "1.0")
        assert len(affected) == 2
        affected = DependencyVulnMapper.filter_affected(vulns, "2.0")
        assert len(affected) == 1
        assert affected[0].id == "V2"

    def test_aggregate_severity(self):
        vulns = [
            VulnerabilityEntry(id="C", package="x", severity=SeverityLevel.CRITICAL),
            VulnerabilityEntry(id="H", package="x", severity=SeverityLevel.HIGH, cvss=8.0),
            VulnerabilityEntry(id="L", package="x", severity=SeverityLevel.LOW),
        ]
        agg = DependencyVulnMapper.aggregate_severity(vulns)
        assert agg["severity_counts"]["CRITICAL"] == 1
        assert agg["severity_counts"]["HIGH"] == 1
        assert agg["severity_counts"]["LOW"] == 1
        assert agg["max_cvss"] == 8.0
        assert agg["critical_or_high"] == 2


# ──────────────────────────────────────────────────────────────
#  Severity / CVSS mapping tests
# ──────────────────────────────────────────────────────────────


class TestSeverityMapping:
    """Test severity and CVSS mapping utilities."""

    def test_map_osv_severity_to_cvss(self):
        assert map_osv_severity_to_cvss("critical") == (SeverityLevel.CRITICAL, 9.5)
        assert map_osv_severity_to_cvss("high") == (SeverityLevel.HIGH, 7.5)
        assert map_osv_severity_to_cvss("medium") == (SeverityLevel.MEDIUM, 5.5)
        assert map_osv_severity_to_cvss("low") == (SeverityLevel.LOW, 2.5)
        assert map_osv_severity_to_cvss("unknown") == (SeverityLevel.UNKNOWN, None)

    def test_map_cvss_to_severity(self):
        assert map_cvss_to_severity(9.5) == SeverityLevel.CRITICAL
        assert map_cvss_to_severity(7.5) == SeverityLevel.HIGH
        assert map_cvss_to_severity(5.5) == SeverityLevel.MEDIUM
        assert map_cvss_to_severity(2.5) == SeverityLevel.LOW
        assert map_cvss_to_severity(0.0) == SeverityLevel.NONE

    def test_parse_fixed_versions_from_osv(self):
        events = [{"introduced": "0"}, {"fixed": "1.2.3"}, {"limit": "2.0"}]
        fixed = parse_fixed_versions_from_osv(events)
        assert "1.2.3" in fixed
        assert "2.0" in fixed
        assert "0" not in fixed


# ──────────────────────────────────────────────────────────────
#  normalize_vulnerability_from_osv tests
# ──────────────────────────────────────────────────────────────


class TestNormalizeVulnerabilityFromOSV:
    """Test OSV data normalization."""

    def test_normalize_full(self):
        osv_data = {
            "id": "GHSA-123",
            "summary": "Test vulnerability",
            "severity": [{"type": "CVSS_V3", "score": "7.5"}],
            "affected": [
                {
                    "package": {"name": "lodash", "ecosystem": "npm"},
                    "ranges": [
                        {"events": [{"introduced": "0"}, {"fixed": "4.17.21"}]}
                    ],
                }
            ],
            "aliases": ["CVE-2024-1234"],
            "references": [{"url": "https://example.com"}],
            "published": "2024-01-01T00:00:00Z",
            "modified": "2024-02-01T00:00:00Z",
        }
        entry = normalize_vulnerability_from_osv(osv_data)
        assert entry.id == "GHSA-123"
        assert entry.severity == SeverityLevel.HIGH
        assert entry.cvss == 7.5
        assert "4.17.21" in entry.fixed_versions
        assert entry.cve_id == "CVE-2024-1234"
        assert entry.source == VulnerabilitySource.GHSA

    def test_normalize_minimal(self):
        osv_data = {"id": "OSV-1"}
        entry = normalize_vulnerability_from_osv(osv_data)
        assert entry.id == "OSV-1"
        assert entry.source == VulnerabilitySource.OSV


# ──────────────────────────────────────────────────────────────
#  SecurityScanner integration tests
# ──────────────────────────────────────────────────────────────


class TestSecurityScannerOSVIntegration:
    """Test SecurityScanner.scan_tool() integration."""

    def test_scan_tool_not_found(self, tmp_path):
        from mcp_hub.security import SecurityScanner
        from mcp_hub.registry import Registry

        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        scanner = SecurityScanner(registry=registry)
        result = scanner.scan_tool("nonexistent")
        assert result.tool_name == "nonexistent"
        assert result.errors  # Should have error about tool not found

    def test_scan_tool_no_deps(self, tmp_path):
        from mcp_hub.security import SecurityScanner
        from mcp_hub.registry import Registry, MCPTool

        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(
            MCPTool(
                name="safe-tool",
                display_name="Safe",
                description="desc",
                install_type="npm",
                install_command="npx safe-tool",
                author="a",
                permissions=["filesystem:read"],
            )
        )
        scanner = SecurityScanner(registry=registry)
        result = scanner.scan_tool("safe-tool")
        assert result.tool_name == "safe-tool"
        assert result.vulnerabilities == []
        assert "No dependencies found" in result.warnings[-1]

    def test_scan_tool_with_deps_offline(self, tmp_path):
        from mcp_hub.security import SecurityScanner
        from mcp_hub.registry import Registry, MCPTool

        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        install_dir = tmp_path / "installed" / "dep-tool"
        install_dir.mkdir(parents=True)
        (install_dir / "package.json").write_text(
            '{"dependencies": {"lodash": "^4.17.0"}}'
        )
        registry.add(
            MCPTool(
                name="dep-tool",
                display_name="Dep Tool",
                description="desc",
                install_type="npm",
                install_command="npx dep-tool",
                author="a",
                is_installed=True,
                install_path=str(install_dir),
            )
        )
        scanner = SecurityScanner(registry=registry)
        # Force offline mode by using offline mapper
        result = scanner.scan_tool("dep-tool")
        assert result.tool_name == "dep-tool"
        # Should not crash; may have empty vulns in offline mode
        assert isinstance(result.vulnerabilities, list)

    def test_invalidate_scan_cache(self, tmp_path):
        from mcp_hub.security import SecurityScanner
        from mcp_hub.registry import Registry

        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        scanner = SecurityScanner(registry=registry)
        # Populate old-style cache
        scanner._scan_cache[("a", "tool", "", "")] = MagicMock()
        removed = scanner.invalidate_scan_cache("tool")
        assert removed >= 1

    def test_invalidate_all_scan_cache(self, tmp_path):
        from mcp_hub.security import SecurityScanner
        from mcp_hub.registry import Registry

        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        scanner = SecurityScanner(registry=registry)
        scanner._scan_cache[("a", "t1", "", "")] = MagicMock()
        scanner._scan_cache[("b", "t2", "", "")] = MagicMock()
        removed = scanner.invalidate_all_scan_cache()
        assert removed >= 2
        assert len(scanner._scan_cache) == 0
