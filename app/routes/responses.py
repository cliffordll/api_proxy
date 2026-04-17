"""POST /v1/responses — Responses 端点"""

from __future__ import annotations

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.core.proxy import registry
from app.core.errors import handle_anthropic_error, handle_openai_error

router = APIRouter()


@router.post("/v1/responses")
async def responses(
    request: Request,
    authorization: str | None = Header(None),
):
    try:
        body = await request.json()
    except Exception:
        return _error(400, "Invalid JSON in request body", "invalid_request_error")

    api_key = _extract_bearer_key(authorization) or body.pop("api_key", None)
    if not api_key:
        return _error(401, "Missing api key", "auth_error", "invalid_api_key")

    stream = body.get("stream", False)
    proxy = registry.get("responses")

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


def _extract_bearer_key(authorization: str | None) -> str | None:
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    return None


def _error(status: int, message: str, error_type: str = "api_error", code: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": error_type, "code": code}},
    )


def _handle_exception(e: Exception) -> JSONResponse:
    import anthropic
    import openai
    if isinstance(e, anthropic.APIError):
        status, body = handle_anthropic_error(e)
        return JSONResponse(status_code=status, content={
            "error": {"message": body.get("error", {}).get("message", str(e)), "type": "api_error", "code": None}
        })
    if isinstance(e, openai.APIError):
        status, body = handle_openai_error(e)
        return JSONResponse(status_code=status, content={
            "error": {"message": body.get("error", {}).get("message", str(e)), "type": "api_error", "code": None}
        })
    if isinstance(e, (KeyError, ValueError)):
        return _error(400, f"Invalid request: {e}", "invalid_request_error")
    return _error(500, f"Internal error: {e}", "api_error")
