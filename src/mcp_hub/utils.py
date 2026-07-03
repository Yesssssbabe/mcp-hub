"""MCP Hub utilities module."""

import functools
import json
import os
import pathlib
import subprocess
import sys
import time
from typing import Any, Callable, List, Literal, Optional, TextIO, TypeVar

from mcp_hub.constants import MCPHubError


class ExecutionError(MCPHubError):
    """Raised when a command execution fails."""


class FileOperationError(MCPHubError):
    """Raised when a file operation fails."""


class Logger:
    """Simple logger for MCP Hub.

    Supports standard logging levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.
    Output can be redirected by passing a file-like object to ``output``.

    Level mapping:
        - DEBUG    → 10
        - INFO     → 20
        - WARNING  → 30
        - ERROR    → 40
        - CRITICAL → 50
    """

    LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

    def __init__(
        self,
        name: str = "mcp-hub",
        level: str = "INFO",
        output: Optional[TextIO] = None,
    ):
        self.name = name
        self.level = self.LEVELS.get(level.upper(), 20)
        self.output = output

    def _log(
        self,
        level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        message: str,
    ) -> None:
        """Log a message if the level is sufficient."""
        if self.LEVELS.get(level, 0) >= self.level:
            print(f"[{level}] {self.name}: {message}", file=self.output or sys.stdout)

    def debug(self, message: str) -> None:
        """Log a DEBUG message."""
        self._log("DEBUG", message)

    def info(self, message: str) -> None:
        """Log an INFO message."""
        self._log("INFO", message)

    def warning(self, message: str) -> None:
        """Log a WARNING message."""
        self._log("WARNING", message)

    def error(self, message: str) -> None:
        """Log an ERROR message."""
        self._log("ERROR", message)

    def critical(self, message: str) -> None:
        """Log a CRITICAL message."""
        self._log("CRITICAL", message)


class ProgressBar:
    """Simple progress bar with optional output stream injection."""

    def __init__(
        self,
        total: int,
        width: int = 40,
        desc: str = "",
        output: Optional[TextIO] = None,
    ):
        self.total = total
        self.width = width
        self.desc = desc
        self.current = 0
        self.output = output or sys.stdout

    def update(self, n: int = 1) -> None:
        """Update progress by n steps."""
        self.current += n
        self._display()

    def _display(self) -> None:
        """Display the progress bar."""
        if self.total == 0:
            desc_prefix = f"{self.desc}: " if self.desc else ""
            print(
                f"\r{desc_prefix}Processing... ({self.current})",
                end="",
                flush=True,
                file=self.output,
            )
            return
        ratio = self.current / self.total
        filled = int(self.width * ratio)
        bar = "█" * filled + "░" * (self.width - filled)
        percent = ratio * 100
        desc_prefix = f"{self.desc}: " if self.desc else ""
        print(
            f"\r{desc_prefix}[{bar}] {percent:.1f}% ({self.current}/{self.total})",
            end="",
            flush=True,
            file=self.output,
        )
        if self.current >= self.total:
            print(file=self.output)

    def close(self) -> None:
        """Close the progress bar by setting it to completion."""
        if self.current < self.total:
            self.current = self.total
            self._display()


def _resolve_path(path: str) -> str:
    """Resolve and validate a path, rejecting any parent directory traversal.

    Raises ValueError if '..' is detected in the path components.
    """
    if ".." in pathlib.PurePath(path).parts:
        raise ValueError(f"Path traversal detected: {path}")
    return os.path.abspath(path)


def get_platform() -> str:
    """Get the current platform as a normalized OS identifier.

    Returns:
        One of "macos", "windows", or "linux". This aligns with
        ``config._get_current_os()``.
    """
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32" or os.name == "nt":
        return "windows"
    return "linux"


def is_windows() -> bool:
    """Check if running on Windows."""
    return get_platform() == "windows"


def is_macos() -> bool:
    """Check if running on macOS."""
    return get_platform() == "macos"


def is_linux() -> bool:
    """Check if running on Linux."""
    return get_platform() == "linux"


