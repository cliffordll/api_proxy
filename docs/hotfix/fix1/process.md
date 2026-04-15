# 开发过程记录 - Hotfix fix1：消除 dict 传参

---

## Phase 1：抽象接口改造

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 1.1 | BaseConverter 改为 Generic | 引入 TypeVar（TRequest, TResponse, TEvent），签名从 dict/Any 改为泛型 | `app/core/converter.py` | 待开始 |
| 1.2 | BaseClient params 类型变更 | `params: dict` → `params: Any` | `app/core/client.py` | 待开始 |

**验收**：接口定义可正常 import，不影响现有子类继承

**执行记录**：

> 待填写

---

## Phase 2：转换器改造

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 2.1 | OpenAIToClaudeConverter 请求转换 | 输入从 `dict` 改为 `ChatCompletionCreateParams`，输出改为 `MessageCreateParams`，内部字段访问从 `req["field"]` 改为 `req.field` | `app/converters/openai_to_claude.py` | 待开始 |
| 2.2 | OpenAIToClaudeConverter 响应转换 | 输出从 `dict` 改为 `ChatCompletion`（SDK 对象），使用构造函数创建 | `app/converters/openai_to_claude.py` | 待开始 |
| 2.3 | OpenAIToClaudeConverter 流式转换 | 输出从 `list[str]` 改为 `list[ChatCompletionChunk]`（SDK 对象） | `app/converters/openai_to_claude.py` | 待开始 |
| 2.4 | ClaudeToOpenAIConverter 请求转换 | 输入从 `dict` 改为 `MessageCreateParams`，输出改为 `ChatCompletionCreateParams`，内部字段访问从 `req["field"]` 改为 `req.field` | `app/converters/claude_to_openai.py` | 待开始 |
| 2.5 | ClaudeToOpenAIConverter 响应转换 | 输出从 `dict` 改为 `Message`（SDK 对象），使用构造函数创建 | `app/converters/claude_to_openai.py` | 待开始 |
| 2.6 | ClaudeToOpenAIConverter 流式转换 | 保持 `list[str]` 返回（Claude SSE 无对应 SDK 类型），但输入改为 `ChatCompletionChunk` | `app/converters/claude_to_openai.py` | 待开始 |

**验收**：转换器可正常实例化，继承关系正确，`convert_request` / `convert_response` 返回 SDK 类型对象

**执行记录**：

> 待填写

---

## Phase 3：客户端适配

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 3.1 | ClaudeClient.send 适配 | `params` 从 dict 改为接收 `MessageCreateParams`，内部通过 `model_dump()` 或直接传入 SDK | `app/clients/claude_client.py` | 待开始 |
| 3.2 | OpenAIClient.send 适配 | `params` 从 dict 改为接收 `ChatCompletionCreateParams`，内部通过 `model_dump()` 或直接传入 SDK | `app/clients/openai_client.py` | 待开始 |

**验收**：客户端能正确接收 SDK Params 类型并发起请求

**执行记录**：

> 待填写

---

## Phase 4：路由层适配

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 4.1 | openai_compat.py 请求解析 | `await request.json()` → 用 SDK 类型解析请求体 | `app/routes/openai_compat.py` | 待开始 |
| 4.2 | openai_compat.py 响应序列化 | `JSONResponse(content=dict)` → `JSONResponse(content=resp.model_dump())` | `app/routes/openai_compat.py` | 待开始 |
| 4.3 | openai_compat.py 流式序列化 | SSE 行从字符串改为 `chunk.model_dump_json()` | `app/routes/openai_compat.py` | 待开始 |
| 4.4 | claude_compat.py 请求解析 | `await request.json()` → 用 SDK 类型解析请求体 | `app/routes/claude_compat.py` | 待开始 |
| 4.5 | claude_compat.py 响应序列化 | `JSONResponse(content=dict)` → `JSONResponse(content=resp.model_dump())` | `app/routes/claude_compat.py` | 待开始 |
| 4.6 | claude_compat.py 流式保持 | Claude SSE 仍为 `list[str]`，无需改动序列化方式 | `app/routes/claude_compat.py` | 待开始 |

**验收**：`python main.py` 启动，两个端点非流式和流式均正常工作

**执行记录**：

> 待填写

---

## Phase 5：测试适配

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 5.1 | 转换器单元测试 | 输入改用 SDK 类型构造，断言返回值为 SDK 对象（检查属性而非 dict key） | `tests/test_converters/` | 待开始 |
| 5.2 | 路由集成测试 | 适配新的序列化方式，断言响应格式不变 | `tests/test_routes/` | 待开始 |
| 5.3 | 全量回归测试 | `pytest` 全部通过 | — | 待开始 |

**验收**：`pytest` 全部通过

**执行记录**：

> 待填写
