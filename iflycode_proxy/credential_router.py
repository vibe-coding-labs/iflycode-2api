"""Multi-account routing — maps API keys to iFlyCode Client instances."""

import logging
from typing import Dict, List, Optional

from iflycode_proxy.client import Client

log = logging.getLogger("iflycode-proxy.router")


class CredentialRouter:
    def __init__(self):
        self._clients: Dict[str, Client] = {}
        self._default_models: Dict[str, str] = {}
        self._default_key: Optional[str] = None

    @property
    def default_key(self) -> Optional[str]:
        return self._default_key

    def add_account(self, api_key: str, token: str, user_id: str,
                    default: bool = False, default_model: str = ""):
        client = Client(token, user_id)
        self._clients[api_key] = client
        if default_model:
            self._default_models[api_key] = default_model
        elif api_key in self._default_models:
            del self._default_models[api_key]
        if default or self._default_key is None:
            self._default_key = api_key
        log.info("Account registered: api_key=%s user_id=%s", api_key, user_id)

    def get_client(self, api_key: Optional[str] = None) -> Client:
        if api_key and api_key in self._clients:
            return self._clients[api_key]
        if self._default_key and self._default_key in self._clients:
            return self._clients[self._default_key]
        raise KeyError(f"No account found for key '{api_key}' and no default configured")

    def get_default_model(self, api_key: Optional[str] = None) -> str:
        if api_key:
            return self._default_models.get(api_key, "")
        if self._default_key:
            return self._default_models.get(self._default_key, "")
        return ""

    def list_accounts(self) -> List[Dict]:
        result = []
        for key, client in self._clients.items():
            result.append({
                "api_key": key,
                "user_id": client.user_id,
                "is_default": key == self._default_key,
                "default_model": self._default_models.get(key, ""),
            })
        return result

    def remove_account(self, api_key: str) -> bool:
        if api_key in self._clients:
            self._clients[api_key].close()
            del self._clients[api_key]
            self._default_models.pop(api_key, None)
            if self._default_key == api_key:
                self._default_key = next(iter(self._clients), None)
            log.info("Account removed: api_key=%s", api_key)
            return True
        return False

    def validate_all(self) -> Dict[str, bool]:
        results = {}
        for key, client in self._clients.items():
            try:
                results[key] = client.validate()
            except Exception:
                results[key] = False
        return results
