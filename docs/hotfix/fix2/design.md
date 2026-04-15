# Hotfix fix2：流式 state 内聚到转换器实例

## 1. 问题描述

当前流式转换的 `state` 由调用方（路由层）创建并传入：

```python
# 路由层
state = {}
async for event in stream:
    chunks = converter.convert_stream_event(event, state)
```

问题：
- 路由层需要知道 `state` 的存在和用法，职责泄漏
- `state` 是 dict，内部字段（`started`、`tool_call_index`、`content_block_index` 等）对调用方不透明
- `convert_stream_done(state)` 也需要传入 state，调用方需要在正确时机调用

## 2. 修改目标

将 `state` 内聚到转换器内部，路由层不再感知 state 的存在。不创建新实例，不暴露 `start_stream()` 方法。

## 3. 当前 vs 修改后 时序图

### 当前流程（state 外部传入）

```
客户端              路由层                    转换器(单例)              上游API
  │                  │                         │                       │
  │── 流式请求 ──────►│                         │                       │
  │                  │── state = {} ──────────►│                       │
  │                  │── convert_request() ───►│                       │
  │                  │◄── claude_req ─────────│                       │
  │                  │── send(stream=True) ──────────────────────────►│
  │                  │◄── stream ────────────────────────────────────│
  │                  │                         │                       │
  │                  │  ┌─ 循环每个 event ────┐  │                       │
  │                  │  │ convert_stream_event │  │                       │
  │                  │──┤   (event, state) ───►│  state 在多次调用间      │
  │                  │  │◄── chunks ─────────│  通过参数传递，           │
  │◄── SSE chunk ───│  │                     │  路由层需要管理 state     │
  │                  │  └────────────────────┘  │                       │
  │                  │                         │                       │
  │                  │── convert_stream_done ──►│                       │
  │                  │     (state) ◄───────────│                       │
  │◄── [DONE] ──────│                         │                       │
```

### 修改后流程（state 通过 contextvars 自动管理）

```
客户端              路由层                    转换器(单例)              上游API
  │                  │                         │                       │
  │── 流式请求 ──────►│                         │                       │
  │                  │── convert_request() ───►│                       │
  │                  │◄── claude_req ─────────│                       │
  │                  │── send(stream=True) ──────────────────────────►│
  │                  │◄── stream ────────────────────────────────────│
  │                  │                         │                       │
  │                  │  ┌─ 循环每个 event ────┐  │                       │
  │                  │  │ convert_stream_event │  │                       │
  │                  │──┤   (event) ─────────►│  首次调用自动初始化       │
  │                  │  │◄── chunks ─────────│  state 通过 ContextVar   │
  │◄── SSE chunk ───│  │                     │  自动按请求隔离           │
  │                  │  └────────────────────┘  │                       │
  │                  │                         │                       │
  │                  │── convert_stream_done()─►│ 读取当前请求的 state    │
  │◄── [DONE] ──────│◄────────────────────────│                       │
```

**改进**：
- 路由层不再创建、传递、管理 state
- 转换器保持单例，不创建新实例
- `contextvars.ContextVar` 自动按请求隔离 state，天然并发安全
- 首次调用 `convert_stream_event` 自动初始化 state，无需 `start_stream()`

## 4. 方案设计

### 4.1 核心机制：contextvars

Python 的 `contextvars.ContextVar` 在 asyncio 中天然按 Task 隔离。FastAPI 为每个请求创建独立的异步 Task，流式生成器在子 Task 中运行并继承父 Task 的上下文副本。因此：

- 请求 A 的流式事件写入的 ContextVar 值，请求 B 看不到
- 同一请求内多次调用共享同一个 ContextVar 值
- 请求结束后 ContextVar 自动释放，无需手动清理

### 4.2 BaseConverter 接口变更

```python
# 当前
class BaseConverter(ABC, Generic[TRequest, TResponse, TEvent]):
    def convert_stream_event(self, event: TEvent, state: dict) -> list: ...

# 修改后
class BaseConverter(ABC, Generic[TRequest, TResponse, TEvent]):
    def convert_stream_event(self, event: TEvent) -> list: ...
```

仅移除 `state` 参数，不新增任何方法。

### 4.3 转换器内部实现

```python
from contextvars import ContextVar

class OpenAIToClaudeConverter(BaseConverter[...]):
    _state_var: ContextVar[dict] = ContextVar('o2c_stream_state')

    @property
    def _stream_state(self) -> dict:
        """获取当前请求的流式状态，首次访问自动初始化。"""
        try:
            return self._state_var.get()
        except LookupError:
            state = {}
            self._state_var.set(state)
            return state

    def convert_stream_event(self, event) -> list[ChatCompletionChunk]:
        state = self._stream_state  # 自动获取或初始化
        # 逻辑不变
        ...
```

### 4.4 路由层调用方式变更

```python
# 当前
state = {}
async for event in stream:
    chunks = converter.convert_stream_event(event, state)
done_lines = converter.convert_stream_done(state)

# 修改后（无 state 参数）
async for event in stream:
    chunks = converter.convert_stream_event(event)
done_lines = converter.convert_stream_done()
```

### 4.5 并发安全

```
请求A (Task A)                    请求B (Task B)
    │                                 │
    │── convert_stream_event() ──►    │── convert_stream_event() ──►
    │   ContextVar → state_A          │   ContextVar → state_B
    │   (互不干扰)                     │   (互不干扰)
```

不需要创建新实例，不需要加锁，ContextVar 天然隔离。

## 5. 修改范围

| 文件 | 修改内容 |
|------|---------|
| `app/core/converter.py` | `convert_stream_event` 移除 state 参数 |
| `app/converters/openai_to_claude.py` | 新增 `ContextVar` + `_stream_state` 属性，方法内用 `self._stream_state` 替代 state 参数 |
| `app/converters/claude_to_openai.py` | 同上，`convert_stream_done()` 也移除 state 参数 |
| `app/routes/openai_compat.py` | 调用时不再传 state |
| `app/routes/claude_compat.py` | 调用时不再传 state |
| `tests/` | 适配新接口 |

## 6. 不修改的部分

- `app/core/client.py` — 客户端不涉及
- `app/core/registry.py` — ProviderEntry 结构不变，转换器保持单例
- `app/core/config.py` — 配置层不变
- `app/core/errors.py` — 错误处理不变
- 非流式的 `convert_request()` / `convert_response()` — 不涉及 state
