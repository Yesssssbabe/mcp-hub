"""MCP Hub utilities module."""

import functools
import os
import platform
import subprocess
import sys
import time
from typing import Any, Callable, List, Optional


class Logger:
    """Simple logger for MCP Hub."""

    LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

    def __init__(self, name: str = "mcp-hub", level: str = "INFO"):
        self.name = name
        self.level = self.LEVELS.get(level.upper(), 20)

    def _log(self, level: str, message: str) -> None:
        """Log a message."""
        if self.LEVELS.get(level, 0) >= self.level:
            print(f"[{level}] {self.name}: {message}")

    def debug(self, message: str) -> None:
        self._log("DEBUG", message)

    def info(self, message: str) -> None:
        self._log("INFO", message)

    def warning(self, message: str) -> None:
        self._log("WARNING", message)

    def error(self, message: str) -> None:
        self._log("ERROR", message)

    def critical(self, message: str) -> None:
        self._log("CRITICAL", message)


class ProgressBar:
    """Simple progress bar."""

    def __init__(self, total: int, width: int = 40, desc: str = ""):
        self.total = total
        self.width = width
        self.desc = desc
        self.current = 0

    def update(self, n: int = 1) -> None:
        """Update progress."""
        self.current += n
        self._display()

    def _display(self) -> None:
        """Display the progress bar."""
        if self.total == 0:
            return
        ratio = self.current / self.total
        filled = int(self.width * ratio)
        bar = "█" * filled + "░" * (self.width - filled)
        percent = ratio * 100
        desc_prefix = f"{self.desc}: " if self.desc else ""
        print(f"\r{desc_prefix}[{bar}] {percent:.1f}% ({self.current}/{self.total})", end="", flush=True)
        if self.current >= self.total:
            print()

    def close(self) -> None:
        """Close the progress bar."""
        if self.current < self.total:
            self.current = self.total
            self._display()


def get_platform() -> str:
    """Get the current platform."""
    return platform.system().lower()


def is_windows() -> bool:
    """Check if running on Windows."""
    return platform.system() == "Windows"


def is_macos() -> bool:
    """Check if running on macOS."""
    return platform.system() == "Darwin"


def is_linux() -> bool:
    """Check if running on Linux."""
    return platform.system() == "Linux"


def run_command(cmd: List[str], check: bool = True, timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """Run a shell command."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=check,
        timeout=timeout,
    )


def read_file(path: str) -> str:
    """Read text from a file."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path: str, content: str) -> None:
    """Write text to a file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def ensure_dir(path: str) -> None:
    """Ensure directory exists."""
    os.makedirs(path, exist_ok=True)


def compare_versions(v1: str, v2: str) -> int:
    """Compare two version strings. Returns -1, 0, or 1."""
    parts1 = [int(x) for x in v1.split(".")]
    parts2 = [int(x) for x in v2.split(".")]
    max_len = max(len(parts1), len(parts2))
    parts1.extend([0] * (max_len - len(parts1)))
    parts2.extend([0] * (max_len - len(parts2)))
    for a, b in zip(parts1, parts2):
        if a < b:
            return -1
        if a > b:
            return 1
    return 0


def format_bytes(size: int) -> str:
    """Format bytes to human readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def retry(max_retries: int = 3, delay: float = 1.0, exceptions: tuple = (Exception,)) -> Callable:
    """Decorator to retry a function on exception."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        time.sleep(delay * (attempt + 1))
            raise last_exception
        return wrapper
    return decorator


def timer(func: Callable) -> Callable:
    """Decorator to measure function execution time."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        print(f"{func.__name__} took {elapsed:.4f}s")
        return result
    return wrapper


def truncate_string(s: str, max_length: int, suffix: str = "...") -> str:
    """Truncate a string to a maximum length."""
    if len(s) <= max_length:
        return s
    return s[: max_length - len(suffix)] + suffix


def safe_json_loads(s: str) -> Optional[Any]:
    """Safely load JSON string, returning None on failure."""
    import json
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None
