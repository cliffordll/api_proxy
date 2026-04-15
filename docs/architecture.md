# 架构设计 - API Proxy

## 1. 系统架构总览

```
                         API Proxy Service (FastAPI)
                        ┌─────────────────────────────────┐
                        │                                 │
  OpenAI 格式客户端 ──────►  /v1/chat/completions          │
                        │    │                            │
                        │    ▼                            │
                        │  OpenAI→Claude 转换器            │
                        │    │                            │
                        │    ▼                            │         ┌──────────────┐
                        │  Claude Client ─────────────────────────► │ Claude API   │
                        │    │                            │         └──────────────┘
                        │    ▼                            │
                        │  Claude→OpenAI 转换器（响应）     │
                        │    │                            │
                        │    ▼                            │
  OpenAI 格式客户端 ◄──────  OpenAI 格式响应               │
                        │                                 │
                        │─────────────────────────────────│
                        │                                 │
  Claude 格式客户端 ──────►  /v1/messages                  │
                        │    │                            │
                        │    ▼                            │
                        │  Claude→OpenAI 转换器            │
                        │    │                            │
                        │    ▼                            │         ┌──────────────┐
                        │  OpenAI Client ─────────────────────────► │ OpenAI API   │
                        │    │                            │         └──────────────┘
                        │    ▼                            │
                        │  OpenAI→Claude 转换器（响应）     │
                        │    │                            │
                        │    ▼                            │
  Claude 格式客户端 ◄──────  Claude 格式响应               │
                        │                                 │
                        └─────────────────────────────────┘
```

## 2. 设计决策

| 决策项 | 结论 | 说明 |
|--------|------|------|
| 方向 | **双向** | 同时支持 OpenAI->Claude 和 Claude->OpenAI |
| 多模态 | **暂不支持，预留扩展** | content 块采用多态设计，当前只实现 text 类型 |
| Tool Calling | **首版支持** | 完整支持 tools/tool_choice/tool_calls/tool_use 互转 |
| 认证 | **透传 Key** | 从请求 Header 提取 Key 直接传给上游，不做自定义鉴权 |
| 模型映射 | **配置文件加载** | 默认内置映射 + 支持 YAML 配置文件覆盖，未命中则透传 |

## 3. 核心模块

### 3.1 路由层 (Routes)

薄层，仅负责接收请求、提取 Header、调度转换和客户端、返回响应。

- **`openai_compat.py`** — `POST /v1/chat/completions`
- **`claude_compat.py`** — `POST /v1/messages`

### 3.2 转换层 (Converters)

**核心层**。纯函数，无 I/O，无副作用，方便单元测试。

#### `openai_to_claude.py`

| 函数 | 输入 | 输出 |
|------|------|------|
| `convert_request(openai_req)` | OpenAI 请求体 | Claude 请求体 |
| `convert_response(claude_resp)` | Claude 响应体 | OpenAI 响应体 |
| `convert_stream_event(claude_event, state)` | Claude SSE 事件 | OpenAI SSE 数据行 |

#### `claude_to_openai.py`

| 函数 | 输入 | 输出 |
|------|------|------|
| `convert_request(claude_req)` | Claude 请求体 | OpenAI 请求体 |
| `convert_response(openai_resp)` | OpenAI 响应体 | Claude 响应体 |
| `convert_stream_event(openai_event, state)` | OpenAI SSE 数据行 | Claude SSE 事件 |

> 流式转换函数接收 `state` 参数（可变字典），用于跨事件累积 tool_call 参数片段。

### 3.3 客户端层 (Clients)

使用 `httpx.AsyncClient` 长连接池，统一封装：

- **`claude_client.py`** — 调用 Anthropic API，设置 `x-api-key` + `anthropic-version` Header
- **`openai_client.py`** — 调用 OpenAI API，设置 `Authorization: Bearer` Header

两个客户端对外暴露统一接口：

```python
async def send(request_body: dict, api_key: str, stream: bool) -> Response | AsyncIterator
```

### 3.4 数据模型层 (Models)

Pydantic v2 模型，作为各层的数据契约。

**多态 content 设计**（预留多模态扩展）：

```python
# 当前实现
class TextContent(BaseModel):
    type: Literal["text"]
    text: str

# 未来扩展（暂不实现）
class ImageContent(BaseModel):
    type: Literal["image"]
    source: ImageSource

# 联合类型，扩展时只需在此添加
ContentBlock = TextContent  # 未来: TextContent | ImageContent | ...
```

### 3.5 配置层 (Config)

```python
class Settings(BaseSettings):
    # 上游 URL
    anthropic_base_url: str = "https://api.anthropic.com"
    openai_base_url: str = "https://api.openai.com"

    # 服务
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # 默认参数
    default_max_tokens: int = 4096

    # 模型映射配置文件路径
    model_mapping_file: str = "config/model_mapping.yaml"
```

