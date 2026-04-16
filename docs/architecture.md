# 架构设计 - API Proxy

> 核心理念：配置驱动，一个 `chat()` 调用走完全程。Provider 决定"调谁"，Converter 决定"格式怎么转"，Proxy 封装完整流程，路由层只做 SSE 包装。

## 1. 整体架构

```
用户请求
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│                       路由层 (Routes)                        │
│  /v1/chat/completions   /v1/responses   /v1/messages         │
│                                                              │
│  极薄：认证提取 + proxy.chat() + SSE 包装                     │
└─────────┬──────────────────┬──────────────────┬──────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌──────────────────────────────────────────────────────────────┐
│                       Proxy.chat()                           │
│                                                              │
│  封装完整流程：                                                │
│  convert_request → client.chat → convert_response/stream     │
│                                                              │
│  路由层只需一行调用，拿到最终格式的 dict 或 str 流               │
├────────────────────┬─────────────────────────────────────────┤
│ 转换层 (Converter)  │ 客户端层 (Client)                       │
│                    │                                         │
│ 纯格式转换          │ 纯传输，统一 chat() 接口                  │
│ dict/str in/out    │ 输入 dict / 输出 dict|str                │
│                    │ SDK 细节封装在内部                        │
│ 6 个转换器:         │                                         │
│ CompletionsFrom*   │ claude ──► ClaudeClient (anthropic SDK)  │
│ MessagesFrom*      │ openai ──► OpenAIClient (openai SDK)    │
│ ResponsesFrom*     │ httpx  ──► HttpxClient  (通用 HTTP)      │
│                    │ mockup ──► MockupClient (调试模式)        │
└────────────────────┴─────────────────────────────────────────┘
          ▲
          │ load_providers()
┌──────────────────────────────────────────────────────────────┐
│                       配置层                                  │
│  config/providers.yaml → 自动创建 Client + Converter → Proxy │
└──────────────────────────────────────────────────────────────┘
```

### 三种接口格式

| 格式 | 端点 | 特征 |
|------|------|------|
| **Completions** | `/v1/chat/completions` | `messages` 数组，响应 `ChatCompletion`（`choices[].message`） |
| **Responses** | `/v1/responses` | `input` + `instructions`，响应 `Response`（`output[]` items） |
| **Messages** | `/v1/messages` | `messages` 数组 + `system`，响应 `Message`（`content[]` blocks） |

### 默认组合

| 接口名 | 路由路径 | Provider | interface | Converter | 转换路径 |
|--------|---------|----------|-----------|-----------|---------|
| `completions` | `/v1/chat/completions` | `claude` | `messages` | `CompletionsFromMessages` | Completions → Messages → Completions |
| `responses` | `/v1/responses` | `claude` | `messages` | `ResponsesFromMessages` | Responses → Messages → Responses |
| `messages` | `/v1/messages` | `openai` | `completions` | `MessagesFromCompletions` | Messages → Completions → Messages |

### 扩展示例（只改配置）

| 接口名 | Provider | interface | Converter | 说明 |
|--------|----------|-----------|-----------|------|
| `messages` | `ollama` | `completions` | `MessagesFromCompletions` | 切换上游为 Ollama |
| `completions` | `httpx` | `completions` | — (透传) | 通过通用 HTTP 接入任意兼容 API |
| `responses` | `openai` | `responses` | — (透传) | 切换上游为 OpenAI |
| `completions` | `mockup` | `messages` | `CompletionsFromMessages` | 调试模式 |

## 2. 设计原则

| 原则 | 说明 |
|------|------|
| **一次调用** | 路由层调 `route.chat(body, api_key, stream)` 即拿到最终结果，不编排内部流程 |
| **两层解耦** | Provider 管终端（调谁），Converter 管格式（怎么转），通过配置绑定 |
| **统一传输接口** | Client 层统一 `chat()` 方法，输入 dict、输出 dict / AsyncIterator[str]，SDK 细节封装在内部 |
| **统一数据契约** | 全链路 dict + str，Client ↔ Converter 之间无 SDK 类型依赖 |
| **配置驱动** | `providers.yaml` 定义 provider + interface + converter 组合，`load_providers()` 自动装配 |
| **状态内聚** | 流式 state 通过 ContextVar 在 Converter 内部管理 |

