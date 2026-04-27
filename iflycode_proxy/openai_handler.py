"""OpenAI-compatible API handler — translates OpenAI format to/from iFlyCode."""

import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

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


def translate_response(content: str, model: str) -> dict:
    return {
        "id": "chatcmpl-" + _short_id(),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _stream_chat(client, body: dict, model: str) -> StreamingResponse:
    def _generate():
        chat_id = "chatcmpl-" + _short_id()
        try:
            # Send initial role chunk
            yield f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': model, 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': ''}}]})}\n\n"

            with client.chat_stream(body.get("messages", []), body) as resp:
                full_content = ""
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
                        chunk = json.loads(payload)
                    except (json.JSONDecodeError, ValueError):
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    reasoning = delta.get("reasoning_content", "")
                    finish_reason = choices[0].get("finish_reason")

                    if content:
                        full_content += content
                        yield f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': model, 'choices': [{'index': 0, 'delta': {'content': content}}]})}\n\n"

                    if reasoning and not content:
                        yield f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': model, 'choices': [{'index': 0, 'delta': {'content': f'[think]{reasoning}[/think]'}}]})}\n\n"

                    if finish_reason:
                        yield f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish_reason}]})}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': {'message': str(exc)}})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "close", "X-Accel-Buffering": "no"},
    )


def _stream_chat_non_streaming(client, body: dict, model: str) -> JSONResponse:
    """Non-streaming: collect full response then return."""
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
                chunk = json.loads(payload)
            except (json.JSONDecodeError, ValueError):
                continue
            choices = chunk.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            if delta.get("content"):
                full_content += delta["content"]
            if delta.get("reasoning_content"):
                reasoning_content += delta["reasoning_content"]

    final = f"[think]{reasoning_content}[/think]\n\n{full_content}" if reasoning_content else full_content
    return JSONResponse(content=translate_response(final, model))


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
        models = [
            {"id": "iflycode-default", "object": "model", "created": 1700000000, "owned_by": "iflycode"},
            {"id": "gpt-4", "object": "model", "created": 1700000000, "owned_by": "iflycode"},
            {"id": "gpt-4o", "object": "model", "created": 1700000000, "owned_by": "iflycode"},
        ]
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
