from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field


# ── Content Blocks (多态设计) ──────────────────────────────

class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ToolUseContent(BaseModel):
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any]


class ToolResultContent(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str | list[TextContent]


ContentBlock = Union[TextContent, ToolUseContent, ToolResultContent]


# ── Tool 定义 ──────────────────────────────────────────────

class ToolDef(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any]


class ToolChoice(BaseModel):
    type: Literal["auto", "any", "tool", "none"]
    name: str | None = None


# ── Message ────────────────────────────────────────────────

class ClaudeMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str | list[ContentBlock]


# ── Request ────────────────────────────────────────────────

class MessagesRequest(BaseModel):
    model: str
    messages: list[ClaudeMessage]
    max_tokens: int
    system: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    stop_sequences: list[str] | None = None
    stream: bool = False
    tools: list[ToolDef] | None = None
    tool_choice: ToolChoice | None = None


# ── Response ───────────────────────────────────────────────

class ClaudeUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class MessagesResponse(BaseModel):
    id: str
    type: str = "message"
    role: str = "assistant"
    model: str
    content: list[ContentBlock]
    stop_reason: str | None = None
    usage: ClaudeUsage | None = None


# ── Stream Events ──────────────────────────────────────────

class MessageStartEvent(BaseModel):
    type: Literal["message_start"] = "message_start"
    message: dict[str, Any]


class ContentBlockStartEvent(BaseModel):
    type: Literal["content_block_start"] = "content_block_start"
    index: int
    content_block: dict[str, Any]


class ContentBlockDeltaEvent(BaseModel):
    type: Literal["content_block_delta"] = "content_block_delta"
    index: int
    delta: dict[str, Any]


class ContentBlockStopEvent(BaseModel):
    type: Literal["content_block_stop"] = "content_block_stop"
    index: int


class MessageDeltaEvent(BaseModel):
    type: Literal["message_delta"] = "message_delta"
    delta: dict[str, Any]
    usage: dict[str, int] | None = None


class MessageStopEvent(BaseModel):
    type: Literal["message_stop"] = "message_stop"


StreamEvent = Union[
    MessageStartEvent,
    ContentBlockStartEvent,
    ContentBlockDeltaEvent,
    ContentBlockStopEvent,
    MessageDeltaEvent,
    MessageStopEvent,
]
