# Hotfix fix4：Server 默认 mockup + chat 启动策略 + `/routes` 命令

---

## 核心理念

- **Server 永远能启动**：未配 routes 时走 mockup，响应带 `[mockup]` 首字标记但正文模拟真实 LLM 风格
- **chat 启动一次性全量探测**：把代理当前能用什么、不能用什么一屏给出
- **统一状态符号**：无论是 mockup / 探测成功 / 失败，展示格式一致
- **切换触发探测、列表不触发**：`/routes` 出即见（快），切换才联网（准）
- 本次**不动** `python main.py models` 子命令，也不支持上游认证 — 拆到 **fix5**

---

## 需求与示例

### 1. Server：未配 routes 时默认 mockup

`app/core/loader.py::DEFAULT_CONFIG` 三条路由统一为 `provider: mockup`。同一份常量移到 `common/routes.py::DEFAULT_MOCKUP_ROUTES`，server 和 CLI 都能读：

```python
# common/routes.py
DEFAULT_MOCKUP_ROUTES = {
    "completions": {"path": "/v1/chat/completions", "base_url": "http://localhost", "provider": "mockup"},
    "responses":   {"path": "/v1/responses",        "base_url": "http://localhost", "provider": "mockup"},
    "messages":    {"path": "/v1/messages",         "base_url": "http://localhost", "provider": "mockup"},
}
```

### 2. Mockup 文案：带模型名 + 协议风格

`app/clients/mockup_client.py::_mock_*` 三种 interface 各用一句：

| interface | 文案 |
|-----------|------|
| messages | `[mockup] {model} speaking (Claude Messages). How can I help?` |
| completions | `[mockup] {model} speaking (OpenAI Completions). How can I help?` |
| responses | `[mockup] {model} speaking (OpenAI Responses). How can I help?` |

流式时按字符逐出，速率同原 mockup（20ms 一个字符），体验等同真实上游。例：用户传 `model=gpt-4o` 打 completions 路由，收到：

```
> 你好
[mockup] gpt-4o speaking (OpenAI Completions). How can I help?
```

三个信号一眼可见：`[mockup]` 非真上游 / `gpt-4o` 传的啥模型 / `(OpenAI Completions)` 走的哪条协议。

### 3. chat 启动流程

#### 3.1 默认（不传 `--base-url`，走 Proxy）

CLI 读 `settings.yaml::routes`；为空则用 `DEFAULT_MOCKUP_ROUTES`。然后对**每条 provider != mockup 的路由**并发探测 `/v1/models`，mockup 路由跳过。每条路由的 Header 格式：`{name}  ({provider})  {status}`，状态分三类详见下方「状态符号」章节。

**yaml 有 routes** — 按路由分组展示，每条路由下方直接列自己的模型：

```
$ python main.py chat
+--------------------------- API Proxy CLI ---------------------------+
| 服务: http://localhost:8008                                         |
| 路由: completions  模型: claude-sonnet-4-6-20250514  流式: on       |
|                                                                     |
| 可用路由:                                                           |
|   completions  (ollama)  ✓  http://localhost:11434/v1               |
|     - qwen2.5:3b                                                    |
|     - deepseek-r1:1.5b                                              |
|     - qwen2.5:7b                                                    |
|                                                                     |
|   responses    (claude)  ✗ 401 Unauthorized                         |
|                                                                     |
|   messages     (openai)  ✓  http://localhost:11434/v1               |
|     - qwen2.5:3b                                                    |
|     - deepseek-r1:1.5b                                              |
+---------------------------------------------------------------------+

> _
```

和 `probe` 子命令（fix5 将做）的展示格式对齐，信息同构、易比对。

**yaml 无 routes（= server mockup 默认）** — 统一用 `[mockup]` 状态展示：

