# Hotfix fix5 开发过程记录

> 前置：fix4

---

## Phase 1 — REPL 内部重构

| 任务 | 说明 | 产出文件 | 状态 |
|------|------|---------|------|
| 拆分与内敛 | completer 和 startup 各自成文件；Repl 内 `_new_client` 聚合、`run()` 瘦身 | `cli/chat/completer.py`、`cli/chat/startup.py`、`cli/repl.py` | 完成 |

**执行记录**：
- 新增 `cli/chat/completer.py`：`DynamicCompleter` + `COMMANDS` / `STREAM_OPTIONS` 常量
- 新增 `cli/chat/startup.py`：把 chat 启动相关全部聚合在这里
  - 结构化路由探测：`probe_route` / `probe_all`（原在 `cli/core/probe.py`）
  - 启动决策：`startup_probe` / `_startup_probe_direct` / `_startup_probe_proxy` / `_compute_footer`
  - 默认模型：`apply_default_model` / `models_for_route`
- `cli/core/probe.py` 瘦身为纯 HTTP 工具：只保留 `probe_models`（chat 和 `/models` 命令共用）
- `cli/repl.py` 重写：
  - 新增 `_new_client()` 消除 3 处重复
  - `_read_input()` / `_post_command()` / `_current_route_conf()` / `_upsert_route_result()` 小方法拆出
  - `_sync_chat` / `_stream_chat` 统一从 `_chat(stream)` 分派
  - `run()` 主循环 ~40 行 → ~15 行
  - `probe_route` 改从 `cli.chat.startup` import
- 85 passed；E2E 默认启动渲染正常

---

## Phase 2 — 删除 `models` 子命令

| 任务 | 说明 | 产出文件 | 状态 |
|------|------|---------|------|
| 删除 models 子命令 | `main.py` 移除 subparser + dispatch；删除 `cli/models.py` | `main.py`、`cli/models.py` | 完成 |

**执行记录**：
- `main.py` 删 `models` subparser + dispatch 分支
- `cli/models.py` 整个文件 `rm`
- 诊断场景回落到 `chat` welcome（显示同样的路由表）或 `test` 子命令
- `python main.py --help` 显示从 4 个子命令缩减到 3 个（server / chat / test）

---

## Phase 3 — 删除 chat 单次对话模式

| 任务 | 说明 | 产出文件 | 状态 |
|------|------|---------|------|
| 删除单次对话 | `chat` subparser 删 `message` 位置参数；`cli/repl.py` 删 `run_single` + `args.message` 分支 | `main.py`、`cli/repl.py` | 完成 |

**执行记录**：
- `main.py::chat_parser` 删掉 `message` 位置参数
- `cli/repl.py`：
  - 删除 `run_single` 函数
  - `start()` 简化到 5 行：load 配置 → startup_probe → 进 Repl
  - 顺带删掉不再使用的 `ROUTE_PRIORITY` import

---

## Phase 4 — 测试 + E2E

| 任务 | 说明 | 产出文件 | 状态 |
|------|------|---------|------|
| 测试 + E2E | pytest 全绿；chat 代理 / 直连 启动 | — | 完成 |

**执行记录**：
- `pytest` 85 passed
- `python main.py --help`：三个子命令（server / chat / test）
- `python main.py chat` 默认模式 welcome 渲染正常，路由表 + 状态 + 模型列表都在

---

## Phase 5 — 文档同步

| 任务 | 说明 | 产出文件 | 状态 |
|------|------|---------|------|
| 文档同步 | README 移除 `models` 子命令 + 单次对话示例；项目结构更新到 chat/core 子目录 | `README.md` | 完成 |

**执行记录**：
- 启动命令示例删掉 `python main.py chat "hello"` 和 `python main.py models`
- "CLI 客户端"特性列表合并 `模型探测` 成一行
- 斜杠命令列表保留 `/models`（REPL 内命令仍在）
- 删掉"模型探测"独立章节
- "项目结构"章节更新：反映 `cli/{chat,core}/` 子目录 + `common/` 共享层
- `main.py` 注释从"server / chat / models / test" → "server / chat / test"
