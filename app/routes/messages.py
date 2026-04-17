"""POST /v1/messages — Messages 端点"""

from __future__ import annotations

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.core.proxy import registry
from app.core.errors import handle_anthropic_error, handle_openai_error

router = APIRouter()


@router.post("/v1/messages")
async def messages(
    request: Request,
    x_api_key: str | None = Header(None, alias="x-api-key"),
):
    try:
        body = await request.json()
    except Exception:
        return _error(400, "invalid_request_error", "Invalid JSON in request body")

    api_key = x_api_key or body.pop("api_key", None)
    if not api_key:
        return _error(401, "authentication_error", "Missing api key")

    stream = body.get("stream", False)
    proxy = registry.get("messages")

    try:
        if not stream:
            result = await proxy.chat(body, api_key, stream=False)
            return Response(content=result, media_type="application/json")

        # 流式：先预取首帧触发上游 HTTP 调用，提前暴露错误便于正确返回状态码
        stream_iter = await proxy.chat(body, api_key, stream=True)
        try:
            first = await stream_iter.__anext__()
        except StopAsyncIteration:
            first = None

        async def generate():
            if first is not None:
                yield first
            async for item in stream_iter:
                yield item

        return StreamingResponse(generate(), media_type="text/event-stream")

    except Exception as e:
        return _handle_exception(e)


def _error(status: int, error_type: str, message: str) -> JSONResponse:
    """Claude 错误格式"""
    return JSONResponse(
        status_code=status,
        content={"type": "error", "error": {"type": error_type, "message": message}},
    )


def _handle_exception(e: Exception) -> JSONResponse:
    import anthropic
    import openai
    if isinstance(e, anthropic.APIError):
        status, body = handle_anthropic_error(e)
        return JSONResponse(status_code=status, content=body)
    if isinstance(e, openai.APIError):
        status, body = handle_openai_error(e)
        return JSONResponse(status_code=status, content=body)
    if isinstance(e, (KeyError, ValueError)):
        return _error(400, "invalid_request_error", f"Invalid request: {e}")
    return _error(500, "api_error", f"Internal error: {e}")
