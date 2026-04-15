# 开发计划 - API Proxy

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
Phase 1 (骨架+配置)
    │
    ▼
Phase 2 (数据模型)
    │
    ├──────────────┐
    ▼              ▼
Phase 3 (转换器)  Phase 4 (客户端)
    │              │
    └──────┬───────┘
           ▼
      Phase 5 (路由层，串联全链路)
           │
           ▼
      Phase 6 (错误处理+收尾)
```

---

## Phase 1：项目骨架与配置

**目标**：项目可启动，健康检查可访问。

| # | 任务 | 产出文件 |
|---|------|---------|
| 1.1 | 创建目录结构和所有 `__init__.py` | app/, app/routes/, app/converters/, app/clients/, app/models/, tests/ |
| 1.2 | 依赖清单 | `requirements.txt` |
| 1.3 | 配置管理：Settings 类 + YAML 模型映射加载 | `app/config.py` |
| 1.4 | 默认模型映射表 | `config/model_mapping.yaml` |
| 1.5 | 环境变量模板 | `.env.example` |
| 1.6 | 应用入口 + `GET /health` | `main.py` |

**验收**：`python main.py` 启动，`GET /health` 返回 200。

---

## Phase 2：数据模型层

**目标**：定义两套协议的完整 Pydantic v2 模型。

| # | 任务 | 产出文件 |
|---|------|---------|
| 2.1 | OpenAI 模型：Request, Response, Chunk, Message, Tool, ToolCall, Function | `app/models/openai_models.py` |
| 2.2 | Claude 模型：Request, Response, ContentBlock(多态), StreamEvent, Tool, ToolUse, ToolResult | `app/models/claude_models.py` |

**设计要点**：
- ContentBlock 用联合类型 `TextContent | ToolUseContent | ToolResultContent`，未来加 ImageContent 只需扩展此处
- OpenAI message.content 支持 `str | list` 两种形式

**验收**：模型可正确 parse 官方 API 文档示例 JSON，`model_dump()` 输出符合协议规范。

---

## Phase 3：转换层

**目标**：实现双向纯函数转换，配合完整单元测试。

| # | 任务 | 产出文件 |
|---|------|---------|
| 3.1 | OpenAI->Claude 请求转换 | `app/converters/openai_to_claude.py` |
| 3.2 | Claude->OpenAI 响应转换（非流式） | 同上 |
| 3.3 | Claude->OpenAI 流式事件转换 | 同上 |
| 3.4 | Claude->OpenAI 请求转换 | `app/converters/claude_to_openai.py` |
| 3.5 | OpenAI->Claude 响应转换（非流式） | 同上 |
| 3.6 | OpenAI->Claude 流式事件转换 | 同上 |
| 3.7 | 单元测试 | `tests/test_converters/test_openai_to_claude.py` |
| 3.8 | 单元测试 | `tests/test_converters/test_claude_to_openai.py` |

**测试覆盖场景**：
- 纯文本对话（单轮/多轮）
- system message 提取/注入
- tools 定义格式转换
- tool_choice 值映射
- tool_calls / tool_use 消息转换
- tool 结果消息转换（OpenAI tool role <-> Claude tool_result block）
- 流式事件逐条转换 + tool_call 参数累积
- max_tokens 缺省时填充默认值
- 模型名映射 + 未命中透传

**验收**：`pytest tests/test_converters/ -v` 全部通过。

---

## Phase 4：客户端层

**目标**：封装上游 API 调用，支持非流式和流式响应。

| # | 任务 | 产出文件 |
|---|------|---------|
| 4.1 | Claude 客户端：send() 方法，Header 设置 (x-api-key, anthropic-version)，流式返回 AsyncIterator | `app/clients/claude_client.py` |
| 4.2 | OpenAI 客户端：send() 方法，Header 设置 (Authorization Bearer)，流式返回 AsyncIterator | `app/clients/openai_client.py` |

**统一接口**：
```python
async def send(request_body: dict, api_key: str, stream: bool = False) -> dict | AsyncIterator[str]
```

**验收**：通过 mock 上游验证请求 Header 和 Body 格式正确。

---

## Phase 5：路由层

**目标**：串联全链路，暴露完整端点。

| # | 任务 | 产出文件 |
|---|------|---------|
| 5.1 | OpenAI 兼容路由：提取 Bearer Key -> 转换请求 -> 调 Claude -> 转换响应，流式走 StreamingResponse | `app/routes/openai_compat.py` |
| 5.2 | Claude 兼容路由：提取 x-api-key -> 转换请求 -> 调 OpenAI -> 转换响应，流式走 StreamingResponse | `app/routes/claude_compat.py` |
| 5.3 | 注册路由到 app | `main.py` |
| 5.4 | 集成测试 | `tests/test_routes/test_openai_compat.py`, `tests/test_routes/test_claude_compat.py` |

**集成测试覆盖**：
- 非流式请求-响应完整链路
- 流式请求-SSE 响应完整链路
- Key 透传验证
- 缺少 Key 时返回 401

**验收**：`pytest tests/test_routes/ -v` 全部通过。

---

## Phase 6：错误处理与收尾

**目标**：健壮性补全，文档对齐。

| # | 任务 | 产出文件 |
|---|------|---------|
| 6.1 | 上游错误格式转换（4xx/5xx -> 目标协议错误体） | 路由层或 middleware |
| 6.2 | 网络异常处理（超时 -> 504，连接拒绝 -> 502） | 客户端层 |
| 6.3 | 请求体校验失败返回目标协议格式 400 | 路由层 |
| 6.4 | 全量测试通过 | `pytest` |
| 6.5 | CLAUDE.md 与实现对齐 | `CLAUDE.md` |

**验收**：`pytest` 全部通过，服务可启动，两个端点正常工作。
