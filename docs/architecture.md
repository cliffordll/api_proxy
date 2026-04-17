# 架构设计 - API Proxy

> 多协议 API 代理 + CLI 客户端。Server 侧实现 OpenAI / Anthropic 三种协议之间的双向转换；CLI 侧提供交互式对话，统一经 `main.py` 分发。

---

## 1. 整体架构

```
┌──────────────────────────────────────────────────────────────┐
│                      main.py 统一入口                        │
│                                                              │
│  python main.py server       → app/server.py                 │
│  python main.py chat         → cli/repl.py                   │
│  python main.py test         → cli/tester.py                 │
└──────────────────────────────┬───────────────────────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
┌────────────────┐   ┌────────────────┐   ┌────────────────┐
│  app/server.py │   │  cli/repl.py   │   │ cli/tester.py  │
│  FastAPI app   │   │  Repl 交互循环 │   │  冒烟测试       │
│  Proxy 装配    │   │  ChatClient    │   │  HttpClient     │
│  路由注册      │   │  Display       │   │  Display        │
└────────┬───────┘   └────────┬───────┘   └────────┬───────┘
         │                    │                    │
         │                    └─── HTTP/SSE ───────┤
         │                                         ▼
         │                            ┌─────────────────────┐
         └──────────── 上游 ─────────▶│  代理服务 / 上游     │
                                     │  (自身 or 真实上游)  │
                                     └─────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  common/ （app + cli 共享）                                   │
│    http.py     HttpClient (httpx 薄封装)                     │
│    routes.py   ROUTE_PATHS / ROUTE_PRIORITY /                │
│                DEFAULT_MOCKUP_ROUTES / auth_headers           │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. 统一入口

```bash
# 启动代理服务
python main.py server
python main.py server --port 8080

# 交互对话（代理模式，走 settings.yaml 的 routes）
python main.py chat
python main.py chat --route messages --model qwen2.5:3b

# 交互对话（直连模式，绕过 Proxy）
python main.py chat --base-url http://localhost:11434

# 冒烟测试
python main.py test
python main.py test --base-url http://remote:8000
python main.py test --route completions
```

### chat 参数

| 参数 | 说明 |
|------|------|
| `--base-url` | 目标地址（空 = 代理模式，走 settings.yaml；有 = 直连模式，绕过代理） |
| `--route` | 路由 / 协议：`completions` / `messages` / `responses` |
| `--model` | 模型名（空则用启动探测到的首个模型） |
| `--api-key` | 认证密钥 |
| `--stream` / `--no-stream` | 流式开关 |

### 配置优先级

```
命令行参数 > settings.yaml 推导值（server 段）> 内置默认值
```

### Server 默认 mockup

`settings.yaml` 缺失或无 `routes` 段时，Server 加载 `common.routes.DEFAULT_MOCKUP_ROUTES` — 三条路由全 `provider: mockup`。永远能启动，响应带 `[mockup]` 前缀，无隐藏的外部依赖。

---

## 3. Server 侧设计

### 3.1 核心组件

- **`app/core/loader.py`**: 读 `settings.yaml` 的 `server` + `routes`，注册每条路由的 `Proxy = Client + Converter`
- **`app/core/proxy.py`**: `Proxy.chat(params, api_key, stream)` 组合 converter + client，一行完成请求转换 → 上游调用 → 响应转换
- **`app/core/converter.py` / `app/core/client.py`**: 基类（BaseConverter / BaseClient）

### 3.2 客户端

| Provider | 类 | 说明 |
|----------|----|----|
| `claude` | `ClaudeClient` | 基于 anthropic SDK |
| `openai` | `OpenAIClient` | 基于 openai SDK |
| `ollama` | `OpenAIClient` | 兼容 OpenAI 协议，别名 |
| `httpx` | `HttpxClient` | 通用 HTTP 透传（用 `common.http.HttpClient`） |
| `mockup` | `MockupClient` | 调试用，返回模拟数据，首字符带 `[mockup]` 标记 |

### 3.3 转换器（6 个方向）

```
messages ↔ completions ↔ responses
```

每对方向一个 `BaseConverter` 子类，6 个类；不配 `from` 字段时走 `PassthroughConverter`（上游格式 = 路由名，不转换）。

---

## 4. CLI 侧设计

### 4.1 文件布局

```
cli/
├── repl.py             # Repl 类 + start() 入口 + chat 子命令主流程
├── tester.py           # Tester 类 + start() 入口 + test 子命令
├── chat/               # chat 会话相关
│   ├── commands.py     # CommandHandler + DynamicCompleter（斜杠命令 + Tab 补全）
│   ├── conversation.py # Conversation 多轮对话
│   └── probe.py        # Probe 类：启动决策 + 路由探测 + 默认模型
└── core/               # 跨命令共用
    ├── client.py       # ChatClient：HTTP/SSE 请求发送与响应解析
    ├── config.py       # load_client_config / merge_args / load_routes
    └── display.py      # Display：rich 终端输出
```

### 4.2 Repl 组件

```python
class Repl:
    def __init__(self, config, route_results=None):
        self.client = ChatClient(...)          # 发送对话请求
        self.conversation = Conversation()     # 历史
        self.display = Display()               # 输出
        self.commands = CommandHandler(config, ..., route_results)  # 斜杠命令
        self.route_results = route_results     # 启动探测缓存
        self.available_models = ...            # 当前路由模型
