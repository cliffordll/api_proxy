# 架构设计 - API Proxy（SDK 原生版）

> 核心理念：使用 OpenAI / Anthropic 官方 SDK 原生类型，通过抽象接口和注册机制实现良好封装与可扩展性。

## 1. 系统架构总览

```
                         API Proxy Service (FastAPI)
                        ┌─────────────────────────────────┐
                        │                                 │
  OpenAI 格式客户端 ──────►  /v1/chat/completions          │
                        │    │                            │
                        │    ▼                            │
                        │  OpenAI→Claude 转换器            │
                        │  (openai.types → anthropic.types)│
                        │    │                            │
                        │    ▼                            │         ┌──────────────┐
                        │  anthropic.AsyncAnthropic ──────────────► │ Claude API   │
                        │    │                            │         └──────────────┘
                        │    ▼                            │
                        │  Claude→OpenAI 转换器（响应）     │
                        │  (anthropic.types → openai.types)│
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
                        │  (anthropic.types → openai.types)│
                        │    │                            │
                        │    ▼                            │         ┌──────────────┐
                        │  openai.AsyncOpenAI ────────────────────► │ OpenAI API   │
                        │    │                            │         └──────────────┘
                        │    ▼                            │
                        │  OpenAI→Claude 转换器（响应）     │
                        │  (openai.types → anthropic.types)│
                        │    │                            │
                        │    ▼                            │
  Claude 格式客户端 ◄──────  Claude 格式响应               │
                        │                                 │
                        └─────────────────────────────────┘
```

## 2. 设计原则

| 原则 | 说明 |
|------|------|
| **接口抽象** | 客户端层和转换层通过 Protocol 定义抽象接口，各实现可独立替换 |
| **注册机制** | 通过 Provider 注册表管理客户端和转换器，新增 Provider 只需注册，不改路由层 |
| **SDK 原生** | 数据模型直接使用官方 SDK 类型，不自定义 Pydantic 模型 |
| **职责分离** | 路由层薄调度、转换层纯函数、客户端层封装 I/O，各层通过接口解耦 |
| **配置驱动** | 模型映射、上游地址等均通过配置管理，不硬编码 |

## 3. 依赖

```
# requirements.txt
fastapi>=0.110.0
uvicorn>=0.29.0
pydantic-settings>=2.2.0
pyyaml>=6.0.1
openai>=1.30.0          # AsyncOpenAI 客户端 + openai.types
anthropic>=0.49.0        # AsyncAnthropic 客户端 + anthropic.types
pytest>=8.1.0
pytest-asyncio>=0.23.0
```

## 4. 核心模块

### 4.1 抽象接口层 (Protocols)

定义客户端和转换器的抽象接口，所有实现必须遵循。

```python
# app/core/protocols.py

from typing import Protocol, Any, AsyncIterator, runtime_checkable

@runtime_checkable
class BaseClient(Protocol):
    """客户端抽象接口"""
    async def send(
        self, params: dict, api_key: str, stream: bool = False
    ) -> Any:
        """发送请求，非流式返回响应对象，流式返回异步迭代器"""
        ...

@runtime_checkable
class BaseConverter(Protocol):
    """转换器抽象接口"""
    def convert_request(self, request: dict) -> dict:
        """将源协议请求转换为目标协议请求"""
        ...

    def convert_response(self, response: Any) -> dict:
        """将目标协议响应转换为源协议响应"""
        ...

    def convert_stream_event(self, event: Any, state: dict) -> list:
        """将目标协议流式事件转换为源协议流式事件"""
        ...
```

### 4.2 Provider 注册表 (Registry)

集中管理所有 Provider 的客户端和转换器，路由层通过注册表获取实例。

