"""iFlyCode HTTP client — mimics the real agent request fingerprint."""

import json
import logging
import re
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

# Retry config for upstream engine errors
_MAX_RETRIES = 3
_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 8.0

# Patterns indicating transient upstream errors worth retrying
_RETRYABLE_ERROR_PATTERNS = [
    re.compile(r"EngineInternalError", re.IGNORECASE),
    re.compile(r"kernel\s*error", re.IGNORECASE),
    re.compile(r"engineCode\s*=\s*10908", re.IGNORECASE),
    re.compile(r"code\s*=\s*1010\b", re.IGNORECASE),
    re.compile(r"service\s*overloaded", re.IGNORECASE),
    re.compile(r"rate\s*limit", re.IGNORECASE),
    re.compile(r"too\s*many\s*requests", re.IGNORECASE),
]


def _is_retryable_error(text: str) -> bool:
    return any(p.search(text) for p in _RETRYABLE_ERROR_PATTERNS)


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
        backoff = _INITIAL_BACKOFF
        last_exc = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = self._http.post(url, headers=self._headers(), json=body)
                resp.raise_for_status()
                data = resp.json()
                # Check for upstream engine errors in the response body
                resp_text = json.dumps(data)
                if _is_retryable_error(resp_text) and attempt < _MAX_RETRIES:
                    log.warning("Upstream retryable error on attempt %d/%d, retrying in %.1fs: %s",
                                attempt + 1, _MAX_RETRIES, backoff, resp_text[:200])
                    time.sleep(backoff)
                    backoff = min(backoff * 2, _MAX_BACKOFF)
                    continue
                return resp
            except httpx.HTTPStatusError as exc:
                resp_text = ""
                try:
                    resp_text = exc.response.text
                except Exception:
                    pass
                if _is_retryable_error(resp_text) and attempt < _MAX_RETRIES:
                    log.warning("Upstream HTTP %d error on attempt %d/%d, retrying in %.1fs",
                                exc.response.status_code, attempt + 1, _MAX_RETRIES, backoff)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, _MAX_BACKOFF)
                    last_exc = exc
                    continue
                raise
            except (httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.PoolTimeout) as exc:
                if attempt < _MAX_RETRIES:
                    log.warning("Connection error on attempt %d/%d, retrying in %.1fs: %s",
                                attempt + 1, _MAX_RETRIES, backoff, exc)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, _MAX_BACKOFF)
                    last_exc = exc
                    continue
                raise
        raise last_exc  # type: ignore[misc]

    def chat_stream(self, messages: List[Dict], options: Optional[Dict] = None):
        body = self.build_chat_body(messages, options)
        url = f"{CHAT_ENDPOINT}?token={self.token}"
        return _RetryableStream(self._http, url, self._headers(), body)

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


class _RetryableStream:
    """Context manager that wraps an httpx stream with retry on upstream engine errors.

    Reads the first SSE chunk; if it contains a retryable error, closes the stream,
    waits with exponential backoff, and retries. Otherwise yields lines normally.
    """

    def __init__(self, http_client: httpx.Client, url: str, headers: Dict, body: Dict):
        self._http = http_client
        self._url = url
        self._headers = headers
        self._body = body
        self._resp: Optional[httpx.Response] = None
        self._line_iter: Optional[Iterator[bytes]] = None

    def __enter__(self):
        self._open_stream()
        return self

    def __exit__(self, *args):
        self._close_resp()

    def _close_resp(self):
        if self._resp is not None:
            try:
                self._resp.close()
            except Exception:
                pass
            self._resp = None
            self._line_iter = None

    def _open_stream(self):
        self._resp = self._http.stream("POST", self._url, headers=self._headers, json=self._body).__enter__()
        self._line_iter = self._resp.iter_lines()

    def iter_lines(self):
        backoff = _INITIAL_BACKOFF
        for attempt in range(_MAX_RETRIES + 1):
            try:
                # Peek at the first non-empty line to detect engine errors
                first_lines = []
                if self._line_iter is not None:
                    for raw_line in self._line_iter:
                        if raw_line:
                            first_lines.append(raw_line)
                            break

                # If we got a first line, check for retryable errors
                if first_lines:
                    line = first_lines[0]
                    decoded = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else line
                    if decoded.startswith("data:"):
                        payload = decoded[5:].strip()
                        if payload != "[DONE]" and _is_retryable_error(payload) and attempt < _MAX_RETRIES:
                            log.warning("Stream upstream error on attempt %d/%d, retrying in %.1fs: %s",
                                        attempt + 1, _MAX_RETRIES, backoff, payload[:200])
                            self._close_resp()
                            time.sleep(backoff)
                            backoff = min(backoff * 2, _MAX_BACKOFF)
                            # Rebuild body with new requestId
                            self._body["requestId"] = str(uuid.uuid4())
                            self._body["sessionId"] = self._body.get("sessionId", str(uuid.uuid4()))
                            self._open_stream()
                            continue
                        # Not retryable, yield the first line and continue
                        yield line

                # Yield remaining lines
                if self._line_iter is not None:
                    for raw_line in self._line_iter:
                        if raw_line:
                            yield raw_line
                return

            except (httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.PoolTimeout) as exc:
                if attempt < _MAX_RETRIES:
                    log.warning("Stream connection error on attempt %d/%d, retrying in %.1fs: %s",
                                attempt + 1, _MAX_RETRIES, backoff, exc)
                    self._close_resp()
                    time.sleep(backoff)
                    backoff = min(backoff * 2, _MAX_BACKOFF)
                    self._body["requestId"] = str(uuid.uuid4())
                    self._body["sessionId"] = self._body.get("sessionId", str(uuid.uuid4()))
                    self._open_stream()
                    continue
                raise
