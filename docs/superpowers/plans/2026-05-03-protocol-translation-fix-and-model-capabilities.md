# Protocol Translation Fix + Model Capability UI Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** Fix the Anthropic protocol translation layer so tool_use works reliably (tag format, known_tools passthrough, nested JSON parsing), and add model capability differentiation (coding vs chat-only) to the admin UI.

**Architecture:** Anthropic tool_use request -> _translate_messages injects tool instruction system prompt with INVOKE_TAG format -> upstream SparkDesk generates text with INVOKE_TAG-wrapped JSON -> _parse_tool_calls extracts tool calls using raw_decode for nested JSON -> returns Anthropic-format tool_use content blocks. Frontend: sparkModels.ts adds capability flags -> AccountDetail table shows badges -> Chat page shows warnings.

**Tag format convention:** In this plan, `INVOKE_TAG` refers to the XML tag pair used for tool calls. The opening tag is a 7-character string starting with `<` and ending with `>`, and the closing tag adds `/` after `<`. The actual tag name will be applied via Python script in Step 1.

**Tech Stack:** Python 3.12, FastAPI, React 19, TypeScript 5, Ant Design 6, Vite 8

**Risks:**
- Task 1 changes the tool call tag format — existing conversations with old format cached in IndexedDB won't be re-parsed -> mitigation: backward compat regex still matches old format
- Task 1 uses Python script to modify anthropic_handler.py because XML tags conflict with editing tools -> mitigation: py_compile verification after each change
- Task 1 regex change from `\{.*?\}` to `.*?` could over-match -> mitigation: _try_parse uses raw_decode which only extracts valid JSON

---

### Task 1: Fix anthropic_handler.py Protocol Translation Pipeline

**Depends on:** None
**Files:**
- Modify: `iflycode_proxy/anthropic_handler.py` (lines 20-27, 47-86, 155-221, 223-229, 274, 465, 570-572)

**Issues being fixed:**
1. Tag format uses Chinese characters instead of proper XML tags
2. `_TOOL_CALL_TAG_OPEN`/`_TOOL_CALL_TAG_CLOSE` constants defined but never used
3. `_TOOL_CALL_RE` regex uses `\{.*?\}` which breaks on nested JSON objects
4. `_non_stream_response` line 465 doesn't pass `known_tools=tools`
5. `create_anthropic_router` lines 570-572 don't pass `tools=tools`

- [ ] **Step 1: Apply all fixes to anthropic_handler.py via Python script**

Because the file contains XML-like tags that conflict with editing tools, all changes must be applied via a single Python script that handles the 7 fixes atomically.

```bash
cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api
python3 apply_protocol_fixes.py
```

The script `apply_protocol_fixes.py` will be created in Step 1a below.

- [ ] **Step 1a: Create the fix script — apply_protocol_fixes.py**

Create a Python script at the project root that reads `iflycode_proxy/anthropic_handler.py`, applies all 7 fixes, and writes the result back.

The script performs these changes:
1. Replace `_TOOL_CALL_TAG_OPEN = "OLD_TAG"` with `_TOOL_CALL_TAG_OPEN = "INVOKE_OPEN"` (7-char XML opening tag)
2. Replace `_TOOL_CALL_TAG_CLOSE = "OLD_TAG"` with `_TOOL_CALL_TAG_CLOSE = "INVOKE_CLOSE"` (9-char XML closing tag)
3. Replace the main `_TOOL_CALL_RE` regex from `OLD_TAG\s*(\{.*?\})\s*OLD_TAG` to `INVOKE_OPEN\s*(.*?)\s*INVOKE_CLOSE` (fixes nested JSON bug)
4. Replace `_TOOL_SYSTEM_PROMPT` to use the new tag format
5. Replace `_parse_tool_calls` to use `json.JSONDecoder().raw_decode()` and add legacy regex for backward compat
6. Replace `_strip_tool_calls_from_text` to handle both new and legacy formats
7. Fix `_translate_messages` tool_use text format to use new tags
8. Fix `_non_stream_response` to pass `known_tools=tools`
9. Fix `create_anthropic_router` to pass `tools=tools` to both stream and non-stream paths

- [ ] **Step 2: Verify Python syntax**

```bash
cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api
python3 -m py_compile iflycode_proxy/anthropic_handler.py && echo "SYNTAX OK" || echo "SYNTAX ERROR"
```

Expected:
  - Exit code: 0
  - Output contains: "SYNTAX OK"

- [ ] **Step 3: Verify all fixes were applied correctly**

```bash
cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api
python3 -c "
with open('iflycode_proxy/anthropic_handler.py', 'r') as f:
    content = f.read()

checks = [
    ('known_tools=tools', 'known_tools passthrough in _non_stream_response'),
    ('tools=tools', 'tools parameter in router calls'),
    ('raw_decode', 'JSON raw_decode for nested objects'),
    ('_LEGACY_TAG_RE', 'Backward compat regex for old format'),
]
all_ok = True
for pattern, desc in checks:
    if pattern in content:
        print(f'OK: {desc}')
    else:
        print(f'FAIL: {desc} NOT found')
        all_ok = False

if all_ok:
    print('All checks PASSED')
else:
    print('Some checks FAILED')
"
```

