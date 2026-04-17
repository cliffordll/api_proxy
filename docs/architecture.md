# 架构设计 - API Proxy v0.4（CLI 客户端）

> 核心理念：基于现有 Proxy 服务，提供统一入口（server / chat / test），支持交互式对话、流式输出、Tool Call 展示和冒烟测试。

## 1. 整体架构

```
┌──────────────────────────────────────────────────────────────┐
│                      main.py 统一入口                         │
│                                                              │
│  python main.py server       → app/server.py                 │
│  python main.py chat         → cli/repl.py                   │
│  python main.py test         → cli/tester.py                 │
│                                                              │
│  ┌─ app/server.py ─┐  ┌─ cli/ ──────────────────────────┐  │
│  │ load_providers() │  │ ChatClient    HTTP + SSE 请求    │  │
│  │ uvicorn.run()    │  │ Conversation  多轮对话历史       │  │
│  │                  │  │ CommandHandler 斜杠命令          │  │
│  │                  │  │ Display       rich 格式化输出    │  │
│  │                  │  │ Tester        冒烟测试           │  │
│  └──────────────────┘  └─────────────────────────────────┘  │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTP / SSE
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    API Proxy 服务（或任意兼容服务）             │
│  /v1/chat/completions    /v1/responses    /v1/messages        │
└──────────────────────────────────────────────────────────────┘
```

## 2. 统一入口

```bash
# 启动代理服务
python main.py server
python main.py server --port 8080

# 交互对话
python main.py chat
python main.py chat --base-url http://remote:8000 --route messages --model qwen2.5:3b

# 单次对话
python main.py chat "hello"

# 冒烟测试
python main.py test
python main.py test --base-url http://remote:8000
python main.py test --route completions
```

### 全局参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--base-url` | `http://localhost:8000` | 目标服务基础地址 |
| `--route` | `messages` | 路由：`completions` / `messages` / `responses` |
| `--model` | `claude-sonnet-4-6-20250514` | 模型名 |
| `--api-key` | 配置文件或环境变量 `API_KEY` | 认证密钥 |
| `--stream` / `--no-stream` | `--stream` | 流式开关 |

### 配置优先级

```
命令行参数 > config/settings.yaml 推导值（server 段）> 内置默认值
```

```yaml
# config/settings.yaml
server:
  host: 0.0.0.0
  port: 8000
  ...

routes:
  completions:
    path: /v1/chat/completions
    base_url: https://api.anthropic.com
    provider: claude
    from: messages
  responses:
    path: /v1/responses
    base_url: https://api.anthropic.com
    provider: claude
    from: messages
  messages:
    path: /v1/messages
    base_url: https://api.openai.com/v1
    provider: openai
    from: completions
```

## 3. 模块设计

### 3.1 ChatClient — HTTP 客户端

```python
# cli/client.py

class ChatClient:
    """向目标服务发送请求，处理 SSE 流。"""

    def __init__(self, base_url: str, route: str, api_key: str):
        self.base_url = base_url
        self.route = route
        self.api_key = api_key

    async def send(self, messages: list[dict], model: str,
                   stream: bool = True) -> dict | AsyncIterator[str]:
        """发送对话请求。"""

    def _build_request(self, messages, model, stream) -> tuple[str, dict, dict]:
        """根据 route 构建 URL / headers / body。"""

    def _parse_response(self, data: dict) -> tuple[str, list[dict]]:
        """解析响应，提取文本和 tool_calls。"""

    def _parse_stream_event(self, line: str) -> str | None:
        """解析 SSE 行，提取增量文本。"""
```

三种路由的差异封装在 ChatClient 内部：

| route | URL | 认证头 | 请求体 | 响应解析 |
|-------|-----|--------|--------|---------|
| `completions` | `/v1/chat/completions` | `Authorization: Bearer` | `{"messages": [...]}` | `choices[0].message` |
| `messages` | `/v1/messages` | `x-api-key` | `{"messages": [...]}` | `content[0].text` |
| `responses` | `/v1/responses` | `Authorization: Bearer` | `{"input": [...]}` | `output[0].content` |

### 3.2 Conversation — 对话管理

```python
# cli/conversation.py

class Conversation:
    """多轮对话历史管理。"""

    def add_user(self, content: str) -> None: ...
    def add_assistant(self, content: str, tool_calls: list[dict] = None) -> None: ...
    def add_tool_result(self, tool_call_id: str, result: str) -> None: ...
    def get_messages(self) -> list[dict]: ...
    def clear(self) -> None: ...
```

### 3.3 CommandHandler — 斜杠命令

```python
# cli/commands.py

class CommandHandler:
    """解析和执行斜杠命令。"""

    def handle(self, input_text: str, context: dict) -> bool:
        """处理斜杠命令，返回 True 表示已处理。"""
```

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助 |
| `/model <name>` | 切换模型 |
| `/route <name>` | 切换路由 |
| `/stream on\|off` | 开关流式 |
| `/history` | 查看对话历史 |
| `/clear` | 清空对话 |
| `/quit` 或 `/exit` | 退出 |

