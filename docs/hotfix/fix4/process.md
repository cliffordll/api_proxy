# Hotfix fix4 开发过程记录

---

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 1 | 协议常量扩展 | `common/routes.py` 新增 `ROUTE_PRIORITY` + `DEFAULT_MOCKUP_ROUTES` | `common/routes.py` | 完成 |
| 2 | Server 默认 mockup | `DEFAULT_CONFIG` 引用 `DEFAULT_MOCKUP_ROUTES`，三条全 mockup | `app/core/loader.py` | 完成 |
| 3 | Mockup 文案个性化 | `[mockup] {model} speaking ({协议}). How can I help?` | `app/clients/mockup_client.py` | 完成 |
| 4 | CLI 读 routes 回退 | `load_routes` 在 yaml 无 routes 时回退到 `DEFAULT_MOCKUP_ROUTES` | `cli/core/config.py` | 完成 |
| 5 | probe 结构化 | 新增 `probe_route` / `probe_all`，返回 `{status, status_reason, models, ...}` | `cli/core/probe.py` | 完成 |
| 6 | Display 扩展 | 新增 `_format_route_sections` / `print_welcome` 改版 / `print_route_status` / `print_route_picker`；强制 UTF-8 避免 Windows GBK 编码失败 | `cli/core/display.py`、`main.py` | 完成 |
| 7 | chat 启动决策 | `_startup_probe` 决定路由 + 并发探测；Repl 接收 route_results + footer_note；`_refresh_current_route` 单路由刷新 | `cli/repl.py` | 完成 |
| 8 | `/routes` 命令 | 数字 picker，选中后走 `/route <name>` 流水线 | `cli/chat/commands.py` | 完成 |
| 9 | Tab 补全 + /help | `/routes` 加入 COMMANDS；帮助文案同步 | `cli/repl.py`、`cli/chat/commands.py` | 完成 |
| 10 | 测试 + E2E | pytest 85 passed；默认 / 显式 --base-url 启动 E2E 验证 | — | 完成 |
| 11 | 文档同步 | README 同步 | `README.md` | 完成 |

**执行记录**：

- **P1 — 协议常量扩展**
  - `common/routes.py` 加 `ROUTE_PRIORITY = ["completions", "responses", "messages"]`
  - 加 `DEFAULT_MOCKUP_ROUTES`（三条路由 provider=mockup，base_url `http://localhost` 占位）

- **P2 — Server 默认 mockup**
  - `app/core/loader.py::DEFAULT_CONFIG = DEFAULT_MOCKUP_ROUTES`
  - server 无 routes 配置时全部走 mockup，无隐藏的 anthropic/openai 依赖
  - 85 passed

- **P3 — Mockup 文案**
  - 三种 interface 文案：
    - messages: `[mockup] {model} speaking (Claude Messages). How can I help?`
    - completions: `[mockup] {model} speaking (OpenAI Completions). How can I help?`
    - responses: `[mockup] {model} speaking (OpenAI Responses). How can I help?`
  - 流式按字符逐出不变

- **P4 — CLI 读 routes 回退**
  - `cli/core/config.py::load_routes` 在 yaml 没有 routes 段时，返回 `{**DEFAULT_MOCKUP_ROUTES}`
  - 既 server 又 CLI 在"无配置"时看到同一份 mockup routes，展示统一

- **P5 — probe 结构化**
  - `probe_route(name, conf)` 返回 `{route, provider, base_url, status: "ok"|"failed"|"mockup", status_reason, models}`
  - mockup 路由跳过实际 HTTP 探测，`probe_all` 用 `asyncio.gather` 并发

- **P6 — Display 扩展**
  - `_format_route_sections(results)` 统一格式化多条路由展示
  - `print_welcome` 签名改为 `(..., route_results, footer_note)`，复用 `_format_route_sections`
  - `print_route_status(result)` 单路由 inline 展示（用于 `/route` 切换后）
  - `print_route_picker(routes_with_provider, current)` 数字选择器
  - Windows 适配：`main.py` 给 stdout reconfigure `utf-8`，否则 GBK 无法编码 `✓/✗`

- **P7 — chat 启动决策**
  - `_startup_probe(config, args)` 前置：
    - 默认模式：load_routes → probe_all → 默认路由 = 首个 key
    - 显式 --base-url：probe 单条，默认 route = `ROUTE_PRIORITY[0]`
    - 计算 `footer_note`：全 mockup → 提示；全失败 → 告警
  - `Repl.__init__` 接收 `route_results` / `footer_note`，`run()` 打印 welcome 不再重新探测
  - `_refresh_current_route` 在 `/route`、`/routes` 切换后只探新路由，调用 `print_route_status`

- **P8 — `/routes` 命令**
  - `CommandHandler._cmd_routes`：
    - 默认场景读 yaml routes（带 provider 信息）
    - 显式场景固定列 `ROUTE_PRIORITY`（provider 填 None）
    - 选中后更新 `config["route"]`，REPL 主循环会检测路由变化并走统一切换流水线

- **P9 — Tab 补全 + /help**
  - `COMMANDS` 列表补 `/routes`，Tab 能补到
  - `/help` 文案新增一行 `/routes  列出路由并选择切换`

- **P10 — 测试 + E2E**
  - `pytest` 85 passed
  - E2E：
    - 默认启动：routes 从 settings.yaml 读，并发探测，按配置顺序展示 completions (ollama) ✓ / responses (claude) ✗ / messages (openai) ✓
    - 显式 `--base-url http://localhost:11434`：单条路由 completions (direct) ✓
    - 两条路径都正确渲染 Unicode 符号（✓/✗）和中文文案

- **P11 — 文档同步**
  - README 特性列表：启动展示语义更新，新增 `/routes` 命令和 server mockup 默认说明
  - README 斜杠命令表新增 `/routes`，`/route` 描述改为"直接切换"以区分
