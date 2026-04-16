from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.core.config import get_settings
from app.core.loader import load_providers
from app.routes.completions import router as completions_router
from app.routes.responses import router as responses_router
from app.routes.messages import router as messages_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_providers("config/settings.yaml")
    yield


app = FastAPI(
    title="API Proxy",
    description="OpenAI <-> Claude 双向协议转换代理",
    lifespan=lifespan,
)

app.include_router(completions_router)
app.include_router(responses_router)
app.include_router(messages_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    # 先加载配置，再读取服务参数
    load_providers("config/settings.yaml")
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings["host"],
        port=settings["port"],
        log_level=settings["log_level"],
    )
