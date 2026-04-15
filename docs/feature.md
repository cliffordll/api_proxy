# 开发计划 - API Proxy（SDK 原生版）

## 过程记录要求

每完成一个任务步骤，同步更新 `docs/process.md`，包含：
- **任务编号 + 状态**（完成/进行中/阻塞）
- **关键实现说明**（设计决策、遇到的问题及解决方案）
- **测试数据**（输入样例）
- **测试结果**（输出 + 通过/失败）
- **阶段验收结论**（每个 Phase 结束时汇总）

---

## 阶段总览

```
Phase 1 (依赖更新 + 清理)
    │
    ▼
Phase 2 (抽象接口 + 注册表)
    │
    ├──────────────┐
    ▼              ▼
Phase 3 (客户端)  Phase 4 (转换器)
    │              │
    └──────┬───────┘
           ▼
      Phase 5 (路由层适配)
           │
           ▼
      Phase 6 (错误处理)
           │
           ▼
      Phase 7 (测试 + 收尾)
```

---

## Phase 1：依赖更新与清理

**目标**：切换到官方 SDK 依赖，删除自定义数据模型，建立 core 目录结构。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 1.1 | 更新依赖清单 | 添加 `anthropic>=0.49.0`，移除直接 `httpx` 依赖 | `requirements.txt` |
| 1.2 | 删除自定义数据模型 | 删除 `openai_models.py` 和 `claude_models.py` | — |
| 1.3 | 清理 models 目录 | 删除 `app/models/` 目录（含 `__init__.py`） | — |
| 1.4 | 创建 core 目录 | 创建 `app/core/` 及 `__init__.py` | `app/core/__init__.py` |
| 1.5 | 迁移 config.py | 将 `app/config.py` 移动到 `app/core/config.py`，更新所有引用 | `app/core/config.py` |
| 1.6 | 清理全局引用 | 移除代码中对 `app.models` 的所有 import | 涉及文件全局检查 |

**验收**：`pip install -r requirements.txt` 成功，`import openai` 和 `import anthropic` 正常，`from app.core.config import get_settings` 正常。

---

## Phase 2：抽象接口与注册表

**目标**：定义客户端和转换器的抽象接口，实现 Provider 注册机制，为可扩展性打好基础。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 2.1 | 定义 BaseClient 协议 | 使用 `typing.Protocol`，声明 `send()` 抽象方法 | `app/core/protocols.py` |
| 2.2 | 定义 BaseConverter 协议 | 声明 `convert_request()`、`convert_response()`、`convert_stream_event()` 三个抽象方法 | `app/core/protocols.py` |
| 2.3 | 实现 ProviderRegistry | 包含 `register()`、`get()`、`list_providers()` 方法，管理 ProviderEntry（client + converter 组合） | `app/core/registry.py` |

**BaseClient 接口**：
```python
@runtime_checkable
class BaseClient(Protocol):
    async def send(self, params: dict, api_key: str, stream: bool = False) -> Any: ...
```

**BaseConverter 接口**：
```python
@runtime_checkable
class BaseConverter(Protocol):
    def convert_request(self, request: dict) -> dict: ...
    def convert_response(self, response: Any) -> dict: ...
    def convert_stream_event(self, event: Any, state: dict) -> list: ...
```

**ProviderEntry 结构**：
```python
@dataclass
class ProviderEntry:
    client: BaseClient
    request_converter: BaseConverter
    response_converter: BaseConverter
```

**验收**：Protocol 可被正确 isinstance 检查，Registry 注册和获取逻辑正确。

---

## Phase 3：客户端层实现

**目标**：实现 `BaseClient` 接口，使用官方 SDK 封装上游调用。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 3.1 | 实现 ClaudeClient | 封装 `anthropic.AsyncAnthropic`，非流式返回 `Message`，流式返回 `MessageStream` | `app/clients/claude_client.py` |
| 3.2 | 实现 OpenAIClient | 封装 `openai.AsyncOpenAI`，非流式返回 `ChatCompletion`，流式返回 `AsyncStream[ChatCompletionChunk]` | `app/clients/openai_client.py` |
| 3.3 | 清理遗留文件 | 删除 `app/clients/openai_sdk_client.py` | — |

