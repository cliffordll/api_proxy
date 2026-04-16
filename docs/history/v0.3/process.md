# 开发过程记录 - API Proxy v0.3

---

## Phase 1：核心层

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 1.1 | BaseClient | 统一 `chat(params: dict, api_key, stream)` 方法，`interface` 参数初始化时传入 | `app/core/client.py` | 完成 |
| 1.2 | BaseConverter | 无泛型，`convert_request(dict→dict)`、`convert_response(dict→dict)`、`convert_stream_event(str→list[str])` | `app/core/converter.py` | 完成 |
| 1.3 | Proxy + ProxyRegistry | Proxy 封装 `chat()` 完整流程，ProxyRegistry 按名管理 | `app/core/providers.py` | 完成 |
| 1.4 | 配置加载器 | `PROVIDER_REGISTRY` + `CONVERTER_REGISTRY` + `DEFAULT_CONFIG`（含 interface）+ `load_providers()` | `app/core/loader.py` | 完成 |
| 1.5 | 确认 errors.py | 与新架构兼容 | `app/core/errors.py` | 完成 |

**验收**：核心层可正常 import，抽象接口定义正确

**执行记录**：

> - 1.1 BaseClient：重写为单一 `chat()` 抽象方法，`__init__` 接收 `base_url` + `interface`
> - 1.2 BaseConverter：去掉泛型和 `upstream_interface`，三个方法统一 dict/str 输入输出
> - 1.3 Proxy + ProxyRegistry：新建 `providers.py`，Proxy.chat() 封装 convert_request → client.chat → convert_response/_stream 完整流程，ProxyRegistry 提供 add/get/list
> - 1.4 loader.py：使用延迟导入避免循环依赖，DEFAULT_CONFIG 含 interface 字段，load_providers() 自动装配。Client/Converter 注册表在后续 Phase 实现后逐步取消注释
> - 1.5 errors.py：只处理 SDK 异常→HTTP 错误映射，不依赖 BaseClient/BaseConverter 接口，无需修改
> - 旧 registry.py 暂保留（openai_compat.py / claude_compat.py 仍引用），Phase 5 删除旧路由时一并清理
> - 验证：`python -c "from app.core.client import BaseClient; ..."` 全部 import 成功

---

## Phase 2：客户端层

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 2.1 | ClaudeClient | 实现 `chat()`，内部 anthropic SDK，非流式返回 dict，流式 yield str | `app/clients/claude_client.py` | 完成 |
| 2.2 | OpenAIClient | 实现 `chat()`，内部 openai SDK，根据 `interface` 调 completions 或 responses | `app/clients/openai_client.py` | 完成 |
| 2.3 | HttpxClient | 实现 `chat()`，httpx.AsyncClient，根据 `interface` 拼接上游 URL | `app/clients/httpx_client.py` | 完成 |
| 2.4 | 删除旧文件 | 删除 v0.2 遗留的旧转换器文件 | — | 完成 |

**验收**：Client 继承 BaseClient，`chat()` 返回 dict（非流式）或 AsyncIterator[str]（流式）

**执行记录**：

> - 2.1 ClaudeClient：chat() 内部调 anthropic SDK，非流式 `response.model_dump(mode="json")` → dict，流式 `_stream_chat()` 逐事件 `json.dumps(event.model_dump())` → yield str
> - 2.2 OpenAIClient：chat() 根据 interface 分发到 `_chat_completions()` 或 `_chat_responses()`，各自处理非流式/流式
> - 2.3 HttpxClient：新建，chat() 根据 interface 拼接 URL 路径（INTERFACE_PATHS），认证头根据 interface 区分（messages→x-api-key，其他→Bearer），流式透传上游 SSE data
> - 2.4 删除旧文件：删除 `claude_to_openai.py`、`openai_to_claude.py`
> - loader.py 已更新：PROVIDER_REGISTRY 加入 HttpxClient
> - 验证：三个 Client 均正确继承 BaseClient，初始化参数（base_url + interface）正常

---

## Phase 3：转换层 — Completions ↔ Messages

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 3.1 | CompletionsFromMessagesConverter | 请求/响应/流式转换，输入输出 dict/str | `app/converters/completions_from_messages.py` | 完成 |
| 3.2 | MessagesFromCompletionsConverter | 请求/响应/流式转换，含 `convert_stream_done()`，输入输出 dict/str | `app/converters/messages_from_completions.py` | 完成 |

**验收**：继承 BaseConverter，输入输出为 dict/str

**执行记录**：

