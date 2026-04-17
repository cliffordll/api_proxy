# Hotfix fix2：上游模型探测与展示

## 需求

1. `python main.py models` 子命令：根据 settings.yaml 的 routes 配置，逐个探测各上游服务的可用模型并统一展示
2. `python main.py chat` REPL：
   - 启动时在 welcome 框内展示当前 route 对应上游的模型列表（原先打到 Proxy `/v1/models`，Proxy 无此端点，一直显示"探测不可用"）
   - `/route` 切换后重探并以扁平列表展示（区分"总览"和"运行中提示"）
   - `/models` 命令走同一套探测逻辑
3. `chat --base-url` 覆盖 base_url 时，探测目标改为该地址（用户在绕过 Proxy 直连），不再走 routes 配置

## 使用方式

```bash
python main.py models                          # 探测所有路由
python main.py models --route messages         # 仅探测指定路由

python main.py chat                            # 启动时探测当前 route 上游模型
python main.py chat --base-url http://host:port  # 探测该地址（不走 routes）
# 在 REPL 内 /route <name> 切换路由 → 自动重探
# 在 REPL 内 /models → 列出当前 route 上游模型（可选择切换）
```

## 输出效果

### `python main.py models`

```
╭─────────────── Available Models ───────────────╮
│ 服务: http://localhost:8008                     │
│                                                 │
│ completions (http://localhost:11434/v1 / ollama)│
│   - qwen2.5:3b                                  │
│   - deepseek-r1:1.5b                            │
│                                                 │
│ responses (https://api.anthropic.com / claude)  │
│   模型探测不可用                                │
│                                                 │
│ messages (http://localhost:11434/v1 / openai)   │
│   - qwen2.5:3b                                  │
╰─────────────────────────────────────────────────╯
```

### `python main.py chat`

```
╭─────────────── API Proxy CLI ───────────────╮
│ 服务: http://localhost:8008                  │
│ 路由: completions  模型: ...  流式: on       │
│                                              │
│ 可用模型 (http://localhost:11434/v1):        │
│   - qwen2.5:3b                               │
│   - deepseek-r1:1.5b                         │
╰──────────────────────────────────────────────╯
```

## 核心 API（cli/models.py）

- `load_routes(config_path)` — 读 settings.yaml 的 routes 段
- `get_route_base_url(route, config_path)` — 取某路由上游 base_url
- `probe_models(base_url)` — 直连上游 `/v1/models`（兼容 base_url 已含 /v1 的情况），5s 超时，失败返回 `None`（区分"不可用"与"空列表"）
- `list_all(route_filter, config_path)` — 并发探测所有路由，返回 `[{route, base_url, provider, models}]`
- `start(args)` — CLI 入口，读 `--route` 过滤后委托 Display 渲染

## 探测路径决策（chat）

| 条件 | 探测目标 |
|------|---------|
| 默认（未传 `--base-url`） | `routes[当前路由].base_url`（Proxy 的真实上游） |
| CLI 显式传 `--base-url` | `config["base_url"]` 本身（用户绕过 Proxy 直连） |

判定依据：`merge_args` 在处理 `--base-url` 时写入 `config["base_url_override"] = True`，REPL / `/models` 据此分流。

## 改动

| # | 文件 | 说明 |
|---|------|------|
| 1 | `main.py` | 新增 `models` 子命令 |
| 2 | `cli/models.py` | 读 routes、探测上游、按路由聚合、`start()` 入口 |
| 3 | `cli/display.py` | 新增 `print_route_models`（Panel + 服务头部 + 多路由分节）；`print_welcome` 扩展 `models` / `upstream` 参数；`print_models` 扩展 `upstream` 参数 |
| 4 | `cli/repl.py` | `_probe_current_models()` 启动 + `/route` 切换后重探；静默探测填入 welcome |
| 5 | `cli/commands.py` | `/models` 命令改走 `probe_models(upstream)`，不再打到 Proxy |
| 6 | `cli/config.py` | `merge_args` 处理 `--base-url` 时记录 `base_url_override` |
| 7 | `cli/client.py` | 移除已废弃的 `ChatClient.list_models`（之前打 Proxy） |
