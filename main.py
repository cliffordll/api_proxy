import uvicorn
from fastapi import FastAPI

from app.core.config import get_settings
from app.core.registry import registry, ProviderEntry
from app.clients.claude_client import ClaudeClient
from app.clients.openai_client import OpenAIClient
from app.converters.openai_to_claude import OpenAIToClaudeConverter
from app.converters.claude_to_openai import ClaudeToOpenAIConverter
from app.routes.openai_compat import router as openai_router
from app.routes.claude_compat import router as claude_router

app = FastAPI(title="API Proxy", description="OpenAI <-> Claude 双向协议转换代理")


@app.on_event("startup")
async def startup():
    """应用启动时注册 Provider。"""
    settings = get_settings()

    # 注册 Claude Provider（供 /v1/chat/completions 使用）
    registry.register("claude", ProviderEntry(
        client=ClaudeClient(base_url=settings.anthropic_base_url),
        request_converter=OpenAIToClaudeConverter(),
        response_converter=OpenAIToClaudeConverter(),
    ))

    # 注册 OpenAI Provider（供 /v1/messages 使用）
    registry.register("openai", ProviderEntry(
        client=OpenAIClient(base_url=f"{settings.openai_base_url}/v1"),
        request_converter=ClaudeToOpenAIConverter(),
        response_converter=ClaudeToOpenAIConverter(),
    ))


app.include_router(openai_router)
app.include_router(claude_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )
