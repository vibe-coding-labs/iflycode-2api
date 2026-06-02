"""Anthropic Messages API handler — translates Anthropic format to/from iFlyCode."""

import json
import logging
import re
import time
import uuid
from typing import Any, Iterator, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from iflycode_proxy.credential_router import CredentialRouter
from iflycode_proxy.proxy_logger import log_request, log_response, log_error
from iflycode_proxy.truncate import preemptive_truncate

log = logging.getLogger("iflycode-proxy.anthropic")

PROTOCOL = "anthropic"

_TOOL_CALL_TAG_OPEN = "<invoke>"
_TOOL_CALL_TAG_CLOSE = "</invoke>"

# Match invocate-tag format: <invocate>JSON</invocate>
_TOOL_CALL_RE = re.compile(
    r"<invoke>\s*(.*?)\s*</invoke>",
    re.DOTALL,
)

# Match markdown code block with tool JSON
_MD_TOOL_CALL_RE = re.compile(
    r"```(?:json)?\s*\n(\{\s*\"(?:name|tool|function)\".*?\})\s*\n```",
    re.DOTALL,
)

# Match function_call:/tool_call: prefix format
_PREFIX_CALL_RE = re.compile(
    r"(?:function_call|tool_call)\s*[:：]\s*(\{.*?\})",
    re.DOTALL,
)

# Match pure JSON block with tool indicators
_JSON_BLOCK_RE = re.compile(
    r"```json\s*\n(\{\s*\"(?:name|tool|function)\".*?\})\s*\n```",
    re.DOTALL,
)

_TOOL_SYSTEM_PROMPT = """

You are an AI assistant with access to tools. When you need to perform an action, you MUST call a tool using the EXACT format below. Do NOT describe what to do, do NOT show example commands.

TOOL CALL FORMAT (use EXACTLY this format, no other format is accepted):
<invoke>
{"name": "<tool_name>", "arguments": {<argument_key>: <argument_value>}}
</invoke>

CRITICAL RULES (violating any = WRONG response):
1. To perform ANY action, output a tool call using the <invoke> format above. NO EXCEPTIONS.
2. NEVER say "you can use the command..." or "run this in your terminal" — CALL THE TOOL instead.
3. NEVER wrap tool calls in markdown code blocks (```bash etc.)
4. The JSON inside <invoke> must be valid. Put "name" and "arguments" keys.
5. You may add brief text BEFORE the tool call, but the tool call itself is mandatory when action is needed.
6. After receiving [tool_result], continue the task or make another tool call.
7. When in doubt about whether to use a tool, ALWAYS use the tool.
8. Make sure to close the </invoke> tag after the JSON.

EXAMPLES:

User: "list files in current directory"
Let me list the files for you.
<invoke>
{"name": "Bash", "arguments": {"command": "ls -la"}}
</invoke>

User: "read the file main.py"
I will read that file.
<invoke>
{"name": "Read", "arguments": {"file_path": "main.py"}}
</invoke>

User: "what time is it"
Let me check the current time.
<invoke>
{"name": "Bash", "arguments": {"command": "date"}}
</invoke>

Available tools:
{tool_defs}"""


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


def _summarize_messages(messages: list) -> str:
    """Create a compact summary of messages for logging."""
    parts = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content", "")
        if isinstance(content, str):
            preview = content[:100]
        elif isinstance(content, list):
            texts = [b.get("text", "")[:50] for b in content if b.get("type") == "text"]
            preview = " | ".join(texts)[:100]
        else:
            preview = str(content)[:100]
        parts.append(f"{role}: {preview}")
    return "; ".join(parts)


