"""Scan cache with TTL, persistence, and dependency-change detection."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from pydantic import BaseModel

from mcp_hub.vulnerability_models import ScanResult, VulnerabilityEntry

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 24 * 3600


class ScanCache:
    """Small TTL cache used by v0.2 vulnerability scanning.

    The public API intentionally accepts both the newer ``dep_hash`` style and
    the test-suite ``dep_files``/``scan_type`` style so cache users can migrate
    without losing invalidation behavior.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        cache_dir: Optional[str] = None,
        cache_path: Optional[str] = None,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.cache_path = cache_path
        self._memory: Dict[str, Dict[str, Any]] = {}
        self._dep_hashes: Dict[str, str] = {}

        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._load_cache_dir()
        if self.cache_path:
            self._load_cache_file()

    def _make_key(
        self,
        tool_name: str,
        dep_hash: str = "",
        registry_id: str = "",
        scan_type: str = "default",
    ) -> str:
        return "|".join([tool_name, scan_type or "default", dep_hash, registry_id])

    def _resolve_dep_hash(
        self,
        dep_hash: str = "",
        dep_files: Optional[Iterable[object]] = None,
    ) -> str:
        if dep_hash:
            return dep_hash
        if dep_files is not None:
            return self._hash_files(dep_files)
        return ""

    def get(
        self,
        tool_name: str,
        dep_hash: str = "",
        registry_id: str = "",
        *,
        scan_type: str = "default",
        dep_files: Optional[Iterable[object]] = None,
    ) -> Optional[Any]:
        dep_hash = self._resolve_dep_hash(dep_hash, dep_files)
        key = self._make_key(tool_name, dep_hash, registry_id, scan_type)
        entry = self._memory.get(key)
        if entry is None:
            return None

        if self._is_entry_expired(entry):
            self._delete(key)
            return None
        return entry["result"]

    def set(
        self,
        tool_name: str,
        result: Any,
        dep_hash: str = "",
        registry_id: str = "",
        *,
        scan_type: str = "default",
        dep_files: Optional[Iterable[object]] = None,
    ) -> None:
        dep_hash = self._resolve_dep_hash(dep_hash, dep_files)
        key = self._make_key(tool_name, dep_hash, registry_id, scan_type)
        self._memory[key] = {
            "timestamp": time.time(),
            "dep_hash": dep_hash,
            "registry_id": registry_id,
            "scan_type": scan_type or "default",
            "result": result,
        }
        if dep_hash:
            self._dep_hashes[tool_name] = dep_hash
        self._save_cache_file()
        self._save_to_cache_dir(key)

    def invalidate(self, tool_name: str, *, scan_type: Optional[str] = None) -> bool:
        removed = False
        for key, entry in list(self._memory.items()):
            key_tool = key.split("|", 1)[0]
            if key_tool != tool_name:
                continue
            if scan_type is not None and entry.get("scan_type") != scan_type:
                continue
            self._delete(key)
            removed = True
        return removed

    def invalidate_all(self) -> int:
        count = len(self._memory)
        for key in list(self._memory):
            self._delete(key)
        self._dep_hashes.clear()
        self._save_cache_file()
        return count

    def invalidate_by_pattern(self, pattern: str) -> int:
        removed = 0
        for key in list(self._memory):
            if pattern in key.split("|", 1)[0]:
                self._delete(key)
                removed += 1
        return removed

    def invalidate_by_dependency_change(
        self, tool_name: str, dep_files: Iterable[object]
    ) -> bool:
        current_hash = self._hash_files(dep_files)
        previous_hash = self._dep_hashes.get(tool_name)
        self._dep_hashes[tool_name] = current_hash
        if previous_hash == current_hash:
            return False
        return self.invalidate(tool_name)

    def is_fresh(
        self,
        tool_name: str,
        *,
        scan_type: str = "default",
        dep_hash: str = "",
        dep_files: Optional[Iterable[object]] = None,
        registry_id: str = "",
    ) -> bool:
        return (
            self.get(
                tool_name,
                dep_hash,
                registry_id,
                scan_type=scan_type,
                dep_files=dep_files,
            )
            is not None
        )

    def ttl_remaining(
        self,
        tool_name: str,
        *,
        scan_type: str = "default",
        dep_hash: str = "",
        dep_files: Optional[Iterable[object]] = None,
        registry_id: str = "",
    ) -> float:
        dep_hash = self._resolve_dep_hash(dep_hash, dep_files)
        key = self._make_key(tool_name, dep_hash, registry_id, scan_type)
        entry = self._memory.get(key)
        if entry is None or self._is_entry_expired(entry):
            return -1.0
        return max(0.0, self.ttl_seconds - (time.time() - entry["timestamp"]))

    @staticmethod
    def hash_dependencies(deps: list[dict[str, Any]]) -> str:
        normalized = [
            f"{d.get('name', '')}@{d.get('version', '')}"
            for d in sorted(deps, key=lambda x: x.get("name", ""))
        ]
        return hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()[:16]

    def _hash_files(self, files: Iterable[object]) -> str:
        digest = hashlib.sha256()
        for item in sorted(str(Path(os.fspath(f))) for f in files):
            path = Path(item)
            digest.update(item.encode("utf-8"))
            try:
                stat = path.stat()
                digest.update(str(stat.st_mtime_ns).encode("utf-8"))
                digest.update(str(stat.st_size).encode("utf-8"))
                digest.update(path.read_bytes())
            except OSError:
                digest.update(b"<missing>")
        return digest.hexdigest()[:32]

    def stats(self) -> Dict[str, Any]:
        total = len(self._memory)
        expired = sum(1 for entry in self._memory.values() if self._is_entry_expired(entry))
        return {
            "total_entries": total,
            "valid_entries": total - expired,
            "expired_entries": expired,
            "ttl_seconds": self.ttl_seconds,
            "cache_dir": str(self.cache_dir) if self.cache_dir else None,
            "cache_path": self.cache_path,
        }

    def _is_entry_expired(self, entry: Dict[str, Any]) -> bool:
        return time.time() - float(entry.get("timestamp", 0.0)) > self.ttl_seconds

    def _delete(self, key: str) -> None:
        self._memory.pop(key, None)
        path = self._disk_path(key)
        if path and path.exists():
            try:
                os.remove(path)
            except OSError:
                pass
        self._save_cache_file()

    def _disk_path(self, key: str) -> Optional[Path]:
        if self.cache_dir is None:
            return None
        safe = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self.cache_dir / f"{safe}.json"

    def _serialize_result(self, result: Any) -> Dict[str, Any]:
        if isinstance(result, ScanResult):
            return {"kind": "scan_result", "value": result.to_dict()}
        if isinstance(result, BaseModel):
            return {"kind": result.__class__.__name__, "value": result.model_dump()}
        return {"kind": "raw", "value": result}

    def _deserialize_result(self, payload: Dict[str, Any]) -> Any:
        kind = payload.get("kind")
        value = payload.get("value")
        if kind == "scan_result" and isinstance(value, dict):
            vulns = [
                VulnerabilityEntry(**v)
                for v in value.get("vulnerabilities", [])
                if isinstance(v, dict)
            ]
            result = ScanResult(**{**value, "vulnerabilities": vulns})
            return result
        return value

    def _entry_to_json(self, entry: Dict[str, Any], key: str = "") -> Dict[str, Any]:
        return {
            "key": key,
            "timestamp": entry["timestamp"],
            "dep_hash": entry.get("dep_hash", ""),
            "registry_id": entry.get("registry_id", ""),
            "scan_type": entry.get("scan_type", "default"),
            "result": self._serialize_result(entry.get("result")),
        }

    def _entry_from_json(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "timestamp": float(data.get("timestamp", 0.0)),
            "dep_hash": data.get("dep_hash", ""),
            "registry_id": data.get("registry_id", ""),
            "scan_type": data.get("scan_type", "default"),
            "result": self._deserialize_result(data.get("result", {})),
        }

    def _save_to_cache_dir(self, key: str) -> None:
        path = self._disk_path(key)
        if path is None:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._entry_to_json(self._memory[key], key), f, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.debug("Failed to save cache entry: %s", exc)

    def _load_cache_dir(self) -> None:
        if self.cache_dir is None or not self.cache_dir.exists():
            return
        for path in self.cache_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                key = data.get("key", "")
                if key:
                    entry = self._entry_from_json(data)
                    self._memory[key] = entry
                    dep_hash = entry.get("dep_hash", "")
                    if dep_hash:
                        self._dep_hashes[key.split("|", 1)[0]] = dep_hash
            except (OSError, json.JSONDecodeError, TypeError, AttributeError) as exc:
                logger.debug("Failed to load scan cache entry %s: %s", path, exc)

    def _load_cache_file(self) -> None:
        if not self.cache_path:
            return
        path = Path(self.cache_path)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entries = data.get("entries", {}) if isinstance(data, dict) else {}
            self._dep_hashes = data.get("dep_hashes", {}) if isinstance(data, dict) else {}
            for key, entry in entries.items():
                self._memory[key] = self._entry_from_json(entry)
        except (OSError, json.JSONDecodeError, TypeError, AttributeError) as exc:
            logger.debug("Failed to load scan cache: %s", exc)

    def _save_cache_file(self) -> None:
        if not self.cache_path:
            return
        path = Path(self.cache_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "entries": {
                    key: self._entry_to_json(entry, key)
                    for key, entry in self._memory.items()
                },
                "dep_hashes": self._dep_hashes,
            }
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, TypeError) as exc:
            logger.debug("Failed to save scan cache: %s", exc)
