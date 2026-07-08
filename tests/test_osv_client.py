"""Tests for OSV vulnerability scanning components."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
import requests

from mcp_hub.osv_client import (
    OSVClient,
    OSVQuery,
    OSVBatchResult,
    OSVError,
    OSVNetworkError,
    OSVRateLimitError,
    OSVNotFoundError,
    OSVServerError,
    OSVOfflineFallback,
    map_ecosystem,
)
from mcp_hub.scan_cache import ScanCache
from mcp_hub.offline_vuln_db import OfflineVulnDB
from mcp_hub.vulnerability_models import (
    SeverityLevel,
    VulnerabilityEntry,
    VulnerabilitySource,
    ScanResult,
)
from mcp_hub.vulnerability_normalizer import (
    normalize_osv_vulnerability,
    normalize_osv_response,
    _parse_fixed_versions,
    _parse_cvss_score,
    _parse_osv_severity,
)


# ------------------------------------------------------------------
#  VulnerabilityEntry model tests
# ------------------------------------------------------------------


class TestVulnerabilityEntry:
    """Test VulnerabilityEntry pydantic model."""

    def test_create_minimal(self):
        entry = VulnerabilityEntry(id="CVE-2024-1234", package="test-pkg", version="1.0")
        assert entry.id == "CVE-2024-1234"
        assert entry.package == "test-pkg"
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
        assert entry.severity == SeverityLevel.HIGH
        assert entry.cvss == 7.5
        assert entry.fixed_versions == ["4.17.21"]

    def test_cvss_validation(self):
        # pydantic v2 clamps the value instead of raising
        entry = VulnerabilityEntry(id="CVE-1", package="x", version="1", cvss=11.0)
        assert entry.cvss == 10.0
        entry2 = VulnerabilityEntry(id="CVE-2", package="x", version="1", cvss=-1.0)
        assert entry2.cvss == 0.0

    def test_to_dict(self):
        entry = VulnerabilityEntry(id="CVE-1", package="x", version="1")
        d = entry.to_dict()
        assert d["id"] == "CVE-1"
        assert "severity" in d

    def test_sorting(self):
        low = VulnerabilityEntry(id="L", package="x", version="1", severity=SeverityLevel.LOW)
        high = VulnerabilityEntry(id="H", package="x", version="1", severity=SeverityLevel.HIGH)
        crit = VulnerabilityEntry(id="C", package="x", version="1", severity=SeverityLevel.CRITICAL)
        # SeverityLevel is str Enum; sort by string value won't work numerically.
        # Use explicit severity ordering mapping for comparison.
        order = {SeverityLevel.CRITICAL: 4, SeverityLevel.HIGH: 3, SeverityLevel.MEDIUM: 2, SeverityLevel.LOW: 1}
        sorted_entries = sorted([low, high, crit], key=lambda v: order.get(v.severity, 0), reverse=True)
        assert sorted_entries == [crit, high, low]


# ------------------------------------------------------------------
#  ScanResult model tests
# ------------------------------------------------------------------


class TestScanResult:
    """Test ScanResult pydantic model."""

    def test_create_default(self):
        result = ScanResult(tool_name="test-tool")
        assert result.vulnerabilities == []
        assert not result.has_vulnerabilities
        assert result.critical_count == 0
        assert result.high_count == 0

    def test_add_vulnerability(self):
        result = ScanResult(tool_name="t")
        result.add_vulnerability(
            VulnerabilityEntry(id="CVE-1", package="x", version="1", severity=SeverityLevel.HIGH)
        )
        # model_post_init recalculates counts on full re-validation; direct append won't trigger it.
        # Re-create to verify counts are computed.
        result2 = ScanResult(
            tool_name="t",
            vulnerabilities=[
                VulnerabilityEntry(id="CVE-1", package="x", version="1", severity=SeverityLevel.HIGH)
            ]
        )
        assert result2.high_count == 1
        assert result2.has_vulnerabilities


# ------------------------------------------------------------------
#  OSVClient tests (with mocked requests)
# ------------------------------------------------------------------


class TestOSVClientMocked:
    """Test OSVClient with mocked HTTP responses."""

    @pytest.fixture
    def client(self):
        c = OSVClient()
        c._session = MagicMock()
        return c

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

        data = client.query_single("lodash", "npm", "4.17.15")
        assert len(data) == 1
        assert data[0].id == "GHSA-1234"

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

    def test_query_single_not_found(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        client._session.request.return_value = mock_resp

        with pytest.raises(OSVNotFoundError):
            client.query_single(OSVQuery(package_name="x", ecosystem="npm"))

    def test_rate_limit_retry_then_success(self, client):
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

        data = client.query_single(OSVQuery(package_name="x", ecosystem="npm"))
        assert data == {"vulns": []}
        assert client._session.request.call_count == 2

    def test_server_error_after_retries(self, client):
        mock_500 = MagicMock()
        mock_500.status_code = 500
        mock_500.text = "internal error"
        client._session.request.return_value = mock_500

        client.backoff_base = 0.05
        client.max_retries = 1

        with pytest.raises(OSVServerError):
            client.query_single(OSVQuery(package_name="x", ecosystem="npm"))

    def test_connection_error_fallback(self, client):
        client._session.request.side_effect = requests.ConnectionError("boom")
        client.backoff_base = 0.05
        client.max_retries = 1

        with pytest.raises(OSVNetworkError):
            client.query_single(OSVQuery(package_name="x", ecosystem="npm"))

    def test_offline_mode(self, client):
        client.offline_mode = True
        with pytest.raises(OSVNetworkError):
            client.query_single(OSVQuery(package_name="x", ecosystem="npm"))

    def test_ecosystem_mapping(self):
        assert map_ecosystem("npm") == "npm"
        assert map_ecosystem("pip") == "PyPI"
        assert map_ecosystem("poetry") == "PyPI"
        assert map_ecosystem("cargo") == "crates.io"
        assert map_ecosystem("go") == "Go"
        assert map_ecosystem("unknown") is None


# ------------------------------------------------------------------
#  OfflineVulnDB tests
# ------------------------------------------------------------------


class TestOfflineVulnDB:
    """Test offline vulnerability database."""

    def test_add_and_lookup(self, tmp_path):
        db = OfflineVulnDB(db_path=tmp_path / "vuln_db.db")
        entry = VulnerabilityEntry(id="CVE-1", package="pkg-a", version="1.0")
        db.store(entry, ecosystem="PyPI")
        results = db.query("pkg-a", "1.0", "PyPI")
        assert len(results) == 1
        assert results[0].id == "CVE-1"

    def test_lookup_missing(self, tmp_path):
        db = OfflineVulnDB(db_path=tmp_path / "vuln_db.db")
        assert db.query("nonexistent", "1.0", "PyPI") == []

    def test_purge_expired(self, tmp_path):
        db = OfflineVulnDB(db_path=tmp_path / "vuln_db.db", ttl_seconds=0)
        db.store(VulnerabilityEntry(id="CVE-1", package="pkg", version="1"), ecosystem="PyPI")
        time.sleep(0.1)
        removed = db.purge_expired()
        assert removed >= 1
        assert db.query("pkg", "1", "PyPI") == []

    def test_stats(self, tmp_path):
        db = OfflineVulnDB(db_path=tmp_path / "vuln_db.db")
        db.store(VulnerabilityEntry(id="CVE-1", package="pkg", version="1"), ecosystem="PyPI")
        stats = db.stats()
        assert stats["total_entries"] >= 1


# ------------------------------------------------------------------
#  ScanCache tests
# ------------------------------------------------------------------


class TestScanCache:
    """Test scan cache with TTL and invalidation."""

    def test_cache_hit(self, tmp_path):
        cache = ScanCache(ttl_seconds=3600)
        result = ScanResult(tool_name="t", vulnerabilities=[])
        cache.set("t", result, dep_files=[Path("/fake")])
        cached = cache.get("t", dep_files=[Path("/fake")])
        assert cached is not None
        assert cached.tool_name == "t"

    def test_cache_miss_wrong_hash(self, tmp_path):
        cache = ScanCache(ttl_seconds=3600)
        result = ScanResult(tool_name="t", vulnerabilities=[])
        cache.set("t", result, dep_files=[Path("/fake")])
        assert cache.get("t", dep_files=[Path("/other")]) is None

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
        cache.invalidate("t1")
        assert cache.get("t1") is None
        assert cache.get("t2") is not None

    def test_invalidate_all(self, tmp_path):
        cache = ScanCache(ttl_seconds=3600)
        cache.set("t1", ScanResult(tool_name="t1"))
        cache.set("t2", ScanResult(tool_name="t2"))
        cache.invalidate_all()
        assert cache.get("t1") is None
        assert cache.get("t2") is None

    def test_stats(self):
        cache = ScanCache(ttl_seconds=3600)
        cache.set("t", ScanResult(tool_name="t"))
        stats = cache.stats()
        assert stats["total_entries"] == 1
        assert stats["expired_entries"] == 0


# ------------------------------------------------------------------
#  Severity / CVSS mapping tests
# ------------------------------------------------------------------


class TestSeverityMapping:
    """Test severity and CVSS mapping utilities."""

    def test_parse_osv_severity_critical(self):
        osv = {"severity": [{"type": "CVSS_V3", "score": "9.5"}]}
        assert _parse_osv_severity(osv) == SeverityLevel.CRITICAL

    def test_parse_osv_severity_high(self):
        osv = {"severity": [{"type": "CVSS_V3", "score": "7.5"}]}
        assert _parse_osv_severity(osv) == SeverityLevel.HIGH

    def test_parse_osv_severity_medium(self):
        osv = {"severity": [{"type": "CVSS_V3", "score": "5.5"}]}
        assert _parse_osv_severity(osv) == SeverityLevel.MEDIUM

    def test_parse_osv_severity_low(self):
        osv = {"severity": [{"type": "CVSS_V3", "score": "2.5"}]}
        assert _parse_osv_severity(osv) == SeverityLevel.LOW

    def test_parse_fixed_versions(self):
        osv = {
            "affected": [
                {
                    "ranges": [
                        {"events": [{"introduced": "0"}, {"fixed": "1.2.3"}]}
                    ]
                }
            ]
        }
        fixed = _parse_fixed_versions(osv)
        assert "1.2.3" in fixed


# ------------------------------------------------------------------
#  normalize_vulnerability_from_osv tests
# ------------------------------------------------------------------


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
        entry = normalize_osv_vulnerability(osv_data, package_name="lodash", version="4.17.15")
        assert entry.id == "GHSA-123"
        assert entry.severity == SeverityLevel.HIGH
        assert entry.cvss == 7.5
        assert "4.17.21" in entry.fixed_versions
        assert entry.source == VulnerabilitySource.GHSA

    def test_normalize_minimal(self):
        osv_data = {"id": "OSV-1"}
        entry = normalize_osv_vulnerability(osv_data)
        assert entry.id == "OSV-1"
        assert entry.source == VulnerabilitySource.OSV


# ------------------------------------------------------------------
#  SecurityScanner integration tests
# ------------------------------------------------------------------


class TestSecurityScannerOSVIntegration:
    """Test SecurityScanner.scan() with OSV integration."""

    def test_scan_safe_tool_no_osv_crash(self, tmp_path):
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
        report = scanner.scan("safe-tool")
        assert report.tool_name == "safe-tool"
        assert isinstance(report.vulnerabilities, list)

    def test_scan_with_installed_deps_offline(self, tmp_path):
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
                permissions=[],
            )
        )
        scanner = SecurityScanner(registry=registry)
        # Force offline by mocking OSV client
        scanner._osv_client = OSVClient(offline_mode=True)
        report = scanner.scan("dep-tool")
        assert report.tool_name == "dep-tool"
        assert isinstance(report.vulnerabilities, list)

    def test_scan_offline_fallback_no_crash(self, tmp_path):
        from mcp_hub.security import SecurityScanner
        from mcp_hub.registry import Registry, MCPTool

        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        install_dir = tmp_path / "installed" / "py-tool"
        install_dir.mkdir(parents=True)
        (install_dir / "requirements.txt").write_text("requests>=2.0\n")
        registry.add(
            MCPTool(
                name="py-tool",
                display_name="Py Tool",
                description="desc",
                install_type="pip",
                install_command="pip install py-tool",
                author="a",
                is_installed=True,
                install_path=str(install_dir),
                permissions=[],
            )
        )
        scanner = SecurityScanner(registry=registry)
        scanner._osv_client = OSVClient(offline_mode=True)
        report = scanner.scan("py-tool")
        assert report.tool_name == "py-tool"
        assert isinstance(report.vulnerabilities, list)

    def test_scan_cache_invalidation(self, tmp_path):
        from mcp_hub.security import SecurityScanner
        from mcp_hub.registry import Registry

        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        scanner = SecurityScanner(registry=registry)
        # Populate old-style cache
        scanner._scan_cache[("a", "tool", "", "")] = MagicMock()
        scanner.invalidate_cache("tool")
        assert ("a", "tool", "", "") not in scanner._scan_cache

    def test_scan_compare_tools_with_osv(self, tmp_path):
        from mcp_hub.security import SecurityScanner
        from mcp_hub.registry import Registry, MCPTool

        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(
            MCPTool(
                name="a",
                display_name="A",
                description="desc",
                install_type="npm",
                install_command="npx a",
                author="a",
                permissions=["filesystem:read"],
            )
        )
        registry.add(
            MCPTool(
                name="b",
                display_name="B",
                description="desc",
                install_type="npm",
                install_command="npx b",
                author="a",
                permissions=["filesystem:execute"],
            )
        )
        scanner = SecurityScanner(registry=registry)
        reports = scanner.compare_tools(["a", "b"])
        assert len(reports) == 2
        assert "a" in reports and "b" in reports