```

### 4.3 启动决策（`cli/chat/probe.py::Probe`）

```
Probe(config, args).run()
  ├── 代理模式（无 --base-url）
  │     routes_conf = load_routes()                        # yaml，缺失的标准路由自动 fallback 到 mockup
  │     results = await self._probe_all(routes_conf)       # 并发探所有路由
  │     default route = yaml 首条
  │
  └── 直连模式（有 --base-url）
        models = await self._probe_models(base_url)        # 一次探测
        results = [三条路由共享同一 models]
        default route = ROUTE_PRIORITY[0] = completions
```

**探测时机**：**只在启动时探测一次**。之后 `/route` / `/routes` 切换、`/models` 命令全部查缓存，不再联网。

**默认模型**：
- 未传 `--model` → 用当前路由首个模型
- 传了 `--model` → 以用户指定为准（`model_override=True`）
- 切换路由时始终用新路由首个模型（不受 override 影响）

### 4.4 路由 / 协议展示

三种 welcome 渲染：

**代理模式 yaml 有 routes**：
```
| 可用路由:                                          |
|   completions  (ollama)  ✓  http://localhost:11434/v1   *
|     - qwen2.5:3b
|     - ...
|   responses  (mockup)  ✓  http://localhost:8008
|     - (mockup)
|   messages  (openai)  ✓  ...
|     - ...
```

缺失的标准路由自动回落到 mockup（server loader + CLI load_routes 共享 `merge_routes`，用 `DEFAULT_MOCKUP_ROUTES` 填充 yaml 里没写的）。

**代理模式全 mockup（yaml 无 routes 或全 mockup）**：
```
| 可用路由:                                          |
|   completions  (mockup)  ✓  http://localhost:8008   *
|     - (mockup)
|   responses  (mockup)  ✓  http://localhost:8008
|     - (mockup)
|   messages  (mockup)  ✓  http://localhost:8008
|     - (mockup)
```

mockup 状态的 header 用 server 地址（用户真正请求的目标），体格与真实 ✓ 行一致。

**直连模式**：
```
| 直连端点:                                          |
|   completions  (direct)  ✓  http://localhost:11434
|     - qwen2.5:3b
|     - ...
```

直连模式下只展示当前路由（3 条 cache 共享同一探测结果），路由名自带协议语义（completions/responses/messages），不重复展示协议全称。

### 4.5 斜杠命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助 |
| `/route <name>` | 直接切换路由（名字定位） |
| `/routes` | 列出路由 + 数字选中切换；直连模式下走协议切换语义 |
| `/model <name>` | 直接切换模型 |
| `/models` | 列出当前路由模型（缓存）+ 数字选中切换 |
| `/stream on\|off` | 开关流式 |
| `/history` | 查看对话历史 |
| `/clear` | 清空对话 |
| `/quit` / `/exit` | 退出 |

---

## 5. 共享层 `common/`

打破 app ↔ cli 的严格隔离（原 CLAUDE.md 规范），新增中间层：

- **`common/http.py::HttpClient`**：SDK 风格的 httpx 封装，`get_json` / `post_json` / `iter_sse`（含 `skip_done`）；被 `app/clients/httpx_client.py`、`cli/core/client.py`、`cli/chat/probe.py` 共用
- **`common/routes.py`**：
  - `ROUTE_PATHS` — 协议名 → URL 路径
  - `ROUTES` — 所有协议名列表
  - `ROUTE_PRIORITY` — 排序优先级
  - `DEFAULT_MOCKUP_ROUTES` — 默认 mockup 路由配置
  - `merge_routes(yaml_routes)` — 将 yaml 与 DEFAULT_MOCKUP_ROUTES 合并，缺失的标准路由自动用 mockup 填充
  - `auth_headers(route, key)` — OpenAI / Anthropic 风格认证头

---

## 6. 数据流

### Server 侧请求处理
```
POST /v1/xxx
  │
  ▼
app/routes/*.py 路由 handler
  │
  ▼
Proxy.chat(params, api_key, stream)
  ├── converter.convert_request(params) → 目标格式
  ├── client.chat(params', api_key, stream)
  │     └── 上游 HTTP 调用（httpx / openai SDK / anthropic SDK）
  ▼
converter.convert_response(resp) → 原协议格式
  │
  ▼ 响应或 SSE 流
```

### CLI chat 交互
```
启动
  ├── load_client_config + merge_args
  ├── Probe(config, args).run() → route_results（同时回写 config.route / config.model）
  └── Repl.__init__ + run()
         │
         ▼  主循环
         ├── 斜杠命令 → CommandHandler.handle → 修改 config / 查缓存
         │     路由切换 → _apply_cached_route → 状态展示 + 默认模型切换
         │
         └── 普通对话 → Conversation.add_user
                         ▼
                    ChatClient.send / send_stream
                         ▼
                    Display.print_response / print_stream_chunk
                         ▼
                    Conversation.add_assistant
```

---

## 7. 技术栈

| 组件 | 选型 |
|------|------|
| Web 框架 | FastAPI |
| OpenAI 客户端 | openai SDK |
| Anthropic 客户端 | anthropic SDK |
| 通用 HTTP | httpx |
| 配置管理 | PyYAML |
| CLI 终端 | rich + prompt_toolkit |
| 测试 | pytest + pytest-asyncio |
