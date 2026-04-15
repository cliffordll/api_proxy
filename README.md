# API Proxy — OpenAI / Claude 双向协议转换代理

一个基于 FastAPI 的轻量级 API 代理服务，实现 OpenAI 和 Claude (Anthropic) 两套 API 协议之间的**双向实时转换**。你可以用 OpenAI 客户端调用 Claude 模型，也可以用 Claude 客户端调用 OpenAI 模型，无需修改任何业务代码。

---

## 功能特性

- **双向协议转换**：OpenAI Chat Completions <-> Claude Messages，请求和响应全自动转换
- **流式响应 (SSE)**：完整支持流式输出，逐 token 转换，延迟极低
- **Tool Calling**：完整支持工具调用互转（tools 定义、tool_choice、tool_calls/tool_use、tool 结果消息）
- **模型名自动映射**：gpt-4o <-> claude-sonnet-4-6 等，可通过 YAML 配置自定义，未命中则透传
- **认证透传**：不存储任何 API Key，从客户端请求中提取后直接传给上游
- **错误格式转换**：利用 SDK 内置异常体系，自动转换为目标协议的错误格式
- **SDK 原生类型**：全链路使用 OpenAI / Anthropic 官方 SDK 类型，类型安全，自动对齐上游 API
- **可扩展架构**：ABC 抽象接口 + Provider 注册表，新增 Provider 只需实现接口并注册

---

## 快速开始

### 环境要求

- Python 3.10+

### 安装

```bash
# 克隆项目
git clone https://github.com/cliffordll/api_proxy.git
cd api_proxy

# 安装依赖
pip install -r requirements.txt
```

### 配置（可选）

复制环境变量模板并按需修改：

```bash
cp .env.example .env
```

所有配置项均有默认值，零配置即可启动。详见下方 [配置说明](#配置说明)。

### 启动

```bash
python main.py
```

服务默认监听 `http://0.0.0.0:8000`。

### 验证

```bash
curl http://localhost:8000/health
# 返回: {"status":"ok"}
```

---

## API 端点

### `GET /health`

健康检查端点。

**响应**：
```json
{"status": "ok"}
```

---

### `POST /v1/chat/completions`

**OpenAI 兼容端点**。接收 OpenAI Chat Completions 格式的请求，内部转换为 Claude Messages 格式，调用 Claude API，再将响应转回 OpenAI 格式返回。

**认证方式**：`Authorization: Bearer <your-claude-api-key>`

> 注意：这里传入的是你的 **Claude API Key**（sk-ant-xxx），代理会自动将其转为 Claude 需要的 `x-api-key` Header。

#### 非流式请求示例

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-ant-xxxxx" \
  -d '{
    "model": "gpt-4o",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Hello!"}
    ],
    "max_tokens": 1024
  }'
```

#### 流式请求示例

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-ant-xxxxx" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Tell me a joke"}],
    "stream": true
  }'
```

#### Tool Calling 示例

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-ant-xxxxx" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "What is the weather in Beijing?"}],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_weather",
          "description": "Get the current weather for a city",
          "parameters": {
            "type": "object",
            "properties": {
              "city": {"type": "string", "description": "The city name"}
            },
            "required": ["city"]
          }
        }
      }
    ],
    "tool_choice": "auto"
  }'
```

---

### `POST /v1/messages`

**Claude 兼容端点**。接收 Claude Messages 格式的请求，内部转换为 OpenAI Chat Completions 格式，调用 OpenAI API，再将响应转回 Claude 格式返回。

**认证方式**：`x-api-key: <your-openai-api-key>`

> 注意：这里传入的是你的 **OpenAI API Key**（sk-xxx），代理会自动将其转为 OpenAI 需要的 `Authorization: Bearer` Header。

#### 非流式请求示例

```bash
curl http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: sk-xxxxx" \
  -d '{
    "model": "claude-sonnet-4-6-20250514",
    "max_tokens": 1024,
    "system": "You are a helpful assistant.",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

#### 流式请求示例

```bash
curl http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: sk-xxxxx" \
  -d '{
    "model": "claude-sonnet-4-6-20250514",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Tell me a joke"}],
    "stream": true
  }'
```

---

## 与 OpenAI SDK 配合使用

只需修改 `base_url` 即可通过代理调用 Claude：

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-ant-xxxxx",  # 你的 Claude API Key
    base_url="http://localhost:8000/v1",
)

