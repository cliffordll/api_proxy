# API Proxy — 多协议双向转换代理

一个基于 FastAPI 的轻量级 API 代理服务，实现 OpenAI、Claude (Anthropic)、Responses 三套 API 协议之间的**双向实时转换**。支持通过配置灵活切换上游供应商，内置 CLI 客户端，无需修改业务代码。

---

## 功能特性

### 代理服务
- **三协议互转**：Completions / Messages / Responses 三种格式 6 个方向全覆盖
- **配置驱动**：`settings.yaml` 一个文件管理服务 + 路由
- **Proxy 架构**：`proxy.chat()` 一行调用，自动完成 请求转换 → 上游调用 → 响应转换
- **四种客户端**：ClaudeClient / OpenAIClient (ollama 复用) / HttpxClient / MockupClient
- **自动透传**：不配 `from` 字段时自动透传，无需格式转换
- **无 routes 自动 mockup**：settings.yaml 无 `routes` 段时，server 加载 `DEFAULT_MOCKUP_ROUTES`，三条路由全 mockup，永远能启动
- **流式响应 (SSE)**：完整支持流式输出
- **Tool Calling**：完整支持工具调用互转
- **模型名透传**：直接透传上游，无隐式改名
- **认证透传**：不存储 API Key，从请求中提取后直接传给上游

### CLI 客户端
- **交互对话**：多轮对话 + 流式输出 + 上下文记忆
- **Tab 补全**：斜杠命令、模型名、路由名动态补全
- **一次探测、永久缓存**：`chat` 启动并发探测所有路由，welcome 框内统一展示 `(provider)` + 状态符号 (`✓` / `✗` / `[mockup]`) + 模型列表；后续 `/route` / `/routes` / `/models` 切换都只查缓存，不再联网
- **直连模式**：`--base-url` 直连任意兼容端点，绕过 Proxy；三条路由共享同一探测结果
- **斜杠命令**：`/route` `/routes` `/model` `/models` `/stream` `/history` `/clear` `/quit`
- **Tool Call 展示**：格式化展示工具调用参数和结果
- **冒烟测试**：`python main.py test` 一键验证服务可用性

---

## 快速开始

### 安装

```bash
git clone https://github.com/cliffordll/api_proxy.git
cd api_proxy
pip install -r requirements.txt
```

### 配置

```bash
cp config/settings.example.yaml config/settings.yaml
```

所有配置通过 `config/settings.yaml` 统一管理，不存在时使用内置默认值。

### 启动

```bash
python main.py server          # 启动代理服务
python main.py chat            # 交互对话
python main.py test            # 冒烟测试
```

### 调试模式

```bash
cp config/settings.mockup.yaml config/settings.yaml
python main.py server
```

---

## CLI 使用

### 交互模式

```bash
python main.py chat
python main.py chat --base-url http://localhost:8000 --route messages --model qwen2.5:3b
```

支持 Tab 自动补全和上下箭头翻历史。

### 斜杠命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助 |
| `/model <name>` | 切换模型 |
| `/models` | 查看可用模型并选择 |
| `/route <name>` | 直接切换路由（completions / messages / responses） |
| `/routes` | 列出路由 + 数字选中切换 |
| `/stream on\|off` | 开关流式 |
| `/history` | 查看对话历史 |
| `/clear` | 清空对话 |
| `/quit` | 退出 |

### 命令行参数

| 参数 | 说明 |
|------|------|
| `--base-url` | 目标服务基础地址（不带 /v1） |
| `--route` | 路由：completions / messages / responses |
| `--model` | 模型名 |
| `--api-key` | 认证密钥 |
| `--stream` / `--no-stream` | 流式开关 |

参数优先级：命令行 > settings.yaml 推导值（`server` 段）> 内置默认值。

### 冒烟测试

```bash
python main.py test                                # 测本地服务
python main.py test --base-url http://remote:8000  # 测远程服务
python main.py test --route completions            # 测单个路由
```

---

## API 端点

### `GET /health`

健康检查。返回 `{"status": "ok"}`。

### `POST /v1/chat/completions`

Completions 兼容端点。认证：`Authorization: Bearer <api-key>`

### `POST /v1/responses`

Responses 兼容端点。认证：`Authorization: Bearer <api-key>`

### `POST /v1/messages`

Messages 兼容端点。认证：`x-api-key: <api-key>`

