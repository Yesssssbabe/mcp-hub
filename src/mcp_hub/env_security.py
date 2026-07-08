"""Environment variable security — whitelist-based filtering for subprocess isolation."""

import os
from typing import Dict, List, Optional
import logging

logger = logging.getLogger("mcp_hub.env_security")


# ── 全局最小环境变量集（所有安装方式共享） ──
MINIMAL_ENV_VARS: List[str] = [
    # 绝对必要：找到可执行文件
    "PATH",
    # 操作系统基本标识
    "HOME",
    "USER",
    "USERNAME",
    "TMPDIR",
    "TEMP",
    "TMP",
    # 区域设置（某些构建脚本需要）
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    # 终端（用于彩色输出判断，不含敏感数据）
    "TERM",
    "NO_COLOR",
    # 平台特定
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "LOCALAPPDATA",
    "APPDATA",
    "PROGRAMFILES",
    "SYSTEMROOT",
]

# ── 安装方法特定的环境变量白名单 ──
METHOD_SPECIFIC_VARS: Dict[str, List[str]] = {
    "npm": [
        # npm 配置（不含认证 Token）
        "npm_config_",
        "NODE_NO_WARNINGS",
        # 禁止传递: NODE_OPTIONS（可通过 --require 注入代码）
        # 禁止传递: NPM_TOKEN, NODE_AUTH_TOKEN, etc.
    ],
    "pip": [
        # pip 配置（不含认证）
        "PIP_NO_CACHE_DIR",
        "PIP_DISABLE_PIP_VERSION_CHECK",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONUNBUFFERED",
        "PYTHONNOUSERSITE",
        # 虚拟环境（不含密钥）
        "VIRTUAL_ENV",
        # 禁止传递: PIP_EXTRA_INDEX_URL（可能含密码）
    ],
    "docker": [
        # Docker 上下文
        "DOCKER_HOST",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
        "DOCKER_BUILDKIT",
        # 禁止传递: DOCKER_CONFIG（可能含 auth）
    ],
    "git": [
        # Git 基本配置（不含凭证）
        "GIT_TERMINAL_PROMPT",
        "GIT_SSL_NO_VERIFY",
        # 禁止传递: GIT_ASKPASS, 含 token 的 URL
    ],
    "binary": [
        # 二进制下载尽量不需要额外环境
    ],
}

# ── 已知敏感环境变量黑名单（绝对禁止传递） ──
SENSITIVE_ENV_PATTERNS: List[str] = [
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "GITHUB_TOKEN",
    "GITHUB_API_TOKEN",
    "GITLAB_TOKEN",
    "DOCKER_TOKEN",
    "NPM_TOKEN",
    "NODE_AUTH_TOKEN",
    "PYPI_TOKEN",
    "TWINE_PASSWORD",
    "SLACK_BOT_TOKEN",
    "SENTRY_AUTH_TOKEN",
    "NOTION_API_KEY",
    "BRAVE_API_KEY",
    "FIRECRAWL_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "DATABASE_URL",
    "POSTGRES_PASSWORD",
    "MYSQL_PASSWORD",
    "REDIS_PASSWORD",
    "MONGO_URI",
    "SECRET_KEY",
    "PRIVATE_KEY",
    "PASSWORD",
    "PASSWD",
    "TOKEN",
    "API_KEY",
    "APIKEY",
    "CREDENTIAL",
    "AUTH",
    "BEARER",
    "PASSPHRASE",
]


class EnvWhitelistManager:
    """Manages environment variable whitelisting for subprocess isolation.

    Usage:
        manager = EnvWhitelistManager()
        safe_env = manager.build_safe_env(method="npm")
        subprocess.run(cmd, env=safe_env)
    """

    def __init__(
        self,
        extra_whitelist: Optional[List[str]] = None,
        extra_blacklist: Optional[List[str]] = None,
    ):
        self.extra_whitelist = set(extra_whitelist or [])
        self.extra_blacklist = set(extra_blacklist or [])
        self._audit_log: List[str] = []

    def build_safe_env(self, method: str) -> Dict[str, str]:
        """Build a safe environment dict for the given install method.

        Steps:
        1. Start with MINIMAL_ENV_VARS.
        2. Add method-specific vars (matching prefixes allowed).
        3. Add user-configured extra_whitelist.
        4. Remove any var matching SENSITIVE_ENV_PATTERNS or extra_blacklist.
        5. Log all decisions for audit.
        """
        allowed = set()

        # 1. 最小环境变量集
        for key in MINIMAL_ENV_VARS:
            allowed.add(key)

        # 2. 方法特定的白名单（支持前缀匹配）
        method_prefixes = METHOD_SPECIFIC_VARS.get(method, [])
        for key in os.environ:
            for prefix in method_prefixes:
                if key.startswith(prefix) or key == prefix:
                    allowed.add(key)

        # 3. 用户自定义扩展
        allowed |= self.extra_whitelist

        # 4. 过滤：只保留存在于当前 os.environ 中的变量
        safe_env = {}
        for key in allowed:
            if key in os.environ:
                safe_env[key] = os.environ[key]

        # 5. 应用黑名单（精确匹配 + 子串匹配）
        blacklist_patterns = set(SENSITIVE_ENV_PATTERNS) | self.extra_blacklist
        removed = []
        for key in list(safe_env.keys()):
            for pattern in blacklist_patterns:
                if pattern in key.upper():
                    removed.append(key)
                    del safe_env[key]
                    break

        # 6. 审计日志
        if removed:
            self._audit_log.append(
                f"[{method}] Removed sensitive env vars: {', '.join(removed)}"
            )
            logger.info("Removed sensitive env vars for method '%s': %s", method, removed)

        self._audit_log.append(
            f"[{method}] Safe env contains {len(safe_env)} vars: {sorted(safe_env.keys())}"
        )
        return safe_env

    def get_audit_log(self) -> List[str]:
        """Return the audit log of environment filtering decisions."""
        return self._audit_log.copy()

    @staticmethod
    def get_removed_vars_report() -> Dict[str, List[str]]:
        """Return a report of which sensitive vars were present in the original env."""
        report: Dict[str, List[str]] = {"present": [], "blocked": []}
        for key in os.environ:
            for pattern in SENSITIVE_ENV_PATTERNS:
                if pattern in key.upper():
                    report["present"].append(key)
                    report["blocked"].append(f"{key}={os.environ[key][:4]}****")
        return report