```python
# app/core/registry.py

from dataclasses import dataclass

@dataclass
class ProviderEntry:
    """Provider 注册条目"""
    client: BaseClient
    request_converter: BaseConverter   # 入站协议 → 该 Provider 协议
    response_converter: BaseConverter  # 该 Provider 协议 → 入站协议

class ProviderRegistry:
    """Provider 注册表"""
    _providers: dict[str, ProviderEntry] = {}

    def register(self, name: str, entry: ProviderEntry) -> None: ...
    def get(self, name: str) -> ProviderEntry: ...
    def list_providers(self) -> list[str]: ...
```

**扩展方式**：新增 Provider（如 Gemini）只需：
1. 实现 `BaseClient` 和 `BaseConverter`
2. 调用 `registry.register("gemini", entry)` 注册
3. 添加对应路由（或复用通用路由）

### 4.3 客户端层 (Clients)

实现 `BaseClient` 接口，封装官方 SDK 调用。

#### `claude_client.py`

```python
import anthropic
from app.core.protocols import BaseClient

class ClaudeClient(BaseClient):
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def send(self, params: dict, api_key: str, stream: bool = False):
        client = anthropic.AsyncAnthropic(api_key=api_key, base_url=self.base_url)
        if not stream:
            return await client.messages.create(**params)
        return client.messages.stream(**params)
```

#### `openai_client.py`

```python
import openai
from app.core.protocols import BaseClient

class OpenAIClient(BaseClient):
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def send(self, params: dict, api_key: str, stream: bool = False):
        client = openai.AsyncOpenAI(api_key=api_key, base_url=self.base_url)
        if not stream:
            return await client.chat.completions.create(**params)
        return await client.chat.completions.create(**params, stream=True)
```

**封装要点**：
- 客户端实例化封装在类内部，外部只关心 `send()` 接口
- SDK 自动管理 Header（`x-api-key`、`Authorization: Bearer`、`anthropic-version`）
- base_url 通过构造函数注入，支持自定义上游地址

### 4.4 转换层 (Converters)

实现 `BaseConverter` 接口，纯函数逻辑封装为类方法，无 I/O，无副作用。

#### `openai_to_claude.py`

```python
from app.protocols import BaseConverter

class OpenAIToClaudeConverter(BaseConverter):
    def convert_request(self, request: dict) -> dict:
        """OpenAI 请求 dict → Claude MessageCreateParams"""
        ...

    def convert_response(self, response) -> dict:
        """anthropic.types.Message → OpenAI ChatCompletion dict"""
        ...

    def convert_stream_event(self, event, state: dict) -> list:
        """RawMessageStreamEvent → list[ChatCompletionChunk dict]"""
        ...
```

#### `claude_to_openai.py`

```python
from app.protocols import BaseConverter

class ClaudeToOpenAIConverter(BaseConverter):
    def convert_request(self, request: dict) -> dict:
        """Claude 请求 dict → OpenAI ChatCompletionCreateParams"""
        ...

    def convert_response(self, response) -> dict:
        """ChatCompletion → anthropic.types.Message dict"""
        ...

    def convert_stream_event(self, event, state: dict) -> list:
        """ChatCompletionChunk → list[str] (Claude SSE 事件行)"""
        ...
```

**SDK 类型速查**：

```python
# OpenAI SDK (openai.types.chat)
from openai.types.chat import (
    ChatCompletion, ChatCompletionChunk, ChatCompletionMessage,
    ChatCompletionMessageParam, ChatCompletionToolParam,
    ChatCompletionToolChoiceOptionParam,
)

# Anthropic SDK (anthropic.types)
from anthropic.types import (
    Message, MessageParam, MessageCreateParams,
    ContentBlock, TextBlock, ToolUseBlock,
    ToolParam, ToolChoiceParam, ToolResultBlockParam, Usage,
    RawMessageStreamEvent, RawMessageStartEvent,
    RawContentBlockStartEvent, RawContentBlockDeltaEvent,
    RawContentBlockStopEvent, RawMessageDeltaEvent, RawMessageStopEvent,
)
```

### 4.5 路由层 (Routes)

薄层调度，通过注册表获取客户端和转换器，不直接依赖具体实现。

