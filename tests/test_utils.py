"""Tests for mcp_hub.utils module."""

import os
import subprocess
import time
from unittest.mock import MagicMock

import pytest

from mcp_hub.utils import (
    ExecutionError,
    Logger,
    ProgressBar,
    compare_versions,
    ensure_dir,
    format_bytes,
    format_duration,
    get_platform,
    is_linux,
    is_macos,
    is_windows,
    read_file,
    retry,
    run_command,
    safe_json_loads,
    timer,
    truncate_string,
    write_file,
)


class TestLogger:
    """Test Logger class."""

    def test_init_default(self):
        logger = Logger()
        assert logger.name == "mcp-hub"
        assert logger.level == 20

    def test_init_custom(self):
        logger = Logger(name="custom", level="DEBUG")
        assert logger.name == "custom"
        assert logger.level == 10

    def test_log_levels(self, capsys):
        logger = Logger(level="DEBUG")
        logger.debug("debug msg")
        logger.info("info msg")
        logger.warning("warning msg")
        logger.error("error msg")
        logger.critical("critical msg")
        captured = capsys.readouterr()
        assert "DEBUG" in captured.out
        assert "INFO" in captured.out
        assert "WARNING" in captured.out
        assert "ERROR" in captured.out
        assert "CRITICAL" in captured.out

    def test_log_level_filtering(self, capsys):
        logger = Logger(level="ERROR")
        logger.info("should not appear")
        logger.error("should appear")
        captured = capsys.readouterr()
        assert "should not appear" not in captured.out
        assert "should appear" in captured.out

    def test_log_output_format(self, capsys):
        logger = Logger(name="test", level="INFO")
        logger.info("hello")
        captured = capsys.readouterr()
        assert "[INFO] test: hello" in captured.out


class TestProgressBar:
    """Test ProgressBar class."""

    def test_init(self):
        pb = ProgressBar(total=100, width=20, desc="Test")
        assert pb.total == 100
        assert pb.width == 20
        assert pb.desc == "Test"
        assert pb.current == 0

    def test_update(self, capsys):
        pb = ProgressBar(total=10, width=10)
        pb.update(5)
        captured = capsys.readouterr()
        assert "50.0%" in captured.out

    def test_update_complete(self, capsys):
        pb = ProgressBar(total=5)
        pb.update(5)
        captured = capsys.readouterr()
        assert "100.0%" in captured.out

    def test_close(self, capsys):
        pb = ProgressBar(total=10)
        pb.update(5)
        pb.close()
        captured = capsys.readouterr()
        assert "100.0%" in captured.out

    def test_zero_total(self, capsys):
        pb = ProgressBar(total=0)
        pb.update(1)
        captured = capsys.readouterr()
        assert "Processing... (1)" in captured.out


class TestPlatformDetection:
    """Test platform detection functions."""

    def test_get_platform(self, monkeypatch):
        monkeypatch.setattr("mcp_hub.utils.sys.platform", "linux")
        monkeypatch.setattr("mcp_hub.utils.os.name", "posix")
        assert get_platform() == "linux"
        monkeypatch.setattr("mcp_hub.utils.sys.platform", "darwin")
        assert get_platform() == "macos"
        monkeypatch.setattr("mcp_hub.utils.sys.platform", "win32")
        monkeypatch.setattr("mcp_hub.utils.os.name", "nt")
        assert get_platform() == "windows"

    def test_is_windows(self, monkeypatch):
        monkeypatch.setattr("mcp_hub.utils.sys.platform", "win32")
        monkeypatch.setattr("mcp_hub.utils.os.name", "nt")
        assert is_windows() is True
        monkeypatch.setattr("mcp_hub.utils.sys.platform", "linux")
        monkeypatch.setattr("mcp_hub.utils.os.name", "posix")
        assert is_windows() is False

    def test_is_macos(self, monkeypatch):
        monkeypatch.setattr("mcp_hub.utils.sys.platform", "darwin")
        assert is_macos() is True

    def test_is_linux(self, monkeypatch):
        monkeypatch.setattr("mcp_hub.utils.sys.platform", "linux")
        monkeypatch.setattr("mcp_hub.utils.os.name", "posix")
        assert is_linux() is True