Expected:
  - Exit code: 0
  - Output contains: "All checks PASSED"

- [ ] **Step 4: Commit**

```bash
cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api
git add iflycode_proxy/anthropic_handler.py apply_protocol_fixes.py && git commit -m "fix(anthropic): fix tool_use protocol - new tag format, known_tools passthrough, nested JSON parsing, backward compat"
```

---

### Task 2: Add Model Capability Fields to sparkModels.ts

**Depends on:** None
**Files:**
- Modify: `web/src/data/sparkModels.ts:1-13` (SparkModelInfo interface)
- Modify: `web/src/data/sparkModels.ts:15-102` (7 model data objects)

- [ ] **Step 1: Add supportsToolUse and supportsCoding to SparkModelInfo interface**

File: `web/src/data/sparkModels.ts:1-13`

Add two new fields to the interface after `tierLabel`:

```typescript
  supportsToolUse: boolean;
  supportsCoding: boolean;
```

- [ ] **Step 2: Add capability values to all 7 models**

Add at the end of each model object (after `tierLabel`):

| Model | supportsToolUse | supportsCoding |
|-------|----------------|----------------|
| 4.0Ultra | true | true |
| max-32k | true | true |
| generalv3.5 | true | true |
| pro-128k | true | true |
| generalv3 | true | false |
| lite | false | false |
| kjwx | false | false |

- [ ] **Step 3: Verify TypeScript compilation**

```bash
cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api/web
npx tsc --noEmit --pretty 2>&1 | head -30
```

Expected:
  - Exit code: 0
  - Output does NOT contain: "error TS" related to sparkModels

- [ ] **Step 4: Commit**

```bash
cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api
git add web/src/data/sparkModels.ts && git commit -m "feat(models): add supportsToolUse and supportsCoding fields to spark model data"
```

---

### Task 3: Show Model Capability Badges in AccountDetail

**Depends on:** Task 2
**Files:**
- Modify: `web/src/pages/AccountDetail.tsx:363-372` (model table capability column)

- [ ] **Step 1: Update model table capability column to show tool_use and coding badges**

File: `web/src/pages/AccountDetail.tsx:363-372`

Replace the "capabilities" column render function with one that shows `编码` (purple) and `工具调用` (cyan) Tag components before the existing capability tags:

```typescript
                {
                  title: '能力',
                  key: 'capabilities',
                  render: (_: unknown, record: any) => (
                    <Space size={[4, 4]} wrap>
                      {record.supportsCoding && <Tag color="purple" style={{ fontSize: 11 }}>编码</Tag>}
                      {record.supportsToolUse && <Tag color="cyan" style={{ fontSize: 11 }}>工具调用</Tag>}
                      {record.capabilities.slice(0, 2).map((c: string) => <Tag key={c} color="blue" style={{ fontSize: 11 }}>{c}</Tag>)}
                      {record.capabilities.length > 2 && <Tag style={{ fontSize: 11 }}>+{record.capabilities.length - 2}</Tag>}
                    </Space>
                  ),
                },
```

- [ ] **Step 2: Verify TypeScript compilation**

```bash
cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api/web
npx tsc --noEmit --pretty 2>&1 | head -20
```

Expected:
  - Exit code: 0

- [ ] **Step 3: Commit**

```bash
cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api
git add web/src/pages/AccountDetail.tsx && git commit -m "feat(ui): show tool_use and coding capability badges in account detail model table"
```

---

### Task 4: Add Model Capability Hints to Chat Page

**Depends on:** Task 2
**Files:**
- Modify: `web/src/pages/Chat.tsx:264-272` (model Select options)
- Modify: `web/src/pages/Chat.tsx:276` (add capability hint text after model selector)

- [ ] **Step 1: Add [纯聊天] label for non-coding models in Chat model selector**

File: `web/src/pages/Chat.tsx:264-272`

Replace the options array in the model Select. Add `${!m.supportsCoding ? ' [纯聊天]' : ''}` to the label:

```typescript
            options={[
              { value: '', label: '默认模型（服务器自动选择）' },
              ...SPARK_MODELS.filter(m => m.status === 'available').map(m => ({
                value: m.domain,
                label: `${m.name}${authorizedModels.has(m.domain) ? '' : '（未授权）'}${!m.supportsCoding ? ' [纯聊天]' : ''}`,
                disabled: !authorizedModels.has(m.domain),
              })),
            ]}
```

- [ ] **Step 2: Add capability warning text below model selector when non-tool-use model is selected**

File: `web/src/pages/Chat.tsx` — add inside the `<Space wrap>` block, after the model Select and before the Popconfirm:

```typescript
          {selectedModel && !SPARK_MODELS.find(m => m.domain === selectedModel)?.supportsToolUse && (
            <Typography.Text type="warning" style={{ fontSize: 12 }}>
              当前模型不支持工具调用，仅适合纯对话
            </Typography.Text>
          )}
```

- [ ] **Step 3: Verify TypeScript compilation**

```bash
cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api/web
npx tsc --noEmit --pretty 2>&1 | head -20
```

Expected:
  - Exit code: 0

- [ ] **Step 4: Commit**

```bash
cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api
git add web/src/pages/Chat.tsx && git commit -m "feat(ui): add model capability hints in chat page - show chat-only label and tool_use warning"
```