## 3. 依赖

```
# requirements.txt
fastapi>=0.110.0
uvicorn>=0.29.0
pydantic-settings>=2.2.0
pyyaml>=6.0.1
httpx>=0.27.0            # AsyncClient，通用 HTTP 客户端 + SSE 流式
openai>=1.30.0           # AsyncOpenAI 客户端
anthropic>=0.49.0        # AsyncAnthropic 客户端
pytest>=8.1.0
pytest-asyncio>=0.23.0
```

## 4. 核心模块

### 4.1 BaseClient — 客户端抽象

```python
# app/core/client.py
from abc import ABC, abstractmethod
from typing import AsyncIterator

class BaseClient(ABC):
    """供应商客户端抽象接口。
    
    统一传输层：输入 dict，输出 dict（非流式）或 AsyncIterator[str]（流式 SSE data）。
    SDK 细节封装在各子类内部，对外只暴露 dict/str。
    """

    def __init__(self, base_url: str, interface: str):
        self.base_url = base_url
        self.interface = interface  # "messages" / "completions" / "responses"

    @abstractmethod
    async def chat(self, params: dict, api_key: str, stream: bool = False
    ) -> dict | AsyncIterator[str]:
        """发送请求到上游 API。
        
        Args:
            params: 上游请求参数（dict）
            api_key: 认证密钥
            stream: 是否流式
            
        Returns:
            非流式: dict（上游 JSON 响应）
            流式:   AsyncIterator[str]（SSE data 内容，不含 "data: " 前缀）
        """
        ...
```

### 4.2 BaseConverter — 转换器抽象

```python
# app/core/converter.py
from abc import ABC, abstractmethod

class BaseConverter(ABC):
    """格式转换器抽象接口。纯格式转换，与供应商无关。"""

    @abstractmethod
    def convert_request(self, request: dict) -> dict:
        """将下游请求转换为上游请求参数。"""
        ...

    @abstractmethod
    def convert_response(self, response: dict) -> dict:
        """将上游响应转换为下游响应。"""
        ...

    @abstractmethod
    def convert_stream_event(self, data: str) -> list[str]:
        """将上游 SSE data 转换为下游 SSE data 列表。
        
        Args:
            data: 上游 SSE 的 data 字段内容（JSON 字符串或 [DONE]）
        Returns:
            转换后的 SSE data 列表，空列表表示跳过
        """
        ...
```

### 4.3 Proxy — 调度核心

```python
# app/core/providers.py

class Proxy:
    """客户端 + 转换器的组合，封装完整的 请求转换 → 上游调用 → 响应转换 流程。
    
    路由层只需调用 chat()，不关心内部编排。
    """

    def __init__(self, client: BaseClient, converter: BaseConverter):
        self.client = client
        self.converter = converter

    async def chat(self, body: dict, api_key: str, stream: bool = False
    ) -> dict | AsyncIterator[str]:
        """统一调度入口。
        
        Returns:
            非流式: dict（已转换为下游格式的响应）
            流式:   AsyncIterator[str]（已转换为下游格式的 SSE data）
        """
        req = self.converter.convert_request(body)

        if not stream:
            resp = await self.client.chat(req, api_key, stream=False)
            return self.converter.convert_response(resp)
        else:
            upstream = await self.client.chat(req, api_key, stream=True)
            return self._stream(upstream)

    async def _stream(self, upstream: AsyncIterator[str]) -> AsyncIterator[str]:
        async for data in upstream:
            for item in self.converter.convert_stream_event(data):
                yield item
        # 流结束事件（Messages 协议需要）
        if hasattr(self.converter, 'convert_stream_done'):
            for item in self.converter.convert_stream_done():
                yield item

class ProxyRegistry:
    """Proxy 容器，按接口名管理。"""
    def add(self, name: str, proxy: Proxy) -> None: ...
    def get(self, name: str) -> Proxy: ...
    def list(self) -> list[str]: ...
```

### 4.4 配置加载

