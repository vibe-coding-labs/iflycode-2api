"""Anthropic Messages API handler — translates Anthropic format to/from iFlyCode."""

import json
import logging
import time
import uuid
from typing import Any, Iterator, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from iflycode_proxy.credential_router import CredentialRouter

log = logging.getLogger("iflycode-proxy.anthropic")


def _msg_id() -> str:
    return f"msg_{uuid.uuid4().hex[:24]}"


def _error_response(message: str, status_code: int = 500, error_type: str = "api_error") -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"type": "error", "error": {"type": error_type, "message": message}},
    )


def _extract_api_key(request: Request) -> str:
    """Extract API key from x-api-key or Authorization header."""
    api_key = request.headers.get("x-api-key", "")
    if not api_key:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            api_key = auth[7:]
    return api_key


def _translate_messages(req_body: dict) -> list:
    """Convert Anthropic message format to iFlyCode/OpenAI message format."""
    messages = []
    system = req_body.get("system")
    if system:
        if isinstance(system, str):
            system_text = system
        elif isinstance(system, list):
            system_text = "\n".join(
                block.get("text", "") for block in system if block.get("type") == "text"
            )
        else:
            system_text = str(system)
        if system_text:
            messages.append({"role": "system", "content": system_text})

    for msg in req_body.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            parts = []
            for block in content:
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
            content = "\n".join(parts)
        messages.append({"role": role, "content": content})

    return messages


def _build_non_stream_response(content: str, model: str, input_tokens: int = 0,
                                output_tokens: int = 0) -> dict:
    return {
        "id": _msg_id(),
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": content}],
        "model": model,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


def _stream_anthropic(client, messages: list, body: dict, model: str) -> StreamingResponse:
    def _generate() -> Iterator[str]:
        msg_id = _msg_id()
        try:
            # message_start
            start_data = {
                "type": "message_start",
                "message": {
                    "id": msg_id,
                    "type": "message",
                    "role": "assistant",
                    "content": [],
                    "model": model,
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            }
            yield f"event: message_start\ndata: {json.dumps(start_data)}\n\n"

            # content_block_start
            yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n"

            output_tokens = 0
            with client.chat_stream(messages, body) as resp:
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

                    if reasoning and not content:
                        content = f"[think]{reasoning}[/think]"

                    if content:
                        output_tokens += 1
                        delta_event = {
                            "type": "content_block_delta",
                            "index": 0,
                            "delta": {"type": "text_delta", "text": content},
                        }
                        yield f"event: content_block_delta\ndata: {json.dumps(delta_event)}\n\n"

                    if finish_reason:
                        break

            # content_block_stop
            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"

            # message_delta
            delta_event = {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": output_tokens},
            }
            yield f"event: message_delta\ndata: {json.dumps(delta_event)}\n\n"

            # message_stop
            yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

        except Exception as exc:
            log.error("Anthropic stream error: %s", exc)
            error_event = {
                "type": "error",
                "error": {"type": "api_error", "message": str(exc)},
            }
            yield f"event: error\ndata: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "close", "X-Accel-Buffering": "no"},
    )


def _non_stream_response(client, messages: list, body: dict, model: str) -> JSONResponse:
    full_content = ""
    reasoning_content = ""

    with client.chat_stream(messages, body) as resp:
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
    resp_data = _build_non_stream_response(final, model, output_tokens=len(final.split()))
    return JSONResponse(content=resp_data)


def create_anthropic_router(cred_router: CredentialRouter) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/messages")
    async def create_message(request: Request) -> Any:
        api_key = _extract_api_key(request)
        try:
            client = cred_router.get_client(api_key or None)
        except KeyError:
            return _error_response(
                "No account available. Add an account via /api/accounts first.",
                401, "authentication_error",
            )

        try:
            req_body = await request.json()
        except Exception:
            return _error_response("invalid JSON", 400, "invalid_request_error")

        model = req_body.get("model", "claude-3-5-sonnet-20241022")
        stream = bool(req_body.get("stream", False))
        max_tokens = req_body.get("max_tokens", 4096)

        messages = _translate_messages(req_body)

        jc_body: dict = {"stream": True}
        temperature = req_body.get("temperature")
        if temperature is not None:
            jc_body["temperature"] = temperature

        if stream:
            return _stream_anthropic(client, messages, jc_body, model)

        return _non_stream_response(client, messages, jc_body, model)

    return router
