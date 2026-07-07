#!/usr/bin/env python3
"""Apply protocol translation fixes to anthropic_handler.py.

Fixes:
1. Replace Chinese tag constants with proper XML tags
2. Fix main regex to use (.*?) instead of ({.*?}) for nested JSON
3. Replace _TOOL_SYSTEM_PROMPT with new tag format
4. Replace _parse_tool_calls with raw_decode and legacy compat
5. Replace _strip_tool_calls_from_text with both format support
6. Fix _translate_messages tool_use text format
7. Fix _non_stream_response missing known_tools
8. Fix create_anthropic_router missing tools passthrough
"""

import re

OPEN_TAG = "<invoke>"
CLOSE_TAG = "</invoke>"
OLD_TAG = "专区"  # 专区

with open("iflycode_2api/anthropic_handler.py", "r") as f:
    content = f.read()

# ============================================================
# Fix 1: Replace tag constants
# ============================================================
content = content.replace(
    '_TOOL_CALL_TAG_OPEN = "' + OLD_TAG + '"',
    '_TOOL_CALL_TAG_OPEN = "' + OPEN_TAG + '"'
)
content = content.replace(
    '_TOOL_CALL_TAG_CLOSE = "' + OLD_TAG + '"',
    '_TOOL_CALL_TAG_CLOSE = "' + CLOSE_TAG + '"'
)
print("Fix 1: Tag constants updated")

# ============================================================
# Fix 2: Replace main regex
# ============================================================
# Old regex pattern: 专区\s*(\{.*?\})\s*专区
# New regex pattern: <invoke>\s*(.*?)\s*</invoke>
# The old pattern breaks on nested JSON because \{.*?\} stops at first }
# The new pattern captures everything between tags, then raw_decode handles JSON

old_regex_line = '_TOOL_CALL_RE = re.compile(\n    r"' + OLD_TAG + r'\s*(\{.*?\})\s*' + OLD_TAG + '",\n    re.DOTALL,\n)'
new_regex_line = '_TOOL_CALL_RE = re.compile(\n    r"' + OPEN_TAG + r'\s*(.*?)\s*' + CLOSE_TAG + '",\n    re.DOTALL,\n)'

content = content.replace(old_regex_line, new_regex_line)
print("Fix 2: Main regex updated")

# ============================================================
# Fix 3: Replace _TOOL_SYSTEM_PROMPT
# ============================================================
prompt_start = '_TOOL_SYSTEM_PROMPT = """'
prompt_end_marker = '{tool_defs}"""'
idx_s = content.index(prompt_start)
idx_e = content.index(prompt_end_marker) + len(prompt_end_marker)

new_prompt = (
    '_TOOL_SYSTEM_PROMPT = """\n'
    '\n'
    'You are an AI assistant with access to tools. When you need to perform an action, you MUST call a tool using the EXACT format below. Do NOT describe what to do, do NOT show example commands.\n'
    '\n'
    'TOOL CALL FORMAT (use EXACTLY this format, no other format is accepted):\n'
    + OPEN_TAG + '\n'
    '{"name": "<tool_name>", "arguments": {<argument_key>: <argument_value>}}\n'
    + CLOSE_TAG + '\n'
    '\n'
    'CRITICAL RULES (violating any = WRONG response):\n'
    '1. To perform ANY action, output a tool call using the ' + OPEN_TAG + ' format above. NO EXCEPTIONS.\n'
    '2. NEVER say "you can use the command..." or "run this in your terminal" — CALL THE TOOL instead.\n'
    '3. NEVER wrap tool calls in markdown code blocks (```bash etc.)\n'
    '4. The JSON inside ' + OPEN_TAG + ' must be valid. Put "name" and "arguments" keys.\n'
    '5. You may add brief text BEFORE the tool call, but the tool call itself is mandatory when action is needed.\n'
    '6. After receiving [tool_result], continue the task or make another tool call.\n'
    '7. When in doubt about whether to use a tool, ALWAYS use the tool.\n'
    '8. Make sure to close the ' + CLOSE_TAG + ' tag after the JSON.\n'
    '\n'
    'EXAMPLES:\n'
    '\n'
    'User: "list files in current directory"\n'
    'Let me list the files for you.\n'
    + OPEN_TAG + '\n'
    '{"name": "Bash", "arguments": {"command": "ls -la"}}\n'
    + CLOSE_TAG + '\n'
    '\n'
    'User: "read the file main.py"\n'
    'I will read that file.\n'
    + OPEN_TAG + '\n'
    '{"name": "Read", "arguments": {"file_path": "main.py"}}\n'
    + CLOSE_TAG + '\n'
    '\n'
    'User: "what time is it"\n'
    'Let me check the current time.\n'
    + OPEN_TAG + '\n'
    '{"name": "Bash", "arguments": {"command": "date"}}\n'
    + CLOSE_TAG + '\n'
    '\n'
    'Available tools:\n'
    '{tool_defs}"""'
)