所有端点均支持 `"stream": true` 流式输出。

---

## 配置

### 完整结构

```yaml
# config/settings.yaml

server:
  host: 0.0.0.0
  port: 8000
  log_level: info
  default_max_tokens: 4096

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

CLI 默认值：`base_url` 从 `server.host:port` 推导。

### 路由配置字段

| 字段 | 说明 |
|------|------|
| `path` | 本代理暴露的路由路径 |
| `base_url` | 上游 API 地址（claude 不带 /v1，openai/ollama 带 /v1） |
| `provider` | 客户端类型：`claude` / `openai` / `ollama` / `httpx` / `mockup` |
| `from` | 上游格式，自动推导转换器（`{路由名}_from_{from值}`），不配则透传 |

### 扩展示例

```yaml
# Ollama
routes:
  messages:
    path: /v1/messages
    base_url: http://localhost:11434/v1
    provider: ollama
    from: completions

# 透传（不配 from，不做格式转换）
  completions:
    path: /v1/chat/completions
    base_url: http://localhost:11434/v1
    provider: httpx
```

---

## 与 SDK 配合使用

### OpenAI SDK → Claude

```python
from openai import OpenAI

client = OpenAI(api_key="sk-ant-xxxxx", base_url="http://localhost:8000/v1")
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

### Anthropic SDK → OpenAI

```python
import anthropic

client = anthropic.Anthropic(api_key="sk-xxxxx", base_url="http://localhost:8000")
message = client.messages.create(
    model="claude-sonnet-4-6-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}],
)
print(message.content[0].text)
```

---

## 项目结构

```
api_proxy/
├── main.py                          # 统一入口（server / chat / test）
├── requirements.txt
├── config/
│   ├── settings.yaml                # 配置（server + routes）
│   ├── settings.example.yaml        # 配置模板
│   └── settings.mockup.yaml         # 调试模式配置
├── app/                             # 代理服务
│   ├── server.py                    # 服务启动（FastAPI app）
│   ├── core/                        # 核心层（BaseClient/BaseConverter/Proxy/Loader）
│   ├── clients/                     # 客户端层（Claude/OpenAI/Httpx/Mockup）
│   ├── converters/                  # 转换层（6 个转换器 + PassthroughConverter）
│   ├── routes/                      # 路由层（completions/messages/responses）
│   └── tests/                       # 服务测试
├── cli/                             # CLI 客户端（独立，不 import app/）
│   ├── repl.py                      # 交互循环 Repl + start 入口
│   ├── tester.py                    # 冒烟测试
│   ├── chat/                        # chat 会话相关
│   │   ├── commands.py              # 斜杠命令 + Tab 补全 (CommandHandler + DynamicCompleter)
│   │   ├── conversation.py          # 多轮对话管理
│   │   └── probe.py                 # Probe 类：启动决策 + 路由探测 + 默认模型
│   ├── core/                        # 基础组件（跨命令共用）
│   │   ├── client.py                # ChatClient (HTTP + SSE)
│   │   ├── config.py                # 配置加载 + load_routes (mockup 自动回退)
│   │   └── display.py               # rich 格式化输出
│   └── tests/                       # CLI 测试
├── common/                          # app 和 cli 共享
│   ├── http.py                      # HttpClient (httpx 薄封装)
│   └── routes.py                    # 路由常量 + 默认 mockup 配置 + merge_routes 自动回退
└── docs/
    ├── architecture.md              # 架构设计
    ├── feature.md                   # 开发计划
    ├── process.md                   # 开发过程记录
    ├── hotfix/                      # Hotfix 设计与过程
    └── history/                     # 归档历史
```

---

## 测试

```bash
python -m pytest app/tests/ cli/tests/ -v   # 全部测试（85）
python -m pytest app/tests/ -v              # 服务测试（57）
python -m pytest cli/tests/ -v              # CLI 测试（28）
python main.py test                         # 冒烟测试（需服务运行）
```

---

## 技术栈

| 组件 | 选型 |
|------|------|
| Web 框架 | FastAPI |
| OpenAI 客户端 | openai SDK |
| Anthropic 客户端 | anthropic SDK |
| 通用 HTTP | httpx |
| 配置管理 | PyYAML |
| CLI 终端 | rich + prompt_toolkit |
| 测试 | pytest + pytest-asyncio |

---

## License

MIT
