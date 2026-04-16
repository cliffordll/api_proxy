# Hotfix fix1 开发过程记录

---

## Phase 1：Client 层去掉序列化

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 1.1 | ClaudeClient | 去掉 `model_dump()` / `json.dumps()`，直接返回 SDK 对象/事件 | `app/clients/claude_client.py` | 完成 |
| 1.2 | OpenAIClient | 去掉 `model_dump()` / `json.dumps()`，直接返回 SDK 对象/事件 | `app/clients/openai_client.py` | 完成 |
| 1.3 | BaseClient | 返回类型改为 `Any` | `app/core/client.py` | 完成 |

**执行记录**：

> Client 纯传输，不做任何序列化

---

## Phase 2：Proxy 层纯透传

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 2.1 | Proxy | 直接把 Client 返回值传给 Converter | `app/core/proxy.py` | 完成 |

**执行记录**：

> Proxy 无序列化代码

---

## Phase 3：Converter 层

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 3.1 | BaseConverter | `_to_dict()` 处理 SDK/dict/str → dict，`convert_response` 返回 str | `app/core/converter.py` | 完成 |
| 3.2 | 6 个 Converter | 输入类型明确（SDK type \| dict），输出 str，SSE 封装在 converter 内 | `app/converters/*.py` | 完成 |

**执行记录**：

> - convert_response 返回 JSON str
> - convert_stream_event 返回完整 SSE 块（Completions: `data: ...\n\n`，Messages/Responses: `event: ...\ndata: ...\n\n`）
> - `_to_dict` 统一处理 SDK 对象/dict/str → dict
> - 去掉了 `_to_str`，直接用 `_to_dict` 操作 dict

---

## Phase 4：路由层 + 验证

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 4.1 | 路由层简化 | 非流式 `Response(content=str)`，流式 `yield item` | `app/routes/*.py` | 完成 |
| 4.2 | 测试更新 | convert_response 结果加 json.loads，流式断言适配 SSE 块 | `tests/` | 完成 |
| 4.3 | 全量测试 | 57 passed | — | 完成 |

**执行记录**：

> - 路由层去掉 json import 和 SSE 封装逻辑，只剩 yield item
> - 57 passed in 4.85s
