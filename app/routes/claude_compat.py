"""POST /v1/messages — Claude 兼容端点，转发到 OpenAI API"""

from __future__ import annotations

import httpx
from openai import APIConnectionError, APITimeoutError, APIStatusError
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.clients import openai_sdk_client as openai_client
from app.converters import claude_to_openai

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
    print(f"[DEBUG] /v1/messages headers: {dict(request.headers)}")
    print(f"[DEBUG] x_api_key: {x_api_key}")

    try:
        body = await request.json()
    except Exception:
        return _claude_error(400, "invalid_request_error", "Invalid JSON in request body")

    print(f"[DEBUG] /v1/messages body: {body}")

    api_key = x_api_key or body.pop("api_key", None)
    if not api_key:
        return _claude_error(401, "authentication_error", "Missing api key: x-api-key header or api_key in body")

    stream = body.get("stream", False)

    try:
        openai_req = claude_to_openai.convert_request(body)
        result = await openai_client.send(openai_req, api_key=api_key, stream=stream)
    except APIConnectionError as e:
        return _claude_error(502, "api_error", f"Failed to connect to upstream API: {e}")
    except APITimeoutError:
        return _claude_error(504, "api_error", "Upstream API request timed out")
    except APIStatusError as e:
        return _claude_error(e.status_code, "api_error", e.message)
    except (KeyError, ValueError) as e:
        return _claude_error(400, "invalid_request_error", f"Invalid request: {e}")

    if not stream:
        claude_resp = claude_to_openai.convert_response(result)
        return JSONResponse(content=claude_resp)

    async def generate():
        state = {}
        async for sse_line in result:
            lines = claude_to_openai.convert_stream_event(sse_line, state)
            for line in lines:
                yield line

    return StreamingResponse(generate(), media_type="text/event-stream")