response = client.chat.completions.create(
    model="gpt-4o",  # 会被自动映射为 claude-sonnet-4-6
    messages=[{"role": "user", "content": "Hello!"}],
)

print(response.choices[0].message.content)
```

流式调用同样支持：

```python
stream = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Tell me a story"}],
    stream=True,
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

---

## 与 Anthropic SDK 配合使用

只需修改 `base_url` 即可通过代理调用 OpenAI：

```python
import anthropic

client = anthropic.Anthropic(
    api_key="sk-xxxxx",  # 你的 OpenAI API Key
    base_url="http://localhost:8000",
)

message = client.messages.create(
    model="claude-sonnet-4-6-20250514",  # 会被自动映射为 gpt-4o
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}],
)

print(message.content[0].text)
```

---

## 配置说明

所有配置通过环境变量或 `.env` 文件管理，均有合理默认值。

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | Claude API 上游地址 |
| `OPENAI_BASE_URL` | `https://api.openai.com` | OpenAI API 上游地址 |
| `HOST` | `0.0.0.0` | 服务监听地址 |
| `PORT` | `8000` | 服务监听端口 |
| `LOG_LEVEL` | `info` | 日志级别（debug/info/warning/error） |
| `DEFAULT_MAX_TOKENS` | `4096` | OpenAI 请求未指定 max_tokens 时的默认值（Claude API 要求必填） |
| `MODEL_MAPPING_FILE` | `config/model_mapping.yaml` | 模型映射配置文件路径 |

### 自定义上游地址

如果你使用第三方代理或私有化部署的 API，可以修改上游地址：

```env
ANTHROPIC_BASE_URL=https://your-claude-proxy.example.com
OPENAI_BASE_URL=https://your-openai-proxy.example.com
```

---

## 模型映射

代理内置了默认的模型名映射关系，也支持通过 `config/model_mapping.yaml` 自定义。

### 默认映射表

| OpenAI 模型名 | Claude 模型名 |
|---------------|---------------|
| `gpt-4o` | `claude-sonnet-4-6-20250514` |
| `gpt-4-turbo` | `claude-sonnet-4-6-20250514` |
| `gpt-4` | `claude-opus-4-6-20250514` |
| `gpt-3.5-turbo` | `claude-haiku-4-5-20251001` |

反向映射同理。

### 自定义映射

编辑 `config/model_mapping.yaml`：

```yaml
openai_to_claude:
  gpt-4o: claude-sonnet-4-6-20250514
  gpt-4o-mini: claude-haiku-4-5-20251001
  my-custom-model: claude-opus-4-6-20250514

claude_to_openai:
  claude-sonnet-4-6-20250514: gpt-4o
  claude-haiku-4-5-20251001: gpt-4o-mini
```

### 映射策略

1. 优先使用 YAML 配置文件中的映射
2. 配置文件不存在或未命中时，使用内置默认映射
3. 默认映射也未命中时，**模型名原样透传**给上游

---

## 错误处理

代理利用 SDK 内置异常体系捕获错误并转换为目标协议格式。

| 错误场景 | HTTP 状态码 | 说明 |
|----------|------------|------|
| 缺少认证 Header | 401 | 缺少 `Authorization` 或 `x-api-key` |
| 请求体 JSON 无效 | 400 | JSON 解析失败 |
| 请求字段缺失/无效 | 400 | 转换过程中 Key/Value 错误 |
| 上游认证失败 | 401 | `AuthenticationError` |
| 上游频率限制 | 429 | `RateLimitError` |
| 上游服务错误 | 502 | `InternalServerError` |
| 上游连接失败 | 502 | `APIConnectionError` |
| 上游请求超时 | 504 | `APITimeoutError` |

**OpenAI 格式错误响应**：
```json
{"error": {"message": "...", "type": "api_error", "code": "..."}}
```

**Claude 格式错误响应**：
```json
{"type": "error", "error": {"type": "api_error", "message": "..."}}
```

---

## 项目结构

