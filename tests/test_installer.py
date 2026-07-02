"""Tests for mcp_hub.installer module."""

import os
from unittest.mock import MagicMock, patch

import pytest

from mcp_hub.installer import InstallResult, Installer
from mcp_hub.registry import MCPTool, Registry


def make_tool(**kwargs):
    defaults = {
        "name": "test-tool",
        "display_name": "Test Tool",
        "description": "desc",
        "install_type": "npm",
        "install_command": "npx test-tool",
        "author": "a",
        "repository": "https://github.com/a/b",
    }
    defaults.update(kwargs)
    return MCPTool(**defaults)


class TestInstallResult:
    """Test InstallResult dataclass."""

    def test_create_success(self):
        result = InstallResult(
            success=True,
            tool_name="test",
            message="ok",
            install_path="/path",
            install_method="npm",
        )
        assert result.success is True
        assert result.install_method == "npm"
        assert result.errors == []

    def test_create_failure(self):
        result = InstallResult(
            success=False,
            tool_name="test",
            message="fail",
            errors=["err1"],
        )
        assert result.success is False
        assert result.errors == ["err1"]


class TestInstallerInit:
    """Test Installer initialization."""

    def test_init_default(self):
        installer = Installer()
        assert installer.install_dir.endswith(".mcp-hub/installed")

    def test_init_custom_install_dir(self, tmp_path):
        installer = Installer(install_dir=str(tmp_path))
        assert installer.install_dir == str(tmp_path)

    def test_init_creates_directories(self, tmp_path):
        custom = tmp_path / "custom_install"
        Installer(install_dir=str(custom))
        assert custom.exists()


class TestInstallerInstall:
    """Test Installer.install method."""

    def test_install_tool_not_found(self, tmp_path):
        installer = Installer(install_dir=str(tmp_path))
        result = installer.install("nonexistent-tool")
        assert result.success is False
        assert "not found" in result.message.lower()

    def test_install_unsupported_method(self, tmp_path, monkeypatch):
        registry = Registry(registry_path=str(tmp_path / "registry.json"))
        registry.add(make_tool(name="bad-method"))
        installer = Installer(install_dir=str(tmp_path))
        installer.registry = registry
        monkeypatch.setattr(installer, "_detect_install_method", lambda t: "unsupported")
        result = installer.install("bad-method")
        assert result.success is False
        assert "Unsupported" in result.message

    def test_install_prerequisites_fail(self, tmp_path, monkeypatch):
        registry = Registry(registry_path=str(tmp_path / "registry.json"))
        registry.add(make_tool(name="preq-fail"))
        installer = Installer(install_dir=str(tmp_path))
        installer.registry = registry
        monkeypatch.setattr(installer, "_check_prerequisites", lambda m: False)
        result = installer.install("preq-fail")
        assert result.success is False
        assert "Prerequisites" in result.message

    def test_install_npm_mock(self, tmp_path, monkeypatch):
        registry = Registry(registry_path=str(tmp_path / "registry.json"))
        registry.add(make_tool(name="npm-tool", install_type="npm"))
        installer = Installer(install_dir=str(tmp_path))
        installer.registry = registry
        monkeypatch.setattr(
            installer, "_run_command",
            lambda cmd, cwd=None, env=None, timeout=300: (0, "ok", "")
        )
        monkeypatch.setattr(installer, "_verify_npm_installation", lambda n, p: True)
        result = installer.install("npm-tool")
        assert result.success is True

    def test_install_pip_mock(self, tmp_path, monkeypatch):
        registry = Registry(registry_path=str(tmp_path / "registry.json"))
        registry.add(make_tool(name="pip-tool", install_type="pip", install_command="pip install x"))
        installer = Installer(install_dir=str(tmp_path))
        installer.registry = registry
        monkeypatch.setattr(
            installer, "_run_command",
            lambda cmd, cwd=None, env=None, timeout=300: (0, "ok", "")
        )
        monkeypatch.setattr(installer, "_verify_pip_installation", lambda n, p: True)
        result = installer.install("pip-tool")
        assert result.success is True

    def test_install_docker_mock(self, tmp_path, monkeypatch):
        registry = Registry(registry_path=str(tmp_path / "registry.json"))
        registry.add(make_tool(name="docker-tool", install_type="docker", install_command="docker pull x"))
        installer = Installer(install_dir=str(tmp_path))
        installer.registry = registry
        monkeypatch.setattr(
            installer, "_run_command",
            lambda cmd, cwd=None, env=None, timeout=300: (0, "ok", "")
        )
        monkeypatch.setattr(installer, "_verify_docker_installation", lambda n, p: True)
        result = installer.install("docker-tool")
        assert result.success is True

    def test_install_command_failure(self, tmp_path, monkeypatch):
        registry = Registry(registry_path=str(tmp_path / "registry.json"))
        registry.add(make_tool(name="fail"))
        installer = Installer(install_dir=str(tmp_path))
        installer.registry = registry
        monkeypatch.setattr(
            installer, "_run_command",
            lambda cmd, cwd=None, env=None, timeout=300: (1, "", "error")
        )
        result = installer.install("fail")
        assert result.success is False

    def test_install_verify_fails(self, tmp_path, monkeypatch):
        registry = Registry(registry_path=str(tmp_path / "registry.json"))
        registry.add(make_tool(name="verify-fail"))
        installer = Installer(install_dir=str(tmp_path))
        installer.registry = registry
        monkeypatch.setattr(
            installer, "_run_command",
            lambda cmd, cwd=None, env=None, timeout=300: (0, "ok", "")
        )
        monkeypatch.setattr(installer, "verify_installation", lambda n: False)
        result = installer.install("verify-fail")
        assert result.success is False


