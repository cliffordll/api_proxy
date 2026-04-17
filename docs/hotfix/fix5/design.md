# Hotfix fix5：CLI 命令面简化 + REPL 内部重构

> 基于 fix4。chat 代理模式的 welcome 已经用统一格式展示了所有路由 + 探测状态 + 模型列表，`models` 子命令冗余；`chat "msg"` 单次对话也可以用脚本调用 REST API 代替，价值不高。同时 `cli/repl.py` 随 fix4 演化变得庞大（290+ 行），拆分与内敛有明显收益。
>
> 本 hotfix 三件事：
> 1. 删除 `python main.py models` 子命令
> 2. 删除 `python main.py chat "msg"` 单次对话模式
> 3. `cli/repl.py` 内部重构（拆 completer + startup，聚合 client 构造，瘦身 Repl.run）

---

## 需求

### 1. 删除 `models` 子命令

- chat 代理模式 welcome 已含同样内容，诊断场景用 `chat` 或 `test`
- `main.py` 删 subparser + dispatch；`cli/models.py` 整个删除
- REPL 内 `/models` 命令**保留**

### 2. 删除 chat 单次对话模式

- `python main.py chat "hello"` 这种一次性调用意义不大（用 curl / test 子命令也能做）
- `chat_parser.add_argument("message", ...)` 删掉
- `cli/repl.py::run_single()` 函数整个删除
- `start()` 中 `if args.message:` 分支删除

### 3. REPL 内部重构

`cli/repl.py` 从"一坨 290 行"分离到：

| 文件 | 职责 |
|------|------|
| `cli/chat/completer.py`（新） | `DynamicCompleter` + `COMMANDS` / `STREAM_OPTIONS` 常量 |
| `cli/chat/startup.py`（新） | 启动决策：`startup_probe` / `apply_default_model` / `models_for_route` |
| `cli/repl.py`（瘦身） | 仅 `Repl` 类 + `start()` 入口 |

Repl 类内部：
- 新增 `_new_client()` 方法消除 3 处 `ChatClient(...)` 重复
- `_read_input()` / `_post_command()` / `_current_route_conf()` / `_upsert_route_result()` 等小方法拆出
- `_sync_chat` / `_stream_chat` 统一从 `_chat(stream)` 分派
- `run()` 主循环从 ~40 行收紧到 ~15 行

---

## 改动清单

| # | 文件 | 说明 |
|---|------|------|
| 1 | `cli/chat/completer.py` | **新增**，从 repl.py 拆出 DynamicCompleter |
| 2 | `cli/chat/startup.py` | **新增**，从 repl.py 拆出启动决策逻辑 |
| 3 | `cli/repl.py` | 重写，瘦身到 ~130 行；删 run_single + args.message 分支 |
| 4 | `main.py` | 删 `models` subparser + dispatch；`chat` subparser 删 `message` 位置参数 |
| 5 | `cli/models.py` | **删除文件** |
| 6 | `README.md` | 移除 `models` 子命令 + 单次对话示例 |

---

## 兼容性 / 破坏性变更

- **破坏**：`python main.py models` 删除
- **破坏**：`python main.py chat "msg"` 删除
- REPL 内 `/models` 命令保留
- `/route` / `/routes` / `--base-url` / `--route` 等不变
- REPL 内部重构对用户完全透明（行为未变，仅代码组织改动）