```
$ python main.py chat
+--------------------------- API Proxy CLI ---------------------------+
| 服务: http://localhost:8008                                         |
| 路由: completions  模型: claude-sonnet-4-6-20250514  流式: on       |
|                                                                     |
| 可用路由:                                                           |
|   completions  (mockup)  [mockup]                                   |
|                                                                     |
|   responses    (mockup)  [mockup]                                   |
|                                                                     |
|   messages     (mockup)  [mockup]                                   |
|                                                                     |
| [mockup] 模式下响应正文开头会带 [mockup] 标记                       |
+---------------------------------------------------------------------+

> _
```

**yaml 有 routes 但全失败** — 告警但不退出，默认按 priority 取首条：

```
| 可用路由:                                                           |
|   completions  (claude)  ✗ 401 Unauthorized                         |
|                                                                     |
|   responses    (claude)  ✗ 401 Unauthorized                         |
|                                                                     |
|   messages     (openai)  ✗ timeout                                  |
|                                                                     |
| [!] 所有路由探测失败，代理可能不可用。默认路由仍为 completions      |
```

**默认路由挑选规则**：按 yaml 中 `routes` 段的**配置顺序**取第一条；yaml 无 routes 时，`DEFAULT_MOCKUP_ROUTES` 的第一条 = `completions`。用户控制权在自己手里（yaml 里谁写前面谁是默认），不再用 `ROUTE_PRIORITY` 隐式筛选。

#### 3.2 显式 `--base-url`（用户直连）

不读 routes，只探测用户指定的地址：

- 带 `--route`：直接用
- 不带 `--route`：默认取 yaml `routes` 第一条（yaml 为空时 = `completions`，即 `DEFAULT_MOCKUP_ROUTES` 首条）；用户进入 REPL 后可用 `/routes` 切换

展示和默认场景一致（单条路由分组格式）：

```
$ python main.py chat --base-url http://localhost:11434
+--------------------------- API Proxy CLI ---------------------------+
| 服务: http://localhost:11434                                        |
| 路由: completions  模型: claude-sonnet-4-6-20250514  流式: on       |
|                                                                     |
| 可用路由:                                                           |
|   completions  (direct)  ✓  http://localhost:11434/v1               |
|     - qwen2.5:3b                                                    |
|     - deepseek-r1:1.5b                                              |
+---------------------------------------------------------------------+

> _
```

显式直连没有 yaml provider 信息，统一填 `(direct)` 占位（用户直连标记）。

探测失败时：

```
| 可用路由:                                                           |
|   completions  (direct)  ✗ timeout                                  |
```

### 4. `/route` 和 `/routes` REPL 命令

#### `/route <name>` —— 直接切（保留）

```
> /route messages
路由已切换: messages
[探测中...]

可用路由:
  messages  (openai)  ✓  http://localhost:11434/v1
    - qwen2.5:3b
    - deepseek-r1:1.5b
```

#### `/routes` —— 纯列表 + 数字选择器（**不探测**）

```
> /routes
  [1] completions  (ollama)   *
  [2] responses    (claude)
  [3] messages     (openai)
选择路由 (输入编号，回车跳过): 2

路由已切换: responses
[探测中...]

可用路由:
  responses  (claude)  ✗ 401 Unauthorized
```

- 列表即出（不触发探测，读 yaml 或 `DEFAULT_MOCKUP_ROUTES`）
- 当前路由标 `*`
- 选中后走 `/route <name>` 流水线（探测新路由 + 刷模型 + 更新补全词表）
- 回车/Ctrl-C/无效编号跳过

显式 `--base-url` 场景下 `/routes` 不读 yaml，固定列三个标准名：

```
> /routes
  [1] completions   *
  [2] responses
  [3] messages
选择路由 (输入编号，回车跳过):
```

---

## 状态符号（贯穿 chat 启动 / `/route` / `/routes` 切换后）

| 符号 | 含义 | Header 之后 |
|------|------|------|
| `✓  {base_url}` | 探测成功 | 缩进列模型 |
| `✗ {原因}` | 探测失败（`401 {reason}` / `timeout` / `空列表`） | 无 |
| `[mockup]` | provider=mockup，跳过探测 | 无 |