```python
# app/core/loader.py

# 供应商工厂：provider 名 → Client 类
PROVIDER_REGISTRY = {
    "claude": ClaudeClient,
    "openai": OpenAIClient,
    "ollama": OpenAIClient,    # 兼容 OpenAI 协议
    "httpx":  HttpxClient,     # 通用 HTTP 客户端
    "mockup": MockupClient,    # 调试模式
}

# 转换器工厂：converter 名 → Converter 类
CONVERTER_REGISTRY = {
    "completions_from_messages":  CompletionsFromMessagesConverter,
    "completions_from_responses": CompletionsFromResponsesConverter,
    "messages_from_completions":  MessagesFromCompletionsConverter,
    "messages_from_responses":    MessagesFromResponsesConverter,
    "responses_from_messages":    ResponsesFromMessagesConverter,
    "responses_from_completions": ResponsesFromCompletionsConverter,
}

# 内置默认配置（config/providers.yaml 不存在时使用）
DEFAULT_CONFIG = {
    "completions": {
        "path": "/v1/chat/completions",
        "base_url": "https://api.anthropic.com",
        "provider": "claude",
        "interface": "messages",
        "converter": "completions_from_messages",
    },
    "responses": {
        "path": "/v1/responses",
        "base_url": "https://api.anthropic.com",
        "provider": "claude",
        "interface": "messages",
        "converter": "responses_from_messages",
    },
    "messages": {
        "path": "/v1/messages",
        "base_url": "https://api.openai.com/v1",
        "provider": "openai",
        "interface": "completions",
        "converter": "messages_from_completions",
    },
}

def load_providers(config_path: str) -> None:
    """从 YAML 加载配置，自动创建 Client + Converter，组装为 Proxy。"""
    if Path(config_path).exists():
        config = yaml.safe_load(open(config_path))
    else:
        config = DEFAULT_CONFIG

    for name, conf in config.items():
        client_cls = PROVIDER_REGISTRY[conf["provider"]]
        converter_cls = CONVERTER_REGISTRY[conf["converter"]]
        registry.add(name, Proxy(
            client=client_cls(base_url=conf["base_url"], interface=conf["interface"]),
            converter=converter_cls(),
        ))
```

### 4.5 配置文件

```yaml
# config/providers.yaml

completions:
  path: /v1/chat/completions
  base_url: ${ANTHROPIC_BASE_URL:https://api.anthropic.com}
  provider: claude
  interface: messages
  converter: completions_from_messages

responses:
  path: /v1/responses
  base_url: ${ANTHROPIC_BASE_URL:https://api.anthropic.com}
  provider: claude
  interface: messages
  converter: responses_from_messages

messages:
  path: /v1/messages
  base_url: ${OPENAI_BASE_URL:https://api.openai.com}/v1
  provider: openai
  interface: completions
  converter: messages_from_completions
```

字段说明：

| 字段 | 作用 |
|------|------|
| `path` | 本代理暴露的路由路径 |
| `base_url` | 上游 API 地址 |
| `provider` | Client 类型，映射到 `PROVIDER_REGISTRY` |
| `interface` | 上游接口类型，传给 Client，决定内部调哪个 endpoint |
| `converter` | 转换器类型，映射到 `CONVERTER_REGISTRY` |

## 5. 客户端层

每个 Client 统一实现 `chat()` 方法，`interface` 在初始化时传入。

| Provider | Client 类 | 支持的 interface | 内部实现 |
|----------|----------|-----------------|---------|
| `claude` | `ClaudeClient` | `messages` | `anthropic.AsyncAnthropic` |
| `openai` | `OpenAIClient` | `completions`, `responses` | `openai.AsyncOpenAI` |
| `ollama` | `OpenAIClient` | `completions` | 复用，兼容 OpenAI 协议 |
| `httpx`  | `HttpxClient` | `messages`, `completions`, `responses` | `httpx.AsyncClient` |
| `mockup` | `MockupClient` | `messages`, `completions`, `responses` | 无外部调用，返回模拟数据 |

