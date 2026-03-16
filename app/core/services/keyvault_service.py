"""Azure Key Vault secret loader.

Uses DefaultAzureCredential — works transparently in both environments:
  Local dev:    az login session (no extra config needed)
  Production:   Managed Identity on Container Apps (no keys needed)

Usage:
    from app.core.services.keyvault_service import secrets
    db_url = secrets.get("database-url")
"""

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


class KeyVaultService:
    def __init__(self, vault_url: str):
        self.vault_url = vault_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
            self._client = SecretClient(
                vault_url=self.vault_url,
                credential=DefaultAzureCredential(),
            )
        return self._client

    def get(self, name: str, fallback: str | None = None) -> str | None:
        """Fetch a secret by name. Returns fallback if not found or vault unreachable."""
        try:
            secret = self._get_client().get_secret(name)
            return secret.value
        except Exception as e:
            if fallback is not None:
                logger.debug(f"Key Vault secret '{name}' unavailable, using fallback: {e}")
                return fallback
            logger.warning(f"Key Vault secret '{name}' not found and no fallback: {e}")
            return None

    def set(self, name: str, value: str) -> None:
        """Store or update a secret."""
        self._get_client().set_secret(name, value)
        logger.info(f"Key Vault: stored secret '{name}'")


@lru_cache(maxsize=1)
def get_keyvault_service(vault_url: str) -> KeyVaultService:
    return KeyVaultService(vault_url)
