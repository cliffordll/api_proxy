"""OpenAI API 客户端 — 基于官方 openai SDK"""

from __future__ import annotations

import json
from typing import AsyncIterator

from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, APIStatusError

from app.config import get_settings


async def send(request_body: dict, api_key: str, stream: bool = False) -> dict | AsyncIterator[str]:
    """
    使用 OpenAI 官方 SDK 发送请求。
    非流式返回 dict，流式返回 AsyncIterator[str]。
    """
    settings = get_settings()

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=f"{settings.openai_base_url}/v1",
    )

    params = dict(request_body)
    params["stream"] = stream

    print(f"[DEBUG] openai_sdk_client.send -> base_url: {settings.openai_base_url}/v1")
    print(f"[DEBUG] openai_sdk_client.send -> api_key: {api_key}")
    print(f"[DEBUG] openai_sdk_client.send -> params: {params}")

    try:
        if not stream:
            response = await client.chat.completions.create(**params)
            result = response.model_dump()
            print(f"[DEBUG] openai_sdk_client.send -> response: {json.dumps(result, ensure_ascii=False)[:500]}")
            return result

        # 流式：先拿到 stream 对象，再包装成生成器返回
        stream_response = await client.chat.completions.create(**params)
        return _wrap_stream(client, stream_response)

    except APIConnectionError as e:
        print(f"[DEBUG] openai_sdk_client.send -> APIConnectionError: {e}")
        raise
    except APITimeoutError as e:
        print(f"[DEBUG] openai_sdk_client.send -> APITimeoutError: {e}")
        raise
    except APIStatusError as e:
        print(f"[DEBUG] openai_sdk_client.send -> APIStatusError: {e.status_code} {e.message}")
        raise
    except Exception as e:
        print(f"[DEBUG] openai_sdk_client.send -> Exception: {type(e).__name__}: {e}")
        raise


async def _wrap_stream(client: AsyncOpenAI, stream_response) -> AsyncIterator[str]:
    """将 SDK 流式响应转为 SSE data 行，保持 client 引用防止提前回收"""
    try:
        async for chunk in stream_response:
            data = chunk.model_dump()
            line = f"data: {json.dumps(data, ensure_ascii=False)}"
            print(f"[DEBUG] stream chunk: {line[:200]}")
            yield line
        yield "data: [DONE]"
        print("[DEBUG] stream completed")
    except Exception as e:
        print(f"[DEBUG] stream error: {type(e).__name__}: {e}")
        raise
    finally:
        await client.close()