**封装要点**：
- 类实现，构造函数接收 `base_url`
- `send()` 方法内部创建 SDK 客户端实例（api_key 每次请求可能不同）
- SDK 自动管理 Header（`x-api-key`、`Authorization: Bearer`、`anthropic-version`）
- 流式和非流式通过 `stream` 参数统一入口

**验收**：通过 mock 上游验证客户端能正确发出请求并返回 SDK 类型对象。

---

## Phase 4：转换层实现

**目标**：实现 `BaseConverter` 接口，纯函数逻辑封装为类方法，无 I/O，无副作用。

### 4A：OpenAI → Claude 方向

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 4.1 | 实现 OpenAIToClaudeConverter | 实现 BaseConverter 三个方法 | `app/converters/openai_to_claude.py` |

**convert_request** — `dict`（OpenAI JSON）→ `MessageCreateParams`：
- system message 提取到顶层 `system` 参数
- messages 中 tool role → `ToolResultBlockParam`
- assistant tool_calls → `ToolUseBlock` content
- tools 定义：`{type: "function", function: {...}}` → `ToolParam`
- tool_choice 值映射：`"none"/"auto"/"required"` → `{type: "none"/"auto"/"any"}`
- model 查映射表，未命中透传
- max_tokens 缺省时填充默认值

**convert_response** — `anthropic.types.Message` → `ChatCompletion` dict：
- id 加 `chatcmpl-` 前缀
- content[].text → choices[0].message.content
- content[].tool_use → choices[0].message.tool_calls[]
- stop_reason 映射为 finish_reason
- usage 字段映射

**convert_stream_event** — `RawMessageStreamEvent` → `list[ChatCompletionChunk dict]`：
- 按事件类型逐条转换（见 architecture.md 第 6.1 节）
- state 参数用于跨事件累积 tool_call 参数片段

### 4B：Claude → OpenAI 方向

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 4.2 | 实现 ClaudeToOpenAIConverter | 实现 BaseConverter 三个方法 | `app/converters/claude_to_openai.py` |

**convert_request** — `dict`（Claude JSON）→ `ChatCompletionCreateParams` dict：
- 顶层 `system` → messages[0] `{role: "system"}`
- `ToolResultBlockParam` content → tool role message
- `ToolUseBlock` content → assistant tool_calls
- tools 定义：`ToolParam` → `{type: "function", function: {...}}`
- tool_choice 值映射：`{type: "any"}` → `"required"`

**convert_response** — `ChatCompletion` → `anthropic.types.Message` dict：
- 字段映射（见 architecture.md 第 5.4 节）

**convert_stream_event** — `ChatCompletionChunk` → `list[str]`（Claude SSE 事件行）：
- 按事件类型逐条转换（见 architecture.md 第 6.2 节）
- state 参数用于跨事件累积 tool_call 参数片段

### 4C：类型访问方式

```python
# SDK 属性访问（非 dict .get()）
text = content_block.text        # anthropic.types.TextBlock
model = resp.model               # anthropic.types.Message
content = chunk.choices[0].delta.content  # openai ChatCompletionChunk
```

**验收**：`pytest tests/test_converters/ -v` 全部通过。

---

## Phase 5：路由层适配与 Provider 注册

**目标**：路由层通过注册表调度，串联全链路。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 5.1 | 注册 Provider | 在应用启动时注册 Claude 和 OpenAI 两个 Provider | `main.py` |
| 5.2 | 更新 OpenAI 兼容路由 | 通过注册表获取 Claude Provider，调度转换和客户端 | `app/routes/openai_compat.py` |
| 5.3 | 更新 Claude 兼容路由 | 通过注册表获取 OpenAI Provider，调度转换和客户端 | `app/routes/claude_compat.py` |
| 5.4 | 流式响应处理 | 非流式：`.model_dump()` 序列化；流式：迭代 SDK 原生流，转换后输出 SSE | 同上 |

