"""Secure secret management for MCP Hub.

Provides a unified interface to OS keychain services:
- macOS: Keychain (via keyring library)
- Windows: Credential Manager (via keyring library)
- Linux: Secret Service / kwallet (via keyring library)

All secrets are stored in the OS keychain, never in config files.
"""

import os
import sys
from typing import Dict, Optional, List
import logging

try:
    import keyring
    from keyring.errors import KeyringError, PasswordDeleteError
    _HAS_KEYRING = True
except ImportError:
    _HAS_KEYRING = False

logger = logging.getLogger("mcp_hub.secrets")

KEYRING_SERVICE_NAME = "mcp-hub"
ENV_REF_PREFIX = "${"  # 配置文件中的引用标记: ${GITHUB_TOKEN}
ENV_REF_SUFFIX = "}"


class SecretManager:
    """Manages API keys and tokens using OS-native keychain services.

    Usage:
        manager = SecretManager()
        manager.set_secret("GITHUB_TOKEN", "ghp_xxx")
        token = manager.get_secret("GITHUB_TOKEN")  # 从 OS keychain 获取
    """

    def __init__(self):
        self._fallback_store: Dict[str, str] = {}  # keyring 不可用时降级到内存
        self._keyring_available = _HAS_KEYRING and keyring.get_keyring().name != ""
        if not self._keyring_available:
            logger.warning(
                "OS keychain not available. Secrets will be stored in memory only. "
                "Install 'keyring' for persistent secure storage: pip install keyring"
            )

    def _keyring_key(self, name: str) -> str:
        """Return the keyring key for a secret name."""
        return f"mcp-hub:{name}"

    def set_secret(self, name: str, value: str) -> None:
        """Store a secret securely."""
        if self._keyring_available:
            try:
                keyring.set_password(KEYRING_SERVICE_NAME, self._keyring_key(name), value)
                logger.info("Secret '%s' stored in OS keychain", name)
            except KeyringError as exc:
                logger.error("Failed to store secret '%s' in keychain: %s", name, exc)
                raise SecretStorageError(f"Failed to store secret: {exc}")
        else:
            self._fallback_store[name] = value
            logger.warning("Secret '%s' stored in memory (keyring unavailable)", name)

    def get_secret(self, name: str) -> Optional[str]:
        """Retrieve a secret from secure storage."""
        if self._keyring_available:
            try:
                return keyring.get_password(KEYRING_SERVICE_NAME, self._keyring_key(name))
            except KeyringError as exc:
                logger.error("Failed to retrieve secret '%s': %s", name, exc)
                return None
        return self._fallback_store.get(name)

    def delete_secret(self, name: str) -> bool:
        """Delete a secret from secure storage."""
        if self._keyring_available:
            try:
                keyring.delete_password(KEYRING_SERVICE_NAME, self._keyring_key(name))
                return True
            except PasswordDeleteError:
                return False
            except KeyringError as exc:
                logger.error("Failed to delete secret '%s': %s", name, exc)
                return False
        else:
            return self._fallback_store.pop(name, None) is not None

    def list_secrets(self) -> List[str]:
        """List all secret names stored for MCP Hub."""
        if self._keyring_available:
            try:
                # keyring 不直接支持 list，使用 get_credential 或第三方扩展
                # 这里使用一个元数据条目来跟踪列表
                metadata = keyring.get_password(KEYRING_SERVICE_NAME, "__metadata__")
                if metadata:
                    return metadata.split(",")
            except KeyringError:
                pass
            return []
        return list(self._fallback_store.keys())

    def is_available(self) -> bool:
        """Return whether persistent secure storage is available."""
        return self._keyring_available

    # ── 配置文件引用处理 ──

    @staticmethod
    def is_env_reference(value: str) -> bool:
        """Check if a value is an environment variable reference.
        
        Examples:
            ${GITHUB_TOKEN} -> True
            plain_value -> False
        """
        return value.startswith(ENV_REF_PREFIX) and value.endswith(ENV_REF_SUFFIX)

    @staticmethod
    def extract_reference_name(value: str) -> str:
        """Extract the secret name from a reference.
        
        Example: ${GITHUB_TOKEN} -> GITHUB_TOKEN
        """
        if not SecretManager.is_env_reference(value):
            return value
        return value[len(ENV_REF_PREFIX):-len(ENV_REF_SUFFIX)]

    def resolve_env_references(self, env_dict: Dict[str, str]) -> Dict[str, str]:
        """Resolve environment variable references to actual secret values.
        
        Input:  {"GITHUB_TOKEN": "${GITHUB_TOKEN}", "NODE_ENV": "production"}
        Output: {"GITHUB_TOKEN": "ghp_xxx", "NODE_ENV": "production"}
        
        Non-reference values are passed through unchanged.
        Missing secrets are logged as warnings and left as references.
        """
        resolved = {}
        for key, value in env_dict.items():
            if self.is_env_reference(value):
                secret_name = self.extract_reference_name(value)
                secret_value = self.get_secret(secret_name)
                if secret_value is not None:
                    resolved[key] = secret_value
                else:
                    logger.warning(
                        "Secret '%s' referenced in config but not found in keychain. "
                        "Run: mcp-hub secrets set %s",
                        secret_name, secret_name
                    )
                    resolved[key] = value  # 保留引用，让运行时处理
            else:
                resolved[key] = value
        return resolved


class SecretStorageError(Exception):
    """Raised when secret storage operation fails."""
    pass