> - 3.1 CompletionsFromMessagesConverter：基于 v0.2 OpenAIToClaudeConverter 重写，去掉 SDK 类型依赖。请求转换（model 映射、messages/system/tools/tool_choice 转换）、响应转换（content blocks → choices、stop_reason → finish_reason、usage 映射）、流式转换（Messages 事件 JSON → Completions chunk JSON，message_stop → [DONE]）
> - 3.2 MessagesFromCompletionsConverter：基于 v0.2 ClaudeToOpenAIConverter 重写。请求转换（反向，含 tool_use/tool_result 消息处理）、响应转换（choices → content blocks）、流式转换（Completions chunk JSON → Messages 事件 JSON）、convert_stream_done（content_block_stop + message_delta + message_stop）
> - loader.py 已更新：CONVERTER_REGISTRY 注册两个转换器
> - 验证：请求/响应/流式转换全部正确，model 映射、tool_calls 处理、stream_done 事件生成均通过

---

## Phase 4：转换层 — Responses 相关

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 4.1 | ResponsesFromMessagesConverter | 请求/响应/流式转换，输入输出 dict/str | `app/converters/responses_from_messages.py` | 完成 |
| 4.2 | ResponsesFromCompletionsConverter | 请求/响应/流式转换，输入输出 dict/str | `app/converters/responses_from_completions.py` | 完成 |
| 4.3 | CompletionsFromResponsesConverter | 请求/响应/流式转换，输入输出 dict/str | `app/converters/completions_from_responses.py` | 完成 |
| 4.4 | MessagesFromResponsesConverter | 请求/响应/流式转换，含 `convert_stream_done()`，输入输出 dict/str | `app/converters/messages_from_responses.py` | 完成 |

**验收**：4 个转换器继承 BaseConverter，输入输出为 dict/str

**执行记录**：

> - 4.1 ResponsesFromMessagesConverter：Responses input/instructions → Messages messages/system，Messages content blocks → Responses output items，流式 Messages 事件 → Responses SSE 事件（response.created/output_text.delta/function_call_arguments.delta/completed 等）
> - 4.2 ResponsesFromCompletionsConverter：Responses input → Completions messages，Completions choices → Responses output，流式 Completions chunks → Responses SSE 事件，[DONE] → response.completed
> - 4.3 CompletionsFromResponsesConverter：Completions messages → Responses input/instructions，Responses output → Completions choices，流式 Responses SSE → Completions chunks + [DONE]
> - 4.4 MessagesFromResponsesConverter：Messages messages/system → Responses input/instructions，Responses output → Messages content blocks，流式 Responses SSE → Messages 事件，convert_stream_done 生成 content_block_stop + message_delta + message_stop
> - loader.py 已更新：全部 6 个转换器注册完毕
> - 验证：4 个转换器请求/响应/流式转换全部通过

---

## Phase 5：路由层 + 配置加载

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 5.1 | completions.py | `POST /v1/chat/completions`，`registry.get("completions").chat()` | `app/routes/completions.py` | 完成 |
| 5.2 | responses.py | `POST /v1/responses`，`registry.get("responses").chat()` | `app/routes/responses.py` | 完成 |
| 5.3 | messages.py | `POST /v1/messages`，`registry.get("messages").chat()` | `app/routes/messages.py` | 完成 |
| 5.4 | 删除旧路由 | 删除 `openai_compat.py`、`claude_compat.py`、`registry.py` | — | 完成 |
| 5.5 | 更新 main.py | `lifespan` 调用 `load_providers()`，注册三个路由 | `main.py` | 完成 |
| 5.6 | 创建默认配置 | `config/settings.yaml`（含 interface 字段） | `config/settings.yaml` | 完成 |

**验收**：`python main.py` 启动，`GET /health` 返回 200，三个端点认证校验正常

**执行记录**：

> - 5.1~5.3 三个路由：极薄调度，`proxy.chat(body, api_key, stream)` 一行调用。Completions 流式直接 `data: {str}\n\n`，Responses/Messages 流式解析 type 后 `event: {type}\ndata: {str}\n\n`。各端点按自身协议返回错误格式
> - 5.4 删除旧文件：openai_compat.py、claude_compat.py、registry.py
> - 5.5 main.py：lifespan 调用 load_providers()，注册三个新路由
> - 5.6 settings.yaml：默认配置 completions→claude/messages, responses→claude/messages, messages→openai/completions
> - 验证：ASGI 测试 health 200，三端点无 key 返回 401，config 加载正确（3 个 Proxy 注册成功）

---

