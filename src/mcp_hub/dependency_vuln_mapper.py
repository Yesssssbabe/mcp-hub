"""Dependency-to-OSV query mapper and batch vulnerability scanner.

Converts parsed dependency dictionaries (from SecurityScanner._parse_dependency_file)
into OSV query tuples, then performs batch or single vulnerability lookups.

Supports:
- npm (package.json)
- PyPI (requirements.txt, pyproject.toml, Pipfile)
- Go (go.mod)
- Rust/crates.io (Cargo.toml)
- Maven/Gradle (pom.xml, build.gradle)
- RubyGems (Gemfile)
- Packagist (composer.json)

Network-unavailable graceful degradation: returns empty lists with warnings.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from mcp_hub.osv_client import OSVClient
from mcp_hub.vulnerability_models import VulnerabilityEntry, VulnerabilityBatch

logger = logging.getLogger(__name__)

# Batch size for OSV API (OSV supports up to 1000 per batch)
OSV_BATCH_SIZE = 100


class DependencyVulnMapper:
    """Maps parsed dependencies to OSV vulnerability queries.

    Usage:
        mapper = DependencyVulnMapper(osv_client=OSVClient())
        deps = [{"name": "requests", "version": "2.28.0", "type": "pip"}]
        vulns = mapper.query_dependencies(deps)
    """

    def __init__(self, osv_client: Optional[OSVClient] = None) -> None:
        self.osv_client = osv_client or OSVClient()

    def query_dependencies(
        self,
        dependencies: List[Dict[str, Any]],
    ) -> Tuple[List[VulnerabilityEntry], List[str]]:
        """Query OSV for vulnerabilities in a list of dependencies.

        Args:
            dependencies: List of dicts with keys: name, version, type.

        Returns:
            Tuple of (vulnerability_entries, warnings).
            Warnings include offline-mode or unsupported-ecosystem messages.
        """
        warnings: List[str] = []
        if not dependencies:
            return [], warnings

        # Build OSV-compatible query tuples
        queries: List[Dict[str, str]] = []
        skipped: List[str] = []
        for dep in dependencies:
            dep_type = dep.get("type", "")
            ecosystem = map_ecosystem(dep_type)
            if ecosystem is None:
                skipped.append(dep.get("name", "unknown"))
                continue
            name = dep.get("name", "")
            version = dep.get("version", "")
            # Clean version: strip leading operators (^, ~, >=, etc.)
            clean_version = self._clean_version(version)
            if not name or not clean_version:
                skipped.append(name or "unknown")
                continue
            queries.append({
                "package_name": name,
                "ecosystem": ecosystem,
                "version": clean_version,
            })

        if skipped:
            warnings.append(
                f"Skipped {len(skipped)} dependencies with unsupported ecosystems: "
                f"{', '.join(skipped[:5])}{'...' if len(skipped) > 5 else ''}"
            )

        if not queries:
            return [], warnings

        # Batch query OSV
        try:
            from mcp_hub.osv_client import OSVQuery
            osv_queries = [OSVQuery(**q) for q in queries]
            all_vulns = self.osv_client.query_batch(osv_queries)
        except Exception as exc:
            logger.warning("OSV batch query failed: %s", exc)
            warnings.append(f"OSV vulnerability query failed: {exc}")
            return [], warnings

        return all_vulns, warnings

    def query_single(
        self,
        dep_type: str,
        name: str,
        version: str,
    ) -> Tuple[List[VulnerabilityEntry], List[str]]:
        """Query OSV for a single dependency.

        Args:
            dep_type: Internal dependency type (e.g., "pip", "npm", "cargo").
            name: Package name.
            version: Package version.

        Returns:
            Tuple of (vulnerability_entries, warnings).
        """
        warnings: List[str] = []
        ecosystem = map_ecosystem(dep_type)
        if ecosystem is None:
            warnings.append(f"Unsupported ecosystem for dependency type: {dep_type}")
            return [], warnings

        clean_version = self._clean_version(version)
        if not clean_version:
            warnings.append(f"Invalid version for {name}: {version}")
            return [], warnings

        try:
            vulns = self.osv_client.query_single(name, ecosystem, clean_version)
        except Exception as exc:
            logger.warning("OSV single query failed: %s", exc)
            warnings.append(f"OSV query failed for {name}@{clean_version}: {exc}")
            return [], warnings

        return vulns, warnings

    @staticmethod
    def _clean_version(version: str) -> str:
        """Strip leading version operators from a version string.

        Examples:
            ^4.0.0 -> 4.0.0
            >=2.0.0 -> 2.0.0
            ~1.2.3 -> 1.2.3
            1.0.0 -> 1.0.0
        """
        if not version or version in ("unspecified", "complex", "latest"):
            return ""
        # Strip common prefix operators
        cleaned = version.lstrip("^~>=<!")
        # Strip whitespace
        cleaned = cleaned.strip()
        # If it starts with a digit, keep it; otherwise empty
        if cleaned and cleaned[0].isdigit():
            return cleaned
        return ""

    def close(self) -> None:
        """Close the underlying OSV client session."""
        self.osv_client.close()

    def __enter__(self) -> DependencyVulnMapper:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
