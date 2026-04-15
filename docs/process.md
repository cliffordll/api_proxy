# 开发过程记录 - API Proxy（SDK 原生版重构）

---

## Phase 1：依赖更新与目录重构

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 1.1 | 更新依赖清单 | 添加 `anthropic>=0.49.0`，移除 `httpx` 和 `httpx[http2]` | `requirements.txt` | 完成 |
| 1.2 | 删除 models 目录 | 删除 `app/models/` 整个目录 | — | 完成 |
| 1.3 | 创建 core 目录 | 创建 `app/core/` 及 `__init__.py` | `app/core/__init__.py` | 完成 |
| 1.4 | 迁移 config.py | `app/config.py` → `app/core/config.py` | `app/core/config.py` | 完成 |
| 1.5 | 更新全局引用 | `from app.config` → `from app.core.config`（6处） | 多文件 | 完成 |

**验收**：`python -c "from app.core.config import get_settings; print('ok')"` 正常

**执行记录**：

- 1.1：`requirements.txt` 添加 `anthropic>=0.49.0`，移除 `httpx>=0.27.0` 和 `httpx[http2]>=0.27.0`
- 1.2：删除 `app/models/` 整个目录（含 `__init__.py`、`openai_models.py`、`claude_models.py`、`__pycache__/`），无代码引用 `app.models`
- 1.3：创建 `app/core/` 目录及空 `__init__.py`
- 1.4：`app/config.py` → `app/core/config.py`，内容不变
- 1.5：6 处引用更新（main.py、claude_client.py、openai_client.py、openai_sdk_client.py、openai_to_claude.py、claude_to_openai.py）
- 验收：`python -c "from app.core.config import get_settings; print('ok')"` 输出 `ok`，**通过**

---

## Phase 2：抽象接口与注册表

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 2.1 | 定义 BaseClient Protocol | 声明 `send(params, api_key, stream)` 方法 | `app/core/protocols.py` | 完成 |
| 2.2 | 定义 BaseConverter Protocol | 声明 `convert_request()`、`convert_response()`、`convert_stream_event()` 方法 | `app/core/protocols.py` | 完成 |
| 2.3 | 实现 ProviderEntry | `dataclass`：client + request_converter + response_converter | `app/core/registry.py` | 完成 |
| 2.4 | 实现 ProviderRegistry | `register()`、`get()`、`list_providers()` 方法 | `app/core/registry.py` | 完成 |

**验收**：Protocol 可被 `isinstance` 检查，Registry 注册/获取/不存在报错逻辑正确

**执行记录**：

- 2.1：使用 `typing.Protocol` + `@runtime_checkable`，声明 `send(params, api_key, stream)` 方法
- 2.2：声明 `convert_request()`、`convert_response()`、`convert_stream_event()` 三个方法
- 2.3：`@dataclass`，包含 `client`、`request_converter`、`response_converter` 三个字段
- 2.4：`register()`、`get()`（不存在时抛 KeyError）、`list_providers()` 方法，模块级 `registry` 全局实例
- 验收：Registry 注册/获取/不存在报错/list 逻辑全部通过，**通过**

---

## Phase 3：客户端层重写

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 3.1 | 实现 ClaudeClient 类 | 封装 `anthropic.AsyncAnthropic`，非流式返回 `Message`，流式返回 `MessageStream` | `app/clients/claude_client.py` | 完成 |
| 3.2 | 实现 OpenAIClient 类 | 封装 `openai.AsyncOpenAI`，非流式返回 `ChatCompletion`，流式返回 `AsyncStream[ChatCompletionChunk]` | `app/clients/openai_client.py` | 完成 |
| 3.3 | 删除遗留文件 | 删除 `app/clients/openai_sdk_client.py` | — | 完成 |

**验收**：两个客户端类通过 `isinstance(client, BaseClient)` 检查

**执行记录**：

- 3.1：ClaudeClient 类，构造函数接收 `base_url`，`send()` 内部创建 `AsyncAnthropic` 客户端，非流式调用 `client.messages.create()`，流式调用 `client.messages.stream()` 返回上下文管理器
- 3.2：OpenAIClient 类，构造函数接收 `base_url`，`send()` 内部创建 `AsyncOpenAI` 客户端，非流式/流式均调用 `client.chat.completions.create()`
- 3.3：删除 `app/clients/openai_sdk_client.py`
- 验收：`isinstance(ClaudeClient(...), BaseClient)` 和 `isinstance(OpenAIClient(...), BaseClient)` 均为 True，**通过**

