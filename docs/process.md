# 开发过程记录 - API Proxy v0.4

---

## Phase 1：Server 重构

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 1.1 | main.py 改为统一入口 | argparse 子命令：server / chat / test | `main.py` | 待开始 |
| 1.2 | 新建 app/server.py | 迁移服务启动逻辑 | `app/server.py` | 待开始 |
| 1.3 | settings.yaml 结构调整 | routes 段嵌套、新增 client 段 | `config/settings.example.yaml` | 待开始 |
| 1.4 | loader.py 适配 routes 段 | 提取路由配置 | `app/core/loader.py` | 待开始 |
| 1.5 | 测试目录迁移 | `tests/` → `app/tests/` | `app/tests/` | 待开始 |
| 1.6 | 删除旧 tests 目录 | 确认迁移完成后删除 | — | 待开始 |
| 1.7 | 全量测试 | 57 passed | — | 待开始 |

**验收**：`python main.py server` 启动正常，57 passed

**执行记录**：

> 待填写

---

## Phase 2：CLI 基础对话

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 2.1 | cli/ 目录结构 | 创建 cli/ 及 __init__.py | `cli/` | 待开始 |
| 2.2 | ChatClient | HTTP 请求，支持三种 route，非流式 | `cli/client.py` | 待开始 |
| 2.3 | Display 基础 | rich 输出 | `cli/display.py` | 待开始 |
| 2.4 | REPL 基础 | 输入循环 | `cli/repl.py` | 待开始 |
| 2.5 | main.py chat 子命令 | 接入 REPL | `main.py` | 待开始 |
| 2.6 | 配置加载 | settings.yaml client 段 + 命令行覆盖 | `cli/config.py` | 待开始 |

**验收**：`python main.py chat` 可交互对话

**执行记录**：

> 待填写

---

## Phase 3：流式输出

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 3.1 | ChatClient 流式 | SSE 解析 | `cli/client.py` | 待开始 |
| 3.2 | Display 流式 | 逐字显示 | `cli/display.py` | 待开始 |
| 3.3 | REPL 适配 | 流式/非流式分支 | `cli/repl.py` | 待开始 |
| 3.4 | --stream / --no-stream | 命令行参数 | `main.py` | 待开始 |

**验收**：流式输出逐字显示

**执行记录**：

> 待填写

---

## Phase 4：多轮对话

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 4.1 | Conversation | 对话历史管理 | `cli/conversation.py` | 待开始 |
| 4.2 | REPL 接入 | 每轮更新历史 | `cli/repl.py` | 待开始 |

**验收**：连续多轮对话，AI 能记住上文

**执行记录**：

> 待填写

---

## Phase 5：斜杠命令

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 5.1 | CommandHandler | 命令解析 + 分发 | `cli/commands.py` | 待开始 |
| 5.2 | REPL 接入 | 斜杠命令判断 | `cli/repl.py` | 待开始 |

**验收**：所有斜杠命令可用

**执行记录**：

> 待填写

---

## Phase 6：Tool Call 展示

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 6.1 | ChatClient 解析 tool_calls | 提取 tool_calls | `cli/client.py` | 待开始 |
| 6.2 | Display tool call | 格式化显示 | `cli/display.py` | 待开始 |
| 6.3 | Conversation 记录 | add_tool_result | `cli/conversation.py` | 待开始 |

**验收**：tool call 格式化显示

**执行记录**：

> 待填写

---

## Phase 7：冒烟测试

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 7.1 | Tester | health + 三端点 × 流式/非流式 | `cli/tester.py` | 待开始 |
| 7.2 | main.py test 子命令 | 接入 Tester | `main.py` | 待开始 |
| 7.3 | Display 测试结果 | ✓/✗ 输出 | `cli/display.py` | 待开始 |

**验收**：`python main.py test` 输出测试结果

**执行记录**：

> 待填写

---

## Phase 8：测试 + 文档

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 8.1 | CLI 单元测试 | ChatClient / Conversation / CommandHandler | `cli/tests/` | 待开始 |
| 8.2 | 更新 README.md | CLI 用法、项目结构 | `README.md` | 待开始 |
| 8.3 | 更新 CLAUDE.md | 对齐 | `CLAUDE.md` | 待开始 |
| 8.4 | 更新 settings.example.yaml | 完整四段配置示例 | `config/settings.example.yaml` | 待开始 |

**验收**：全部测试通过，文档与实现一致

**执行记录**：

> 待填写