content = content[:idx_s] + new_prompt + content[idx_e:]
print("Fix 3: System prompt updated")

# ============================================================
# Fix 4: Replace _parse_tool_calls function
# ============================================================
func_start = 'def _parse_tool_calls(text: str, known_tools: list = None) -> list:'
func_end_marker = '\ndef _strip_tool_calls_from_text'
idx_fs = content.index(func_start)
idx_fe = content.index(func_end_marker)

new_func = (
    'def _parse_tool_calls(text: str, known_tools: list = None) -> list:\n'
    '    """Parse tool calls from model output. Supports ' + OPEN_TAG + ', markdown, prefix, and legacy formats."""\n'
    '    calls = []\n'
    '    seen_raw = set()\n'
    '    known_names = set()\n'
    '    if known_tools:\n'
    '        for t in known_tools:\n'
    '            known_names.add(t.get("name", ""))\n'
    '\n'
    '    def _try_parse(raw: str) -> dict | None:\n'
    '        raw = raw.strip()\n'
    '        # Strip markdown code fences if present inside the tag\n'
    '        if raw.startswith("```"):\n'
    '            raw = re.sub(r"^```(?:json)?\\s*\\n?", "", raw)\n'
    '            raw = re.sub(r"\\n?```\\s*$", "", raw)\n'
    '            raw = raw.strip()\n'
    '        try:\n'
    '            data, _ = json.JSONDecoder().raw_decode(raw)\n'
    '        except (json.JSONDecodeError, ValueError):\n'
    '            try:\n'
    '                data = json.loads(raw)\n'
    '            except (json.JSONDecodeError, ValueError):\n'
    '                log.warning("Failed to parse tool_call JSON: %s", raw[:200])\n'
    '                return None\n'
    '        if not isinstance(data, dict):\n'
    '            return None\n'
    '        name = data.get("name") or data.get("tool") or data.get("function", {}).get("name", "")\n'
    '        if not name:\n'
    '            return None\n'
    '        arguments = (\n'
    '            data.get("arguments")\n'
    '            or data.get("input")\n'
    '            or data.get("parameters")\n'
    '            or data.get("args")\n'
    '            or data.get("function", {}).get("arguments")\n'
    '            or {}\n'
    '        )\n'
    '        if not isinstance(arguments, dict):\n'
    '            arguments = {}\n'
    '        if known_names and name not in known_names:\n'
    '            lower_name = name.lower()\n'
    '            for kn in known_names:\n'
    '                if lower_name == kn.lower() or lower_name.replace("_", "") == kn.lower().replace("_", ""):\n'
    '                    name = kn\n'
    '                    break\n'
    '        return {"name": name, "input": arguments}\n'
    '\n'
    '    def _add_call(raw: str):\n'
    '        if raw in seen_raw:\n'
    '            return\n'
    '        seen_raw.add(raw)\n'
    '        parsed = _try_parse(raw)\n'
    '        if parsed:\n'
    '            parsed["id"] = f"toolu_{uuid.uuid4().hex[:24]}"\n'
    '            calls.append(parsed)\n'
    '\n'
    '    # 1. ' + OPEN_TAG + ' tag format (primary)\n'
    '    for match in _TOOL_CALL_RE.finditer(text):\n'
    '        _add_call(match.group(1))\n'
    '\n'
    '    # 2. Legacy Chinese tag format (backward compat)\n'
    '    _LEGACY_TAG_RE = re.compile(r"\\u4e13\\u533a\\s*(\\{.*?\\})\\s*\\u4e13\\u533a", re.DOTALL)\n'
    '    for match in _LEGACY_TAG_RE.finditer(text):\n'
    '        _add_call(match.group(1))\n'
    '\n'
    '    # 3. Markdown code block format\n'
    '    for match in _MD_TOOL_CALL_RE.finditer(text):\n'
    '        _add_call(match.group(1))\n'
    '\n'
    '    # 4. function_call:/tool_call: prefix format\n'
    '    for match in _PREFIX_CALL_RE.finditer(text):\n'
    '        _add_call(match.group(1))\n'
    '\n'
    '    # 5. Pure JSON block format (less specific, only if no other matches)\n'
    '    if not calls:\n'
    '        for match in _JSON_BLOCK_RE.finditer(text):\n'
    '            _add_call(match.group(1))\n'
    '\n'
    '    return calls\n'
    '\n'
)

