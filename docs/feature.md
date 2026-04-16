# 开发计划 - API Proxy v0.4

## 版本目标

1. 统一入口（`main.py server/chat/test`）
2. 配置结构调整（routes 段、client 段）
3. 测试目录迁移（app/tests/、cli/tests/）
4. CLI 客户端（交互对话、流式输出、Tool Call 展示、冒烟测试）

---

## 阶段总览

```
Phase 1 (Server 重构)
    │
    ▼
Phase 2 (CLI 基础对话)
    │
    ▼
Phase 3 (流式输出)
    │
    ▼
Phase 4 (多轮对话)
    │
    ▼
Phase 5 (斜杠命令)
    │
    ▼
Phase 6 (Tool Call 展示)
    │
    ▼
Phase 7 (冒烟测试)
    │
    ▼
Phase 8 (测试 + 文档)
```

---

## Phase 1：Server 重构

**目标**：统一入口、配置结构调整、测试目录迁移。不影响现有功能。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 1.1 | main.py 改为统一入口 | argparse 子命令：server / chat / test，server 为默认 | `main.py` |
| 1.2 | 新建 app/server.py | 从 main.py 迁移服务启动逻辑（FastAPI app + lifespan + uvicorn.run） | `app/server.py` |
| 1.3 | settings.yaml 结构调整 | routes 段嵌套、新增 client 段 | `config/settings.example.yaml` |
| 1.4 | loader.py 适配 routes 段 | `config.pop("routes", None)` 提取路由配置 | `app/core/loader.py` |
| 1.5 | 测试目录迁移 | `tests/` → `app/tests/`，更新 conftest.py | `app/tests/` |
| 1.6 | 删除旧 tests 目录 | 确认迁移完成后删除 | — |
| 1.7 | 全量测试 | pytest app/tests/ 57 passed | — |

**验收**：`python main.py server` 启动正常，`python main.py --help` 显示子命令，57 passed

---

## Phase 2：CLI 基础对话

**目标**：实现最简交互对话，非流式，单轮。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 2.1 | cli/ 目录结构 | 创建 cli/ 及 __init__.py | `cli/` |
| 2.2 | ChatClient | HTTP 请求，支持三种 route，非流式 | `cli/client.py` |
| 2.3 | Display 基础 | rich 输出，print_welcome / print_response / print_error | `cli/display.py` |
| 2.4 | REPL 基础 | 输入循环 + ChatClient + Display | `cli/repl.py` |
| 2.5 | main.py chat 子命令 | 接入 REPL，支持 --base-url / --route / --model / --api-key | `main.py` |
| 2.6 | 配置加载 | 从 settings.yaml 的 client 段读取默认值，命令行覆盖 | `cli/config.py` |

**验收**：`python main.py chat` 可交互对话，`python main.py chat "hello"` 单次对话

---

## Phase 3：流式输出

**目标**：ChatClient 支持 SSE 流式，Display 逐字显示。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 3.1 | ChatClient 流式 | SSE 解析，yield 增量文本 | `cli/client.py` |
| 3.2 | Display 流式 | print_stream_start / print_stream_chunk / print_stream_end | `cli/display.py` |
| 3.3 | REPL 适配 | 流式/非流式分支 | `cli/repl.py` |
| 3.4 | --stream / --no-stream | 命令行参数 | `main.py` |

**验收**：流式输出逐字显示

---

## Phase 4：多轮对话

**目标**：维护对话历史，支持上下文连续对话。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 4.1 | Conversation | add_user / add_assistant / get_messages / clear | `cli/conversation.py` |
| 4.2 | REPL 接入 | 每轮对话更新 Conversation | `cli/repl.py` |

**验收**：连续多轮对话，AI 能记住上文

---

## Phase 5：斜杠命令

**目标**：交互模式支持 /help /model /route /stream /history /clear /quit。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 5.1 | CommandHandler | 命令解析 + 分发 | `cli/commands.py` |
| 5.2 | REPL 接入 | 输入前判断是否斜杠命令 | `cli/repl.py` |

**验收**：所有斜杠命令可用

---

## Phase 6：Tool Call 展示

**目标**：检测响应中的 tool_calls，格式化展示。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 6.1 | ChatClient 解析 tool_calls | 从非流式/流式响应中提取 tool_calls | `cli/client.py` |
| 6.2 | Display tool call | print_tool_call / print_tool_result | `cli/display.py` |
| 6.3 | Conversation 记录 | add_tool_result | `cli/conversation.py` |

**验收**：tool call 参数和结果格式化显示

---

## Phase 7：冒烟测试

**目标**：`python main.py test` 自动测试服务可用性。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 7.1 | Tester | health + 三端点 × 流式/非流式 | `cli/tester.py` |
| 7.2 | main.py test 子命令 | 接入 Tester，支持 --base-url / --route | `main.py` |
| 7.3 | Display 测试结果 | ✓/✗ 格式化输出 | `cli/display.py` |

**验收**：`python main.py test` 输出测试结果

---

## Phase 8：测试 + 文档

**目标**：CLI 单元测试，文档更新。

| # | 任务 | 说明 | 产出文件 |
|---|------|------|---------|
| 8.1 | CLI 单元测试 | ChatClient / Conversation / CommandHandler | `cli/tests/` |
| 8.2 | 更新 README.md | CLI 用法、项目结构 | `README.md` |
| 8.3 | 更新 CLAUDE.md | 对齐 | `CLAUDE.md` |
| 8.4 | 更新 settings.example.yaml | 完整四段配置示例 | `config/settings.example.yaml` |

**验收**：全部测试通过，文档与实现一致
