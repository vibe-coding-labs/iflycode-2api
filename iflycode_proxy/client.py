"""iFlyCode HTTP client — mimics the real agent request fingerprint."""

import json
import logging
import time
import uuid
from typing import Any, Dict, Iterator, List, Optional

import httpx

log = logging.getLogger("iflycode-proxy.client")

BASE_URL = "https://iflycode-xfsaas.xfyun.cn"
AGENT_VERSION = "3.4.2"

DEFAULT_CLIENT_INFO = {
    "clientName": "IDEA",
    "clientVersion": "2024.1",
    "pluginVersion": "3.4.2-222",
}

CHAT_ENDPOINT = "/api/starspark/v1/agent/chat/async/ask"
MODEL_LIST_ENDPOINT = "/api/starspark/v1/agent/permission/queryUserFuncModelList"
VALIDATE_ENDPOINT = "/api/starspark/v1/chat/user/valid"
LOGIN_URL_ENDPOINT = "/api/starspark/v1/agent/authSetting/query"
LOGIN_STATUS_ENDPOINT = "/api/starspark/v1/user/authorizationQuery"
LOGOUT_ENDPOINT = "/api/starspark/v1/chat/user/logOut"

DEFAULT_TIMEOUT = httpx.Timeout(connect=10, read=120, write=30, pool=10)


class Client:
    """HTTP client that mimics iFlyCode 3.4.2 agent requests."""

    def __init__(self, token: str, user_id: str = "",
                 base_url: str = BASE_URL, timeout: httpx.Timeout = DEFAULT_TIMEOUT):
        self.token = token
        self.user_id = user_id
        self._http = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            follow_redirects=True,
        )

    def _headers(self, extra: Optional[Dict] = None) -> Dict[str, str]:
        h = {"Content-Type": "application/json", "token": self.token}
        if extra:
            h.update(extra)
        return h

    def _build_base_data(self, options: Optional[Dict] = None) -> Dict[str, Any]:
        opts = options or {}
        data: Dict[str, Any] = {
            "requestId": str(uuid.uuid4()),
            "enterpriseId": opts.get("enterpriseId", ""),
            "token": self.token,
            "language": opts.get("language", "java"),
            "timeStamp": int(time.time() * 1000),
            "fileName": opts.get("fileName", ""),
            "fileNameSuffix": opts.get("fileNameSuffix", ""),
            "projectName": opts.get("projectName", ""),
            "agentVersion": AGENT_VERSION,
            "commandType": opts.get("commandType", "TALK:ASK"),
            "taskName": opts.get("taskName", "TALK_INTELLIGENT"),
            "scene": opts.get("scene", "TALK_INTELLIGENT"),
            "userQuestionContent": opts.get("userQuestionContent", ""),
            **DEFAULT_CLIENT_INFO,
        }
        model_code = opts.get("modelCode")
        if model_code:
            data["modelCode"] = model_code
            data["enableMultiModelSwitch"] = True
        return data

    def build_chat_body(self, messages: List[Dict], options: Optional[Dict] = None) -> Dict[str, Any]:
        opts = options or {}
        user_input = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_input = m.get("content", "")
                break
        base = self._build_base_data({**opts, "userQuestionContent": user_input})
        body: Dict[str, Any] = {
            "sessionId": opts.get("sessionId", str(uuid.uuid4())),
            **base,
            "top_k": 1,
            "temperature": opts.get("temperature", 0.5),
            "messages": messages,
        }
        return body

    def chat(self, messages: List[Dict], options: Optional[Dict] = None) -> httpx.Response:
        body = self.build_chat_body(messages, options)
        url = f"{CHAT_ENDPOINT}?token={self.token}"
        resp = self._http.post(url, headers=self._headers(), json=body)
        resp.raise_for_status()
        return resp

    def chat_stream(self, messages: List[Dict], options: Optional[Dict] = None):
        body = self.build_chat_body(messages, options)
        url = f"{CHAT_ENDPOINT}?token={self.token}"
        return self._http.stream("POST", url, headers=self._headers(), json=body)

    def validate(self) -> bool:
        try:
            resp = self._http.post(
                f"{VALIDATE_ENDPOINT}?token={self.token}",
                headers=self._headers(),
                json={"token": self.token},
            )
            data = resp.json()
            code = str(data.get("resCode", data.get("code", "")))
            return code in ("0", "200")
        except Exception:
            return False

    def list_models(self) -> List[Dict]:
        try:
            resp = self._http.post(
                f"{MODEL_LIST_ENDPOINT}?token={self.token}",
                headers=self._headers(),
                json={"token": self.token},
            )
            data = resp.json()
            raw = data.get("obj") or data.get("data") or []
            models = []
            for item in raw:
                if isinstance(item, dict):
                    code_list = item.get("codeModelList")
                    if isinstance(code_list, list):
                        models.extend(code_list)
                    elif item.get("modelCode"):
                        models.append(item)
            return models
        except Exception as e:
            log.warning("Failed to fetch models: %s", e)
            return []

    def close(self):
        self._http.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