## Phase 6：调试模式

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 6.1 | MockupClient | 实现 `chat()`，根据 `interface` 返回对应格式的模拟 dict/str 数据 | `app/clients/mockup_client.py` | 完成 |
| 6.2 | 注册到 PROVIDER_REGISTRY | `"mockup": MockupClient` | `app/core/loader.py` | 完成 |
| 6.3 | 创建调试配置示例 | `config/settings.mockup.yaml` | `config/settings.mockup.yaml` | 完成 |

**验收**：配置 `provider: mockup`，三个端点非流式和流式均返回模拟数据

**执行记录**：

> - 6.1 MockupClient：根据 interface 分发到 messages/completions/responses 三种模拟，非流式返回完整 dict，流式逐字符 yield SSE data（含 20ms 延迟模拟真实流速）
> - 6.2 loader.py 已更新：PROVIDER_REGISTRY 加入 MockupClient
> - 6.3 settings.mockup.yaml：三个端点全部配置为 mockup provider
> - 修复：三个路由的流式调用需先 `await proxy.chat()` 获取 async iterator，再 `async for` 迭代
> - 验证：Proxy 层 3 端点非流式/流式均通过，HTTP 层 3 端点非流式 200 响应格式正确

---

## Phase 7：测试

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 7.1 | Proxy + ProxyRegistry 单元测试 | `add/get/list`，chat 调度流程 | `tests/test_core/test_providers.py` | 完成 |
| 7.2 | 错误处理测试 | 沿用 v0.2，确认兼容 | `tests/test_core/test_errors.py` | 完成 |
| 7.3 | CompletionsFromMessages 测试 | 请求/响应/流式 | `tests/test_converters/test_completions_from_messages.py` | 完成 |
| 7.4 | MessagesFromCompletions 测试 | 请求/响应/流式/stream_done | `tests/test_converters/test_messages_from_completions.py` | 完成 |
| 7.5 | Responses 相关转换器测试 | 4 个转换器 | `tests/test_converters/test_responses_*.py` 等 | 完成 |
| 7.6 | completions 路由测试 | 非流式 + 流式 + 认证 | `tests/test_routes/test_completions.py` | 完成 |
| 7.7 | responses 路由测试 | 非流式 + 认证 | `tests/test_routes/test_responses.py` | 完成 |
| 7.8 | messages 路由测试 | 非流式 + 认证 | `tests/test_routes/test_messages.py` | 完成 |
| 7.9 | MockupClient 测试 | 三个 interface 非流式 + 流式 | `tests/test_clients/test_mockup.py` | 完成 |
| 7.10 | 全量回归 | `pytest` 全部通过 | — | 完成 |

**验收**：`pytest` 全部通过

**执行记录**：

> - 清理旧测试文件：test_claude_to_openai.py、test_openai_to_claude.py、test_registry.py、test_claude_compat.py、test_openai_compat.py
> - conftest.py 重写：使用 mockup 配置自动加载
> - 7.1 ProxyRegistry：add/get/list/overwrite/not_registered，Proxy：non_stream/stream 调度
> - 7.2 errors.py：沿用 v0.2 测试，8 个用例全部通过
> - 7.3~7.5 转换器：6 个转换器共 35 个用例，覆盖请求/响应/流式/tool_calls/stream_done
> - 7.6~7.8 路由：3 端点认证 401 + 非流式 200 + completions 流式 [DONE]
> - 7.9 MockupClient：3 个 interface × 2（非流式+流式）= 6 个用例
> - 7.10 全量回归：57 passed in 4.85s

---

## Phase 8：文档与收尾

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 8.1 | 更新 README.md | 项目结构、API 端点、调试模式 | `README.md` | 完成 |
| 8.2 | 更新 CLAUDE.md | 技术栈对齐 | `CLAUDE.md` | 完成 |
| 8.3 | 确认 architecture.md | 与实现一致 | `docs/architecture.md` | 完成 |

**验收**：文档与实现一致，`pytest` 全部通过，`python main.py` 启动正常

**执行记录**：

> - 8.1 README.md：全面重写，新增三端点说明、Provider 配置、调试模式、项目结构、Proxy 架构图
> - 8.2 CLAUDE.md：技术栈加入 httpx，编码规范加入 Client 统一 chat() 接口、Proxy 调度、Provider 配置
> - 8.3 architecture.md：与实现一致，5 个 provider（claude/openai/ollama/httpx/mockup）、6 个 converter、3 端点
> - requirements.txt：加入 httpx>=0.27.0
> - 最终验证：57 passed in 4.75s
