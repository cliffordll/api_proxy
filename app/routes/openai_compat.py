"""POST /v1/chat/completions — OpenAI 兼容端点，转发到 Claude API"""

from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.clients import claude_client
from app.converters import openai_to_claude

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

    try:
        claude_req = openai_to_claude.convert_request(body)
        result = await claude_client.send(claude_req, api_key=api_key, stream=stream)
    except httpx.ConnectError:
        return _openai_error(502, "Failed to connect to upstream API", "api_error")
    except httpx.TimeoutException:
        return _openai_error(504, "Upstream API request timed out", "api_error")
    except httpx.HTTPStatusError as e:
        try:
            upstream_error = e.response.json()
            msg = upstream_error.get("error", {}).get("message", str(e))
        except Exception:
            msg = str(e)
        return _openai_error(e.response.status_code, msg, "api_error")
    except (KeyError, ValueError) as e:
        return _openai_error(400, f"Invalid request: {e}", "invalid_request_error")

    if not stream:
        openai_resp = openai_to_claude.convert_response(result)
        return JSONResponse(content=openai_resp)

    async def generate():
        state = {}
        async for data_str in result:
            try:
                event = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            lines = openai_to_claude.convert_stream_event(event, state)
            for line in lines:
                yield line

    return StreamingResponse(generate(), media_type="text/event-stream")