def run_command(
    cmd: List[str],
    check: bool = True,
    timeout: Optional[int] = 30,
) -> subprocess.CompletedProcess[str]:
    """Run a shell command with captured output.

    Args:
        cmd: Command and arguments as a list of strings.
        check: If True, raise ExecutionError on non-zero exit code.
        timeout: Timeout in seconds. Default 30. Set to None for no timeout
            (not recommended).

    Returns:
        A CompletedProcess instance with stdout/stderr as strings.

    Raises:
        ValueError: If timeout is not positive or None.
        ExecutionError: If the command is not found, times out, or returns
            a non-zero exit code (when check=True).
    """
    if timeout is not None and timeout <= 0:
        raise ValueError("timeout must be positive or None")
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        raise ExecutionError(
            f"Command failed: {' '.join(cmd)}",
            error_code="EXEC_CMD_FAILED",
            details={"cmd": cmd, "error": str(e)},
        ) from e


def read_file(path: str, max_size: int = 10 * 1024 * 1024) -> str:
    """Read text from a UTF-8 encoded file.

    Args:
        path: Path to the file to read.
        max_size: Maximum allowed file size in bytes (default 10MB).

    Returns:
        The file contents as a string.

    Raises:
        ValueError: If the path contains '..' or the file exceeds ``max_size``.
        FileOperationError: If the file is not found, permission is denied,
            or it is not valid UTF-8.
    """
    try:
        resolved = _resolve_path(path)
        if not os.path.exists(resolved):
            raise FileOperationError(
                f"File not found: {path}",
                error_code="FILE_NOT_FOUND",
                details={"path": path},
            )
        file_size = os.path.getsize(resolved)
        if file_size > max_size:
            raise ValueError(
                f"File size {file_size} exceeds max allowed {max_size}"
            )
        with open(resolved, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError as e:
        raise FileOperationError(
            f"File not found: {path}",
            error_code="FILE_NOT_FOUND",
            details={"path": path},
        ) from e
    except PermissionError as e:
        raise FileOperationError(
            f"Permission denied: {path}",
            error_code="FILE_PERMISSION_DENIED",
            details={"path": path},
        ) from e
    except UnicodeDecodeError as e:
        raise FileOperationError(
            f"File is not valid UTF-8: {path}",
            error_code="FILE_ENCODING_ERROR",
            details={"path": path},
        ) from e


def write_file(path: str, content: str, max_size: int = 10 * 1024 * 1024) -> None:
    """Write text to a file, creating parent directories if needed.

    Args:
        path: Path to the file to write.
        content: Text content to write.
        max_size: Maximum allowed content size in bytes (default 10MB).

    Raises:
        ValueError: If the path contains '..' or content exceeds ``max_size``.
        FileOperationError: If the file cannot be written due to permission
            or I/O errors.
    """
    if len(content) > max_size:
        raise ValueError(
            f"Content size {len(content)} exceeds max allowed {max_size}"
        )
    try:
        resolved = _resolve_path(path)
        parent = os.path.dirname(resolved)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)
    except PermissionError as e:
        raise FileOperationError(
            f"Permission denied writing file: {path}",
            error_code="FILE_WRITE_PERMISSION_DENIED",
            details={"path": path},
        ) from e
    except OSError as e:
        raise FileOperationError(
            f"Failed to write file: {path}",
            error_code="FILE_WRITE_ERROR",
            details={"path": path, "error": str(e)},
        ) from e


def ensure_dir(path: str) -> None:
    """Ensure directory exists, creating it and parents if necessary.

    Args:
        path: Directory path to ensure exists.
    """
    os.makedirs(path, exist_ok=True)


