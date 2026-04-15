# 开发过程记录 - Hotfix fix1：消除 dict 传参

---

## Phase 1：抽象接口改造

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 1.1 | BaseConverter 改为 Generic | 引入 TypeVar（TRequest, TResponse, TEvent），签名从 dict/Any 改为泛型 | `app/core/converter.py` | 完成 |
| 1.2 | BaseClient params 类型变更 | `params: dict` → `params: Any` | `app/core/client.py` | 完成 |

**验收**：接口定义可正常 import，不影响现有子类继承

**执行记录**：

- 1.1：BaseConverter 新增 `Generic[TRequest, TResponse, TEvent]`，三个抽象方法签名改用泛型
- 1.2：BaseClient.send `params: dict` → `params: Any`
- 验收：import 正常，**通过**

---

## Phase 2：转换器改造

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 2.1 | OpenAIToClaudeConverter 请求转换 | 输入保持 `dict`（路由层 JSON），输出保持 `dict`（Claude params） | `app/converters/openai_to_claude.py` | 完成 |
| 2.2 | OpenAIToClaudeConverter 响应转换 | 输出从 `dict` 改为 `ChatCompletion`（SDK 对象），使用构造函数创建 | `app/converters/openai_to_claude.py` | 完成 |
| 2.3 | OpenAIToClaudeConverter 流式转换 | 输出从 `list[str]` 改为 `list[ChatCompletionChunk]`（SDK 对象） | `app/converters/openai_to_claude.py` | 完成 |
| 2.4 | ClaudeToOpenAIConverter 请求转换 | 输入保持 `dict`（路由层 JSON），输出保持 `dict`（OpenAI params） | `app/converters/claude_to_openai.py` | 完成 |
| 2.5 | ClaudeToOpenAIConverter 响应转换 | 输出从 `dict` 改为 `Message`（SDK 对象），使用构造函数创建 | `app/converters/claude_to_openai.py` | 完成 |
| 2.6 | ClaudeToOpenAIConverter 流式转换 | 保持 `list[str]` 返回（Claude SSE 无对应 SDK 类型），输入改为 `ChatCompletionChunk` | `app/converters/claude_to_openai.py` | 完成 |

**验收**：转换器可正常实例化，继承关系正确，`convert_response` 返回 SDK 类型对象

**执行记录**：

- 2.1-2.3：OpenAIToClaudeConverter 响应返回 `ChatCompletion`，流式返回 `list[ChatCompletionChunk]`，message_stop 时设置 `state["done"]=True` 由路由层发 [DONE]
- 2.4-2.6：ClaudeToOpenAIConverter 响应返回 `anthropic.types.Message`，流式仍返回 `list[str]`（Claude SSE 无 SDK 类型）
- 验收：`isinstance` 检查通过，`convert_response` 返回 ChatCompletion/Message，**通过**

---

## Phase 3：客户端适配

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 3.1 | ClaudeClient.send 适配 | `params: dict` → `params: Any` | `app/clients/claude_client.py` | 完成 |
| 3.2 | OpenAIClient.send 适配 | `params: dict` → `params: Any` | `app/clients/openai_client.py` | 完成 |

**验收**：客户端签名与 BaseClient 一致

**执行记录**：

- 3.1-3.2：签名从 `params: dict` 改为 `params: Any`，内部逻辑不变（仍用 `**params` 展开）
- 验收：签名一致，**通过**

---

## Phase 4：路由层适配

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 4.1 | openai_compat.py 请求解析 | 请求体保持 `request.json()` dict 入口 | `app/routes/openai_compat.py` | 完成 |
| 4.2 | openai_compat.py 响应序列化 | `JSONResponse(content=resp.model_dump())` | `app/routes/openai_compat.py` | 完成 |
| 4.3 | openai_compat.py 流式序列化 | `chunk.model_dump_json()` + `[DONE]` 由路由层发出 | `app/routes/openai_compat.py` | 完成 |
| 4.4 | claude_compat.py 请求解析 | 请求体保持 `request.json()` dict 入口 | `app/routes/claude_compat.py` | 完成 |
| 4.5 | claude_compat.py 响应序列化 | `JSONResponse(content=resp.model_dump())` | `app/routes/claude_compat.py` | 完成 |
| 4.6 | claude_compat.py 流式保持 | Claude SSE 仍为 `list[str]`，无需改动 | `app/routes/claude_compat.py` | 完成 |

**验收**：`python main.py` 启动，两个端点非流式和流式均正常工作

**执行记录**：

- 4.2-4.3：openai_compat 非流式用 `resp.model_dump()`，流式用 `chunk.model_dump_json()`，路由层末尾发 `[DONE]`
- 4.5：claude_compat 非流式用 `resp.model_dump()`
- 4.6：claude_compat 流式不变（`list[str]`）
- 验收：**通过**

---

## Phase 5：测试适配

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 5.1 | 转换器单元测试 | mock 改用真实 SDK 类型构造，断言返回值为 SDK 对象（属性访问） | `tests/test_converters/` | 完成 |
| 5.2 | 路由集成测试 | mock 改用真实 SDK 类型，断言响应 JSON 格式不变 | `tests/test_routes/` | 完成 |
| 5.3 | 全量回归测试 | `pytest` 全部通过 | — | 完成 |

**验收**：`pytest` 全部通过

**执行记录**：

- 5.1：test_openai_to_claude 的 response/stream 测试改用 `isinstance(result, ChatCompletion/ChatCompletionChunk)` 断言；mock 改用真实 `anthropic.types.Message/TextBlock/ToolUseBlock` 构造。test_claude_to_openai 的 response 测试改用 `isinstance(result, Message)` 断言；mock 改用真实 `ChatCompletion` 构造
- 5.2：路由测试 mock 改用真实 SDK 类型（`Message`、`ChatCompletion`），断言 JSON 响应格式不变
- 5.3：57 passed，**通过**

---

## 补充改进：私有辅助函数封装

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 6.1 | OpenAIToClaudeConverter 辅助函数内聚 | 模块级 `_convert_content_to_claude`、`_merge_text_parts`、`_convert_tool_def`、`_convert_tool_choice_to_claude`、`_make_chunk` 移入类中作为 `@staticmethod` | `app/converters/openai_to_claude.py` | 完成 |
| 6.2 | ClaudeToOpenAIConverter 辅助函数内聚 | 模块级 `_convert_tool_def`、`_convert_tool_choice_to_openai`、`_sse` 移入类中作为 `@staticmethod` | `app/converters/claude_to_openai.py` | 完成 |

**验收**：57 passed，全部通过

**执行记录**：

- 6.1-6.2：所有仅被单个类使用的模块级私有函数移入对应类中，使用 `@staticmethod` 修饰，消除模块级污染
- 验收：57 passed，**通过**
