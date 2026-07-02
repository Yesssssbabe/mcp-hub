"""MCP Hub tool installer and uninstaller.

This module provides the `Installer` class for managing MCP tool lifecycle:
install, uninstall, update, verify, and list installed tools.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import urllib.request

from mcp_hub.constants import (
    DEFAULT_DATA_DIR,
    INSTALL_TYPES,
    InstallationError,
)
from mcp_hub.registry import MCPTool, Registry

logger = logging.getLogger(__name__)


@dataclass
class InstallResult:
    """Result of an install / uninstall / update operation."""

    success: bool
    tool_name: str
    message: str
    install_path: Optional[str] = None
    install_method: Optional[str] = None
    errors: List[str] = field(default_factory=list)


class Installer:
    """Manages MCP tool installation, uninstallation, and verification."""

    # Map shorthand names to the executable checked on PATH
    _PREREQ_COMMANDS: Dict[str, List[str]] = {
        "npm": ["npm", "--version"],
        "pip": ["pip", "--version"],
        "docker": ["docker", "--version"],
        "git": ["git", "--version"],
    }

    def __init__(self, install_dir: Optional[str] = None) -> None:
        self.install_dir = install_dir or os.path.expanduser("~/.mcp-hub/installed")
        self.log_dir = os.path.join(DEFAULT_DATA_DIR, "logs")
        self.registry = Registry()

        os.makedirs(self.install_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def install(
        self,
        tool_name: str,
        method: Optional[str] = None,
    ) -> InstallResult:
        """Install an MCP tool.

        Steps
        -----
        1. Look up the tool in the registry.
        2. Determine the install method (registry default or user override).
        3. Check host prerequisites.
        4. Dispatch to the specialised installer.
        5. Verify the installation.
        6. Mark the tool as installed in the registry.
        7. Return an ``InstallResult``.

        If any step fails the installer attempts to roll back partial changes.
        """
        start_time = time.time()
        errors: List[str] = []

        # 1. Registry lookup
        try:
            tool = self.registry.get_tool(tool_name)
        except Exception as exc:  # pragma: no cover
            msg = f"Tool '{tool_name}' not found in registry: {exc}"
            logger.error(msg)
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=msg,
                errors=[msg],
            )

        # 2. Determine method
        chosen_method = method or self._detect_install_method(tool)
        if chosen_method not in INSTALL_TYPES:
            msg = (
                f"Unsupported install method '{chosen_method}' for '{tool_name}'. "
                f"Supported: {', '.join(INSTALL_TYPES)}"
            )
            logger.error(msg)
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=msg,
                install_method=chosen_method,
                errors=[msg],
            )

        target_dir = os.path.join(self.install_dir, tool_name)

        # 3. Prerequisite check
        if not self._check_prerequisites(chosen_method):
            msg = f"Prerequisites not met for method '{chosen_method}'"
            logger.error(msg)
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=msg,
                install_method=chosen_method,
                errors=[msg],
            )

        # 4. Dispatch installer
        installer_fn = getattr(self, f"_install_{chosen_method}")
        result = installer_fn(tool, target_dir)
        result.install_method = chosen_method

        if not result.success:
            self._cleanup_on_failure(tool_name, target_dir)
            return result

        # 5. Verify
        if not self.verify_installation(tool_name):
            msg = f"Installation verification failed for '{tool_name}'"
            logger.error(msg)
            errors.append(msg)
            self._cleanup_on_failure(tool_name, target_dir)
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=msg,
                install_method=chosen_method,
                install_path=target_dir,
                errors=errors,
            )

        # 6. Mark installed
        try:
            self.registry.mark_installed(tool_name, target_dir, chosen_method)
        except Exception as exc:  # pragma: no cover
            msg = f"Failed to mark '{tool_name}' as installed: {exc}"
            logger.error(msg)
            errors.append(msg)
            self._cleanup_on_failure(tool_name, target_dir)
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=msg,
                install_method=chosen_method,
                install_path=target_dir,
                errors=errors,
            )

        elapsed = time.time() - start_time
        msg = (
            f"Successfully installed '{tool_name}' via {chosen_method} "
            f"in {elapsed:.1f}s at {target_dir}"
        )
        logger.info(msg)
        return InstallResult(
            success=True,
            tool_name=tool_name,
            message=msg,
            install_method=chosen_method,
            install_path=target_dir,
        )

    def uninstall(self, tool_name: str, purge: bool = False) -> InstallResult:
        """Uninstall an MCP tool.

        Parameters
        ----------
        tool_name:
            Name of the tool to remove.
        purge:
            If ``True``, also delete logs and registry metadata.
        """
        install_path = self.get_install_path(tool_name)
        if install_path is None:
            msg = f"Tool '{tool_name}' is not installed"
            logger.warning(msg)
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=msg,
                errors=[msg],
            )

        errors: List[str] = []

        # Remove installation directory
        try:
            if os.path.isdir(install_path):
                shutil.rmtree(install_path)
                logger.info("Removed installation directory: %s", install_path)
        except Exception as exc:  # pragma: no cover
            msg = f"Failed to remove directory {install_path}: {exc}"
            logger.error(msg)
            errors.append(msg)

        # Optional: purge logs
        if purge:
            log_path = self._log_path(tool_name)
            try:
                if os.path.exists(log_path):
                    os.remove(log_path)
                    logger.info("Removed install log: %s", log_path)
            except Exception as exc:  # pragma: no cover
                msg = f"Failed to remove log {log_path}: {exc}"
                logger.error(msg)
                errors.append(msg)

        # Update registry
        try:
            self.registry.mark_uninstalled(tool_name)
        except Exception as exc:  # pragma: no cover
            msg = f"Failed to update registry for '{tool_name}': {exc}"
            logger.error(msg)
            errors.append(msg)

        if errors:
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=f"Uninstall of '{tool_name}' completed with errors",
                install_path=install_path,
                errors=errors,
            )

        msg = f"Successfully uninstalled '{tool_name}'"
        logger.info(msg)
        return InstallResult(
            success=True,
            tool_name=tool_name,
            message=msg,
        )

    def is_installed(self, tool_name: str) -> bool:
        """Check if a tool is installed."""
        return self.registry.is_installed(tool_name)

    def get_install_path(self, tool_name: str) -> Optional[str]:
        """Get installation directory of a tool."""
        return self.registry.get_install_path(tool_name)

    def list_installed(self) -> List[str]:
        """List all installed tool names."""
        return self.registry.list_installed()

    def update(self, tool_name: str) -> InstallResult:
        """Update an installed tool to the latest version."""
        if not self.is_installed(tool_name):
            msg = f"Tool '{tool_name}' is not installed; cannot update"
            logger.warning(msg)
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=msg,
                errors=[msg],
            )

        install_path = self.get_install_path(tool_name)
        method = self.registry.get_install_method(tool_name)

        # For most methods the simplest update is reinstall
        try:
            self.registry.mark_uninstalled(tool_name)
            if install_path and os.path.isdir(install_path):
                shutil.rmtree(install_path)
        except Exception as exc:  # pragma: no cover
            msg = f"Failed to clean old version of '{tool_name}': {exc}"
            logger.error(msg)
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=msg,
                errors=[msg],
            )

        return self.install(tool_name, method=method)

    def verify_installation(self, tool_name: str) -> bool:
        """Verify a tool is properly installed and working."""
        if not self.is_installed(tool_name):
            return False

        install_path = self.get_install_path(tool_name)
        if install_path is None or not os.path.exists(install_path):
            return False

        method = self.registry.get_install_method(tool_name)
        verify_fn = getattr(self, f"_verify_{method}_installation", None)
        if verify_fn is None:
            # Generic fallback: directory must be non-empty
            return len(os.listdir(install_path)) > 0

        return verify_fn(tool_name, install_path)

    def get_install_log(self, tool_name: str) -> Optional[str]:
        """Get installation log for a tool."""
        log_path = self._log_path(tool_name)
        if not os.path.exists(log_path):
            return None
        try:
            with open(log_path, "r", encoding="utf-8") as fh:
                return fh.read()
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to read log for %s: %s", tool_name, exc)
            return None

    # ------------------------------------------------------------------
    # Install methods
    # ------------------------------------------------------------------

    def _install_npm(self, tool: MCPTool, target_dir: str) -> InstallResult:
        """Install an MCP tool via npm."""
        tool_name = tool.name
        package = getattr(tool, "npm_package", None) or tool_name
        errors: List[str] = []

        self._write_log(tool_name, f"[npm] Installing package: {package}\n")

        env = os.environ.copy()
        env["NPM_CONFIG_PREFIX"] = target_dir
        env["PATH"] = os.path.join(target_dir, "bin") + os.pathsep + env.get("PATH", "")

        os.makedirs(target_dir, exist_ok=True)

        # npm install <package>
        cmd = ["npm", "install", package, "--prefix", target_dir]
        returncode, stdout, stderr = self._run_command(
            cmd,
            cwd=target_dir,
            env=env,
            timeout=300,
        )

        self._write_log(tool_name, stdout, stderr)

        if returncode != 0:
            msg = f"npm install failed for '{tool_name}' (exit {returncode})"
            errors.append(msg)
            if stderr:
                errors.append(stderr.strip())
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=msg,
                install_path=target_dir,
                errors=errors,
            )

        return InstallResult(
            success=True,
            tool_name=tool_name,
            message=f"npm install succeeded for '{tool_name}'",
            install_path=target_dir,
        )

    def _install_pip(self, tool: MCPTool, target_dir: str) -> InstallResult:
        """Install an MCP tool via pip."""
        tool_name = tool.name
        package = getattr(tool, "pip_package", None) or tool_name
        editable = getattr(tool, "pip_editable", False)
        errors: List[str] = []

        self._write_log(tool_name, f"[pip] Installing package: {package}\n")

        env = os.environ.copy()
        env["PIP_TARGET"] = target_dir
        env["PYTHONPATH"] = target_dir + os.pathsep + env.get("PYTHONPATH", "")

        os.makedirs(target_dir, exist_ok=True)

        if editable:
            cmd = ["pip", "install", "-e", package, "--target", target_dir]
        else:
            cmd = ["pip", "install", package, "--target", target_dir]

        returncode, stdout, stderr = self._run_command(
            cmd,
            env=env,
            timeout=300,
        )

        self._write_log(tool_name, stdout, stderr)

        if returncode != 0:
            msg = f"pip install failed for '{tool_name}' (exit {returncode})"
            errors.append(msg)
            if stderr:
                errors.append(stderr.strip())
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=msg,
                install_path=target_dir,
                errors=errors,
            )

        return InstallResult(
            success=True,
            tool_name=tool_name,
            message=f"pip install succeeded for '{tool_name}'",
            install_path=target_dir,
        )

    def _install_docker(self, tool: MCPTool, target_dir: str) -> InstallResult:
        """Install an MCP tool via Docker (pull image + generate run script)."""
        tool_name = tool.name
        image = getattr(tool, "docker_image", None) or tool_name
        errors: List[str] = []

        self._write_log(tool_name, f"[docker] Pulling image: {image}\n")

        os.makedirs(target_dir, exist_ok=True)

        # Pull image
        cmd = ["docker", "pull", image]
        returncode, stdout, stderr = self._run_command(
            cmd,
            timeout=600,
        )
        self._write_log(tool_name, stdout, stderr)

        if returncode != 0:
            msg = f"docker pull failed for '{tool_name}' (exit {returncode})"
            errors.append(msg)
            if stderr:
                errors.append(stderr.strip())
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=msg,
                install_path=target_dir,
                errors=errors,
            )

        # Write a helper run script so the tool can be started later
        run_script = os.path.join(target_dir, "run.sh")
        try:
            with open(run_script, "w", encoding="utf-8") as fh:
                fh.write(f"#!/bin/sh\n")
                fh.write(f'docker run --rm -it "{image}" "$@"\n')
            os.chmod(run_script, 0o755)
        except Exception as exc:  # pragma: no cover
            msg = f"Failed to write docker run script for '{tool_name}': {exc}"
            errors.append(msg)
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=msg,
                install_path=target_dir,
                errors=errors,
            )

        return InstallResult(
            success=True,
            tool_name=tool_name,
            message=f"Docker image '{image}' pulled for '{tool_name}'",
            install_path=target_dir,
        )

    def _install_git(self, tool: MCPTool, target_dir: str) -> InstallResult:
        """Install an MCP tool by cloning a Git repository."""
        tool_name = tool.name
        repo_url = getattr(tool, "git_repo", None)
        if not repo_url:
            msg = f"No git_repo defined for '{tool_name}'"
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=msg,
                errors=[msg],
            )

        errors: List[str] = []
        self._write_log(tool_name, f"[git] Cloning repo: {repo_url}\n")

        # Clone into target_dir
        cmd = ["git", "clone", "--depth", "1", repo_url, target_dir]
        returncode, stdout, stderr = self._run_command(
            cmd,
            timeout=300,
        )
        self._write_log(tool_name, stdout, stderr)

        if returncode != 0:
            msg = f"git clone failed for '{tool_name}' (exit {returncode})"
            errors.append(msg)
            if stderr:
                errors.append(stderr.strip())
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=msg,
                install_path=target_dir,
                errors=errors,
            )

        # Run optional post-clone install command
        install_cmd = getattr(tool, "install_command", None)
        if install_cmd:
            self._write_log(tool_name, f"[git] Running install command: {install_cmd}\n")
            returncode, stdout, stderr = self._run_command(
                install_cmd.split(),
                cwd=target_dir,
                timeout=300,
            )
            self._write_log(tool_name, stdout, stderr)
            if returncode != 0:
                msg = (
                    f"Post-clone install command failed for '{tool_name}' "
                    f"(exit {returncode})"
                )
                errors.append(msg)
                if stderr:
                    errors.append(stderr.strip())
                return InstallResult(
                    success=False,
                    tool_name=tool_name,
                    message=msg,
                    install_path=target_dir,
                    errors=errors,
                )

        return InstallResult(
            success=True,
            tool_name=tool_name,
            message=f"git clone succeeded for '{tool_name}'",
            install_path=target_dir,
        )

    def _install_binary(self, tool: MCPTool, target_dir: str) -> InstallResult:
        """Download and install a binary from a URL."""
        tool_name = tool.name
        binary_url = getattr(tool, "binary_url", None)
        if not binary_url:
            msg = f"No binary_url defined for '{tool_name}'"
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=msg,
                errors=[msg],
            )

        errors: List[str] = []
        self._write_log(tool_name, f"[binary] Downloading from: {binary_url}\n")

        os.makedirs(target_dir, exist_ok=True)

        # Determine filename
        parsed = urlparse(binary_url)
        filename = os.path.basename(parsed.path) or tool_name
        dest_path = os.path.join(target_dir, filename)

        # Download with urllib (no extra deps)
        try:
            req = urllib.request.Request(
                binary_url,
                headers={"User-Agent": "mcp-hub-installer/1.0"},
            )
            with urllib.request.urlopen(req, timeout=300) as response:
                with open(dest_path, "wb") as out_file:
                    out_file.write(response.read())
        except Exception as exc:  # pragma: no cover
            msg = f"Failed to download binary for '{tool_name}': {exc}"
            errors.append(msg)
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=msg,
                install_path=target_dir,
                errors=errors,
            )

        # Make executable on Unix-like systems
        if platform.system() != "Windows":
            try:
                os.chmod(dest_path, 0o755)
            except Exception as exc:  # pragma: no cover
                logger.warning("Could not chmod binary for %s: %s", tool_name, exc)

        # Optionally handle archives (zip / tar.gz)
        if filename.endswith(".zip"):
            return self._extract_archive(tool, target_dir, dest_path, "zip")
        if filename.endswith((".tar.gz", ".tgz")):
            return self._extract_archive(tool, target_dir, dest_path, "tar.gz")

        return InstallResult(
            success=True,
            tool_name=tool_name,
            message=f"Binary downloaded for '{tool_name}' to {dest_path}",
            install_path=target_dir,
        )

    # ------------------------------------------------------------------
    # Verification helpers
    # ------------------------------------------------------------------

    def _verify_npm_installation(self, tool_name: str, install_path: str) -> bool:
        """Verify npm installation by checking node_modules exists."""
        node_modules = os.path.join(install_path, "node_modules")
        return os.path.isdir(node_modules) and len(os.listdir(node_modules)) > 0

    def _verify_pip_installation(self, tool_name: str, install_path: str) -> bool:
        """Verify pip installation by checking the target directory is non-empty."""
        return os.path.isdir(install_path) and len(os.listdir(install_path)) > 0

    def _verify_docker_installation(self, tool_name: str, install_path: str) -> bool:
        """Verify docker installation by checking run script exists."""
        return os.path.exists(os.path.join(install_path, "run.sh"))

    def _verify_git_installation(self, tool_name: str, install_path: str) -> bool:
        """Verify git installation by checking .git directory exists."""
        git_dir = os.path.join(install_path, ".git")
        return os.path.isdir(git_dir)

    def _verify_binary_installation(self, tool_name: str, install_path: str) -> bool:
        """Verify binary installation by ensuring at least one executable exists."""
        for _, _, files in os.walk(install_path):
            for f in files:
                path = os.path.join(install_path, f)
                if os.access(path, os.X_OK):
                    return True
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_install_method(self, tool: MCPTool) -> str:
        """Auto-detect the best install method for a tool.

        Priority order:
        1. Explicitly declared method on the tool object.
        2. npm if npm_package exists.
        3. pip if pip_package exists.
        4. docker if docker_image exists.
        5. git if git_repo exists.
        6. binary if binary_url exists.
        7. Fall back to 'npm' ( safest default ).
        """
        declared = getattr(tool, "preferred_install_method", None)
        if declared and declared in INSTALL_TYPES:
            return declared

        if getattr(tool, "npm_package", None):
            return "npm"
        if getattr(tool, "pip_package", None):
            return "pip"
        if getattr(tool, "docker_image", None):
            return "docker"
        if getattr(tool, "git_repo", None):
            return "git"
        if getattr(tool, "binary_url", None):
            return "binary"

        return "npm"

    def _check_prerequisites(self, method: str) -> bool:
        """Check if the host has the required tools for *method*."""
        if method == "binary":
            # Binary only needs a working Python urllib
            return True

        cmd = self._PREREQ_COMMANDS.get(method)
        if cmd is None:
            return False

        returncode, _, _ = self._run_command(cmd, timeout=10)
        return returncode == 0

    def _run_command(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: int = 300,
    ) -> Tuple[int, str, str]:
        """Run a shell command and return (returncode, stdout, stderr).

        Parameters
        ----------
        cmd:
            Command and arguments as a list.
        cwd:
            Working directory for the subprocess.
        env:
            Optional environment dict.  If omitted, inherits the current env.
        timeout:
            Maximum seconds to wait for the command.

        Returns
        -------
        tuple
            (returncode, stdout_string, stderr_string)
        """
        logger.debug("Running command: %s in cwd=%s timeout=%s", cmd, cwd, timeout)
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return proc.returncode, proc.stdout or "", proc.stderr or ""
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode("utf-8", errors="replace") if exc.stdout else ""
            stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
            logger.error("Command timed out after %ss: %s", timeout, cmd)
            return -1, stdout, f"Command timed out after {timeout}s\n{stderr}"
        except FileNotFoundError:
            logger.error("Command not found: %s", cmd[0])
            return -1, "", f"Command not found: {cmd[0]}"
        except Exception as exc:  # pragma: no cover
            logger.error("Unexpected error running %s: %s", cmd, exc)
            return -1, "", str(exc)

    def _write_log(
        self,
        tool_name: str,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        """Append output to the per-tool install log."""
        log_path = self._log_path(tool_name)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(f"\n--- {timestamp} ---\n")
                if stdout:
                    fh.write("[stdout]\n")
                    fh.write(stdout)
                    fh.write("\n")
                if stderr:
                    fh.write("[stderr]\n")
                    fh.write(stderr)
                    fh.write("\n")
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to write log for %s: %s", tool_name, exc)

    def _log_path(self, tool_name: str) -> str:
        """Return the filesystem path for a tool's installation log."""
        return os.path.join(self.log_dir, f"{tool_name}.install.log")

    def _cleanup_on_failure(self, tool_name: str, target_dir: str) -> None:
        """Remove partially-installed artifacts on failure."""
        logger.info("Rolling back partial installation for '%s' at %s", tool_name, target_dir)
        try:
            if os.path.isdir(target_dir):
                shutil.rmtree(target_dir)
        except Exception as exc:  # pragma: no cover
            logger.error("Rollback failed for '%s': %s", tool_name, exc)

        try:
            self.registry.mark_uninstalled(tool_name)
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to clear registry for '%s': %s", tool_name, exc)

    def _extract_archive(
        self,
        tool: MCPTool,
        target_dir: str,
        archive_path: str,
        archive_type: str,
    ) -> InstallResult:
        """Extract a downloaded archive."""
        tool_name = tool.name
        errors: List[str] = []
        self._write_log(tool_name, f"[binary] Extracting {archive_type} archive: {archive_path}\n")

        try:
            if archive_type == "zip":
                import zipfile
                with zipfile.ZipFile(archive_path, "r") as zf:
                    zf.extractall(target_dir)
            elif archive_type in ("tar.gz", "tgz"):
                import tarfile
                with tarfile.open(archive_path, "r:gz") as tf:
                    tf.extractall(target_dir)
            # Remove archive after extraction
            os.remove(archive_path)
        except Exception as exc:  # pragma: no cover
            msg = f"Failed to extract archive for '{tool_name}': {exc}"
            errors.append(msg)
            return InstallResult(
                success=False,
                tool_name=tool_name,
                message=msg,
                install_path=target_dir,
                errors=errors,
            )

        return InstallResult(
            success=True,
            tool_name=tool_name,
            message=f"Archive extracted for '{tool_name}'",
            install_path=target_dir,
        )