路由 Header 格式：`{name}  ({provider})  {status}`（显式 `--base-url` 场景无 yaml provider 信息，统一填 `(direct)`）

---

## 探测时机规范

| 时机 | 探测 | 延迟 |
|------|------|------|
| `chat` 启动，默认模式 | 所有非 mockup 路由（`asyncio.gather`） | ~1s |
| `chat` 启动，显式 `--base-url` | 仅该地址 | ~300ms |
| `/route <name>` | 仅新路由 | ~300ms |
| `/routes` 列出 | 无 | 即时 |
| `/routes` 选中后切换 | 仅新路由 | ~300ms |

---

## 关键设计

### `common/routes.py` 扩展

```python
ROUTE_PRIORITY = ["completions", "responses", "messages"]

DEFAULT_MOCKUP_ROUTES = {
    # 见需求 1，按 completions → responses → messages 顺序写
}
```

- `ROUTE_PRIORITY`：**仅用于**显式 `--base-url` 场景的 `/routes` 固定列出顺序（那种场景没 yaml 可读）
- `DEFAULT_MOCKUP_ROUTES`：server loader 和 CLI load_routes 都在"yaml 无 routes"时回退；内部顺序 = ROUTE_PRIORITY
- 默认路由永远 = 实际 routes 配置的第一条

### 路由状态统一表示

`probe` 结果结构（在 cli/core/probe.py 返回）：

```python
{
    "status": "ok" | "failed" | "mockup",
    "status_reason": "401 Unauthorized" | "timeout" | "空列表" | None,
    "models": ["qwen2.5:3b", ...] | None,
}
```

Mockup 路由不走 HTTP 探测，直接 `{status: "mockup", status_reason: None, models: None}`。

### 路由选择器（仅 `/routes` 使用）

```python
def prompt_route_choice(
    routes: list[str],
    current: str | None = None,
    provider_map: dict[str, str] | None = None,
) -> str | None:
    """数字选择器。Ctrl-C/回车/无效编号返回 None（保持当前）。"""
```

- 启动流程不用 picker（都有确定的默认路由）
- `provider_map` 为空时在 `/routes` picker 里给每条路由填 `(direct)`（显式 `--base-url` 场景）
- 当前路由 `*` 标记

---

## 改动清单

| # | 文件 | 说明 |
|---|------|------|
| 1 | `common/routes.py` | 新增 `ROUTE_PRIORITY` + `DEFAULT_MOCKUP_ROUTES` |
| 2 | `app/core/loader.py` | `DEFAULT_CONFIG` 替换为 `DEFAULT_MOCKUP_ROUTES` |
| 3 | `app/clients/mockup_client.py` | 三种 interface 文案个性化（带 model + 协议风格） |
| 4 | `cli/core/config.py` | `load_routes()` 在 yaml 无 routes 时回退到 `DEFAULT_MOCKUP_ROUTES` |
| 5 | `cli/core/probe.py` | `probe_models` 保持；新增 `probe_all(routes)` 并发探测，mockup 跳过，返回结构化状态 |
| 6 | `cli/core/display.py` | 新增 `print_startup_routes(results, current)` 统一格式；`print_route_picker(routes, current, provider_map)` |
| 7 | `cli/repl.py` | `start()` 路由决策 + 并发探测 + welcome 展示；显式场景无 `--route` 时走 picker |
| 8 | `cli/chat/commands.py` | 新增 `/routes` 命令 |
| 9 | `cli/repl.py::COMMANDS` | 补 `/routes` 到 Tab 补全 |
| 10 | `README.md` | 同步 `/routes` + 启动语义 + server mockup 默认 |

---

## 兼容性

- `--route` / `/route <name>` 不变
- `settings.mockup.yaml` 保留（显式 mockup 用法仍有效）
- `python main.py models` 本次不动（fix5 再重命名 + 扩展）
- 测试不会被破坏（DEFAULT_CONFIG 仍然是三条路由，只是 provider 变了）
