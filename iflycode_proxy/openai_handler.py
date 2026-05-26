"""OpenAI-compatible API handler — translates OpenAI format to/from iFlyCode.

Uses openai SDK Pydantic types for type-safe response construction.
"""

import json
import logging
import time
from typing import Any, Iterator, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice, ChoiceDelta
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.completion_usage import CompletionUsage
from openai.types.model import Model

from iflycode_proxy.credential_router import CredentialRouter
from iflycode_proxy.proxy_logger import log_request, log_response, log_error
from iflycode_proxy.sessions import record_session

log = logging.getLogger("iflycode-proxy.openai")

# Static model metadata — mirrors web/src/data/sparkModels.ts
SPARK_MODEL_META = {
    "4.0Ultra":    {"name": "星火 4.0 Ultra", "supports_coding": True,  "tier": "旗舰版", "context": "32K"},
    "max-32k":     {"name": "星火 Max-32K",   "supports_coding": True,  "tier": "专业版", "context": "32K"},
    "generalv3.5": {"name": "星火 Max",       "supports_coding": True,  "tier": "专业版", "context": "8K"},
    "pro-128k":    {"name": "星火 Pro-128K",  "supports_coding": True,  "tier": "专业版", "context": "128K"},
    "generalv3":   {"name": "星火 Pro",       "supports_coding": False, "tier": "专业版", "context": "8K"},
    "lite":        {"name": "星火 Lite",      "supports_coding": False, "tier": "免费",   "context": "4K"},
    "kjwx":        {"name": "科技文献大模型",  "supports_coding": False, "tier": "专业版", "context": "未知"},
}

# permissionCode -> model type mapping
PERMISSION_TYPE_MAP = {
    "TALK_INTELLIGENT": "chat",
    "INLINE_CHAT": "coding",
}

DEFAULT_MODEL = "iflycode-default"
PROTOCOL = "openai"


def _short_id() -> str:
    return str(int(time.time() * 1e6) % 10**12)


def _error_response(message: str, status_code: int = 500) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"message": message, "type": "api_error"}})


def _summarize_messages(messages: list) -> str:
    """Create a compact summary of messages for logging."""
    parts = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content", "")
        preview = str(content)[:100] if content else "(empty)"
        parts.append(f"{role}: {preview}")
    return "; ".join(parts)


def translate_request(req_body: dict) -> dict:
    model = req_body.get("model", "")
    stream = bool(req_body.get("stream", False))
    body: dict = {"stream": stream}
    messages = req_body.get("messages")
    if messages:
        body["messages"] = messages
    temperature = req_body.get("temperature")
    if temperature is not None:
        body["temperature"] = temperature
    return body


def _build_completion(content: str, model: str) -> ChatCompletion:
    return ChatCompletion(
        id=f"chatcmpl-{_short_id()}",
        object="chat.completion",
        created=int(time.time()),
        model=model,
        choices=[
            Choice(
                index=0,
                message=ChatCompletionMessage(role="assistant", content=content),
                finish_reason="stop",
            )
        ],
        usage=CompletionUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
    )


def _build_chunk(chat_id: str, model: str, delta: ChoiceDelta,
                 finish_reason: Optional[str] = None) -> ChatCompletionChunk:
    return ChatCompletionChunk(
        id=chat_id,
        object="chat.completion.chunk",
        created=int(time.time()),
        model=model,
        choices=[
            ChunkChoice(index=0, delta=delta, finish_reason=finish_reason)
        ],
    )


