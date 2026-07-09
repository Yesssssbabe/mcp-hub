"""Dependency-to-OSV query mapping for multiple ecosystems.

Parses dependency files (package.json, requirements.txt, go.mod, Cargo.toml)
and converts them into OSV-compatible query tuples.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mcp_hub.vulnerability_models import OSVQueryItem

logger = logging.getLogger(__name__)

# OSV ecosystem identifiers
ECOSYSTEM_NPM = "npm"
ECOSYSTEM_PYPI = "PyPI"
ECOSYSTEM_GO = "Go"
ECOSYSTEM_RUST = "crates.io"


def parse_npm_dependencies(file_path: str) -> List[Dict[str, Any]]:
    """Parse package.json and extract dependencies.

    Args:
        file_path: Path to package.json.

    Returns:
        List of dependency dicts with name, version, type keys.
    """
    deps: List[Dict[str, Any]] = []
    path = Path(file_path)
    if not path.exists():
        return deps

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as exc:
        logger.warning("Failed to parse package.json: %s", exc)
        return deps

    for key in ("dependencies", "devDependencies", "peerDependencies"):
        if key not in data or not isinstance(data[key], dict):
            continue
        for name, version in data[key].items():
            # Clean version prefix
            clean_version = str(version).lstrip("^~>=<!").strip()
            deps.append(
                {
                    "name": name,
                    "version": clean_version,
                    "type": "npm",
                    "source": key,
                }
            )

    return deps


def parse_pypi_dependencies(file_path: str) -> List[Dict[str, Any]]:
    """Parse requirements.txt and extract PyPI dependencies.

    Args:
        file_path: Path to requirements.txt.

    Returns:
        List of dependency dicts.
    """
    deps: List[Dict[str, Any]] = []
    path = Path(file_path)
    if not path.exists():
        return deps

    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except IOError as exc:
        logger.warning("Failed to read requirements.txt: %s", exc)
        return deps

    # Regex for package==version or package>=version
    req_re = re.compile(r"^([A-Za-z0-9_.\-]+)\s*([=<>!~]+)\s*([^\s;#]+)")
    # Simple package name without version
    simple_re = re.compile(r"^([A-Za-z0-9_.\-]+)(?:\s*;|\s*#|$)")

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue

        match = req_re.match(line)
        if match:
            name = match.group(1)
            version = match.group(3).strip()
            deps.append(
                {
                    "name": name,
                    "version": version,
                    "type": "pypi",
                    "source": "requirements.txt",
                }
            )
            continue

        match = simple_re.match(line)
        if match:
            name = match.group(1)
            deps.append(
                {
                    "name": name,
                    "version": "unknown",
                    "type": "pypi",
                    "source": "requirements.txt",
                }
            )

    return deps


def parse_go_dependencies(file_path: str) -> List[Dict[str, Any]]:
    """Parse go.mod and extract module dependencies.

    Args:
        file_path: Path to go.mod.

    Returns:
        List of dependency dicts.
    """
    deps: List[Dict[str, Any]] = []
    path = Path(file_path)
    if not path.exists():
        return deps

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except IOError as exc:
        logger.warning("Failed to read go.mod: %s", exc)
        return deps

    # Match require blocks: require ( ... ) or require module version
    # Single-line require
    single_re = re.compile(r'^require\s+([\w.\-/]+)\s+v?([^\s\)]+)', re.MULTILINE)
    for match in single_re.finditer(content):
        name = match.group(1)
        version = match.group(2).strip()
        deps.append(
            {
                "name": name,
                "version": version,
                "type": "go",
                "source": "go.mod",
            }
        )

    # Block require
    block_re = re.compile(r'require\s*\((.*?)\)', re.DOTALL)
    for block_match in block_re.finditer(content):
        block = block_match.group(1)
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                version = parts[1].lstrip("v")
                deps.append(
                    {
                        "name": name,
                        "version": version,
                        "type": "go",
                        "source": "go.mod",
                    }
                )

    return deps


def parse_rust_dependencies(file_path: str) -> List[Dict[str, Any]]:
    """Parse Cargo.toml and extract crate dependencies.

    Args:
        file_path: Path to Cargo.toml.

    Returns:
        List of dependency dicts.
    """
    deps: List[Dict[str, Any]] = []
    path = Path(file_path)
    if not path.exists():
        return deps

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        # Cargo.toml is TOML, not JSON. Try basic regex fallback.
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except IOError as exc:
            logger.warning("Failed to read Cargo.toml: %s", exc)
            return deps

        # Simple regex for [dependencies] section
        dep_section = re.search(r'\[dependencies\](.*?)(?=\[|$)', content, re.DOTALL)
        if dep_section:
            section = dep_section.group(1)
            # name = "version" or name = { version = "...", ... }
            for line in section.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Simple version string
                simple_match = re.match(r'^([A-Za-z0-9_\-]+)\s*=\s*"([^"]+)"', line)
                if simple_match:
                    deps.append(
                        {
                            "name": simple_match.group(1),
                            "version": simple_match.group(2),
                            "type": "rust",
                            "source": "Cargo.toml",
                        }
                    )
                    continue
                # Table with version key
                table_match = re.match(r'^([A-Za-z0-9_\-]+)\s*=\s*\{', line)
                if table_match:
                    name = table_match.group(1)
                    ver_match = re.search(r'version\s*=\s*"([^"]+)"', line)
                    if ver_match:
                        deps.append(
                            {
                                "name": name,
                                "version": ver_match.group(1),
                                "type": "rust",
                                "source": "Cargo.toml",
                            }
                        )
        return deps

    # If json.load succeeded (unlikely for valid Cargo.toml), handle it
    for key in ("dependencies", "dev-dependencies", "build-dependencies"):
        if key not in data or not isinstance(data[key], dict):
            continue
        for name, spec in data[key].items():
            if isinstance(spec, str):
                version = spec.lstrip("^~>=<!").strip()
            elif isinstance(spec, dict):
                version = spec.get("version", "unknown")
                if isinstance(version, str):
                    version = version.lstrip("^~>=<!").strip()
            else:
                version = "unknown"
            deps.append(
                {
                    "name": name,
                    "version": version,
                    "type": "rust",
                    "source": key,
                }
            )

    return deps


def map_dependencies_to_osv_queries(
    dependencies: List[Dict[str, Any]],
) -> List[OSVQueryItem]:
    """Convert parsed dependencies to OSV query items.

    Args:
        dependencies: List of dependency dicts with name, version, type.

    Returns:
        List of OSVQueryItem objects.
    """
    ecosystem_map = {
        "npm": ECOSYSTEM_NPM,
        "pypi": ECOSYSTEM_PYPI,
        "go": ECOSYSTEM_GO,
        "rust": ECOSYSTEM_RUST,
    }

    queries: List[OSVQueryItem] = []
    for dep in dependencies:
        dep_type = dep.get("type", "").lower()
        ecosystem = ecosystem_map.get(dep_type)
        if not ecosystem:
            continue
        name = dep.get("name", "").strip()
        version = dep.get("version", "").strip()
        if not name:
            continue
        if not version or version == "unknown":
            # Skip unknown versions for OSV query
            continue
        queries.append(OSVQueryItem(package_name=name, ecosystem=ecosystem, version=version))

    return queries


def detect_dependency_files(directory: str) -> List[str]:
    """Detect known dependency files in a directory.

    Args:
        directory: Path to scan.

    Returns:
        List of file paths.
    """
    files = []
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return files

    patterns = {
        "package.json": "npm",
        "requirements.txt": "pypi",
        "go.mod": "go",
        "Cargo.toml": "rust",
    }

    for filename, dep_type in patterns.items():
        file_path = dir_path / filename
        if file_path.exists():
            files.append(str(file_path))

    return files


def parse_dependencies_from_file(file_path: str) -> List[Dict[str, Any]]:
    """Auto-detect file type and parse dependencies.

    Args:
        file_path: Path to dependency file.

    Returns:
        List of dependency dicts.
    """
    path = Path(file_path)
    filename = path.name.lower()

    if filename == "package.json":
        return parse_npm_dependencies(file_path)
    elif filename == "requirements.txt":
        return parse_pypi_dependencies(file_path)
    elif filename == "go.mod":
        return parse_go_dependencies(file_path)
    elif filename == "cargo.toml":
        return parse_rust_dependencies(file_path)
    else:
        logger.warning("Unknown dependency file type: %s", file_path)
        return []


def parse_dependencies_from_directory(directory: str) -> List[Dict[str, Any]]:
    """Parse all dependency files in a directory.

    Args:
        directory: Directory to scan.

    Returns:
        Combined list of dependency dicts from all detected files.
    """
    all_deps: List[Dict[str, Any]] = []
    for file_path in detect_dependency_files(directory):
        deps = parse_dependencies_from_file(file_path)
        all_deps.extend(deps)
    return all_deps
