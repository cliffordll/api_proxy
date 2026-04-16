"""错误处理单元测试"""

import anthropic
import openai

from app.core.errors import handle_anthropic_error, handle_openai_error


class TestHandleAnthropicError:
    def test_timeout(self):
        e = anthropic.APITimeoutError(request=None)
        status, body = handle_anthropic_error(e)
        assert status == 504
        assert body["error"]["type"] == "api_error"
        assert body["error"]["code"] == "timeout"

    def test_connection_error(self):
        e = anthropic.APIConnectionError(request=None, message="conn refused")
        status, body = handle_anthropic_error(e)
        assert status == 502
        assert body["error"]["type"] == "api_error"

    def test_unknown_exception(self):
        e = Exception("something broke")
        status, body = handle_anthropic_error(e)
        assert status == 500
        assert "something broke" in body["error"]["message"]

    def test_output_is_openai_format(self):
        e = anthropic.APITimeoutError(request=None)
        _, body = handle_anthropic_error(e)
        assert "error" in body
        assert "message" in body["error"]
        assert "type" in body["error"]
        assert "code" in body["error"]


class TestHandleOpenAIError:
    def test_timeout(self):
        e = openai.APITimeoutError(request=None)
        status, body = handle_openai_error(e)
        assert status == 504
        assert body["error"]["type"] == "api_error"

    def test_connection_error(self):
        e = openai.APIConnectionError(request=None, message="conn refused")
        status, body = handle_openai_error(e)
        assert status == 502
        assert body["error"]["type"] == "api_error"

    def test_unknown_exception(self):
        e = Exception("something broke")
        status, body = handle_openai_error(e)
        assert status == 500
        assert "something broke" in body["error"]["message"]

    def test_output_is_claude_format(self):
        e = openai.APITimeoutError(request=None)
        _, body = handle_openai_error(e)
        assert body["type"] == "error"
        assert "error" in body
        assert "type" in body["error"]
        assert "message" in body["error"]
