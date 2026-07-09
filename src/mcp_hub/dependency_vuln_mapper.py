"""Dependency-to-OSV query mapper and vulnerability scanner."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from mcp_hub.offline_vuln_db import OfflineVulnDB
from mcp_hub.osv_client import OSVBatchResult, OSVClient, OSVQuery, map_ecosystem
from mcp_hub.scan_cache import ScanCache
from mcp_hub.vulnerability_models import (
    ScanResult,
    SeverityLevel,
    VulnerabilityEntry,
    normalize_vulnerability_from_osv,
)

logger = logging.getLogger(__name__)

OSV_BATCH_SIZE = 100


class DependencyVulnMapper:
    """Map parsed dependencies to OSV queries and vulnerability results."""

    def __init__(
        self,
        osv_client: Optional[OSVClient] = None,
        *,
        offline_mode: bool = False,
        offline_db: Optional[OfflineVulnDB] = None,
        scan_cache: Optional[ScanCache] = None,
    ) -> None:
        self.offline_mode = offline_mode
        self.osv_client = osv_client or OSVClient(offline_mode=offline_mode)
        self.offline_db = offline_db or OfflineVulnDB()
        self.scan_cache = scan_cache or ScanCache()

    def deps_to_osv_queries(self, dependencies: List[Dict[str, Any]]) -> List[OSVQuery]:
        queries: List[OSVQuery] = []
        for dep in dependencies:
            ecosystem = map_ecosystem(str(dep.get("type", "")))
            name = str(dep.get("name", ""))
            version = self._clean_version(str(dep.get("version", "")))
            if ecosystem and name and version:
                queries.append(OSVQuery(name, ecosystem, version))
        return queries

    def scan_dependencies(
        self,
        tool_name: str,
        dependencies: List[Dict[str, Any]],
    ) -> ScanResult:
        result = ScanResult(
            tool_name=tool_name,
            dependency_count=len(dependencies),
            offline_mode=self.offline_mode,
            source="offline" if self.offline_mode else "osv",
            osv_available=not self.offline_mode,
            osv_status="offline" if self.offline_mode else "ok",
        )
        queries = self.deps_to_osv_queries(dependencies)
        if not queries:
            result.add_warning("No mappable dependencies found")
            return result

        dep_hash = self.scan_cache.hash_dependencies(dependencies)
        cached = self.scan_cache.get(tool_name, dep_hash=dep_hash, scan_type="dependencies")
        if isinstance(cached, ScanResult):
            return cached

        vulnerabilities: List[VulnerabilityEntry] = []
        if self.offline_mode:
            vulnerabilities = self._query_offline(queries)
        else:
            try:
                response = self.osv_client.query_batch(queries)
                vulnerabilities = self._entries_from_batch_response(response, queries)
                for vuln in vulnerabilities:
                    self.offline_db.store(vuln, ecosystem=vuln.ecosystem)
            except Exception as exc:
                result.add_error(f"OSV query failed: {exc}")
                result.add_warning("OSV query failed; falling back to offline DB")
                result.osv_available = False
                result.osv_status = "degraded"
                vulnerabilities = self._query_offline(queries)

        for vuln in self._dedupe(vulnerabilities):
            result.add_vulnerability(vuln)

        self.scan_cache.set(tool_name, result, dep_hash=dep_hash, scan_type="dependencies")
        return result

    def query_dependencies(
        self,
        dependencies: List[Dict[str, Any]],
    ) -> Tuple[List[VulnerabilityEntry], List[str]]:
        result = self.scan_dependencies("dependencies", dependencies)
        return result.vulnerabilities, result.warnings + result.errors

    def query_single(
        self,
        dep_type: str,
        name: str,
        version: str,
    ) -> Tuple[List[VulnerabilityEntry], List[str]]:
        result = self.scan_dependencies(
            name,
            [{"name": name, "version": version, "type": dep_type}],
        )
        return result.vulnerabilities, result.warnings + result.errors

    def _query_offline(self, queries: List[OSVQuery]) -> List[VulnerabilityEntry]:
        vulns: List[VulnerabilityEntry] = []
        for query in queries:
            vulns.extend(
                self.offline_db.query(query.package_name, query.version, query.ecosystem)
            )
        return vulns

    @staticmethod
    def _entries_from_batch_response(
        response: Any,
        queries: List[OSVQuery],
    ) -> List[VulnerabilityEntry]:
        if isinstance(response, list):
            return response
        raw_results = response.results if isinstance(response, OSVBatchResult) else []
        entries: List[VulnerabilityEntry] = []
        for index, raw_result in enumerate(raw_results):
            query = queries[index] if index < len(queries) else None
            for raw_vuln in raw_result.get("vulns", []):
                entry = normalize_vulnerability_from_osv(
                    raw_vuln,
                    package_name=query.package_name if query else "",
                    version=query.version if query else "",
                )
                if entry is not None:
                    entries.append(entry)
        return entries

    @staticmethod
    def _dedupe(vulnerabilities: List[VulnerabilityEntry]) -> List[VulnerabilityEntry]:
        by_id: Dict[str, VulnerabilityEntry] = {}
        for vuln in vulnerabilities:
            by_id[vuln.id] = vuln
        return list(by_id.values())

    @staticmethod
    def _clean_version(version: str) -> str:
        if not version or version in ("unspecified", "complex", "latest", "unknown"):
            return ""
        cleaned = str(version).split(";", 1)[0].split(",", 1)[0].strip()
        cleaned = cleaned.lstrip("^~>=<!")
        return cleaned if cleaned and cleaned[0].isdigit() else ""

    @staticmethod
    def is_version_affected(vuln: VulnerabilityEntry, version: str) -> bool:
        if not version or not vuln.fixed_versions:
            return True
        current = _version_tuple(version)
        return all(current != _version_tuple(fixed) for fixed in vuln.fixed_versions)

    @classmethod
    def filter_affected(
        cls,
        vulns: List[VulnerabilityEntry],
        version: str,
    ) -> List[VulnerabilityEntry]:
        return [vuln for vuln in vulns if cls.is_version_affected(vuln, version)]

    @staticmethod
    def aggregate_severity(vulns: List[VulnerabilityEntry]) -> Dict[str, Any]:
        counts = {level.value: 0 for level in SeverityLevel}
        max_cvss = None
        for vuln in vulns:
            counts[vuln.severity.value] = counts.get(vuln.severity.value, 0) + 1
            if vuln.cvss is not None:
                max_cvss = vuln.cvss if max_cvss is None else max(max_cvss, vuln.cvss)
        return {
            "severity_counts": counts,
            "max_cvss": max_cvss,
            "critical_or_high": counts.get("CRITICAL", 0) + counts.get("HIGH", 0),
            "total": len(vulns),
        }

    def close(self) -> None:
        self.osv_client.close()

    def __enter__(self) -> DependencyVulnMapper:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def _version_tuple(version: str) -> Tuple[int, ...]:
    parts: List[int] = []
    for part in str(version).split("."):
        digits = ""
        for char in part:
            if char.isdigit():
                digits += char
            else:
                break
        if digits:
            parts.append(int(digits))
    return tuple(parts or [0])
