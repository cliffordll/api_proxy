# Hotfix fix1：Client 返回 SDK 原始数据，Converter 统一序列化输出

## 问题

1. Client 在内部做了 `model_dump()` / `json.dumps()` 序列化，不应该是 Client 的职责
2. Converter 用 `Any` 接收参数，类型不明确
3. Converter 返回 dict，路由层还要再序列化一次

## 目标

- Client 纯传输，返回 SDK 原始对象
- Converter 输入类型明确（每个 Converter 知道自己接收的 SDK 类型）
- Converter 输出统一为 str（JSON 字符串），一步到位完成序列化
- Proxy 纯透传，不做任何转换
- 路由层直接输出 str，不再二次序列化

## 数据流

```
Client 返回 SDK 原始对象（或 dict/str）
    ↓
Proxy 直接透传
    ↓
Converter 接收明确类型，输出 str
    → convert_response(Message | dict) → str（JSON 字符串）
    → convert_stream_event(RawMessageStreamEvent | str) → list[str]（SSE data）
    ↓
路由层直接输出
    → 非流式: Response(content=str, media_type="application/json")
    → 流式:   yield f"data: {data}\n\n"
```

## 改动范围

### BaseClient

返回类型 `Any`（SDK 对象或 dict，取决于 Client 实现）。

### Client 层

ClaudeClient / OpenAIClient：去掉 `model_dump()` / `json.dumps()`，返回 SDK 原始对象。
HttpxClient / MockupClient：不变。

### BaseConverter

```python
class BaseConverter(ABC):
    def convert_request(self, request: dict) -> dict: ...
    def convert_response(self, response) -> str: ...        # 返回 JSON str
    def convert_stream_event(self, event) -> list[str]: ...  # 返回 SSE data str 列表

    @staticmethod
    def _to_dict(raw) -> dict:
        """SDK 对象 → dict，dict 透传。"""

    @staticmethod
    def _to_str(event) -> str:
        """SDK 事件 → JSON str，str 透传。"""
```

### 各 Converter 输入类型示例

| Converter | convert_response 输入 | convert_stream_event 输入 |
|-----------|----------------------|--------------------------|
| CompletionsFromMessages | `Message \| dict` | `RawMessageStreamEvent \| str` |
| MessagesFromCompletions | `ChatCompletion \| dict` | `ChatCompletionChunk \| str` |
| ResponsesFromMessages | `Message \| dict` | `RawMessageStreamEvent \| str` |
| ResponsesFromCompletions | `ChatCompletion \| dict` | `ChatCompletionChunk \| str` |
| CompletionsFromResponses | `Response \| dict` | `ResponseStreamEvent \| str` |
| MessagesFromResponses | `Response \| dict` | `ResponseStreamEvent \| str` |

> `| dict` / `| str` 兼容 HttpxClient 和 MockupClient 返回的 dict/str。

### Proxy 层

纯透传，不做任何序列化。`chat()` 非流式返回 str。

### 路由层

```python
# 非流式（改前）
result = await proxy.chat(body, api_key, stream=False)
return JSONResponse(content=result)  # result 是 dict

# 非流式（改后）
result = await proxy.chat(body, api_key, stream=False)
return Response(content=result, media_type="application/json")  # result 是 str
```

流式不变。