```python
class ClaudeClient(BaseClient):
    """interface 固定为 "messages"。"""
    async def chat(self, params, api_key, stream=False):
        client = anthropic.AsyncAnthropic(api_key=api_key, base_url=self.base_url)
        # 非流式: client.messages.create() → Message.model_dump() → dict
        # 流式:   client.messages.stream()  → 逐事件 json.dumps() → yield str

class OpenAIClient(BaseClient):
    """interface 为 "completions" 或 "responses"。"""
    async def chat(self, params, api_key, stream=False):
        client = openai.AsyncOpenAI(api_key=api_key, base_url=self.base_url)
        if self.interface == "completions":
            # 非流式: client.chat.completions.create() → .model_dump() → dict
            # 流式:   逐 chunk json.dumps() → yield str
        elif self.interface == "responses":
            # 非流式: client.responses.create() → .model_dump() → dict
            # 流式:   逐 event json.dumps() → yield str

class HttpxClient(BaseClient):
    """通用 HTTP 客户端，不依赖任何 SDK。"""

    INTERFACE_PATHS = {
        "messages": "/v1/messages",
        "completions": "/v1/chat/completions",
        "responses": "/v1/responses",
    }

    async def chat(self, params, api_key, stream=False):
        url = self.base_url + self.INTERFACE_PATHS[self.interface]
        async with httpx.AsyncClient() as client:
            if not stream:
                resp = await client.post(url, json=params, headers=...)
                return resp.json()
            else:
                async with client.stream("POST", url, json=params, headers=...) as resp:
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            yield line[6:]

class MockupClient(BaseClient):
    """调试模式，根据 interface 返回对应格式的模拟 dict / SSE str 流。"""
    async def chat(self, params, api_key, stream=False):
        # 根据 self.interface 返回模拟数据
```

## 6. 转换层

转换器以 `{输出格式}From{输入格式}Converter` 命名，纯格式转换，与供应商无关。全链路 dict/str。

3 种格式两两互转 = 6 个转换器：

| 转换器 | 输入格式 | 输出格式 | 备注 |
|--------|---------|---------|------|
| `CompletionsFromMessagesConverter` | Messages | Completions | |
| `CompletionsFromResponsesConverter` | Responses | Completions | |
| `MessagesFromCompletionsConverter` | Completions | Messages | 含 `convert_stream_done()` |
| `MessagesFromResponsesConverter` | Responses | Messages | 含 `convert_stream_done()` |
| `ResponsesFromMessagesConverter` | Messages | Responses | |
| `ResponsesFromCompletionsConverter` | Completions | Responses | |

每个转换器实现三个方法：

```python
class CompletionsFromMessagesConverter(BaseConverter):
    def convert_request(self, request: dict) -> dict:     # Completions 请求 → Messages 请求
    def convert_response(self, response: dict) -> dict:   # Messages 响应 → Completions 响应
    def convert_stream_event(self, data: str) -> list[str]: # Messages SSE → Completions SSE
```

输出 Messages 格式的转换器额外实现 `convert_stream_done()`，用于生成流结束事件（`message_delta` + `message_stop`）。

## 7. 路由层

极薄调度，三个路由逻辑完全相同：

```python
route = registry.get("completions")  # 或 "responses" / "messages"

# 非流式
result = await route.chat(body, api_key, stream=False)
return JSONResponse(content=result)

# 流式
stream = await route.chat(body, api_key, stream=True)
async for data in stream:
    yield f"data: {data}\n\n"
```

## 8. 数据映射

### 8.1 Completions ↔ Messages

**请求：Completions → Messages**

```
model                    →  model (查映射表)
messages                 →  system + messages
  role: system           →  提取到顶层 system
  role: user             →  role: user
  role: assistant        →  role: assistant
  role: tool             →  role: user + tool_result block
  tool_calls             →  content: [{type: "tool_use"}]
max_tokens               →  max_tokens (必填，无则默认)
temperature / top_p      →  temperature / top_p
stop                     →  stop_sequences
tools                    →  tools (schema 转换)
tool_choice              →  tool_choice (值映射)
```

**响应：Messages → Completions**

```
id                       →  id (加 "chatcmpl-" 前缀)
content[].text           →  choices[0].message.content
content[].tool_use       →  choices[0].message.tool_calls[]
stop_reason: end_turn    →  finish_reason: stop
stop_reason: max_tokens  →  finish_reason: length
stop_reason: tool_use    →  finish_reason: tool_calls
usage.input_tokens       →  usage.prompt_tokens
usage.output_tokens      →  usage.completion_tokens
```

### 8.2 Responses ↔ Messages

**请求：Responses → Messages**

```
model                    →  model (查映射表)
input (string)           →  messages: [{role: "user", content: input}]
input (array)            →  messages (逐项转换)
instructions             →  system
max_output_tokens        →  max_tokens
temperature / top_p      →  temperature / top_p
tools                    →  tools (function 定义转换)
tool_choice              →  tool_choice (值映射)
```

