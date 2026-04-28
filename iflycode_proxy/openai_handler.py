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

log = logging.getLogger("iflycode-proxy.openai")

DEFAULT_MODEL = "iflycode-default"


def _short_id() -> str:
    return str(int(time.time() * 1e6) % 10**12)


def _error_response(message: str, status_code: int = 500) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"message": message, "type": "api_error"}})


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


def _stream_chat(client, body: dict, model: str) -> StreamingResponse:
    def _generate() -> Iterator[str]:
        chat_id = f"chatcmpl-{_short_id()}"
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
                        out_chunk = _build_chunk(chat_id, model, ChoiceDelta(content=content))
                        yield f"data: {out_chunk.model_dump_json()}\n\n"

                    if reasoning and not content:
                        out_chunk = _build_chunk(chat_id, model, ChoiceDelta(content=f"[think]{reasoning}[/think]"))
                        yield f"data: {out_chunk.model_dump_json()}\n\n"

                    if finish_reason:
                        out_chunk = _build_chunk(chat_id, model, ChoiceDelta(), finish_reason=finish_reason)
                        yield f"data: {out_chunk.model_dump_json()}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as exc:
            error_payload = json.dumps({"error": {"message": str(exc)}})
            yield f"data: {error_payload}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "close", "X-Accel-Buffering": "no"},
    )


def _stream_chat_non_streaming(client, body: dict, model: str) -> JSONResponse:
    full_content = ""
    reasoning_content = ""

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
    return JSONResponse(content=completion.model_dump(mode="json"))


def create_openai_router(cred_router: CredentialRouter) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Any:
        api_key = request.headers.get("x-api-key", "")
        try:
            client = cred_router.get_client(api_key or None)
        except KeyError:
            return _error_response("No account available. Add an account via /api/accounts first.", 401)

        try:
            req_body = await request.json()
        except Exception:
            return _error_response("invalid JSON", 400)

        model = req_body.get("model", DEFAULT_MODEL)
        jc_body = translate_request(req_body)

        if jc_body.get("stream"):
            return _stream_chat(client, jc_body, model)

        return _stream_chat_non_streaming(client, jc_body, model)

    @router.get("/v1/models")
    async def list_models() -> Any:
        model_ids = ["iflycode-default", "gpt-4", "gpt-4o"]
        models = [
            Model(id=m, object="model", created=1700000000, owned_by="iflycode")
            for m in model_ids
        ]
        return JSONResponse(content={"object": "list", "data": [m.model_dump(mode="json") for m in models]})

    @router.get("/health")
    async def health() -> Any:
        return JSONResponse(content={
            "status": "ok",
            "service": "iflycode-openai-proxy",
            "accounts": len(cred_router.list_accounts()),
            "endpoints": ["/v1/chat/completions", "/v1/models"],
        })

    return router