---

## Phase 4：转换层重写

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 4.1 | 实现 OpenAIToClaudeConverter | 请求：`dict` → `dict`；响应：`anthropic.types.Message` → `dict`；流式：`RawMessageStreamEvent` → `list[str]` | `app/converters/openai_to_claude.py` | 完成 |
| 4.2 | 实现 ClaudeToOpenAIConverter | 请求：`dict` → `dict`；响应：`ChatCompletion` → `dict`；流式：`ChatCompletionChunk` → `list[str]` | `app/converters/claude_to_openai.py` | 完成 |

**改动要点**：
- 模块级函数 → 类方法
- 非流式响应输入从 dict 改为 SDK 类型（属性访问替代 `.get()`）
- 流式事件输入从 str/dict 改为 SDK 事件类型
- `[DONE]` 信号由路由层处理，不在转换器中处理

**验收**：两个转换器类通过 `isinstance(converter, BaseConverter)` 检查

**执行记录**：

- 4.1：OpenAIToClaudeConverter 类，convert_request 逻辑不变；convert_response 输入改为 `anthropic.types.Message`（属性访问）；convert_stream_event 输入改为 `RawMessageStreamEvent`（属性访问）
- 4.2：ClaudeToOpenAIConverter 类，convert_request 逻辑不变；convert_response 输入改为 `ChatCompletion`（属性访问）；convert_stream_event 输入改为 `ChatCompletionChunk`（属性访问）；新增 `convert_stream_done()` 方法处理流结束事件（原 `[DONE]` 逻辑从转换器移出）
- 验收：`isinstance` 检查均为 True，**通过**

---

## Phase 5：路由层适配与 Provider 注册

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 5.1 | Provider 注册 | `main.py` 启动时创建客户端/转换器实例，注册为 `"claude"` 和 `"openai"` Provider | `main.py` | 待开始 |
| 5.2 | 重写 OpenAI 兼容路由 | 从 Registry 获取 `"claude"` Provider 调度 | `app/routes/openai_compat.py` | 待开始 |
| 5.3 | 重写 Claude 兼容路由 | 从 Registry 获取 `"openai"` Provider 调度 | `app/routes/claude_compat.py` | 待开始 |

**验收**：`python main.py` 启动，`GET /health` 返回 200，两个端点非流式和流式均正常

**执行记录**：

> 待填写

---

## Phase 6：错误处理

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 6.1 | 实现错误处理工具函数 | `handle_anthropic_error(e)` 和 `handle_openai_error(e)`，返回 `(status_code, error_body)` | `app/core/errors.py` | 待开始 |
| 6.2 | OpenAI 兼容路由接入 | 捕获 `anthropic.*Error`，转换为 OpenAI 错误格式 | `app/routes/openai_compat.py` | 待开始 |
| 6.3 | Claude 兼容路由接入 | 捕获 `openai.*Error`，转换为 Claude 错误格式 | `app/routes/claude_compat.py` | 待开始 |

**验收**：模拟各类 SDK 异常，返回正确的状态码和错误格式

**执行记录**：

> 待填写

---

## Phase 7：测试与收尾

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 7.1 | Registry 单元测试 | 注册/获取/不存在报错/list 逻辑 | `tests/test_core/test_registry.py` | 待开始 |
| 7.2 | 错误处理单元测试 | 各类 SDK 异常返回正确状态码和格式 | `tests/test_core/test_errors.py` | 待开始 |
| 7.3 | 转换器单元测试 | 适配类方法调用，mock 对象改用 SDK 类型构造 | `tests/test_converters/` | 待开始 |
| 7.4 | 路由集成测试 | 适配注册表调度方式，更新 mock 路径 | `tests/test_routes/` | 待开始 |
| 7.5 | 全量回归测试 | `pytest` 全部通过 | — | 待开始 |
| 7.6 | 更新 CLAUDE.md | 技术栈移除 httpx，补充 anthropic SDK | `CLAUDE.md` | 待开始 |
| 7.7 | 更新架构文档 | 对齐项目结构章节 | `docs/architecture.md` | 待开始 |

**验收**：`pytest` 全部通过，`python main.py` 启动，两个端点正常工作

**执行记录**：

> 待填写
