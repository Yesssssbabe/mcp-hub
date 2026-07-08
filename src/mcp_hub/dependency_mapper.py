"""Dependency mapper: converts parsed dependency dicts to OSV query tuples.

Supports npm (package.json), PyPI (requirements.txt / pyproject.toml),
Go (go.mod), and Rust (Cargo.toml) ecosystems.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Ecosystem mapping from internal dep_type to OSV ecosystem string
_ECOSYSTEM_MAP = {
    "npm": "npm",
    "pip": "PyPI",
    "poetry": "PyPI",
    "pipenv": "PyPI",
    "cargo": "crates.io",
    "go": "Go",
    "maven": "Maven",
    "gradle": "Maven",
    "bundler": "RubyGems",
    "composer": "Packagist",
}


def map_dependency_to_query(dep: Dict[str, Any]) -> Optional[Tuple[str, str, str]]:
    """Map a single parsed dependency dict to an OSV query tuple.

    Args:
        dep: Dict with keys 'name', 'version', 'type'.

    Returns:
        Tuple of (package_name, version, ecosystem) or None if unsupported.
    """
    name = dep.get("name", "")
    version = dep.get("version", "")
    dep_type = dep.get("type", "")

    if not name or not version:
        return None

    # Clean version string: strip leading operators (^, ~, >=, ==, etc.)
    clean_version = _clean_version(version)
    if not clean_version:
        return None

    ecosystem = _ECOSYSTEM_MAP.get(dep_type, "")
    if not ecosystem:
        logger.debug(f"Skipping unsupported dependency type: {dep_type}")
        return None

    return (name, clean_version, ecosystem)


def map_dependencies_to_queries(
    dependencies: List[Dict[str, Any]],
) -> List[Tuple[str, str, str]]:
    """Map multiple parsed dependency dicts to OSV query tuples.

    Args:
        dependencies: List of dependency dicts from _parse_dependency_file.

    Returns:
        List of (package_name, version, ecosystem) tuples.
    """
    queries: List[Tuple[str, str, str]] = []
    for dep in dependencies:
        query = map_dependency_to_query(dep)
        if query:
            queries.append(query)
    return queries


def _clean_version(version: str) -> str:
    """Strip version prefixes/operators to get a plain version string.

    Examples:
        "^4.17.0" -> "4.17.0"
        ">=2.0.0" -> "2.0.0"
        "==1.0.0" -> "1.0.0"
        "~1.2.3" -> "1.2.3"
        "1.0.0" -> "1.0.0"
        "unspecified" -> ""
    """
    if not version or version.lower() == "unspecified":
        return ""

    # Strip common prefixes
    cleaned = version.strip()
    for prefix in ("^", "~", ">=", "<=", ">", "<", "==", "!=", "~="):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break

    # Handle semver ranges like "4.x || >=4.17.15" — take first valid version
    if "||" in cleaned:
        cleaned = cleaned.split("||")[0].strip()
    if " - " in cleaned:
        cleaned = cleaned.split(" - ")[0].strip()

    # Remove trailing comments or markers
    cleaned = cleaned.split(";")[0].split("#")[0].strip()

    # If it looks like a range (e.g., ">=1.0,<2.0"), take the lower bound
    if "," in cleaned:
        parts = [p.strip() for p in cleaned.split(",")]
        for p in parts:
            if p.startswith(">=") or p.startswith(">"):
                cleaned = p.lstrip(">=").lstrip(">").strip()
                break
        else:
            cleaned = parts[0]

    # Final cleanup: remove any remaining non-version chars at start
    cleaned = cleaned.lstrip("^~>=<!").strip()

    # Validate it looks like a version (starts with digit)
    if cleaned and cleaned[0].isdigit():
        return cleaned
    return ""


# ─── Ecosystem-specific parsers ────────────────────────────────────────────


def parse_npm_package_json(file_path: Path) -> List[Dict[str, Any]]:
    """Parse package.json and return dependency dicts.

    Args:
        file_path: Path to package.json.

    Returns:
        List of dependency dicts with keys name, version, type, source.
    """
    deps: List[Dict[str, Any]] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError, OSError) as e:
        logger.warning(f"Failed to parse package.json: {e}")
        return deps

    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        if key in data and isinstance(data[key], dict):
            for name, version in data[key].items():
                deps.append({
                    "name": name,
                    "version": str(version),
                    "type": "npm",
                    "source": key,
                })
    return deps


def parse_requirements_txt(file_path: Path) -> List[Dict[str, Any]]:
    """Parse requirements.txt and return dependency dicts.

    Uses packaging.requirements.Requirement if available, otherwise falls
    back to regex-based parsing.
    """
    deps: List[Dict[str, Any]] = []
    try:
        from packaging.requirements import Requirement
    except ImportError:  # pragma: no cover
        Requirement = None  # type: ignore[misc,assignment]

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (IOError, OSError) as e:
        logger.warning(f"Failed to read requirements.txt: {e}")
        return deps

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue

        if Requirement:
            try:
                req = Requirement(line)
                version = str(req.specifier) if req.specifier else "unspecified"
                deps.append({
                    "name": req.name,
                    "version": version,
                    "type": "pip",
                    "source": "requirements.txt",
                })
                continue
            except Exception as e:
                logger.debug(f"Could not parse requirement line: {line}: {e}")

        # Fallback regex parsing
        clean = line.split(";")[0].split("#")[0].strip()
        import re
        match = re.match(
            r'^([a-zA-Z0-9][a-zA-Z0-9_\-\.]*)'
            r'(?:\[[^\]]+\])?'
            r'\s*([=<>~!]*)'
            r'\s*(.*)$',
            clean,
        )
        if match:
            deps.append({
                "name": match.group(1),
                "version": match.group(3).strip() or "unspecified",
                "type": "pip",
                "source": "requirements.txt",
            })
        else:
            name = re.split(r'[[\]=<>~!]', clean)[0].strip()
            if name and re.match(r'^[a-zA-Z0-9]', name):
                deps.append({
                    "name": name,
                    "version": "unspecified",
                    "type": "pip",
                    "source": "requirements.txt",
                })
    return deps


def parse_go_mod(file_path: Path) -> List[Dict[str, Any]]:
    """Parse go.mod and return dependency dicts."""
    deps: List[Dict[str, Any]] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            in_require_block = False
            for line in f:
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                if line.startswith("require ("):
                    in_require_block = True
                    continue
                if in_require_block and line == ")":
                    in_require_block = False
                    continue
                if in_require_block or line.startswith("require "):
                    req_line = line
                    if req_line.startswith("require "):
                        req_line = req_line[len("require "):].strip()
                    req_line = req_line.strip("()")
                    parts = req_line.split()
                    if len(parts) >= 2:
                        deps.append({
                            "name": parts[0],
                            "version": parts[1],
                            "type": "go",
                            "source": "go.mod",
                        })
    except (IOError, OSError) as e:
        logger.warning(f"Failed to parse go.mod: {e}")
    return deps


def parse_cargo_toml(file_path: Path) -> List[Dict[str, Any]]:
    """Parse Cargo.toml and return dependency dicts."""
    deps: List[Dict[str, Any]] = []
    try:
        import tomllib
    except ImportError:  # pragma: no cover
        try:
            import tomli as tomllib
        except ImportError:  # pragma: no cover
            tomllib = None  # type: ignore[misc,assignment]

    try:
        if tomllib is not None:
            with open(file_path, "rb") as f:
                data = tomllib.load(f)
            cargo_deps = data.get("dependencies", {})
            if isinstance(cargo_deps, dict):
                for name, spec in cargo_deps.items():
                    if isinstance(spec, str):
                        version = spec
                    elif isinstance(spec, dict):
                        version = spec.get("version", "complex")
                    else:
                        version = "complex"
                    deps.append({
                        "name": name,
                        "version": version,
                        "type": "cargo",
                        "source": "Cargo.toml",
                    })
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            import re
            dep_section = re.search(r"\[dependencies\](.*?)(?=\[|$)", content, re.DOTALL)
            if dep_section:
                for line in dep_section.group(1).strip().split("\n"):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    match = re.match(
                        r'^([a-zA-Z0-9][a-zA-Z0-9_\-\.]*)'
                        r'\s*=\s*'
                        r'(?:"([^"]+)"|(\{.*\}))',
                        line,
                    )
                    if match:
                        deps.append({
                            "name": match.group(1),
                            "version": match.group(2) if match.group(2) else "complex",
                            "type": "cargo",
                            "source": "Cargo.toml",
                        })
    except (IOError, OSError, Exception) as e:
        logger.warning(f"Failed to parse Cargo.toml: {e}")
    return deps


def parse_dependencies_for_osv(
    install_path: Path,
    dependency_files: Dict[str, str],
) -> List[Tuple[str, str, str]]:
    """Parse all dependency files in an install path and map to OSV queries.

    Args:
        install_path: Path to the tool installation directory.
        dependency_files: Mapping of filename -> dep_type (from SecurityScanner.DEPENDENCY_FILES).

    Returns:
        List of OSV query tuples (name, version, ecosystem).
    """
    all_deps: List[Dict[str, Any]] = []

    for filename, dep_type in dependency_files.items():
        file_path = install_path / filename
        if not file_path.exists() or not file_path.is_file():
            continue

        try:
            if dep_type == "npm":
                deps = parse_npm_package_json(file_path)
            elif dep_type in ("pip", "poetry", "pipenv"):
                deps = parse_requirements_txt(file_path)
            elif dep_type == "go":
                deps = parse_go_mod(file_path)
            elif dep_type == "cargo":
                deps = parse_cargo_toml(file_path)
            else:
                continue
            all_deps.extend(deps)
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")

    return map_dependencies_to_queries(all_deps)
