"""POST /v1/messages — Claude 兼容端点，转发到 OpenAI API"""

from __future__ import annotations

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

import openai

from app.core.registry import registry
from app.core.errors import handle_openai_error

router = APIRouter()


def _claude_error(status: int, error_type: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": "error", "error": {"type": error_type, "message": message}},
    )


@router.post("/v1/messages")
async def messages(
    request: Request,
    x_api_key: str | None = Header(None, alias="x-api-key"),
):
    try:
        body = await request.json()
    except Exception:
        return _claude_error(400, "invalid_request_error", "Invalid JSON in request body")

    api_key = x_api_key or body.pop("api_key", None)
    if not api_key:
        return _claude_error(401, "authentication_error", "Missing api key: x-api-key header or api_key in body")

    stream = body.get("stream", False)

    provider = registry.get("openai")

    try:
        openai_req = provider.request_converter.convert_request(body)

        if not stream:
            result = await provider.client.send(openai_req, api_key=api_key, stream=False)
            claude_resp = provider.response_converter.convert_response(result)
            return JSONResponse(content=claude_resp)

        # 流式
        async def generate():
            state = {}
            stream_resp = await provider.client.send(openai_req, api_key=api_key, stream=True)
            async for chunk in stream_resp:
                lines = provider.response_converter.convert_stream_event(chunk, state)
                for line in lines:
                    yield line
            # 流结束事件
            done_lines = provider.response_converter.convert_stream_done(state)
            for line in done_lines:
                yield line

        return StreamingResponse(generate(), media_type="text/event-stream")

    except openai.APIError as e:
        status, body = handle_openai_error(e)
        return JSONResponse(status_code=status, content=body)
    except (KeyError, ValueError) as e:
        return _claude_error(400, "invalid_request_error", f"Invalid request: {e}")