## 4. 关键数据映射

### 4.1 请求：OpenAI -> Claude

```
OpenAI                          Claude
─────────────────────────────────────────────────
model                    ->     model (查映射表，未命中透传)
messages                 ->     system + messages
  role: system           ->     提取到顶层 system 参数
  role: user             ->     role: user
  role: assistant        ->     role: assistant
  role: tool             ->     role: user + tool_result content block
  content (string)       ->     content: [{type: "text", text: ...}]
  content (array)        ->     content (映射各 text 块；图片块暂跳过)
  tool_calls             ->     content: [{type: "tool_use", ...}]
max_tokens               ->     max_tokens (必填，无则用默认值)
temperature              ->     temperature
top_p                    ->     top_p
stop                     ->     stop_sequences
stream                   ->     stream
tools                    ->     tools (schema 结构转换)
tool_choice              ->     tool_choice (值映射)
```

### 4.2 请求：Claude -> OpenAI

```
Claude                          OpenAI
─────────────────────────────────────────────────
model                    ->     model (查映射表，未命中透传)
system                   ->     messages[0] {role: "system"}
messages                 ->     messages (追加在 system 之后)
  role: user             ->     role: user
  role: assistant        ->     role: assistant
  tool_result content    ->     role: tool message
  content (array)        ->     合并 text 块为 string 或保留 array
  tool_use content       ->     assistant message + tool_calls
max_tokens               ->     max_tokens
temperature              ->     temperature
top_p                    ->     top_p
stop_sequences           ->     stop
stream                   ->     stream
tools                    ->     tools (schema 结构转换)
tool_choice              ->     tool_choice (值映射)
```

### 4.3 响应：Claude -> OpenAI

```
Claude Response                 OpenAI Response
─────────────────────────────────────────────────
id                       ->     id (加 "chatcmpl-" 前缀)
model                    ->     model
content[].text           ->     choices[0].message.content
content[].tool_use       ->     choices[0].message.tool_calls[]
stop_reason: end_turn    ->     finish_reason: stop
stop_reason: max_tokens  ->     finish_reason: length
stop_reason: tool_use    ->     finish_reason: tool_calls
usage.input_tokens       ->     usage.prompt_tokens
usage.output_tokens      ->     usage.completion_tokens
```

### 4.4 响应：OpenAI -> Claude

```
OpenAI Response                 Claude Response
─────────────────────────────────────────────────
id                       ->     id (去前缀或保留)
model                    ->     model
choices[0].message       ->     content[]
  .content               ->     [{type: "text", text: ...}]
  .tool_calls            ->     [{type: "tool_use", ...}]
finish_reason: stop      ->     stop_reason: end_turn
finish_reason: length    ->     stop_reason: max_tokens
finish_reason: tool_calls ->    stop_reason: tool_use
usage.prompt_tokens      ->     usage.input_tokens
usage.completion_tokens  ->     usage.output_tokens
```

## 5. 流式处理

### 5.1 Claude SSE -> OpenAI SSE

| Claude 事件 | 转换为 OpenAI |
|-------------|--------------|
| `message_start` | 首个 chunk: `{choices: [{delta: {role: "assistant"}}]}` |
| `content_block_start(text)` | 无输出（等待 delta） |
| `content_block_delta(text_delta)` | `{choices: [{delta: {content: "..."}}]}` |
| `content_block_start(tool_use)` | `{choices: [{delta: {tool_calls: [{index, id, function: {name}}]}}]}` |
| `content_block_delta(input_json_delta)` | `{choices: [{delta: {tool_calls: [{index, function: {arguments: "..."}}]}}]}` |
| `content_block_stop` | 无输出 |
| `message_delta` | `{choices: [{finish_reason: "..."}]}`，附带 usage |
| `message_stop` | `data: [DONE]` |

### 5.2 OpenAI SSE -> Claude SSE

| OpenAI 事件 | 转换为 Claude |
|-------------|--------------|
| 首个 chunk (role) | `message_start` + `content_block_start` |
| delta.content | `content_block_delta(text_delta)` |
| delta.tool_calls (首次出现) | `content_block_stop(上一个块)` + `content_block_start(tool_use)` |
| delta.tool_calls (后续) | `content_block_delta(input_json_delta)` |
| finish_reason 出现 | `content_block_stop` + `message_delta(stop_reason)` |
| `[DONE]` | `message_stop` |

## 6. Tool Calling 转换

### 6.1 Tools 定义：OpenAI -> Claude

```python
# OpenAI 格式
{"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}

# Claude 格式
{"name": "...", "description": "...", "input_schema": {...}}
```

