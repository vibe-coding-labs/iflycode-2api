"""Multi-account routing — maps API keys to iFlyCode Client instances."""

import logging
from typing import Dict, List, Optional

from iflycode_2api.client import Client

log = logging.getLogger("iflycode-2api.router")


class CredentialRouter:
    def __init__(self):
        self._clients: Dict[str, Client] = {}  # api_key -> Client
        self._account_ids: Dict[str, str] = {}  # api_key -> account_id
        self._default_models: Dict[str, str] = {}  # account_id -> default_model
        self._default_key: Optional[str] = None  # api_key of default account

    @property
    def default_key(self) -> Optional[str]:
        return self._default_key

    def add_account(self, account_id: str, api_key: str, spark_token: str, user_id: str,
                    default: bool = False, default_model: str = ""):
        client = Client(spark_token, user_id)
        self._clients[api_key] = client
        self._account_ids[api_key] = account_id
        if default_model:
            self._default_models[account_id] = default_model
        elif account_id in self._default_models:
            del self._default_models[account_id]
        if default or self._default_key is None:
            self._default_key = api_key
        log.info("Account registered: account_id=%s api_key=%s user_id=%s", account_id, api_key[:8] + "...", user_id)

    def get_client(self, api_key: Optional[str] = None) -> Client:
        if api_key and api_key in self._clients:
            return self._clients[api_key]
        if self._default_key and self._default_key in self._clients:
            return self._clients[self._default_key]
        raise KeyError(f"No account found for key '{api_key}' and no default configured")

    def get_default_model(self, api_key: Optional[str] = None) -> str:
        account_id = self._account_ids.get(api_key, "") if api_key else ""
        if account_id:
            return self._default_models.get(account_id, "")
        if self._default_key:
            default_account_id = self._account_ids.get(self._default_key, "")
            return self._default_models.get(default_account_id, "")
        return ""

    def get_account_id(self, api_key: Optional[str] = None) -> Optional[str]:
        if api_key and api_key in self._account_ids:
            return self._account_ids[api_key]
        if self._default_key:
            return self._account_ids.get(self._default_key)
        return None

    def set_default_model(self, account_id: str, default_model: str):
        if default_model:
            self._default_models[account_id] = default_model
        elif account_id in self._default_models:
            del self._default_models[account_id]

    def list_accounts(self) -> List[Dict]:
        result = []
        for api_key, client in self._clients.items():
            account_id = self._account_ids.get(api_key, "")
            result.append({
                "account_id": account_id,
                "api_key": api_key,
                "user_id": client.user_id,
                "is_default": api_key == self._default_key,
                "default_model": self._default_models.get(account_id, ""),
            })
        return result

    def remove_account(self, api_key: str) -> bool:
        if api_key in self._clients:
            self._clients[api_key].close()
            del self._clients[api_key]
            account_id = self._account_ids.pop(api_key, "")
            self._default_models.pop(account_id, None)
            if self._default_key == api_key:
                self._default_key = next(iter(self._clients), None)
            log.info("Account removed: api_key=%s", api_key[:8] + "...")
            return True
        return False

    def renew_api_key(self, old_api_key: str, new_api_key: str) -> bool:
        if old_api_key not in self._clients:
            return False
        client = self._clients.pop(old_api_key)
        self._clients[new_api_key] = client
        account_id = self._account_ids.pop(old_api_key, "")
        self._account_ids[new_api_key] = account_id
        if self._default_key == old_api_key:
            self._default_key = new_api_key
        log.info("API key renewed: account_id=%s", account_id)
        return True

    def validate_all(self) -> Dict[str, bool]:
        results = {}
        for key, client in self._clients.items():
            try:
                results[key] = client.validate()
            except Exception:
                results[key] = False
        return results