**响应：Messages → Responses**

```
id                       →  id
content[].text           →  output[]{type: "message", content: [{type: "output_text"}]}
content[].tool_use       →  output[]{type: "function_call", ...}
stop_reason: end_turn    →  status: "completed"
stop_reason: max_tokens  →  status: "incomplete"
stop_reason: tool_use    →  status: "completed"
usage                    →  usage
```

### 8.3 Messages ↔ Completions（反向）

**请求：Messages → Completions**

```
system                   →  messages[0] {role: "system"}
messages                 →  messages
  tool_result content    →  role: tool message
  tool_use content       →  assistant tool_calls
max_tokens               →  max_tokens
stop_sequences           →  stop
tools                    →  tools (schema 转换)
tool_choice              →  tool_choice (值映射)
```

**响应：Completions → Messages**

```
id                       →  id (去前缀或保留)
choices[0].message       →  content[]
  .content               →  [{type: "text", text: ...}]
  .tool_calls            →  [{type: "tool_use", ...}]
finish_reason: stop      →  stop_reason: end_turn
finish_reason: length    →  stop_reason: max_tokens
finish_reason: tool_calls →  stop_reason: tool_use
usage.prompt_tokens      →  usage.input_tokens
usage.completion_tokens  →  usage.output_tokens
```

## 9. 流式事件映射

### 9.1 Messages → Completions SSE

| 上游 Messages 事件 | 下游 Completions SSE |
|---------------------|---------------------|
| `message_start` | `{choices: [{delta: {role: "assistant"}}]}` |
| `content_block_delta(text_delta)` | `{choices: [{delta: {content: "..."}}]}` |
| `content_block_start(tool_use)` | `{choices: [{delta: {tool_calls: [...]}}]}` |
| `content_block_delta(input_json_delta)` | `{choices: [{delta: {tool_calls: [...]}}]}` |
| `message_delta` | `{choices: [{finish_reason: "..."}]}` + usage |
| `message_stop` | `[DONE]` |

### 9.2 Messages → Responses SSE

| 上游 Messages 事件 | 下游 Responses SSE |
|---------------------|---------------|
| `message_start` | `response.created` + `response.in_progress` |
| `content_block_start(text)` | `response.output_item.added` |
| `content_block_delta(text_delta)` | `response.output_text.delta` |
| `content_block_start(tool_use)` | `response.function_call_arguments.delta` 开始 |
| `content_block_delta(input_json_delta)` | `response.function_call_arguments.delta` |
| `content_block_stop` | `response.output_item.done` |
| `message_delta` | `response.completed` |

### 9.3 Completions → Messages SSE

| 上游 Completions 事件 | 下游 Messages SSE |
|---------------------|------------|
| 首个 chunk (role) | `message_start` + `content_block_start` |
| delta.content | `content_block_delta(text_delta)` |
| delta.tool_calls (首次) | `content_block_stop` + `content_block_start(tool_use)` |
| delta.tool_calls (后续) | `content_block_delta(input_json_delta)` |
| finish_reason | 记录到内部 state |
| `convert_stream_done()` | `content_block_stop` + `message_delta` + `message_stop` |

## 10. Tool Calling 转换

### 10.1 Tools 定义

```python
# Completions 格式
{"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}

# Responses 格式
{"type": "function", "name": "...", "description": "...", "parameters": {...}}

# Messages 格式
{"name": "...", "description": "...", "input_schema": {...}}
```

### 10.2 tool_choice 映射

| Completions | Responses | Messages |
|------------|-----------|---------|
| `"none"` | — | `{"type": "none"}` |
| `"auto"` | `"auto"` | `{"type": "auto"}` |
| `"required"` | `"required"` | `{"type": "any"}` |
| `{"type":"function","function":{"name":"X"}}` | `{"type":"function","name":"X"}` | `{"type": "tool", "name": "X"}` |

### 10.3 Tool 结果消息

```
Completions: {role: "tool", tool_call_id: "xxx", content: "..."}
Responses:   input 中的 function_call_output item
Messages:    {role: "user", content: [{type: "tool_result", tool_use_id: "xxx", content: "..."}]}
```

## 11. 错误处理

