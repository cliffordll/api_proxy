# 开发过程记录 - API Proxy v0.3

---

## Phase 1：核心层

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 1.1 | BaseClient | 统一 `chat(params: dict, api_key, stream)` 方法，`interface` 参数初始化时传入 | `app/core/client.py` | 待开始 |
| 1.2 | BaseConverter | 无泛型，`convert_request(dict→dict)`、`convert_response(dict→dict)`、`convert_stream_event(str→list[str])` | `app/core/converter.py` | 待开始 |
| 1.3 | Proxy + ProxyRegistry | Proxy 封装 `chat()` 完整流程，ProxyRegistry 按名管理 | `app/core/providers.py` | 待开始 |
| 1.4 | 配置加载器 | `PROVIDER_REGISTRY` + `CONVERTER_REGISTRY` + `DEFAULT_CONFIG`（含 interface）+ `load_providers()` | `app/core/loader.py` | 待开始 |
| 1.5 | 确认 errors.py | 与新架构兼容 | `app/core/errors.py` | 待开始 |

**验收**：核心层可正常 import，抽象接口定义正确

**执行记录**：

> 待填写

---

## Phase 2：客户端层

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 2.1 | ClaudeClient | 实现 `chat()`，内部 anthropic SDK，非流式返回 dict，流式 yield str | `app/clients/claude_client.py` | 待开始 |
| 2.2 | OpenAIClient | 实现 `chat()`，内部 openai SDK，根据 `interface` 调 completions 或 responses | `app/clients/openai_client.py` | 待开始 |
| 2.3 | HttpxClient | 实现 `chat()`，httpx.AsyncClient，根据 `interface` 拼接上游 URL | `app/clients/httpx_client.py` | 待开始 |
| 2.4 | 删除旧文件 | 删除 v0.2 遗留的旧转换器文件 | — | 待开始 |

**验收**：Client 继承 BaseClient，`chat()` 返回 dict（非流式）或 AsyncIterator[str]（流式）

**执行记录**：

> 待填写

---

## Phase 3：转换层 — Completions ↔ Messages

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 3.1 | CompletionsFromMessagesConverter | 请求/响应/流式转换，输入输出 dict/str | `app/converters/completions_from_messages.py` | 待开始 |
| 3.2 | MessagesFromCompletionsConverter | 请求/响应/流式转换，含 `convert_stream_done()`，输入输出 dict/str | `app/converters/messages_from_completions.py` | 待开始 |

**验收**：继承 BaseConverter，输入输出为 dict/str

**执行记录**：

> 待填写

---

## Phase 4：转换层 — Responses 相关

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 4.1 | ResponsesFromMessagesConverter | 请求/响应/流式转换，输入输出 dict/str | `app/converters/responses_from_messages.py` | 待开始 |
| 4.2 | ResponsesFromCompletionsConverter | 请求/响应/流式转换，输入输出 dict/str | `app/converters/responses_from_completions.py` | 待开始 |
| 4.3 | CompletionsFromResponsesConverter | 请求/响应/流式转换，输入输出 dict/str | `app/converters/completions_from_responses.py` | 待开始 |
| 4.4 | MessagesFromResponsesConverter | 请求/响应/流式转换，含 `convert_stream_done()`，输入输出 dict/str | `app/converters/messages_from_responses.py` | 待开始 |

**验收**：4 个转换器继承 BaseConverter，输入输出为 dict/str

**执行记录**：

> 待填写

---

## Phase 5：路由层 + 配置加载

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 5.1 | completions.py | `POST /v1/chat/completions`，`registry.get("completions").chat()` | `app/routes/completions.py` | 待开始 |
| 5.2 | responses.py | `POST /v1/responses`，`registry.get("responses").chat()` | `app/routes/responses.py` | 待开始 |
| 5.3 | messages.py | `POST /v1/messages`，`registry.get("messages").chat()` | `app/routes/messages.py` | 待开始 |
| 5.4 | 删除旧路由 | 删除 `openai_compat.py`、`claude_compat.py` | — | 待开始 |
| 5.5 | 更新 main.py | `lifespan` 调用 `load_providers()`，注册三个路由 | `main.py` | 待开始 |
| 5.6 | 创建默认配置 | `config/providers.yaml`（含 interface 字段） | `config/providers.yaml` | 待开始 |

**验收**：`python main.py` 启动，`GET /health` 返回 200，三个端点认证校验正常

**执行记录**：

> 待填写

---

## Phase 6：调试模式

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 6.1 | MockupClient | 实现 `chat()`，根据 `interface` 返回对应格式的模拟 dict/str 数据 | `app/clients/mockup_client.py` | 待开始 |
| 6.2 | 注册到 PROVIDER_REGISTRY | `"mockup": MockupClient` | `app/core/loader.py` | 待开始 |
| 6.3 | 创建调试配置示例 | `config/providers.mockup.yaml` | `config/providers.mockup.yaml` | 待开始 |

**验收**：配置 `provider: mockup`，三个端点非流式和流式均返回模拟数据

**执行记录**：

> 待填写

---

## Phase 7：测试

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 7.1 | Proxy + ProxyRegistry 单元测试 | `add/get/list`，chat 调度流程 | `tests/test_core/test_providers.py` | 待开始 |
| 7.2 | 错误处理测试 | 沿用 v0.2，确认兼容 | `tests/test_core/test_errors.py` | 待开始 |
| 7.3 | CompletionsFromMessages 测试 | 请求/响应/流式 | `tests/test_converters/test_completions_from_messages.py` | 待开始 |
| 7.4 | MessagesFromCompletions 测试 | 请求/响应/流式/stream_done | `tests/test_converters/test_messages_from_completions.py` | 待开始 |
| 7.5 | Responses 相关转换器测试 | 4 个转换器 | `tests/test_converters/test_responses_*.py` 等 | 待开始 |
| 7.6 | completions 路由测试 | 非流式 + 认证 | `tests/test_routes/test_completions.py` | 待开始 |
| 7.7 | responses 路由测试 | 非流式 + 认证 | `tests/test_routes/test_responses.py` | 待开始 |
| 7.8 | messages 路由测试 | 非流式 + 认证 | `tests/test_routes/test_messages.py` | 待开始 |
| 7.9 | MockupClient 测试 | 三个 interface 非流式 + 流式 | `tests/test_clients/test_mockup.py` | 待开始 |
| 7.10 | 全量回归 | `pytest` 全部通过 | — | 待开始 |

**验收**：`pytest` 全部通过

**执行记录**：

> 待填写

---

## Phase 8：文档与收尾

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 8.1 | 更新 README.md | 项目结构、API 端点、调试模式 | `README.md` | 待开始 |
| 8.2 | 更新 CLAUDE.md | 技术栈对齐 | `CLAUDE.md` | 待开始 |
| 8.3 | 确认 architecture.md | 与实现一致 | `docs/architecture.md` | 待开始 |

**验收**：文档与实现一致，`pytest` 全部通过，`python main.py` 启动正常

**执行记录**：

> 待填写