```python
# app/routes/openai_compat.py — POST /v1/chat/completions
# app/routes/claude_compat.py — POST /v1/messages

# 路由层伪代码
async def handle_request(request, provider_name: str):
    provider = registry.get(provider_name)
    converted = provider.request_converter.convert_request(request_body)
    response = await provider.client.send(converted, api_key, stream)
    return provider.response_converter.convert_response(response)
```

**职责边界**：
- 接收请求，提取 API Key
- 通过注册表获取对应 Provider
- 调用转换器和客户端
- 返回响应（非流式 JSON / 流式 SSE）

### 4.6 配置层 (Config) — 移入 core

```python
# app/core/config.py
class Settings(BaseSettings):
    anthropic_base_url: str = "https://api.anthropic.com"
    openai_base_url: str = "https://api.openai.com"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    default_max_tokens: int = 4096
    model_mapping_file: str = "config/model_mapping.yaml"
```

## 5. 关键数据映射

### 5.1 请求：OpenAI → Claude

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
  tool_calls             ->     content: [{type: "tool_use", ...}]
max_tokens               ->     max_tokens (必填，无则用默认值)
temperature              ->     temperature
top_p                    ->     top_p
stop                     ->     stop_sequences
stream                   ->     stream
tools                    ->     tools (schema 结构转换)
tool_choice              ->     tool_choice (值映射)
```

### 5.2 请求：Claude → OpenAI

```
Claude                          OpenAI
─────────────────────────────────────────────────
model                    ->     model (查映射表，未命中透传)
system                   ->     messages[0] {role: "system"}
messages                 ->     messages (追加在 system 之后)
  role: user             ->     role: user
  role: assistant        ->     role: assistant
  tool_result content    ->     role: tool message
  tool_use content       ->     assistant message + tool_calls
max_tokens               ->     max_tokens
temperature              ->     temperature
top_p                    ->     top_p
stop_sequences           ->     stop
stream                   ->     stream
tools                    ->     tools (schema 结构转换)
tool_choice              ->     tool_choice (值映射)
```

### 5.3 响应：Claude → OpenAI

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

### 5.4 响应：OpenAI → Claude

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

## 6. 流式处理

### 6.1 Claude SSE → OpenAI SSE

```python
# SDK 原生事件流
async with claude_client.send(params, key, stream=True) as stream:
    async for event in stream:
        # event: RawMessageStreamEvent（已类型化）
        chunks = converter.convert_stream_event(event, state)
```

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

### 6.2 OpenAI SSE → Claude SSE

```python
# SDK 原生 chunk 流
stream = await openai_client.send(params, key, stream=True)
async for chunk in stream:
    # chunk: ChatCompletionChunk（已类型化）
    events = converter.convert_stream_event(chunk, state)