**路由层调度流程**：
```python
# 伪代码
provider = registry.get("claude")  # 或 "openai"
converted = provider.request_converter.convert_request(body)
response = await provider.client.send(converted, api_key, stream)
return provider.response_converter.convert_response(response)
```

**流式处理**：
```python
# OpenAI 兼容路由（调 Claude，返回 OpenAI 格式）
async with provider.client.send(params, key, stream=True) as stream:
    async for event in stream:
        chunks = provider.response_converter.convert_stream_event(event, state)
        for chunk in chunks:
            yield f"data: {json.dumps(chunk)}\n\n"
    yield "data: [DONE]\n\n"
```

**验收**：`python main.py` 启动，两个端点非流式和流式均正常工作。

---

## Phase 6：错误处理

**目标**：利用 SDK 内置异常体系，统一错误捕获与格式转换。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 6.1 | 实现错误处理工具函数 | 封装 SDK 异常到 HTTP 状态码 + 目标协议错误格式的转换逻辑 | `app/core/errors.py` |
| 6.2 | OpenAI 兼容路由异常捕获 | 捕获 `anthropic.*Error`，转换为 OpenAI 错误格式返回 | `app/routes/openai_compat.py` |
| 6.3 | Claude 兼容路由异常捕获 | 捕获 `openai.*Error`，转换为 Claude 错误格式返回 | `app/routes/claude_compat.py` |

**异常 → HTTP 状态码映射**：

| SDK 异常 | HTTP 状态码 |
|---------|-----------|
| `AuthenticationError` | 401 |
| `RateLimitError` | 429 |
| `BadRequestError` | 400 |
| `InternalServerError` | 502 |
| `APITimeoutError` | 504 |
| `APIConnectionError` | 502 |

**错误格式**：
```python
# OpenAI 格式
{"error": {"message": "...", "type": "...", "code": "..."}}

# Claude 格式
{"type": "error", "error": {"type": "...", "message": "..."}}
```

**验收**：异常场景返回正确的状态码和错误格式。

---

## Phase 7：测试与收尾

**目标**：全量测试通过，文档对齐。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 7.1 | Protocol 和 Registry 单元测试 | 验证接口约束和注册/获取逻辑 | `tests/test_registry.py` |
| 7.2 | 客户端单元测试 | mock SDK 客户端，验证 send() 行为 | `tests/test_clients/` |
| 7.3 | 转换器单元测试 | mock 对象改用 SDK 类型构造 | `tests/test_converters/` |
| 7.4 | 路由集成测试 | 适配新的注册表调度、客户端和转换器接口 | `tests/test_routes/` |
| 7.5 | 错误处理测试 | 验证各类 SDK 异常返回正确状态码和格式 | `tests/test_errors.py` |
| 7.6 | 全量回归测试 | `pytest` 全部通过 | — |
| 7.7 | 更新 CLAUDE.md | 技术栈移除 httpx，补充 anthropic SDK | `CLAUDE.md` |
| 7.8 | 更新项目结构文档 | 对齐 architecture.md 第 11 节 | `docs/architecture.md` |

**测试覆盖场景**：
- 纯文本对话（单轮/多轮）
- system message 提取/注入
- tools 定义格式转换
- tool_choice 值映射
- tool_calls / tool_use 消息转换
- tool 结果消息转换
- 流式事件逐条转换 + tool_call 参数累积
- max_tokens 缺省时填充默认值
- 模型名映射 + 未命中透传
- 非流式 / 流式完整链路
- Key 透传验证
- 缺少 Key 时返回 401
- 上游异常返回正确错误格式
- Provider 注册/获取/不存在时报错

**验收**：`pytest` 全部通过，`python main.py` 启动，两个端点正常工作。