| SDK / HTTP 异常 | 返回状态码 |
|---------|-----------|
| `AuthenticationError` | 401 |
| `RateLimitError` | 429 |
| `BadRequestError` | 400 |
| `InternalServerError` | 502 |
| `APITimeoutError` | 504 |
| `APIConnectionError` | 502 |

按端点协议返回错误格式：
- `/v1/chat/completions`、`/v1/responses`：`{"error": {"message": "...", "type": "...", "code": "..."}}`
- `/v1/messages`：`{"type": "error", "error": {"type": "...", "message": "..."}}`

## 12. 模型映射

```yaml
# config/model_mapping.yaml
openai_to_claude:
  gpt-4o: claude-sonnet-4-6-20250514
  gpt-4: claude-opus-4-6-20250514
  gpt-3.5-turbo: claude-haiku-4-5-20251001

claude_to_openai:
  claude-sonnet-4-6-20250514: gpt-4o
  claude-opus-4-6-20250514: gpt-4
  claude-haiku-4-5-20251001: gpt-3.5-turbo
```

策略：YAML 覆盖 → 内置默认 → 未命中透传。

## 13. 认证透传

- `/v1/chat/completions`、`/v1/responses`：`Authorization: Bearer` → 上游认证头
- `/v1/messages`：`x-api-key` → 上游认证头

具体认证头格式由 Client 内部处理（ClaudeClient 用 `x-api-key`，OpenAIClient 用 `Bearer`，HttpxClient 可配置）。

## 14. 配置层

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

```python
# main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_providers("config/providers.yaml")
    yield
```

## 15. 项目结构

```
api_proxy/
├── CLAUDE.md
├── main.py
├── requirements.txt
├── config/
│   ├── model_mapping.yaml              # 模型名映射
│   └── providers.yaml                  # Provider 配置（可选，有内置默认值）
├── .env.example
├── docs/
│   ├── architecture.md
│   ├── feature.md
│   └── process.md
├── app/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                   # Settings + 模型映射
│   │   ├── client.py                   # BaseClient ABC
│   │   ├── converter.py                # BaseConverter ABC
│   │   ├── providers.py                # Proxy + ProxyRegistry
│   │   ├── loader.py                   # 配置加载 + 自动装配
│   │   └── errors.py                   # 异常 → HTTP 错误
│   ├── clients/
│   │   ├── __init__.py
│   │   ├── claude_client.py            # ClaudeClient (anthropic SDK)
│   │   ├── openai_client.py            # OpenAIClient (openai SDK)
│   │   ├── httpx_client.py             # HttpxClient (通用 HTTP)
│   │   └── mockup_client.py            # MockupClient (调试模式)
│   ├── converters/
│   │   ├── __init__.py
│   │   ├── completions_from_messages.py
│   │   ├── completions_from_responses.py
│   │   ├── messages_from_completions.py
│   │   ├── messages_from_responses.py
│   │   ├── responses_from_messages.py
│   │   └── responses_from_completions.py
│   └── routes/
│       ├── __init__.py
│       ├── completions.py              # /v1/chat/completions
│       ├── responses.py                # /v1/responses
│       └── messages.py                 # /v1/messages
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_core/
    │   ├── __init__.py
    │   ├── test_providers.py
    │   └── test_errors.py
    ├── test_converters/
    │   ├── __init__.py
    │   ├── test_completions_from_messages.py
    │   ├── test_completions_from_responses.py
    │   ├── test_messages_from_completions.py
    │   ├── test_messages_from_responses.py
    │   ├── test_responses_from_messages.py
    │   └── test_responses_from_completions.py
    ├── test_clients/
    │   └── test_mockup.py
    └── test_routes/
        ├── __init__.py
        ├── test_completions.py
        ├── test_responses.py
        └── test_messages.py
```

## 16. 扩展预留

| 扩展项 | 扩展方式 |
|--------|---------|
| **新增供应商** | 实现新 Client 或直接用 `HttpxClient`，搭配 Converter，改 `providers.yaml` |
| **任意兼容 API** | 直接用 `HttpxClient`，无需实现新 Client 类 |
| **多模态** | Converter 添加对应分支 |
| **认证中间件** | FastAPI middleware |
| **多 Key 轮询** | Client 内部实现 |
| **日志/监控** | FastAPI middleware |
