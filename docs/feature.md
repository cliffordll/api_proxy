# 开发计划 - API Proxy v0.3

## 过程记录要求

开发过程通过 `docs/process.md` 管理，每个 Phase 下依次包含：任务表、验收标准、执行记录。
每完成一个任务步骤，同步更新对应 Phase 的执行记录（实现说明、测试数据、测试结果、验收结论）。

---

## 版本目标

基于 v0.2 代码，重构为 Proxy 架构（Client + Converter），支持三种接口格式互转，新增 Responses API、HttpxClient 和调试模式。

**核心变更**：
1. BaseClient 统一为单一 `chat(params: dict, api_key, stream)` 方法，输入 dict、输出 dict（非流式）/ AsyncIterator[str]（流式 SSE data）
2. BaseConverter 去掉泛型，输入输出统一 dict/str
3. Proxy 封装 Client + Converter，对外暴露 `chat()` 方法，路由层一行调用拿到最终结果
4. ProxyRegistry 按接口名管理 Proxy 实例
5. Client 通过 `interface` 参数（初始化时传入）决定调哪个上游 endpoint，在 `providers.yaml` 中配置
6. 转换器以 `{输出}From{输入}Converter` 命名，6 个全量实现
7. 配置驱动：`config/providers.yaml` 平铺配置，`load_providers()` 自动装配，有内置默认值
8. 新增 HttpxClient 通用 HTTP 客户端
9. 新增 MockupClient 调试模式
10. 新增 `/v1/responses` 端点
11. 路由文件按接口名命名（completions.py / responses.py / messages.py）

---

## 阶段总览

```
Phase 1 (核心层)
    │
    ▼
Phase 2 (客户端层)
    │
    ▼
Phase 3 (转换层 — Completions ↔ Messages)
    │
    ▼
Phase 4 (转换层 — Responses 相关 4 个)
    │
    ▼
Phase 5 (路由层 + 配置加载)
    │
    ▼
Phase 6 (调试模式)
    │
    ▼
Phase 7 (测试)
    │
    ▼
Phase 8 (文档 + 收尾)
```

---

## Phase 1：核心层

**目标**：实现抽象接口、Proxy 调度、ProxyRegistry 容器、配置加载器。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 1.1 | BaseClient | 统一 `chat(params: dict, api_key, stream)` 方法，`interface` 参数初始化时传入 | `app/core/client.py` |
| 1.2 | BaseConverter | 无泛型，`convert_request(dict→dict)`、`convert_response(dict→dict)`、`convert_stream_event(str→list[str])` | `app/core/converter.py` |
| 1.3 | Proxy + ProxyRegistry | Proxy 封装 `chat()` 完整流程，ProxyRegistry 按名管理 | `app/core/providers.py` |
| 1.4 | 配置加载器 | `PROVIDER_REGISTRY` + `CONVERTER_REGISTRY` + `DEFAULT_CONFIG`（含 interface）+ `load_providers()` | `app/core/loader.py` |
| 1.5 | 确认 errors.py | 与新架构兼容 | `app/core/errors.py` |

**验收**：核心层可正常 import，抽象接口定义正确。

---

## Phase 2：客户端层

**目标**：实现四个 Client，统一 `chat()` 接口，SDK 细节封装在内部。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 2.1 | ClaudeClient | 实现 `chat()`，内部 anthropic SDK，非流式返回 dict，流式 yield str | `app/clients/claude_client.py` |
| 2.2 | OpenAIClient | 实现 `chat()`，内部 openai SDK，根据 `interface` 调 completions 或 responses | `app/clients/openai_client.py` |
| 2.3 | HttpxClient | 实现 `chat()`，httpx.AsyncClient，根据 `interface` 拼接上游 URL | `app/clients/httpx_client.py` |
| 2.4 | 删除旧文件 | 删除 v0.2 遗留的旧转换器文件 | — |

**验收**：Client 继承 BaseClient，`chat()` 返回 dict（非流式）或 AsyncIterator[str]（流式）。

---

## Phase 3：转换层 — Completions ↔ Messages

**目标**：实现核心双向转换，v0.2 已有逻辑的重构。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 3.1 | CompletionsFromMessagesConverter | 请求/响应/流式转换，输入输出 dict/str | `app/converters/completions_from_messages.py` |
| 3.2 | MessagesFromCompletionsConverter | 请求/响应/流式转换，含 `convert_stream_done()`，输入输出 dict/str | `app/converters/messages_from_completions.py` |