```
api_proxy/
├── main.py                      # 应用入口 (python main.py 启动)
├── requirements.txt             # Python 依赖
├── .env.example                 # 环境变量模板
├── README.md                    # 本文档
├── CLAUDE.md                    # 开发规范
├── config/
│   └── model_mapping.yaml       # 模型映射配置
├── docs/
│   ├── architecture.md          # 架构设计文档
│   ├── feature.md               # 开发计划
│   ├── process.md               # 开发过程记录
│   └── hotfix/                  # Hotfix 设计与开发记录
│       └── fix1/
│           ├── design.md
│           └── process.md
├── app/
│   ├── core/
│   │   ├── client.py            # BaseClient 抽象基类
│   │   ├── converter.py         # BaseConverter 抽象基类 (Generic)
│   │   ├── config.py            # Settings 配置 + 模型映射加载
│   │   ├── registry.py          # ProviderRegistry + ProviderEntry
│   │   └── errors.py            # SDK 异常 → HTTP 错误格式转换
│   ├── routes/
│   │   ├── openai_compat.py     # POST /v1/chat/completions
│   │   └── claude_compat.py     # POST /v1/messages
│   ├── converters/
│   │   ├── openai_to_claude.py  # OpenAIToClaudeConverter
│   │   └── claude_to_openai.py  # ClaudeToOpenAIConverter
│   └── clients/
│       ├── claude_client.py     # ClaudeClient (anthropic.AsyncAnthropic)
│       └── openai_client.py     # OpenAIClient (openai.AsyncOpenAI)
└── tests/
    ├── conftest.py
    ├── test_core/
    │   ├── test_registry.py
    │   └── test_errors.py
    ├── test_converters/
    │   ├── test_openai_to_claude.py
    │   └── test_claude_to_openai.py
    └── test_routes/
        ├── test_openai_compat.py
        └── test_claude_compat.py
```

---

## 架构设计

```
请求流向：

OpenAI 客户端 → /v1/chat/completions → OpenAIToClaudeConverter → ClaudeClient → Claude API
                                      ← OpenAIToClaudeConverter ←

Claude 客户端 → /v1/messages → ClaudeToOpenAIConverter → OpenAIClient → OpenAI API
                             ← ClaudeToOpenAIConverter ←
```

核心设计：
- **BaseClient / BaseConverter**：ABC 抽象基类，定义客户端和转换器接口
- **ProviderRegistry**：注册表模式，路由层通过注册表获取 Provider 进行调度
- **SDK 原生类型**：转换器返回 SDK 结构体（`ChatCompletion`、`Message` 等），路由层通过 `model_dump()` 序列化

---

## 测试

```bash
# 运行全部测试
python -m pytest -v

# 仅运行转换器单元测试
python -m pytest tests/test_converters/ -v

# 仅运行路由集成测试
python -m pytest tests/test_routes/ -v

# 仅运行核心模块测试
python -m pytest tests/test_core/ -v
```

当前测试覆盖：**57 个测试**，包括：

- 纯文本对话（单轮/多轮）
- system 消息提取/注入
- tools 定义格式互转
- tool_choice 值映射（none/auto/required/specific）
- tool_calls / tool_use 消息互转
- tool 结果消息互转
- 流式事件逐条转换 + tool_call 参数累积
- max_tokens 缺省填充
- 模型名映射 + 未命中透传
- 认证 Key 透传验证
- 缺少认证返回 401
- Registry 注册/获取/不存在报错
- SDK 异常 → 错误格式转换

---

## 技术栈

| 组件 | 技术选型 |
|------|---------|
| Web 框架 | FastAPI |
| OpenAI 客户端 | openai SDK (AsyncOpenAI) |
| Anthropic 客户端 | anthropic SDK (AsyncAnthropic) |
| 配置管理 | pydantic-settings (支持 .env) |
| 模型映射 | PyYAML |
| 测试 | pytest + pytest-asyncio |

---

## 局限性与后续扩展

| 扩展项 | 扩展方式 |
|--------|---------|
| 新增 Provider（如 Gemini） | 实现 `BaseClient` + `BaseConverter`，注册到 `ProviderRegistry`，添加路由 |
| 多模态（图片/文件） | SDK 类型已原生支持，转换器添加对应分支即可 |
| 自定义认证中间件 | FastAPI middleware，不影响转换和客户端层 |
| 多 Key 轮询/负载均衡 | 客户端类内部实现 Key 池，接口不变 |
| 请求日志/监控 | FastAPI middleware + 结构化日志 |
| 响应缓存 | 路由层添加缓存装饰器 |

---

## License

MIT
