# Hotfix fix1：消除 dict 传参，全链路使用 SDK 结构体

## 1. 问题描述

当前实现中，代理接口和转换器层大量使用 `dict` 作为数据传递类型：

| 位置 | 当前类型 | 问题 |
|------|---------|------|
| `BaseClient.send(params: dict)` | dict | 无类型约束，调用方不知道需要哪些字段 |
| `BaseConverter.convert_request() -> dict` | 返回 dict | 下游无法获得字段提示和校验 |
| `BaseConverter.convert_response() -> dict` | 返回 dict | 路由层需要手动 `JSONResponse(content=dict)` |
| `BaseConverter.convert_stream_event() -> list` | 返回 list[str] | 流式事件是拼好的 SSE 文本行，路由层无法做进一步处理 |
| 路由层 `body = await request.json()` | dict | 请求体无校验，任意字段都能进入转换器 |

## 2. 修改目标

**全链路使用 SDK 结构体和 Pydantic 模型，消除 dict 传参。**

## 3. 涉及修改

### 3.1 路由层：请求体使用 Pydantic 模型接收

```python
# 当前
body = await request.json()  # dict

# 修改后 — openai_compat.py
from openai.types.chat import ChatCompletionCreateParams
body = ChatCompletionCreateParams(**await request.json())

# 修改后 — claude_compat.py
from anthropic.types import MessageCreateParams
body = MessageCreateParams(**await request.json())
```

**收益**：请求体在入口处即完成校验，非法字段直接报 400。

### 3.2 BaseConverter 接口签名变更

```python
# 当前
class BaseConverter(ABC):
    def convert_request(self, request: dict) -> dict: ...
    def convert_response(self, response: Any) -> dict: ...
    def convert_stream_event(self, event: Any, state: dict) -> list: ...

# 修改后
from typing import TypeVar, Generic

TRequest = TypeVar("TRequest")   # 源协议请求类型
TResponse = TypeVar("TResponse") # 目标协议响应类型
TEvent = TypeVar("TEvent")       # 目标协议流式事件类型

class BaseConverter(ABC, Generic[TRequest, TResponse, TEvent]):
    @abstractmethod
    def convert_request(self, request: TRequest) -> Any: ...

    @abstractmethod
    def convert_response(self, response: TResponse) -> Any: ...

    @abstractmethod
    def convert_stream_event(self, event: TEvent, state: dict) -> list: ...
```

### 3.3 OpenAIToClaudeConverter 类型具体化

```python
# 当前
class OpenAIToClaudeConverter(BaseConverter):
    def convert_request(self, openai_req: dict) -> dict: ...
    def convert_response(self, claude_resp: Any) -> dict: ...
    def convert_stream_event(self, event: Any, state: dict) -> list[str]: ...

# 修改后
from openai.types.chat import ChatCompletionCreateParams, ChatCompletion, ChatCompletionChunk
from anthropic.types import MessageCreateParams, Message, RawMessageStreamEvent

class OpenAIToClaudeConverter(BaseConverter[ChatCompletionCreateParams, Message, RawMessageStreamEvent]):
    def convert_request(self, request: ChatCompletionCreateParams) -> MessageCreateParams: ...
    def convert_response(self, response: Message) -> ChatCompletion: ...
    def convert_stream_event(self, event: RawMessageStreamEvent, state: dict) -> list[ChatCompletionChunk]: ...
```

### 3.4 ClaudeToOpenAIConverter 类型具体化

```python
# 当前
class ClaudeToOpenAIConverter(BaseConverter):
    def convert_request(self, claude_req: dict) -> dict: ...
    def convert_response(self, openai_resp: Any) -> dict: ...
    def convert_stream_event(self, chunk: Any, state: dict) -> list[str]: ...

# 修改后
from anthropic.types import MessageCreateParams, Message
from openai.types.chat import ChatCompletionCreateParams, ChatCompletion, ChatCompletionChunk

class ClaudeToOpenAIConverter(BaseConverter[MessageCreateParams, ChatCompletion, ChatCompletionChunk]):
    def convert_request(self, request: MessageCreateParams) -> ChatCompletionCreateParams: ...
    def convert_response(self, response: ChatCompletion) -> Message: ...
    def convert_stream_event(self, chunk: ChatCompletionChunk, state: dict) -> list[str]: ...
```

### 3.5 BaseClient 接口签名变更

```python
# 当前
class BaseClient(ABC):
    async def send(self, params: dict, api_key: str, stream: bool = False) -> Any: ...

# 修改后
class BaseClient(ABC):
    async def send(self, params: Any, api_key: str, stream: bool = False) -> Any: ...
```

`params` 类型从 `dict` 改为 `Any`，实际接收 SDK 的 Params 类型（如 `MessageCreateParams`、`ChatCompletionCreateParams`）。各客户端实现内部做类型适配。

### 3.6 路由层响应序列化

```python
# 当前
openai_resp = provider.response_converter.convert_response(result)  # dict
return JSONResponse(content=openai_resp)

# 修改后
openai_resp = provider.response_converter.convert_response(result)  # ChatCompletion
return JSONResponse(content=openai_resp.model_dump())

# 流式事件
chunks = provider.response_converter.convert_stream_event(event, state)  # list[ChatCompletionChunk]
for chunk in chunks:
    yield f"data: {chunk.model_dump_json()}\n\n"
```

### 3.7 流式事件返回类型变更

| 转换器 | 当前返回 | 修改后返回 |
|--------|---------|-----------|
| OpenAIToClaudeConverter.convert_stream_event | `list[str]`（拼好的 SSE 行） | `list[ChatCompletionChunk]`（SDK 对象） |
| ClaudeToOpenAIConverter.convert_stream_event | `list[str]`（拼好的 SSE 行） | `list[str]`（Claude SSE 行，SDK 无对应对象） |

**说明**：Claude SSE 协议没有对应的 SDK 响应类型，ClaudeToOpenAIConverter 的流式事件仍返回 `list[str]`。

## 4. 修改范围汇总

| 文件 | 修改内容 |
|------|---------|
| `app/core/converter.py` | BaseConverter 改为 Generic，签名使用 TypeVar |
| `app/core/client.py` | `params: dict` → `params: Any` |
| `app/converters/openai_to_claude.py` | 输入输出改为 SDK 类型，内部字段访问相应调整 |
| `app/converters/claude_to_openai.py` | 输入输出改为 SDK 类型，内部字段访问相应调整 |
| `app/routes/openai_compat.py` | 请求体用 SDK 类型解析，响应用 `.model_dump()` 序列化 |
| `app/routes/claude_compat.py` | 请求体用 SDK 类型解析，响应用 `.model_dump()` 序列化 |
| `tests/` | mock 对象和断言适配新类型 |

## 5. 不修改的部分

- `app/core/registry.py` — ProviderEntry 结构不变
- `app/core/config.py` — 配置层不变
- `app/core/errors.py` — 错误处理不变
- `docs/architecture.md` — 整体架构设计不变
- `docs/feature.md` — 开发计划不变