### 6.2 tool_choice 映射

| OpenAI | Claude |
|--------|--------|
| `"none"` | `{"type": "none"}` |  
| `"auto"` | `{"type": "auto"}` |
| `"required"` | `{"type": "any"}` |
| `{"type":"function","function":{"name":"X"}}` | `{"type": "tool", "name": "X"}` |

### 6.3 Tool 结果消息

```
OpenAI: {role: "tool", tool_call_id: "xxx", content: "..."}
Claude: {role: "user", content: [{type: "tool_result", tool_use_id: "xxx", content: "..."}]}
```

## 7. 模型映射

### 7.1 配置文件 `config/model_mapping.yaml`

```yaml
openai_to_claude:
  gpt-4o: claude-sonnet-4-6-20250514
  gpt-4-turbo: claude-sonnet-4-6-20250514
  gpt-4: claude-opus-4-6-20250514
  gpt-3.5-turbo: claude-haiku-4-5-20251001

claude_to_openai:
  claude-opus-4-6-20250514: gpt-4
  claude-sonnet-4-6-20250514: gpt-4o
  claude-haiku-4-5-20251001: gpt-3.5-turbo
```

### 7.2 加载策略

1. 内置默认映射（硬编码兜底）
2. 若 `model_mapping_file` 路径存在，加载 YAML 覆盖默认值
3. 请求中的 model 未命中映射表时，原样透传给上游

## 8. 认证透传

```
客户端请求                    代理提取                    上游请求
────────────────────────────────────────────────────────────────
Authorization: Bearer sk-xxx  -> api_key = "sk-xxx"  -> 对应上游 Header
x-api-key: sk-ant-xxx         -> api_key = "sk-ant-xxx" -> 对应上游 Header
```

- `/v1/chat/completions` 端点：从 `Authorization: Bearer` 提取，转为 Claude 的 `x-api-key`
- `/v1/messages` 端点：从 `x-api-key` 提取，转为 OpenAI 的 `Authorization: Bearer`

## 9. 错误处理

上游错误转换为目标协议格式：

| 场景 | 行为 |
|------|------|
| 上游返回 4xx/5xx | 解析错误体，转换为目标协议的错误格式 |
| 上游连接超时 | 返回 504 Gateway Timeout |
| 上游连接拒绝 | 返回 502 Bad Gateway |
| 请求体校验失败 | 返回 400，使用目标协议的错误格式 |

### 错误格式映射

```python
# OpenAI 错误格式
{"error": {"message": "...", "type": "...", "code": "..."}}

# Claude 错误格式
{"type": "error", "error": {"type": "...", "message": "..."}}
```

## 10. 项目结构

```
api_proxy/
├── CLAUDE.md
├── main.py                      # 应用入口 (python main.py 启动)
├── requirements.txt
├── config/
│   └── model_mapping.yaml       # 模型映射配置
├── .env.example                 # 环境变量示例
├── docs/
│   ├── architecture.md          # 本文档
│   └── feature.md               # 开发计划
├── app/
│   ├── __init__.py
│   ├── config.py                # Settings + 模型映射加载
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── openai_compat.py     # POST /v1/chat/completions
│   │   └── claude_compat.py     # POST /v1/messages
│   ├── converters/
│   │   ├── __init__.py
│   │   ├── openai_to_claude.py  # 请求/响应/流 转换
│   │   └── claude_to_openai.py  # 请求/响应/流 转换
│   ├── clients/
│   │   ├── __init__.py
│   │   ├── claude_client.py     # Anthropic API 调用
│   │   └── openai_client.py     # OpenAI API 调用
│   └── models/
│       ├── __init__.py
│       ├── openai_models.py     # OpenAI Pydantic 模型
│       └── claude_models.py     # Claude Pydantic 模型
└── tests/
    ├── __init__.py
    ├── conftest.py              # 测试 fixtures
    ├── test_converters/
    │   ├── __init__.py
    │   ├── test_openai_to_claude.py
    │   └── test_claude_to_openai.py
    └── test_routes/
        ├── __init__.py
        ├── test_openai_compat.py
        └── test_claude_compat.py
```

## 11. 扩展预留

当前架构为以下能力预留了扩展点，暂不实现：

| 扩展项 | 扩展方式 |
|--------|---------|
| **多模态 (图片/文件)** | Models 层 ContentBlock 联合类型添加新类型，Converters 添加对应分支 |
| **认证中间件** | FastAPI middleware，在路由层之前拦截，不影响转换和客户端层 |
| **多上游负载均衡** | Clients 层内部实现 Key 轮询，对外接口不变 |
| **请求日志/监控** | FastAPI middleware + 结构化日志 |
| **缓存** | 路由层添加缓存装饰器，按请求 hash 缓存响应 |