def compare_versions(v1: str, v2: str) -> int:
    """Compare two dot-separated version strings.

    Supports numeric version segments only (e.g., ``1.2.3``).
    Pre-release tags (e.g., ``-beta``) are not supported and will raise.

    Args:
        v1: First version string.
        v2: Second version string.

    Returns:
        -1 if v1 < v2, 0 if equal, 1 if v1 > v2.

    Raises:
        ValueError: If a version string is empty or contains non-numeric segments.
    """
    if not v1 or not v2:
        raise ValueError(
            f"Version strings must not be empty, got {v1!r} and {v2!r}"
        )
    try:
        parts1 = [int(x) for x in v1.split(".") if x]
        parts2 = [int(x) for x in v2.split(".") if x]
    except ValueError as e:
        raise ValueError(
            f"Version strings must contain only dot-separated integers, "
            f"got {v1!r} and {v2!r}"
        ) from e
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
    """Format bytes to a human-readable string.

    Args:
        size: Number of bytes (must be non-negative).

    Returns:
        Human-readable string like ``1.5 MB``.

    Raises:
        ValueError: If size is negative.
    """
    if size < 0:
        raise ValueError("size must be non-negative")
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def format_duration(seconds: float) -> str:
    """Format duration in seconds to a human-readable string.

    Args:
        seconds: Duration in seconds.

    Returns:
        Formatted string like ``45.0s``, ``2.5m``, or ``1.2h``.
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


T = TypeVar("T")


def retry(
    max_retries: int = 3,
    delay: float = 1.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    max_total_timeout: Optional[float] = 300.0,
    max_delay: float = 60.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to retry a function on specified exceptions.

    The delay grows exponentially with a per-attempt cap:
    ``min(delay * (2 ** attempt), max_delay)``.

    Args:
        max_retries: Maximum number of retry attempts. 0 means execute once
            with no retries. Hard cap 10.
        delay: Base delay in seconds between retries.
        exceptions: Tuple of exception types to catch and retry on.
        max_total_timeout: Maximum cumulative time for all attempts. None disables.
        max_delay: Maximum delay per retry attempt (cap for exponential backoff).

    Returns:
        A decorator that wraps the target function.

    Raises:
        ValueError: If max_retries/delay/max_delay are out of bounds.
        TimeoutError: If retrying exceeds ``max_total_timeout``.
    """
    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    if max_retries > 10:
        raise ValueError("max_retries cannot exceed 10")
    if delay < 0:
        raise ValueError("delay must be non-negative")
    if max_delay < 0 or max_delay > 60:
        raise ValueError("max_delay must be between 0 and 60 seconds")

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            start_time = time.time()
            last_exception: Optional[BaseException] = None
            for attempt in range(max_retries + 1):
                if max_total_timeout is not None and (time.time() - start_time) > max_total_timeout:
                    raise TimeoutError(
                        f"Retry exceeded total timeout of {max_total_timeout}s"
                    )
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        current_delay = min(delay * (2 ** attempt), max_delay)
                        time.sleep(current_delay)
            raise last_exception
        return wrapper
    return decorator


def timer(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to measure and print function execution time.

    Args:
        func: The function to time.

    Returns:
        A wrapped function that prints elapsed time to the default output stream.
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        print(f"{func.__name__} took {elapsed:.4f}s")
        return result
    return wrapper


def truncate_string(s: str, max_length: int, suffix: str = "...") -> str:
    """Truncate a string to a maximum length.

    Args:
        s: The string to truncate.
        max_length: Maximum allowed length of the result.
        suffix: Suffix appended to truncated strings.

    Returns:
        Truncated string, or the original if already short enough.
    """
    if len(s) <= max_length:
        return s
    if max_length < len(suffix):
        return s[:max_length]
    return s[:max_length - len(suffix)] + suffix


def safe_json_loads(s: str, max_size: int = 10 * 1024 * 1024) -> Optional[Any]:
    """Safely parse a JSON string, returning None on failure.

    Args:
        s: A JSON-encoded string.
        max_size: Maximum allowed input size in bytes (default 10MB).

    Returns:
        The parsed Python object, or None if the string is not valid JSON
        or exceeds ``max_size``.
    """
    if not isinstance(s, str):
        return None
    if len(s) > max_size:
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError, RecursionError, ValueError):
        return None