def _stream_chat(client, body: dict, model: str, api_key: str) -> StreamingResponse:
    start_time = time.time()

    def _generate() -> Iterator[str]:
        chat_id = f"chatcmpl-{_short_id()}"
        token_count = 0
        try:
            role_chunk = _build_chunk(chat_id, model, ChoiceDelta(role="assistant", content=""))
            yield f"data: {role_chunk.model_dump_json()}\n\n"

            with client.chat_stream(body.get("messages", []), body) as resp:
                for raw_line in resp.iter_lines():
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else raw_line
                    if line.startswith("data:"):
                        payload = line[5:].strip()
                    else:
                        continue

                    if payload == "[DONE]":
                        continue

                    try:
                        chunk_data = json.loads(payload)
                    except (json.JSONDecodeError, ValueError):
                        continue

                    choices = chunk_data.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    reasoning = delta.get("reasoning_content", "")
                    finish_reason = choices[0].get("finish_reason")

                    if content:
                        token_count += 1
                        out_chunk = _build_chunk(chat_id, model, ChoiceDelta(content=content))
                        yield f"data: {out_chunk.model_dump_json()}\n\n"

                    if reasoning and not content:
                        out_chunk = _build_chunk(chat_id, model, ChoiceDelta(content=f"[think]{reasoning}[/think]"))
                        yield f"data: {out_chunk.model_dump_json()}\n\n"

                    if finish_reason:
                        out_chunk = _build_chunk(chat_id, model, ChoiceDelta(), finish_reason=finish_reason)
                        yield f"data: {out_chunk.model_dump_json()}\n\n"

            yield "data: [DONE]\n\n"

            latency_ms = int((time.time() - start_time) * 1000)
            log_response(
                protocol=PROTOCOL, endpoint="/v1/chat/completions",
                api_key=api_key, model=model,
                status_code=200, latency_ms=latency_ms,
                response_summary=f"stream completed, {token_count} chunks",
                stream=True,
            )

        except Exception as exc:
            log_error(
                protocol=PROTOCOL, endpoint="/v1/chat/completions",
                api_key=api_key, model=model, error=exc,
                context={"stream": True, "chunks_so_far": token_count},
            )
            error_payload = json.dumps({"error": {"message": str(exc)}})
            yield f"data: {error_payload}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "close", "X-Accel-Buffering": "no"},
    )


def _stream_chat_non_streaming(client, body: dict, model: str,
                               api_key: str) -> JSONResponse:
    start_time = time.time()
    full_content = ""
    reasoning_content = ""

    try:
        with client.chat_stream(body.get("messages", []), body) as resp:
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else raw_line
                if line.startswith("data:"):
                    payload = line[5:].strip()
                else:
                    continue
                if payload == "[DONE]":
                    continue
                try:
                    chunk_data = json.loads(payload)
                except (json.JSONDecodeError, ValueError):
                    continue
                choices = chunk_data.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                if delta.get("content"):
                    full_content += delta["content"]
                if delta.get("reasoning_content"):
                    reasoning_content += delta["reasoning_content"]

        final = f"[think]{reasoning_content}[/think]\n\n{full_content}" if reasoning_content else full_content
        completion = _build_completion(final, model)
        latency_ms = int((time.time() - start_time) * 1000)

        log_response(
            protocol=PROTOCOL, endpoint="/v1/chat/completions",
            api_key=api_key, model=model,
            status_code=200, latency_ms=latency_ms,
            response_summary=final[:200],
            stream=False,
        )

        return JSONResponse(content=completion.model_dump(mode="json"))

    except Exception as exc:
        latency_ms = int((time.time() - start_time) * 1000)
        log_error(
            protocol=PROTOCOL, endpoint="/v1/chat/completions",
            api_key=api_key, model=model, error=exc,
            context={"stream": False, "latency_ms": latency_ms},
        )
        return _error_response(str(exc), 500)