class TestRunCommand:
    """Test run_command function."""

    def test_run_command_success(self, monkeypatch):
        mock = MagicMock(returncode=0, stdout="out", stderr="err")
        monkeypatch.setattr("mcp_hub.utils.subprocess.run", lambda *a, **k: mock)
        result = run_command(["echo", "hello"])
        assert result.returncode == 0

    def test_run_command_failure(self, monkeypatch):
        def _raise(*a, **k):
            raise subprocess.CalledProcessError(1, ["false"], stderr="error")
        monkeypatch.setattr("mcp_hub.utils.subprocess.run", _raise)
        with pytest.raises(ExecutionError):
            run_command(["false"])

    def test_run_command_no_check(self, monkeypatch):
        mock = MagicMock(returncode=1, stdout="", stderr="error")
        monkeypatch.setattr("mcp_hub.utils.subprocess.run", lambda *a, **k: mock)
        result = run_command(["false"], check=False)
        assert result.returncode == 1


class TestFileOperations:
    """Test file read/write functions."""

    def test_read_file(self, tmp_path):
        path = tmp_path / "test.txt"
        path.write_text("hello world", encoding="utf-8")
        content = read_file(str(path))
        assert content == "hello world"

    def test_write_file(self, tmp_path):
        path = tmp_path / "output.txt"
        write_file(str(path), "test content")
        assert path.read_text(encoding="utf-8") == "test content"

    def test_read_write_roundtrip(self, tmp_path):
        path = tmp_path / "roundtrip.txt"
        original = "roundtrip content\nwith newline"
        write_file(str(path), original)
        assert read_file(str(path)) == original

    def test_ensure_dir(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        ensure_dir(str(nested))
        assert nested.exists()


class TestCompareVersions:
    """Test compare_versions function."""

    @pytest.mark.parametrize(
        "v1,v2,expected",
        [
            ("1.0.0", "1.0.0", 0),
            ("1.0.0", "2.0.0", -1),
            ("2.0.0", "1.0.0", 1),
            ("1.0.0", "1.1.0", -1),
            ("1.1.0", "1.0.0", 1),
            ("1.0.0", "1.0.1", -1),
            ("1.0", "1.0.0", 0),
            ("1", "1.0.0", 0),
            ("2.0", "1.9.9", 1),
            ("0.9.9", "1.0.0", -1),
        ],
    )
    def test_version_comparison(self, v1, v2, expected):
        assert compare_versions(v1, v2) == expected


class TestFormatBytes:
    """Test format_bytes function."""

    @pytest.mark.parametrize(
        "size,expected",
        [
            (0, "0.0 B"),
            (512, "512.0 B"),
            (1024, "1.0 KB"),
            (1024 * 1024, "1.0 MB"),
            (1024 * 1024 * 1024, "1.0 GB"),
            (1024 * 1024 * 1024 * 1024, "1.0 TB"),
        ],
    )
    def test_format_bytes(self, size, expected):
        assert format_bytes(size) == expected


class TestFormatDuration:
    """Test format_duration function."""

    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (0, "0.0s"),
            (30, "30.0s"),
            (60, "1.0m"),
            (120, "2.0m"),
            (3600, "1.0h"),
            (7200, "2.0h"),
        ],
    )
    def test_format_duration(self, seconds, expected):
        assert format_duration(seconds) == expected


class TestRetryDecorator:
    """Test retry decorator."""

    def test_retry_success(self):
        @retry(max_retries=2, delay=0.1)
        def func():
            return "success"
        assert func() == "success"

    def test_retry_eventual_success(self):
        calls = []
        @retry(max_retries=3, delay=0.01)
        def func():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("fail")
            return "success"
        assert func() == "success"
        assert len(calls) == 3

    def test_retry_exhausted(self):
        @retry(max_retries=2, delay=0.01)
        def func():
            raise RuntimeError("always fails")
        with pytest.raises(RuntimeError, match="always fails"):
            func()

    def test_retry_specific_exception(self):
        @retry(max_retries=2, delay=0.01, exceptions=(ValueError,))
        def func():
            raise TypeError("wrong type")
        with pytest.raises(TypeError):
            func()


class TestTimerDecorator:
    """Test timer decorator."""

    def test_timer(self, capsys):
        @timer
        def func():
            return 42
        result = func()
        assert result == 42
        captured = capsys.readouterr()
        assert "func took" in captured.out


class TestTruncateString:
    """Test truncate_string function."""

    def test_short_string(self):
        assert truncate_string("hello", 10) == "hello"

    def test_long_string(self):
        result = truncate_string("hello world", 8)
        assert "..." in result

    def test_custom_suffix(self):
        result = truncate_string("abcdef", 5, suffix="..")
        assert result.endswith("..")


class TestSafeJsonLoads:
    """Test safe_json_loads function."""

    def test_valid_json(self):
        assert safe_json_loads('{"key": "value"}') == {"key": "value"}

    def test_invalid_json(self):
        assert safe_json_loads("not json") is None

    def test_empty_string(self):
        assert safe_json_loads("") is None

    def test_none_input(self):
        assert safe_json_loads(None) is None
