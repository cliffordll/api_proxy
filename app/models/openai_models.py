from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Tool 相关 ──────────────────────────────────────────────

class FunctionDef(BaseModel):
    name: str
    description: str | None = None
    parameters: dict[str, Any] | None = None


class Tool(BaseModel):
    type: Literal["function"] = "function"
    function: FunctionDef


class FunctionCall(BaseModel):
    name: str
    arguments: str  # JSON 字符串


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: FunctionCall
    index: int | None = None


class ToolChoiceFunction(BaseModel):
    type: Literal["function"] = "function"
    function: dict[str, str]  # {"name": "..."}


# ── Message ────────────────────────────────────────────────

class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]] | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


# ── Request ────────────────────────────────────────────────

class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[Message]
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    stop: str | list[str] | None = None
    stream: bool = False
    tools: list[Tool] | None = None
    tool_choice: str | ToolChoiceFunction | None = None


# ── Response ───────────────────────────────────────────────

class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class Choice(BaseModel):
    index: int = 0
    message: Message
    finish_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int = 0
    model: str
    choices: list[Choice]
    usage: Usage | None = None


# ── Streaming Chunk ────────────────────────────────────────

class DeltaToolCall(BaseModel):
    index: int
    id: str | None = None
    type: Literal["function"] | None = None
    function: dict[str, str] | None = None  # {"name":...} 或 {"arguments":...}


class Delta(BaseModel):
    role: str | None = None
    content: str | None = None
    tool_calls: list[DeltaToolCall] | None = None


class ChunkChoice(BaseModel):
    index: int = 0
    delta: Delta
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int = 0
    model: str
    choices: list[ChunkChoice]
    usage: Usage | None = None
