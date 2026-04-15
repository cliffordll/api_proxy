"""POST /v1/chat/completions — OpenAI 兼容端点，转发到 Claude API"""

from __future__ import annotations

import json

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.registry import registry

router = APIRouter()


def _extract_bearer_key(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return None


def _openai_error(status: int, message: str, error_type: str = "api_error", code: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": error_type, "code": code}},
    )


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    authorization: str | None = Header(None),
):
    try:
        body = await request.json()
    except Exception:
        return _openai_error(400, "Invalid JSON in request body", "invalid_request_error")

    api_key = _extract_bearer_key(authorization) or body.pop("api_key", None)
    if not api_key:
        return _openai_error(401, "Missing api key: Authorization Bearer header or api_key in body", "auth_error", "invalid_api_key")

    stream = body.get("stream", False)

    provider = registry.get("claude")

    try:
        claude_req = provider.request_converter.convert_request(body)

        if not stream:
            result = await provider.client.send(claude_req, api_key=api_key, stream=False)
            openai_resp = provider.response_converter.convert_response(result)
            return JSONResponse(content=openai_resp)

        # 流式
        async def generate():
            state = {}
            async with provider.client.send(claude_req, api_key=api_key, stream=True) as stream_resp:
                async for event in stream_resp:
                    lines = provider.response_converter.convert_stream_event(event, state)
                    for line in lines:
                        yield line

        return StreamingResponse(generate(), media_type="text/event-stream")

    except (KeyError, ValueError) as e:
        return _openai_error(400, f"Invalid request: {e}", "invalid_request_error")