class TestInstallerUninstall:
    """Test Installer.uninstall method."""

    def test_uninstall_not_installed(self, tmp_path):
        installer = Installer(install_dir=str(tmp_path))
        result = installer.uninstall("not-there")
        assert result.success is False
        assert "not installed" in result.message.lower()

    def test_uninstall_success(self, tmp_path, monkeypatch):
        registry = Registry(registry_path=str(tmp_path / "registry.json"))
        registry.add(make_tool(name="gone", is_installed=True, install_path=str(tmp_path / "gone")))
        installer = Installer(install_dir=str(tmp_path))
        installer.registry = registry
        (tmp_path / "gone").mkdir()
        result = installer.uninstall("gone")
        assert result.success is True
        assert "uninstalled" in result.message.lower()

    def test_uninstall_with_purge(self, tmp_path, monkeypatch):
        registry = Registry(registry_path=str(tmp_path / "registry.json"))
        registry.add(make_tool(name="purge-me", is_installed=True, install_path=str(tmp_path / "purge-me")))
        installer = Installer(install_dir=str(tmp_path))
        installer.registry = registry
        (tmp_path / "purge-me").mkdir()
        # Create a log file
        log_path = os.path.join(installer.log_dir, "purge-me.install.log")
        os.makedirs(installer.log_dir, exist_ok=True)
        with open(log_path, "w") as f:
            f.write("log")
        result = installer.uninstall("purge-me", purge=True)
        assert result.success is True
        assert not os.path.exists(log_path)


class TestInstallerIsInstalled:
    """Test Installer.is_installed method."""

    def test_is_installed_true(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "registry.json"))
        registry.add(make_tool(name="yes", is_installed=True))
        installer = Installer(install_dir=str(tmp_path))
        installer.registry = registry
        assert installer.is_installed("yes") is True

    def test_is_installed_false(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "registry.json"))
        registry.add(make_tool(name="no", is_installed=False))
        installer = Installer(install_dir=str(tmp_path))
        installer.registry = registry
        assert installer.is_installed("no") is False


class TestInstallerGetInstallPath:
    """Test Installer.get_install_path method."""

    def test_get_install_path(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "registry.json"))
        registry.add(make_tool(name="path", is_installed=True, install_path="/some/path"))
        installer = Installer(install_dir=str(tmp_path))
        installer.registry = registry
        assert installer.get_install_path("path") == "/some/path"

    def test_get_install_path_none(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "registry.json"))
        registry.add(make_tool(name="no-path"))
        installer = Installer(install_dir=str(tmp_path))
        installer.registry = registry
        assert installer.get_install_path("no-path") is None


class TestInstallerListInstalled:
    """Test Installer.list_installed method."""

    def test_list_installed(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "registry.json"))
        registry.add(make_tool(name="a", is_installed=True))
        registry.add(make_tool(name="b", is_installed=False))
        registry.add(make_tool(name="c", is_installed=True))
        installer = Installer(install_dir=str(tmp_path))
        installer.registry = registry
        installed = installer.list_installed()
        assert sorted(installed) == ["a", "c"]

    def test_list_installed_empty(self, tmp_path):
        installer = Installer(install_dir=str(tmp_path))
        assert installer.list_installed() == []


class TestInstallerUpdate:
    """Test Installer.update method."""

    def test_update_not_installed(self, tmp_path):
        installer = Installer(install_dir=str(tmp_path))
        result = installer.update("missing")
        assert result.success is False
        assert "not installed" in result.message.lower()

    def test_update_success(self, tmp_path, monkeypatch):
        registry = Registry(registry_path=str(tmp_path / "registry.json"))
        registry.add(make_tool(name="upd", is_installed=True, install_path=str(tmp_path / "upd")))
        installer = Installer(install_dir=str(tmp_path))
        installer.registry = registry
        (tmp_path / "upd").mkdir()
        monkeypatch.setattr(
            installer, "install",
            lambda name, method=None: InstallResult(success=True, tool_name=name, message="updated")
        )
        result = installer.update("upd")
        assert result.success is True