def _format_tools_for_prompt(tools: list) -> str:
    """Format tool definitions into a text description for the system prompt."""
    lines = []
    for tool in tools:
        name = tool.get("name", "unknown")
        desc = tool.get("description", "")
        schema = tool.get("input_schema", {})
        props = schema.get("properties", {})
        required = schema.get("required", [])
        param_lines = []
        for pname, pdef in props.items():
            ptype = pdef.get("type", "any")
            pdesc = pdef.get("description", "")
            req = " (required)" if pname in required else ""
            param_lines.append(f"    - {pname}: {ptype}{req} — {pdesc}")
        params_str = "\n".join(param_lines) if param_lines else "    (no parameters)"
        lines.append(f"- {name}: {desc}\n  Parameters:\n{params_str}")
    return "\n".join(lines)


def _build_tools_system_appendix(tools: list) -> str:
    """Build the system prompt appendix for tool definitions."""
    if not tools:
        return ""
    tool_defs = _format_tools_for_prompt(tools)
    return _TOOL_SYSTEM_PROMPT.format(tool_defs=tool_defs)


def _parse_tool_calls(text: str, known_tools: list = None) -> list:
    """Parse tool calls from model output. Supports <invoke>, markdown, prefix, and legacy formats."""
    calls = []
    seen_raw = set()
    known_names = set()
    if known_tools:
        for t in known_tools:
            known_names.add(t.get("name", ""))

    def _try_parse(raw: str) -> dict | None:
        raw = raw.strip()
        # Strip markdown code fences if present inside the tag
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
            raw = re.sub(r"\n?```\s*$", "", raw)
            raw = raw.strip()
        try:
            data, _ = json.JSONDecoder().raw_decode(raw)
        except (json.JSONDecodeError, ValueError):
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                log.warning("Failed to parse tool_call JSON: %s", raw[:200])
                return None
        if not isinstance(data, dict):
            return None
        name = data.get("name") or data.get("tool") or data.get("function", {}).get("name", "")
        if not name:
            return None
        arguments = (
            data.get("arguments")
            or data.get("input")
            or data.get("parameters")
            or data.get("args")
            or data.get("function", {}).get("arguments")
            or {}
        )
        if not isinstance(arguments, dict):
            arguments = {}
        if known_names and name not in known_names:
            lower_name = name.lower()
            for kn in known_names:
                if lower_name == kn.lower() or lower_name.replace("_", "") == kn.lower().replace("_", ""):
                    name = kn
                    break
        return {"name": name, "input": arguments}

    def _add_call(raw: str):
        if raw in seen_raw:
            return
        seen_raw.add(raw)
        parsed = _try_parse(raw)
        if parsed:
            parsed["id"] = f"toolu_{uuid.uuid4().hex[:24]}"
            calls.append(parsed)

    # 1. <invoke> tag format (primary)
    for match in _TOOL_CALL_RE.finditer(text):
        _add_call(match.group(1))

    # 2. Legacy Chinese tag format (backward compat)
    _LEGACY_TAG_RE = re.compile(r"\u4e13\u533a\s*(\{.*?\})\s*\u4e13\u533a", re.DOTALL)
    for match in _LEGACY_TAG_RE.finditer(text):
        _add_call(match.group(1))

    # 3. Markdown code block format
    for match in _MD_TOOL_CALL_RE.finditer(text):
        _add_call(match.group(1))

    # 4. function_call:/tool_call: prefix format
    for match in _PREFIX_CALL_RE.finditer(text):
        _add_call(match.group(1))

    # 5. Pure JSON block format (less specific, only if no other matches)
    if not calls:
        for match in _JSON_BLOCK_RE.finditer(text):
            _add_call(match.group(1))

    return calls


