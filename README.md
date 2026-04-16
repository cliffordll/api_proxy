# API Proxy — 多协议双向转换代理

一个基于 FastAPI 的轻量级 API 代理服务，实现 OpenAI、Claude (Anthropic)、Responses 三套 API 协议之间的**双向实时转换**。支持通过配置灵活切换上游供应商，无需修改业务代码。

---

## 功能特性

- **三协议互转**：Completions / Messages / Responses 三种格式 6 个方向全覆盖
- **配置驱动**：`settings.yaml` 一个文件定义上游供应商 + 转换器组合，新增供应商只改配置
- **Proxy 架构**：`proxy.chat()` 一行调用，自动完成 请求转换 → 上游调用 → 响应转换
- **四种客户端**：ClaudeClient (anthropic SDK) / OpenAIClient (openai SDK) / HttpxClient (通用 HTTP) / MockupClient (调试模式)
- **流式响应 (SSE)**：完整支持流式输出，逐事件转换
- **Tool Calling**：完整支持工具调用互转
- **模型名自动映射**：可通过 YAML 配置自定义，未命中则透传
- **认证透传**：不存储任何 API Key，从请求中提取后直接传给上游
- **调试模式**：MockupClient 无需真实 API 即可测试全流程

---

## 快速开始

### 环境要求

- Python 3.10+

### 安装

```bash
git clone https://github.com/cliffordll/api_proxy.git
cd api_proxy
pip install -r requirements.txt
```

### 配置（可选）

所有配置通过 `config/settings.yaml` 统一管理（含服务参数和 Provider 配置），不存在时使用内置默认值，零配置即可启动。

```bash
cp config/settings.example.yaml config/settings.yaml
```

### 启动服务

```bash
python main.py server
```

服务默认监听 `http://0.0.0.0:8000`。

### CLI 对话

```bash
# 交互模式
python main.py chat

# 单次对话
python main.py chat "hello"

# 指定参数
python main.py chat --base-url http://localhost:8000 --route messages --model qwen2.5:3b
```

交互模式支持斜杠命令：`/help` `/model` `/route` `/stream` `/history` `/clear` `/quit`

### 冒烟测试

```bash
python main.py test
python main.py test --base-url http://remote:8000
```

### 调试模式

无需真实 API Key，使用 MockupClient 测试全流程：

```bash
cp config/settings.mockup.yaml config/settings.yaml
python main.py server
```

### 验证

```bash
curl http://localhost:8000/health
# 返回: {"status":"ok"}
```

---

## API 端点

### `GET /health`

健康检查。返回 `{"status": "ok"}`。

### `POST /v1/chat/completions`

OpenAI Completions 兼容端点。认证：`Authorization: Bearer <api-key>`

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-ant-xxxxx" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"Hello!"}]}'
```

### `POST /v1/responses`

OpenAI Responses 兼容端点。认证：`Authorization: Bearer <api-key>`

```bash
curl http://localhost:8000/v1/responses \
  -H "Authorization: Bearer sk-ant-xxxxx" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","input":"Hello!"}'
```

### `POST /v1/messages`

Claude Messages 兼容端点。认证：`x-api-key: <api-key>`

```bash
curl http://localhost:8000/v1/messages \
  -H "x-api-key: sk-xxxxx" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6-20250514","max_tokens":1024,"messages":[{"role":"user","content":"Hello!"}]}'
```

所有端点均支持 `"stream": true` 流式输出。

---

## 与 SDK 配合使用

### OpenAI SDK → Claude

```python
from openai import OpenAI

client = OpenAI(api_key="sk-ant-xxxxx", base_url="http://localhost:8000/v1")
response = client.chat.completions.create(
    model="gpt-4o",  # 自动映射为 claude-sonnet-4-6
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

### Anthropic SDK → OpenAI

```python
import anthropic

client = anthropic.Anthropic(api_key="sk-xxxxx", base_url="http://localhost:8000")
message = client.messages.create(
    model="claude-sonnet-4-6-20250514",  # 自动映射为 gpt-4o
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}],
)
print(message.content[0].text)
```

---

## Provider 配置

通过 `config/settings.yaml` 配置每个端点的上游供应商和转换器：

```yaml
completions:
  path: /v1/chat/completions
  base_url: https://api.anthropic.com
  provider: claude           # 客户端类型
  interface: messages        # 上游接口类型
  converter: completions_from_messages  # 转换器

responses:
  path: /v1/responses
  base_url: https://api.anthropic.com
  provider: claude
  interface: messages
  converter: responses_from_messages

messages:
  path: /v1/messages
  base_url: https://api.openai.com/v1
  provider: openai
  interface: completions
  converter: messages_from_completions
```

| 字段 | 说明 |
|------|------|
| `provider` | 客户端类型：`claude` / `openai` / `httpx` / `mockup` |
| `interface` | 上游接口：`messages` / `completions` / `responses` |
| `converter` | 转换器：`{输出格式}_from_{输入格式}` |

### 扩展示例

切换上游为 Ollama（兼容 OpenAI 协议）：

```yaml
messages:
  base_url: http://localhost:11434/v1
  provider: ollama
  interface: completions
  converter: messages_from_completions
```

通过 HttpxClient 接入任意兼容 API：

```yaml
completions:
  base_url: https://some-provider.com
  provider: httpx
  interface: completions
  converter: completions_from_completions
```

---

## 模型映射

在 `config/settings.yaml` 的 `mappings` 段配置，未命中则透传：

```yaml
mappings:
  openai_to_claude:
    gpt-4o: claude-sonnet-4-6-20250514
    gpt-4: claude-opus-4-6-20250514
    gpt-3.5-turbo: claude-haiku-4-5-20251001
  claude_to_openai:
    claude-sonnet-4-6-20250514: gpt-4o
    claude-opus-4-6-20250514: gpt-4
    claude-haiku-4-5-20251001: gpt-3.5-turbo
```

---

## 项目结构

```
api_proxy/
├── main.py                          # 统一入口（server / chat / test）
├── requirements.txt
├── config/
│   ├── settings.yaml                # 配置（server + mappings + routes + client）
│   ├── settings.example.yaml        # 配置模板
│   └── settings.mockup.yaml         # 调试模式配置
├── app/                             # 代理服务
│   ├── server.py                    # 服务启动（FastAPI app）
│   ├── core/
│   ├── clients/
│   ├── converters/
│   ├── routes/
│   └── tests/                       # 服务测试（57）
├── cli/                             # CLI 客户端（独立，不 import app/）
│   ├── client.py                    # ChatClient (HTTP + SSE)
│   ├── conversation.py              # 多轮对话管理
│   ├── commands.py                  # 斜杠命令
│   ├── display.py                   # rich 格式化输出
│   ├── repl.py                      # 交互循环
│   ├── tester.py                    # 冒烟测试
│   └── tests/                       # CLI 测试（28）
```

---

## 架构

```
用户请求 → 路由层 → Proxy.chat() → [Converter.convert_request → Client.chat → Converter.convert_response] → 响应
```

- **Proxy**：封装 Client + Converter，`chat()` 一行调用完成全流程
- **ProxyRegistry**：按接口名管理 Proxy 实例，`load_providers()` 从配置自动装配
- **BaseClient**：统一 `chat(dict, api_key, stream)` 接口，输出 dict / AsyncIterator[str]
- **BaseConverter**：纯格式转换，输入输出统一 dict/str，无 SDK 类型依赖

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
| 配置管理 | PyYAML (config/settings.yaml) |
| 模型映射 | PyYAML |
| 测试 | pytest + pytest-asyncio |

---

## License

MIT