class TestInstallerVerifyInstallation:
    """Test Installer.verify_installation method."""

    def test_verify_not_installed(self, tmp_path):
        installer = Installer(install_dir=str(tmp_path))
        assert installer.verify_installation("missing") is False

    def test_verify_directory_missing(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "registry.json"))
        registry.add(make_tool(name="no-dir", is_installed=True, install_path="/nonexistent"))
        installer = Installer(install_dir=str(tmp_path))
        installer.registry = registry
        assert installer.verify_installation("no-dir") is False

    def test_verify_npm(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "registry.json"))
        registry.add(make_tool(name="npm-verify", is_installed=True, install_type="npm", install_path=str(tmp_path / "npm-verify")))
        installer = Installer(install_dir=str(tmp_path))
        installer.registry = registry
        (tmp_path / "npm-verify").mkdir()
        (tmp_path / "npm-verify" / "node_modules").mkdir()
        assert installer.verify_installation("npm-verify") is True


class TestInstallerDetectMethod:
    """Test _detect_install_method."""

    def test_detect_npm(self, tmp_path):
        installer = Installer(install_dir=str(tmp_path))
        tool = make_tool()
        assert installer._detect_install_method(tool) == "npm"

    def test_detect_pip(self, tmp_path):
        installer = Installer(install_dir=str(tmp_path))
        tool = make_tool(pip_package="x")
        assert installer._detect_install_method(tool) == "pip"

    def test_detect_docker(self, tmp_path):
        installer = Installer(install_dir=str(tmp_path))
        tool = make_tool(docker_image="x")
        assert installer._detect_install_method(tool) == "docker"

    def test_detect_git(self, tmp_path):
        installer = Installer(install_dir=str(tmp_path))
        tool = make_tool(git_repo="https://github.com/x/y")
        assert installer._detect_install_method(tool) == "git"

    def test_detect_binary(self, tmp_path):
        installer = Installer(install_dir=str(tmp_path))
        tool = make_tool(binary_url="https://example.com/bin")
        assert installer._detect_install_method(tool) == "binary"

    def test_detect_preferred(self, tmp_path):
        installer = Installer(install_dir=str(tmp_path))
        tool = make_tool(preferred_install_method="pip")
        assert installer._detect_install_method(tool) == "pip"


class TestInstallerCheckPrerequisites:
    """Test _check_prerequisites."""

    def test_check_binary(self, tmp_path):
        installer = Installer(install_dir=str(tmp_path))
        assert installer._check_prerequisites("binary") is True

    def test_check_missing(self, tmp_path, monkeypatch):
        installer = Installer(install_dir=str(tmp_path))
        monkeypatch.setattr(installer, "_run_command", lambda cmd, **kw: (-1, "", "not found"))
        assert installer._check_prerequisites("npm") is False


class TestInstallerRunCommand:
    """Test _run_command."""

    def test_run_command_success(self, tmp_path, monkeypatch):
        installer = Installer(install_dir=str(tmp_path))
        mock = MagicMock(returncode=0, stdout="out", stderr="err")
        monkeypatch.setattr("mcp_hub.installer.subprocess.run", lambda *a, **k: mock)
        rc, out, err = installer._run_command(["echo", "hi"])
        assert rc == 0
        assert out == "out"

    def test_run_command_timeout(self, tmp_path, monkeypatch):
        installer = Installer(install_dir=str(tmp_path))
        import subprocess
        def raise_timeout(*a, **k):
            raise subprocess.TimeoutExpired(cmd=["sleep"], timeout=1)
        monkeypatch.setattr("mcp_hub.installer.subprocess.run", raise_timeout)
        rc, out, err = installer._run_command(["sleep", "10"])
        assert rc == -1

    def test_run_command_not_found(self, tmp_path, monkeypatch):
        installer = Installer(install_dir=str(tmp_path))
        import subprocess
        def raise_not_found(*a, **k):
            raise FileNotFoundError("not found")
        monkeypatch.setattr("mcp_hub.installer.subprocess.run", raise_not_found)
        rc, out, err = installer._run_command(["nonexistent"])
        assert rc == -1


class TestInstallerLog:
    """Test log writing."""

    def test_write_log(self, tmp_path):
        installer = Installer(install_dir=str(tmp_path))
        installer._write_log("test-tool", stdout="output", stderr="error")
        log_path = installer._log_path("test-tool")
        assert os.path.exists(log_path)
        content = open(log_path).read()
        assert "output" in content
        assert "error" in content

    def test_get_install_log(self, tmp_path):
        installer = Installer(install_dir=str(tmp_path))
        installer._write_log("test-tool", stdout="hello")
        log = installer.get_install_log("test-tool")
        assert "hello" in log

    def test_get_install_log_missing(self, tmp_path):
        installer = Installer(install_dir=str(tmp_path))
        assert installer.get_install_log("missing") is None