def _strip_tool_calls_from_text(text: str) -> str:
    """Remove tool call blocks from text (all supported formats)."""
    text = _TOOL_CALL_RE.sub("", text)
    _LEGACY_TAG_RE = re.compile(r"\u4e13\u533a\s*\{.*?\}\s*\u4e13\u533a", re.DOTALL)
    text = _LEGACY_TAG_RE.sub("", text)
    text = _MD_TOOL_CALL_RE.sub("", text)
    text = _PREFIX_CALL_RE.sub("", text)
    text = _JSON_BLOCK_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _translate_messages(req_body: dict) -> tuple:
    """Convert Anthropic message format to iFlyCode/OpenAI message format.

    Returns (messages, tools) tuple.
    Handles tool_use/tool_result/thinking blocks by converting them to text
    since upstream iFlyCode only supports text content.
    """
    messages = []
    tools = req_body.get("tools", [])
    tools_appendix = _build_tools_system_appendix(tools)

    system = req_body.get("system")
    system_text = ""
    if system:
        if isinstance(system, str):
            system_text = system
        elif isinstance(system, list):
            system_text = "\n".join(
                block.get("text", "") for block in system if block.get("type") == "text"
            )
        else:
            system_text = str(system)

    if tools_appendix:
        system_text = system_text + "\n" + tools_appendix if system_text else tools_appendix

    if system_text:
        messages.append({"role": "system", "content": system_text})

    for msg in req_body.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            parts = []
            for block in content:
                btype = block.get("type", "")
                if btype == "text":
                    parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    name = block.get("name", "unknown")
                    inp = block.get("input", {})
                    tc_json = json.dumps({"name": name, "arguments": inp}, ensure_ascii=False)
                    parts.append(f"<tool_call>\n{tc_json}\n</tool_call>")
                elif btype == "tool_result":
                    result = block.get("content", "")
                    if isinstance(result, list):
                        result = "\n".join(
                            b.get("text", "") for b in result if b.get("type") == "text"
                        )
                    parts.append(f"[tool_result for {block.get('tool_use_id', 'unknown')}]: {result}")
                elif btype == "thinking":
                    parts.append(f"[thinking: {block.get('thinking', '')}]")
            content = "\n".join(parts)
        messages.append({"role": role, "content": content})

    return messages, tools


def _build_non_stream_response(content: list, model: str, stop_reason: str,
                                input_tokens: int = 0, output_tokens: int = 0) -> dict:
    return {
        "id": _msg_id(),
        "type": "message",
        "role": "assistant",
        "content": content,
        "model": model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


def _stream_anthropic(client, messages: list, body: dict, model: str,
                      api_key: str, has_tools: bool, tools: list = None) -> StreamingResponse:
    start_time = time.time()

    def _generate() -> Iterator[str]:
        msg_id = _msg_id()
        output_tokens = 0
        full_text = ""
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
                        full_text += content
                        output_tokens += 1
                        delta_event = {
                            "type": "content_block_delta",
                            "index": 0,
                            "delta": {"type": "text_delta", "text": content},
                        }
                        yield f"event: content_block_delta\ndata: {json.dumps(delta_event)}\n\n"

                    if finish_reason:
                        break

            # Parse tool calls from accumulated text if tools were provided
            tool_calls = _parse_tool_calls(full_text, known_tools=tools) if has_tools else []
            clean_text = _strip_tool_calls_from_text(full_text) if tool_calls else full_text

            stop_reason = "tool_use" if tool_calls else "end_turn"

            # content_block_stop for the initial text block
            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"

            # Emit tool_use content blocks
            if tool_calls:
                for i, tc in enumerate(tool_calls):
                    idx = 1 + i
                    yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': idx, 'content_block': {'type': 'tool_use', 'id': tc['id'], 'name': tc['name'], 'input': tc['input']}})}\n\n"
                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': idx})}\n\n"

            # message_delta
            delta_event = {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": output_tokens},
            }
            yield f"event: message_delta\ndata: {json.dumps(delta_event)}\n\n"

            # message_stop
            yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

            latency_ms = int((time.time() - start_time) * 1000)
            log_response(
                protocol=PROTOCOL, endpoint="/v1/messages",
                api_key=api_key, model=model,
                status_code=200, latency_ms=latency_ms,
                response_summary=f"stream completed, {output_tokens} tokens, {len(tool_calls)} tool_calls",
                stream=True,
            )

        except Exception as exc:
            log_error(
                protocol=PROTOCOL, endpoint="/v1/messages",
                api_key=api_key, model=model, error=exc,
                context={"stream": True, "output_tokens_so_far": output_tokens},
            )
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


def _non_stream_response(client, messages: list, body: dict, model: str,
                         api_key: str, has_tools: bool, tools: list = None) -> JSONResponse:
    start_time = time.time()
    full_content = ""
    reasoning_content = ""

    try:
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

        if reasoning_content:
            full_content = f"[think]{reasoning_content}[/think]\n\n{full_content}"

        # Parse tool calls if tools were provided
        tool_calls = _parse_tool_calls(full_content, known_tools=tools) if has_tools else []
        clean_text = _strip_tool_calls_from_text(full_content) if tool_calls else full_content

        content_blocks = []
        if clean_text:
            content_blocks.append({"type": "text", "text": clean_text})
        for tc in tool_calls:
            content_blocks.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": tc["input"],
            })

        stop_reason = "tool_use" if tool_calls else "end_turn"
        resp_data = _build_non_stream_response(
            content_blocks, model, stop_reason,
            output_tokens=len(full_content.split()),
        )
        latency_ms = int((time.time() - start_time) * 1000)

        log_response(
            protocol=PROTOCOL, endpoint="/v1/messages",
            api_key=api_key, model=model,
            status_code=200, latency_ms=latency_ms,
            response_summary=full_content[:200],
            stream=False,
        )

        return JSONResponse(content=resp_data)

    except Exception as exc:
        latency_ms = int((time.time() - start_time) * 1000)
        log_error(
            protocol=PROTOCOL, endpoint="/v1/messages",
            api_key=api_key, model=model, error=exc,
            context={"stream": False, "latency_ms": latency_ms},
        )
        return _error_response(str(exc), 500, "api_error")