def create_openai_router(cred_router: CredentialRouter) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Any:
        api_key = request.headers.get("x-api-key", "")
        try:
            client = cred_router.get_client(api_key or None)
        except KeyError:
            log_error(
                protocol=PROTOCOL, endpoint="/v1/chat/completions",
                api_key=api_key, model="",
                error=KeyError(f"No account for key '{api_key}'"),
                context={"reason": "authentication_failed"},
            )
            return _error_response("No account available. Add an account via /api/accounts first.", 401)

        # Record session activity
        account_id = cred_router.get_account_id(api_key or None) or api_key
        session_id = request.headers.get("x-session-id", "")
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())
        record_session(account_id, session_id)

        try:
            req_body = await request.json()
        except Exception as exc:
            log_error(
                protocol=PROTOCOL, endpoint="/v1/chat/completions",
                api_key=api_key, model="",
                error=exc,
                context={"reason": "invalid_json_body"},
            )
            return _error_response("invalid JSON", 400)

        model = req_body.get("model", DEFAULT_MODEL)

        # Strip -coding suffix and determine mode
        is_coding_mode = model.endswith("-coding")
        real_model = model.removesuffix("-coding") if is_coding_mode else model

        jc_body = translate_request(req_body)

        model_code = cred_router.get_default_model(api_key or None)
        # Strip -coding from default model too (stored with suffix for persistence)
        if model_code and model_code.endswith("-coding"):
            model_code = model_code.removesuffix("-coding")
        # Use real model code (without -coding suffix) for upstream
        effective_model_code = model_code or real_model
        if effective_model_code and effective_model_code != DEFAULT_MODEL:
            jc_body["modelCode"] = effective_model_code
            jc_body["enableMultiModelSwitch"] = True

        # Switch to INLINE_CHAT when -coding suffix or tools are present
        has_tools = bool(req_body.get("tools"))
        if is_coding_mode or has_tools:
            jc_body["commandType"] = "TALK:ASK"
            jc_body["taskName"] = "INLINE_CHAT"
            jc_body["scene"] = "INLINE_CHAT"
            log.info("Coding mode activated (suffix=%s, tools=%s) for model=%s", is_coding_mode, has_tools, real_model)

        log_request(
            protocol=PROTOCOL, endpoint="/v1/chat/completions",
            api_key=api_key, model=model,
            messages_summary=_summarize_messages(req_body.get("messages", [])),
            stream=bool(jc_body.get("stream")),
            extra={"message_count": len(req_body.get("messages", []))},
        )

        if jc_body.get("stream"):
            return _stream_chat(client, jc_body, model, api_key)

        return _stream_chat_non_streaming(client, jc_body, model, api_key)

    @router.get("/v1/models")
    async def list_models(request: Request) -> Any:
        api_key = request.headers.get("authorization", "").replace("Bearer ", "") if request.headers.get("authorization", "").startswith("Bearer ") else request.headers.get("x-api-key", "")
        models = []

        def _make_model(model_id: str, name: str, mode: str, tier: str, context: str) -> dict:
            data = Model(id=model_id, object="model", created=1700000000, owned_by="iflycode").model_dump(mode="json")
            data["name"] = name
            data["mode"] = mode
            data["capabilities"] = ["chat"] if mode == "chat" else ["chat", "coding"]
            data["tier"] = tier
            data["context"] = context
            return data

        # Default/auto models — always present at the top
        models.append(_make_model("iflycode-default", "自动选择 (Chat)", "chat", "", ""))
        models.append(_make_model("iflycode-default-coding", "自动选择 (Coding)", "coding", "", ""))

        try:
            client = cred_router.get_client(api_key or None)
            upstream_models = client.list_models()
            for m in upstream_models:
                model_id = m.get("modelCode", "") or m.get("modelId", "")
                if not model_id:
                    continue
                meta = SPARK_MODEL_META.get(model_id, {})
                perm_code = m.get("permissionCode", "")
                supports_coding = perm_code == "INLINE_CHAT" or meta.get("supports_coding", False)
                name = meta.get("name", m.get("modelName", model_id))
                tier = meta.get("tier", "")
                context = meta.get("context", "")
                models.append(_make_model(model_id, name, "chat", tier, context))
                if supports_coding:
                    models.append(_make_model(f"{model_id}-coding", f"{name} (Coding)", "coding", tier, context))
        except Exception:
            pass
        if len(models) <= 2:
            for model_id, meta in SPARK_MODEL_META.items():
                name = meta["name"]
                tier = meta["tier"]
                context = meta["context"]
                models.append(_make_model(model_id, name, "chat", tier, context))
                if meta["supports_coding"]:
                    models.append(_make_model(f"{model_id}-coding", f"{name} (Coding)", "coding", tier, context))
        return JSONResponse(content={"object": "list", "data": models})

    @router.get("/health")
    async def health() -> Any:
        return JSONResponse(content={
            "status": "ok",
            "service": "iflycode-openai-proxy",
            "accounts": len(cred_router.list_accounts()),
            "endpoints": ["/v1/chat/completions", "/v1/models"],
        })

    return router