```

| OpenAI 事件 | 转换为 Claude |
|-------------|--------------|
| 首个 chunk (role) | `message_start` + `content_block_start` |
| delta.content | `content_block_delta(text_delta)` |
| delta.tool_calls (首次出现) | `content_block_stop(上一个块)` + `content_block_start(tool_use)` |
| delta.tool_calls (后续) | `content_block_delta(input_json_delta)` |
| finish_reason 出现 | `content_block_stop` + `message_delta(stop_reason)` |
| `[DONE]` | `message_stop` |

## 7. Tool Calling 转换

### 7.1 Tools 定义

```python
# OpenAI 格式
{"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}

# Claude 格式
{"name": "...", "description": "...", "input_schema": {...}}
```

### 7.2 tool_choice 映射

| OpenAI | Claude |
|--------|--------|
| `"none"` | `{"type": "none"}` |
| `"auto"` | `{"type": "auto"}` |
| `"required"` | `{"type": "any"}` |
| `{"type":"function","function":{"name":"X"}}` | `{"type": "tool", "name": "X"}` |

### 7.3 Tool 结果消息

```
OpenAI: {role: "tool", tool_call_id: "xxx", content: "..."}
Claude: {role: "user", content: [{type: "tool_result", tool_use_id: "xxx", content: "..."}]}
```

## 8. 错误处理

利用 SDK 内置异常体系：

| SDK 异常 | HTTP 状态码 | 说明 |
|---------|-----------|------|
| `AuthenticationError` | 401 | 认证失败 |
| `RateLimitError` | 429 | 频率限制 |
| `BadRequestError` | 400 | 请求参数错误 |
| `InternalServerError` | 502 | 上游服务错误 |
| `APITimeoutError` | 504 | 网络超时 |
| `APIConnectionError` | 502 | 连接失败 |

错误格式映射：
```python
# OpenAI 错误格式
{"error": {"message": "...", "type": "...", "code": "..."}}

# Claude 错误格式
{"type": "error", "error": {"type": "...", "message": "..."}}
```

## 9. 模型映射

### 9.1 配置文件 `config/model_mapping.yaml`

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

### 9.2 加载策略

1. 内置默认映射（硬编码兜底）
2. 若 `model_mapping_file` 路径存在，加载 YAML 覆盖默认值
3. 请求中的 model 未命中映射表时，原样透传给上游

## 10. 认证透传

```
客户端请求                    代理提取                    上游请求
────────────────────────────────────────────────────────────────
Authorization: Bearer sk-xxx  -> api_key = "sk-xxx"  -> 对应上游 Header
x-api-key: sk-ant-xxx         -> api_key = "sk-ant-xxx" -> 对应上游 Header
```

## 11. 项目结构

```
api_proxy/
├── CLAUDE.md
├── main.py                      # 应用入口 (python main.py 启动)
├── requirements.txt
├── config/
│   └── model_mapping.yaml       # 模型映射配置
├── .env.example
├── docs/
│   ├── architecture.md          # 本文档
│   └── feature.md               # 开发计划
├── app/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            # Settings + 模型映射加载
│   │   ├── protocols.py         # 抽象接口定义 (BaseClient, BaseConverter)
│   │   ├── registry.py          # Provider 注册表
│   │   └── errors.py            # 错误处理工具函数
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── openai_compat.py     # POST /v1/chat/completions
│   │   └── claude_compat.py     # POST /v1/messages
│   ├── converters/
│   │   ├── __init__.py
│   │   ├── openai_to_claude.py  # OpenAIToClaudeConverter
│   │   └── claude_to_openai.py  # ClaudeToOpenAIConverter
│   └── clients/
│       ├── __init__.py
│       ├── claude_client.py     # ClaudeClient (anthropic.AsyncAnthropic)
│       └── openai_client.py     # OpenAIClient (openai.AsyncOpenAI)
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_converters/
    │   ├── __init__.py
    │   ├── test_openai_to_claude.py
    │   └── test_claude_to_openai.py
    └── test_routes/
        ├── __init__.py
        ├── test_openai_compat.py
        └── test_claude_compat.py
```

**与旧版结构差异**：
- 新增 `app/core/` — 集中存放核心基础模块（config、protocols、registry、errors）
- `app/config.py` 移入 `app/core/config.py`
- 删除 `app/models/` — 不再维护自定义数据模型
- 客户端和转换器从模块级函数改为类实现

## 12. 扩展预留

| 扩展项 | 扩展方式 |
|--------|---------|
| **新增 Provider (如 Gemini)** | 实现 `BaseClient` + `BaseConverter`，注册到 `ProviderRegistry`，添加路由 |
| **多模态 (图片/文件)** | SDK 类型已原生支持，转换器添加对应分支即可 |
| **认证中间件** | FastAPI middleware，不影响转换和客户端层 |
| **多上游负载均衡** | 客户端类内部实现 Key 轮询，接口不变 |
| **请求日志/监控** | FastAPI middleware + 结构化日志 |
| **缓存** | 路由层添加缓存装饰器 |