def create_anthropic_router(cred_router: CredentialRouter) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/messages")
    async def create_message(request: Request) -> Any:
        start_time = time.time()
        api_key = _extract_api_key(request)

        try:
            client = cred_router.get_client(api_key or None)
        except KeyError:
            log_error(
                protocol=PROTOCOL, endpoint="/v1/messages",
                api_key=api_key, model="",
                error=KeyError(f"No account for key '{api_key}'"),
                context={"reason": "authentication_failed"},
            )
            return _error_response(
                "No account available. Add an account via /api/accounts first.",
                401, "authentication_error",
            )

        try:
            req_body = await request.json()
        except Exception as exc:
            log_error(
                protocol=PROTOCOL, endpoint="/v1/messages",
                api_key=api_key, model="",
                error=exc,
                context={"reason": "invalid_json_body"},
            )
            return _error_response("invalid JSON", 400, "invalid_request_error")

        model = req_body.get("model", "claude-3-5-sonnet-20241022")
        stream = bool(req_body.get("stream", False))
        max_tokens = req_body.get("max_tokens", 4096)
        messages, tools = _translate_messages(req_body)
        has_tools = bool(tools)

        # Proactively truncate long conversations
        truncation_rounds = preemptive_truncate(messages)
        if truncation_rounds > 0:
            log.info("Preemptive truncation performed %d round(s) for account=%s",
                     truncation_rounds, account_id)

        log_request(
            protocol=PROTOCOL, endpoint="/v1/messages",
            api_key=api_key, model=model,
            messages_summary=_summarize_messages(messages),
            stream=stream,
            extra={
                "max_tokens": max_tokens,
                "system_present": bool(req_body.get("system")),
                "message_count": len(req_body.get("messages", [])),
                "anthropic_version": request.headers.get("anthropic-version", ""),
                "tools_count": len(tools),
            },
        )

        jc_body: dict = {"stream": True}
        temperature = req_body.get("temperature")
        if temperature is not None:
            jc_body["temperature"] = temperature

        model_code = cred_router.get_default_model(api_key or None)
        if model_code:
            jc_body["modelCode"] = model_code
            jc_body["enableMultiModelSwitch"] = True

        if stream:
            return _stream_anthropic(client, messages, jc_body, model, api_key, has_tools, tools=tools)

        return _non_stream_response(client, messages, jc_body, model, api_key, has_tools, tools=tools)

    return router