**验收**：继承 BaseConverter，输入输出为 dict/str。

---

## Phase 4：转换层 — Responses 相关

**目标**：实现 Responses 格式与其他两种格式的互转。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 4.1 | ResponsesFromMessagesConverter | 请求/响应/流式转换，输入输出 dict/str | `app/converters/responses_from_messages.py` |
| 4.2 | ResponsesFromCompletionsConverter | 请求/响应/流式转换，输入输出 dict/str | `app/converters/responses_from_completions.py` |
| 4.3 | CompletionsFromResponsesConverter | 请求/响应/流式转换，输入输出 dict/str | `app/converters/completions_from_responses.py` |
| 4.4 | MessagesFromResponsesConverter | 请求/响应/流式转换，含 `convert_stream_done()`，输入输出 dict/str | `app/converters/messages_from_responses.py` |

**验收**：4 个转换器继承 BaseConverter，输入输出为 dict/str。

---

## Phase 5：路由层 + 配置加载

**目标**：三个路由文件，极薄调度（`proxy.chat()` 一行调用），配置加载驱动装配。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 5.1 | completions.py | `POST /v1/chat/completions`，`registry.get("completions").chat()` | `app/routes/completions.py` |
| 5.2 | responses.py | `POST /v1/responses`，`registry.get("responses").chat()` | `app/routes/responses.py` |
| 5.3 | messages.py | `POST /v1/messages`，`registry.get("messages").chat()` | `app/routes/messages.py` |
| 5.4 | 删除旧路由 | 删除 `openai_compat.py`、`claude_compat.py` | — |
| 5.5 | 更新 main.py | `lifespan` 调用 `load_providers()`，注册三个路由 | `main.py` |
| 5.6 | 创建默认配置 | `config/providers.yaml`（含 interface 字段） | `config/providers.yaml` |

**验收**：`python main.py` 启动，`GET /health` 返回 200，三个端点认证校验正常。

---

## Phase 6：调试模式

**目标**：实现 MockupClient，支持无真实 API 的调试。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 6.1 | MockupClient | 实现 `chat()`，根据 `interface` 返回对应格式的模拟 dict/str 数据 | `app/clients/mockup_client.py` |
| 6.2 | 注册到 PROVIDER_REGISTRY | `"mockup": MockupClient` | `app/core/loader.py` |
| 6.3 | 创建调试配置示例 | `config/providers.mockup.yaml` | `config/providers.mockup.yaml` |

**验收**：配置 `provider: mockup`，三个端点非流式和流式均返回模拟数据。

---

## Phase 7：测试

**目标**：全量测试通过。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 7.1 | Proxy + ProxyRegistry 单元测试 | `add/get/list`，chat 调度流程 | `tests/test_core/test_providers.py` |
| 7.2 | 错误处理单元测试 | 沿用 v0.2，确认兼容 | `tests/test_core/test_errors.py` |
| 7.3 | CompletionsFromMessages 测试 | 请求/响应/流式 | `tests/test_converters/test_completions_from_messages.py` |
| 7.4 | MessagesFromCompletions 测试 | 请求/响应/流式/stream_done | `tests/test_converters/test_messages_from_completions.py` |
| 7.5 | Responses 相关 4 个转换器测试 | 请求/响应/流式 | `tests/test_converters/test_responses_*.py` 等 |
| 7.6 | completions 路由测试 | 非流式 + 认证 | `tests/test_routes/test_completions.py` |
| 7.7 | responses 路由测试 | 非流式 + 认证 | `tests/test_routes/test_responses.py` |
| 7.8 | messages 路由测试 | 非流式 + 认证 | `tests/test_routes/test_messages.py` |
| 7.9 | MockupClient 测试 | 三个 interface 非流式 + 流式 | `tests/test_clients/test_mockup.py` |
| 7.10 | 全量回归 | `pytest` 全部通过 | — |

**验收**：`pytest` 全部通过。

---

## Phase 8：文档与收尾

**目标**：文档对齐，README 更新。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 8.1 | 更新 README.md | 项目结构、架构说明、API 端点、技术栈、调试模式说明 | `README.md` |
| 8.2 | 更新 CLAUDE.md | 技术栈对齐 | `CLAUDE.md` |
| 8.3 | 确认 architecture.md | 与实现一致 | `docs/architecture.md` |

**验收**：所有文档与实现一致，`pytest` 全部通过，`python main.py` 启动正常。
