"""SDK 异常 → HTTP 错误格式转换工具函数"""

from __future__ import annotations

from typing import Any

import anthropic
import openai


def handle_anthropic_error(e: Exception) -> tuple[int, dict[str, Any]]:
    """
    将 anthropic SDK 异常转换为 (HTTP 状态码, OpenAI 错误格式 body)。
    用于 /v1/chat/completions 端点。
    """
    status, message, error_type, code = _classify_anthropic_error(e)
    body = {
        "error": {
            "message": message,
            "type": error_type,
            "code": code,
        }
    }
    return status, body


def handle_openai_error(e: Exception) -> tuple[int, dict[str, Any]]:
    """
    将 openai SDK 异常转换为 (HTTP 状态码, Claude 错误格式 body)。
    用于 /v1/messages 端点。
    """
    status, message, error_type = _classify_openai_error(e)
    body = {
        "type": "error",
        "error": {
            "type": error_type,
            "message": message,
        }
    }
    return status, body


def _classify_anthropic_error(e: Exception) -> tuple[int, str, str, str | None]:
    """返回 (status_code, message, error_type, code)"""
    if isinstance(e, anthropic.AuthenticationError):
        return 401, str(e), "auth_error", "invalid_api_key"
    if isinstance(e, anthropic.RateLimitError):
        return 429, str(e), "rate_limit_error", "rate_limit_exceeded"
    if isinstance(e, anthropic.BadRequestError):
        return 400, str(e), "invalid_request_error", "bad_request"
    if isinstance(e, anthropic.APITimeoutError):
        return 504, "Upstream API request timed out", "api_error", "timeout"
    if isinstance(e, anthropic.APIConnectionError):
        return 502, f"Failed to connect to upstream API: {e}", "api_error", "connection_error"
    if isinstance(e, anthropic.InternalServerError):
        return 502, f"Upstream server error: {e}", "api_error", "server_error"
    if isinstance(e, anthropic.APIStatusError):
        return e.status_code, str(e), "api_error", None
    # 未知异常
    return 500, f"Internal error: {e}", "api_error", None


def _classify_openai_error(e: Exception) -> tuple[int, str, str]:
    """返回 (status_code, message, error_type)"""
    if isinstance(e, openai.AuthenticationError):
        return 401, str(e), "authentication_error"
    if isinstance(e, openai.RateLimitError):
        return 429, str(e), "rate_limit_error"
    if isinstance(e, openai.BadRequestError):
        return 400, str(e), "invalid_request_error"
    if isinstance(e, openai.APITimeoutError):
        return 504, "Upstream API request timed out", "api_error"
    if isinstance(e, openai.APIConnectionError):
        return 502, f"Failed to connect to upstream API: {e}", "api_error"
    if isinstance(e, openai.InternalServerError):
        return 502, f"Upstream server error: {e}", "api_error"
    if isinstance(e, openai.APIStatusError):
        return e.status_code, str(e), "api_error"
    # 未知异常
    return 500, f"Internal error: {e}", "api_error"
