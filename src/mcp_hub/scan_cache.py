"""Scan cache with TTL, manual invalidation, and dependency-change detection."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mcp_hub.vulnerability_models import ScanResult, VulnerabilityEntry

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 24 * 3600  # 24 hours


class ScanCache:
    """Thread-safe (process-safe via file locking) scan result cache.

    Features:
    - TTL-based automatic expiration
    - Manual invalidation by tool name or pattern
    - Dependency-change hash invalidation
    - Optional persistent JSON backing store
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        cache_dir: Optional[str] = None,
        cache_path: Optional[str] = None,
    ):
        self.ttl_seconds = ttl_seconds
        self._memory: Dict[str, Tuple[float, str, ScanResult]] = {}
        # cache_dir stores persistent JSON copies; memory is primary
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.cache_path = cache_path
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def _make_key(
        self, tool_name: str, dep_hash: str = "", registry_id: str = ""
    ) -> str:
        """Build a cache key scoped to tool + dependency state + registry."""
        parts = [tool_name]
        if dep_hash:
            parts.append(dep_hash)
        if registry_id:
            parts.append(registry_id)
        return "|".join(parts)

    def get(
        self, tool_name: str, dep_hash: str = "", registry_id: str = ""
    ) -> Optional[ScanResult]:
        """Retrieve cached ScanResult if not expired.

        Args:
            tool_name: Tool identifier
            dep_hash: Hash of current dependency state; mismatch invalidates
            registry_id: Registry instance identifier for scoping

        Returns:
            ScanResult or None if missing/expired
        """
        key = self._make_key(tool_name, dep_hash, registry_id)
        entry = self._memory.get(key)
        if entry is None:
            # Try persistent cache
            entry = self._load_from_disk(key)
            if entry is None:
                return None
            self._memory[key] = entry

        timestamp, stored_dep_hash, result = entry
        now = time.time()
        if now - timestamp > self.ttl_seconds:
            logger.debug("Cache expired for %s", tool_name)
            self._delete(key)
            return None
        if dep_hash and stored_dep_hash != dep_hash:
            logger.debug(
                "Dependency hash mismatch for %s, invalidating cache", tool_name
            )
            self._delete(key)
            return None
        return result

    def set(
        self,
        tool_name: str,
        result: ScanResult,
        dep_hash: str = "",
        registry_id: str = "",
    ) -> None:
        """Store a ScanResult in cache."""
        key = self._make_key(tool_name, dep_hash, registry_id)
        self._memory[key] = (time.time(), dep_hash, result)
        self._save_to_disk(key, self._memory[key])

    def invalidate(self, tool_name: str) -> int:
        """Invalidate all cache entries matching a tool name.

        Returns:
            Number of entries removed
        """
        removed = 0
        for key in list(self._memory.keys()):
            if key.split("|")[0] == tool_name:
                self._delete(key)
                removed += 1
        return removed

    def invalidate_all(self) -> int:
        """Clear the entire cache.

        Returns:
            Number of entries removed
        """
        count = len(self._memory)
        for key in list(self._memory.keys()):
            self._delete(key)
        return count

    def invalidate_by_pattern(self, pattern: str) -> int:
        """Invalidate cache entries whose tool name contains a substring.

        Returns:
            Number of entries removed
        """
        removed = 0
        for key in list(self._memory.keys()):
            tool_name = key.split("|")[0]
            if pattern in tool_name:
                self._delete(key)
                removed += 1
        return removed

    # ------------------------------------------------------------------
    # Dependency hash helpers
    # ------------------------------------------------------------------

    @staticmethod
    def hash_dependencies(deps: List[Dict[str, Any]]) -> str:
        """Create a stable hash of dependency list for change detection.

        Args:
            deps: List of dependency dicts (must contain 'name' and 'version')

        Returns:
            Hex digest string
        """
        normalized = []
        for d in sorted(deps, key=lambda x: x.get("name", "")):
            normalized.append(f"{d.get('name','')}@{d.get('version','')}")
        payload = "\n".join(normalized)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Persistent store (JSON)
    # ------------------------------------------------------------------

    def _disk_path(self, key: str) -> Optional[Path]:
        if self.cache_dir is None:
            return None
        safe = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self.cache_dir / f"{safe}.json"

    def _load_from_disk(
        self, key: str
    ) -> Optional[Tuple[float, str, ScanResult]]:
        path = self._disk_path(key)
        if path is None or not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            timestamp = data.get("timestamp", 0.0)
            dep_hash = data.get("dep_hash", "")
            result = ScanResult(**data["result"])
            # Convert vulnerability dicts back to models
            vulns = []
            for v in data["result"].get("vulnerabilities", []):
                vulns.append(VulnerabilityEntry(**v))
            result.vulnerabilities = vulns
            return timestamp, dep_hash, result
        except (OSError, json.JSONDecodeError, TypeError, KeyError) as e:
            logger.debug("Failed to load cache from disk: %s", e)
            return None

    def _save_to_disk(
        self, key: str, entry: Tuple[float, str, ScanResult]
    ) -> None:
        path = self._disk_path(key)
        if path is None:
            return
        timestamp, dep_hash, result = entry
        try:
            data = {
                "timestamp": timestamp,
                "dep_hash": dep_hash,
                "result": result.to_dict(),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.debug("Failed to save cache to disk: %s", e)

    def _delete(self, key: str) -> None:
        self._memory.pop(key, None)
        path = self._disk_path(key)
        if path and path.exists():
            try:
                os.remove(path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Stats / introspection
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        now = time.time()
        total = len(self._memory)
        expired = sum(
            1 for ts, _, _ in self._memory.values() if now - ts > self.ttl_seconds
        )
        return {
            "total_entries": total,
            "expired_entries": expired,
            "ttl_seconds": self.ttl_seconds,
            "cache_dir": str(self.cache_dir) if self.cache_dir else None,
        }