### 3.4 Display — 输出格式化

```python
# cli/display.py

class Display:
    """终端格式化输出，基于 rich。"""

    def print_welcome(self): ...
    def print_response(self, text: str): ...
    def print_stream_start(self): ...
    def print_stream_chunk(self, text: str): ...
    def print_stream_end(self): ...
    def print_tool_call(self, name: str, arguments: dict): ...
    def print_tool_result(self, result: str): ...
    def print_error(self, message: str): ...
    def print_info(self, message: str): ...
    def print_history(self, messages: list[dict]): ...
```

输出效果：

```
╭─ API Proxy CLI ──────────────────────────────╮
│ 服务: http://localhost:8000                    │
│ 路由: messages  模型: qwen2.5:3b  流式: on    │
╰──────────────────────────────────────────────╯

> what's the weather in Beijing?

🔧 Tool Call: get_weather
┌─ arguments ─────────────────────┐
│ {"city": "Beijing"}             │
└─────────────────────────────────┘
┌─ result ────────────────────────┐
│ {"temperature": 25, "sunny"}    │
└─────────────────────────────────┘

北京今天晴天，25°C。

> /route completions
✓ 路由已切换: completions

> /quit
Bye!
```

### 3.5 Tester — 冒烟测试

```python
# cli/tester.py

class Tester:
    """自动冒烟测试。"""

    async def run(self, route: str = None) -> bool:
        """运行测试，可指定路由或测全部。"""
```

输出效果：

```
$ python main.py test

API Proxy 冒烟测试
==================
✓ GET  /health                          200
✓ POST /v1/chat/completions (非流式)     200
✓ POST /v1/chat/completions (流式)       200 SSE
✓ POST /v1/messages (非流式)             200
✓ POST /v1/messages (流式)               200 SSE
✓ POST /v1/responses (非流式)            200
✓ POST /v1/responses (流式)              200 SSE

7/7 通过
```

### 3.6 REPL — 交互循环

```python
# cli/repl.py

class Repl:
    """交互式循环，组装各模块。"""

    def __init__(self, client, conversation, commands, display): ...

    async def run(self):
        """主循环：读输入 → 命令或对话 → 显示输出。"""
```

## 4. 项目结构

```
api_proxy/
├── main.py                      # 统一入口（server / chat / test）
├── app/                         # 代理服务代码
│   ├── server.py                # 服务启动逻辑（lifespan + uvicorn.run）
│   ├── core/
│   ├── clients/
│   ├── converters/
│   ├── routes/
│   └── tests/                   # 服务测试（跟着 app/ 走）
│       ├── conftest.py
│       ├── test_core/
│       ├── test_converters/
│       ├── test_clients/
│       └── test_routes/
├── cli/                         # CLI 客户端（独立，不 import app/）
│   ├── __init__.py
│   ├── client.py                # ChatClient (HTTP + SSE)
│   ├── conversation.py          # 多轮对话管理
│   ├── commands.py              # 斜杠命令
│   ├── display.py               # rich 格式化输出
│   ├── repl.py                  # 交互循环
│   ├── tester.py                # 冒烟测试
│   └── tests/                   # CLI 测试（跟着 cli/ 走）
│       ├── __init__.py
│       ├── test_client.py
│       ├── test_conversation.py
│       └── test_commands.py
├── config/
│   └── settings.yaml            # server + mappings + routes + client 配置
└── docs/
```

## 5. 依赖

```
# requirements.txt 新增
rich>=13.0.0                     # 终端美化
```

## 6. 数据流

```
用户输入
  │
  ├─ 斜杠命令 → CommandHandler → Display 输出
  │
  └─ 对话内容 → Conversation.add_user()
                    │
                    ▼
              ChatClient.send()
                    │
                    ├─ 非流式 → 解析响应 → Display.print_response()
                    │                        │
                    │                        ├─ 有 tool_calls → Display.print_tool_call()
                    │                        └─ 纯文本 → 直接显示
                    │
                    └─ 流式 → 逐行解析 SSE → Display.print_stream_chunk()
                    │
                    ▼
              Conversation.add_assistant()
```

## 7. 开发阶段

```
Phase 1: 统一入口 + 基础对话     main.py 子命令 + ChatClient + Repl + Display
Phase 2: 流式输出               SSE 解析 + 逐字显示
Phase 3: 多轮对话               Conversation 历史管理
Phase 4: 斜杠命令               CommandHandler
Phase 5: Tool Call 展示         解析 tool_calls + 格式化显示
Phase 6: 冒烟测试               Tester
Phase 7: 测试 + 文档            单元测试 + README 更新
```
