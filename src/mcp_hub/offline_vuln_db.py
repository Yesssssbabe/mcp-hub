"""Offline vulnerability database cache (JSON-backed) for OSV data."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_hub.vulnerability_models import VulnerabilityEntry

logger = logging.getLogger(__name__)

DEFAULT_DB_NAME = "offline_vuln_db.json"
DEFAULT_MAX_AGE_DAYS = 7


class OfflineVulnDB:
    """Simple JSON-backed offline vulnerability database.

    Stores vulnerability entries keyed by package name for offline querying.
    Supports TTL-based freshness and periodic cleanup.
    """

    def __init__(
        self,
        *,
        db_path: Optional[str] = None,
        max_age_days: int = DEFAULT_MAX_AGE_DAYS,
        ttl_seconds: Optional[float] = None,
    ):
        if db_path:
            self.db_path = Path(db_path)
        else:
            from mcp_hub.constants import DEFAULT_DATA_DIR

            base = (
                Path(DEFAULT_DATA_DIR)
                if DEFAULT_DATA_DIR
                else Path.home() / ".mcp-hub"
            )
            self.db_path = base / DEFAULT_DB_NAME
        self.max_age_days = max_age_days
        if ttl_seconds is not None:
            self.max_age_days = ttl_seconds / 86400.0
        self._data: Dict[str, Any] = {
            "version": 1,
            "entries": {},
            "last_updated": 0.0,
        }
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self.db_path.exists():
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict) and "entries" in loaded:
                    self._data = loaded
                else:
                    logger.warning("Invalid offline DB format, starting fresh")
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("Failed to load offline DB: %s", e)
        else:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _save(self) -> None:
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.warning("Failed to save offline DB: %s", e)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, package_name: str, entries: List[VulnerabilityEntry]) -> None:
        """Store vulnerability entries for a package."""
        key = package_name.lower()
        self._data["entries"][key] = {
            "updated_at": time.time(),
            "vulns": [e.to_dict() for e in entries],
        }
        self._data["last_updated"] = time.time()
        self._save()

    def store(self, entry: VulnerabilityEntry, ecosystem: str = "") -> None:
        """Store a single vulnerability entry.

        Compatibility wrapper for the first v0.2.0 test suite.
        """
        if ecosystem and not entry.ecosystem:
            entry = entry.model_copy(update={"ecosystem": ecosystem})
        existing = self.lookup(entry.package)
        by_id = {v.id: v for v in existing}
        by_id[entry.id] = entry
        self.add(entry.package, list(by_id.values()))

    def lookup(self, package_name: str) -> List[VulnerabilityEntry]:
        """Lookup vulnerabilities for a package (case-insensitive)."""
        key = package_name.lower()
        record = self._data["entries"].get(key)
        if record is None:
            return []
        updated_at = record.get("updated_at", 0.0)
        age_days = (time.time() - updated_at) / 86400.0
        if age_days > self.max_age_days:
            logger.debug(
                "Offline DB entry for %s is stale (%.1f days), ignoring",
                package_name,
                age_days,
            )
            return []
        vulns = record.get("vulns", [])
        return [VulnerabilityEntry(**v) for v in vulns]

    def query(
        self,
        package_name: str,
        version: str = "",
        ecosystem: str = "",
    ) -> List[VulnerabilityEntry]:
        """Lookup vulnerabilities by package, optionally filtering ecosystem/version."""
        results = self.lookup(package_name)
        if ecosystem:
            results = [
                vuln
                for vuln in results
                if not vuln.ecosystem or vuln.ecosystem.lower() == ecosystem.lower()
            ]
        if version:
            filtered = []
            for vuln in results:
                if not vuln.version or vuln.version == version:
                    filtered.append(vuln)
            results = filtered
        return results

    def lookup_batch(
        self, package_names: List[str]
    ) -> Dict[str, List[VulnerabilityEntry]]:
        """Batch lookup vulnerabilities for multiple packages."""
        return {name: self.lookup(name) for name in package_names}

    def delete(self, package_name: str) -> bool:
        """Delete entries for a package."""
        key = package_name.lower()
        if key in self._data["entries"]:
            del self._data["entries"][key]
            self._save()
            return True
        return False

    def clear(self) -> None:
        """Clear all entries."""
        self._data["entries"] = {}
        self._save()

    def cleanup(self) -> int:
        """Remove stale entries older than max_age_days.

        Returns:
            Number of entries removed
        """
        now = time.time()
        stale = []
        for key, record in list(self._data["entries"].items()):
            updated_at = record.get("updated_at", 0.0)
            if (now - updated_at) / 86400.0 > self.max_age_days:
                stale.append(key)
        for key in stale:
            del self._data["entries"][key]
        if stale:
            self._save()
        return len(stale)

    def purge_expired(self) -> int:
        """Compatibility alias for cleanup()."""
        return self.cleanup()

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Return DB statistics."""
        total = len(self._data["entries"])
        now = time.time()
        stale = sum(
            1
            for record in self._data["entries"].values()
            if (now - record.get("updated_at", 0.0)) / 86400.0
            > self.max_age_days
        )
        return {
            "total_packages": total,
            "total_entries": sum(
                len(record.get("vulns", []))
                for record in self._data["entries"].values()
            ),
            "stale_packages": stale,
            "max_age_days": self.max_age_days,
            "db_path": str(self.db_path),
            "last_updated": self._data.get("last_updated", 0.0),
        }
