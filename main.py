import uvicorn
from fastapi import FastAPI

from app.config import get_settings
from app.routes.openai_compat import router as openai_router
from app.routes.claude_compat import router as claude_router

app = FastAPI(title="API Proxy", description="OpenAI <-> Claude 双向协议转换代理")

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