content = content[:idx_fs] + new_func + content[idx_fe:]
print("Fix 4: _parse_tool_calls updated")

# ============================================================
# Fix 5: Replace _strip_tool_calls_from_text
# ============================================================
old_strip = (
    'def _strip_tool_calls_from_text(text: str) -> str:\n'
    '    """Remove tool call blocks from text (all supported formats)."""\n'
    '    text = _TOOL_CALL_RE.sub("", text)\n'
    '    text = _MD_TOOL_CALL_RE.sub("", text)\n'
    '    text = _PREFIX_CALL_RE.sub("", text)\n'
    '    text = _JSON_BLOCK_RE.sub("", text)\n'
    '    return text.strip()'
)

new_strip = (
    'def _strip_tool_calls_from_text(text: str) -> str:\n'
    '    """Remove tool call blocks from text (all supported formats)."""\n'
    '    text = _TOOL_CALL_RE.sub("", text)\n'
    '    _LEGACY_TAG_RE = re.compile(r"\\u4e13\\u533a\\s*\\{.*?\\}\\s*\\u4e13\\u533a", re.DOTALL)\n'
    '    text = _LEGACY_TAG_RE.sub("", text)\n'
    '    text = _MD_TOOL_CALL_RE.sub("", text)\n'
    '    text = _PREFIX_CALL_RE.sub("", text)\n'
    '    text = _JSON_BLOCK_RE.sub("", text)\n'
    '    text = re.sub(r"\\n{3,}", "\\n\\n", text)\n'
    '    return text.strip()'
)

content = content.replace(old_strip, new_strip)
print("Fix 5: _strip_tool_calls_from_text updated")

# ============================================================
# Fix 6: _translate_messages tool_use text format
# ============================================================
content = content.replace(
    'parts.append(f"' + OLD_TAG + '\\n{tc_json}\\n' + OLD_TAG + '")',
    'parts.append(f"' + OPEN_TAG + '\\n{tc_json}\\n' + CLOSE_TAG + '")'
)
print("Fix 6: _translate_messages tool_use format updated")

# ============================================================
# Fix 7: _non_stream_response missing known_tools
# ============================================================
content = content.replace(
    'tool_calls = _parse_tool_calls(full_content) if has_tools else []',
    'tool_calls = _parse_tool_calls(full_content, known_tools=tools) if has_tools else []'
)
print("Fix 7: _non_stream_response now passes known_tools")

# ============================================================
# Fix 8: create_anthropic_router missing tools passthrough
# ============================================================
content = content.replace(
    'return _stream_anthropic(client, messages, jc_body, model, api_key, has_tools)',
    'return _stream_anthropic(client, messages, jc_body, model, api_key, has_tools, tools=tools)'
)
content = content.replace(
    'return _non_stream_response(client, messages, jc_body, model, api_key, has_tools)',
    'return _non_stream_response(client, messages, jc_body, model, api_key, has_tools, tools=tools)'
)
print("Fix 8: Router now passes tools to both stream and non-stream paths")

with open("iflycode_2api/anthropic_handler.py", "w") as f:
    f.write(content)

print("\nAll fixes applied successfully!")
